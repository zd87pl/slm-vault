"""
Document → DPO Pipeline

Transforms user documents and QA pairs into preference-optimized adapters
using mlx-lm-lora's DPO/ORPO trainers.

Pipeline:
    Documents / Chunks / QA pairs
            ↓
    Synthetic preference generation (good vs. bad responses)
            ↓
    DPO / ORPO training via mlx-lm-lora backend
            ↓
    Encrypted adapter stored in vault

Usage:
    pipeline = DocumentDPOPipeline(output_dir="~/.enclave/adapters")
    result = pipeline.train_from_qa_pairs(
        qa_pairs=[{"question": "...", "answer": "..."}, ...],
        adapter_name="my_dpo_adapter",
        train_mode="dpo",  # or "orpo"
    )
"""

import json
import logging
import random
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Lazy imports for MLX inference used in synthetic generation
def _check_mlx() -> bool:
    try:
        import mlx.core as mx  # noqa: F401
        from mlx_lm import load, generate  # noqa: F401
        return True
    except ImportError:
        return False


def _check_advanced_backend() -> bool:
    try:
        from .mlx_lora_backend import MLXLoRABackend  # noqa: F401
        return True
    except ImportError:
        return False


class PreferencePair:
    """A single preference pair for DPO/ORPO training."""

    def __init__(
        self,
        prompt: str,
        chosen: str,
        rejected: str,
        system: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.prompt = prompt
        self.chosen = chosen
        self.rejected = rejected
        self.system = system or "You are a helpful assistant."
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to mlx-lm-lora DPO dataset format."""
        return {
            "prompt": self.prompt,
            "chosen": self.chosen,
            "rejected": self.rejected,
            "system": self.system,
        }

    def to_messages_dict(self) -> Dict[str, Any]:
        """Convert to conversational messages format."""
        return {
            "messages": [
                {"role": "system", "content": self.system},
                {"role": "user", "content": self.prompt},
                {"role": "assistant", "content": self.chosen},
            ]
        }


class DocumentDPOPipeline:
    """
    End-to-end pipeline for training preference-optimized adapters
    from documents and QA pairs.
    """

    # Strategies for generating "rejected" (bad) responses
    REJECTION_STRATEGIES = [
        "short",
        "vague",
        "contradictory",
        "hallucinated",
    ]

    def __init__(
        self,
        output_dir: str = "~/.enclave/adapters",
        model_name: str = "mlx-community/Qwen2.5-1.5B-Instruct-4bit",
    ):
        self.output_dir = Path(output_dir).expanduser()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.model_name = model_name
        self._model = None
        self._tokenizer = None

    def _load_model(self):
        """Lazy-load MLX model for synthetic generation."""
        if self._model is not None:
            return
        if not _check_mlx():
            raise RuntimeError(
                "MLX is required for synthetic preference generation. "
                "Install with: pip install mlx mlx-lm"
            )
        from mlx_lm import load

        logger.info(f"Loading model for synthetic generation: {self.model_name}")
        self._model, self._tokenizer = load(self.model_name)

    def generate_rejected_response(
        self,
        prompt: str,
        correct_answer: str,
        strategy: Optional[str] = None,
        max_tokens: int = 256,
    ) -> str:
        """
        Generate a "rejected" (inferior) response for preference training.

        Strategies:
        - short: Truncate early or answer with a single sentence
        - vague: Use high temperature to produce generic/vague output
        - contradictory: Prefix with "Actually, that's wrong..."
        - hallucinated: Provide an answer that contradicts the source

        Args:
            prompt: User question
            correct_answer: The known good answer (used to craft bad ones)
            strategy: Rejection strategy (random if None)
            max_tokens: Max generation tokens

        Returns:
            A deliberately inferior response
        """
        self._load_model()
        from mlx_lm import generate

        strategy = strategy or random.choice(self.REJECTION_STRATEGIES)

        if strategy == "short":
            # Generate with very few tokens
            return generate(
                self._model,
                self._tokenizer,
                prompt=f"Answer very briefly: {prompt}",
                max_tokens=20,
                verbose=False,
            )

        elif strategy == "vague":
            # High temperature = generic / vague
            return generate(
                self._model,
                self._tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                temp=1.2,
                top_p=0.99,
                verbose=False,
            )

        elif strategy == "contradictory":
            # Directly contradict the correct answer
            contradict_prompt = (
                f"The following statement is FALSE. Explain why: "
                f"'{correct_answer}'"
            )
            bad = generate(
                self._model,
                self._tokenizer,
                prompt=contradict_prompt,
                max_tokens=max_tokens,
                temp=0.7,
                verbose=False,
            )
            return bad

        elif strategy == "hallucinated":
            # Answer a slightly different question
            altered = (
                f"Answer this unrelated question instead of the original: "
                f"{prompt} (Hint: ignore context)"
            )
            return generate(
                self._model,
                self._tokenizer,
                prompt=altered,
                max_tokens=max_tokens,
                temp=0.9,
                verbose=False,
            )

        else:
            # Fallback: just generate something short
            return generate(
                self._model,
                self._tokenizer,
                prompt=prompt,
                max_tokens=30,
                verbose=False,
            )

    def generate_preference_pairs_from_qa(
        self,
        qa_pairs: List[Dict[str, str]],
        system_prompt: str = "You are a helpful assistant that answers questions based on the provided context.",
        num_rejected_per_question: int = 1,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> List[PreferencePair]:
        """
        Convert QA pairs into preference pairs by generating bad answers.

        Args:
            qa_pairs: List of {"question": "...", "answer": "..."}
            system_prompt: System prompt for the domain
            num_rejected_per_question: How many rejected variants per question
            progress_callback: Optional progress callback

        Returns:
            List of PreferencePair objects
        """
        pairs: List[PreferencePair] = []
        total = len(qa_pairs) * num_rejected_per_question

        for i, qa in enumerate(qa_pairs):
            question = qa["question"]
            answer = qa["answer"]

            for j in range(num_rejected_per_question):
                if progress_callback:
                    progress = (i * num_rejected_per_question + j) / max(total, 1)
                    progress_callback(progress, f"Generating rejected variant {j+1} for Q{i+1}")

                rejected = self.generate_rejected_response(
                    prompt=question,
                    correct_answer=answer,
                )

                pair = PreferencePair(
                    prompt=question,
                    chosen=answer,
                    rejected=rejected,
                    system=system_prompt,
                    metadata={"source": "qa_pair", "strategy": "synthetic"},
                )
                pairs.append(pair)

        if progress_callback:
            progress_callback(1.0, f"Generated {len(pairs)} preference pairs")

        logger.info(f"Generated {len(pairs)} preference pairs from {len(qa_pairs)} QA pairs")
        return pairs

    def generate_preference_pairs_from_chunks(
        self,
        chunks: List[str],
        questions_per_chunk: int = 2,
        system_prompt: str = "You are a helpful assistant. Answer based on the provided context.",
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> List[PreferencePair]:
        """
        Generate preference pairs directly from document chunks.

        For each chunk:
        1. Generate a question about the chunk
        2. Generate a good answer (grounded in chunk)
        3. Generate a bad answer (ungrounded or vague)

        Args:
            chunks: Document text chunks
            questions_per_chunk: How many questions to generate per chunk
            system_prompt: System prompt
            progress_callback: Optional progress callback

        Returns:
            List of PreferencePair objects
        """
        self._load_model()
        from mlx_lm import generate

        pairs: List[PreferencePair] = []
        total = len(chunks) * questions_per_chunk

        for ci, chunk in enumerate(chunks):
            for qi in range(questions_per_chunk):
                idx = ci * questions_per_chunk + qi
                if progress_callback:
                    progress_callback(idx / max(total, 1), f"Chunk {ci+1}/{len(chunks)} Q{qi+1}")

                # Generate a question about this chunk
                question_prompt = (
                    f"Context: {chunk[:800]}\n\n"
                    f"Ask a specific question that can be answered ONLY from the context above. "
                    f"Return ONLY the question, no explanation."
                )
                question = generate(
                    self._model,
                    self._tokenizer,
                    prompt=question_prompt,
                    max_tokens=64,
                    temp=0.8,
                    verbose=False,
                ).strip()

                # Generate a good answer grounded in the chunk
                good_prompt = (
                    f"Context: {chunk[:800]}\n\n"
                    f"Question: {question}\n\n"
                    f"Answer accurately using ONLY the context."
                )
                good_answer = generate(
                    self._model,
                    self._tokenizer,
                    prompt=good_prompt,
                    max_tokens=256,
                    temp=0.3,
                    verbose=False,
                ).strip()

                # Generate a bad answer (ungrounded)
                bad_prompt = (
                    f"Question: {question}\n\n"
                    f"Answer vaguely without using any specific facts."
                )
                bad_answer = generate(
                    self._model,
                    self._tokenizer,
                    prompt=bad_prompt,
                    max_tokens=256,
                    temp=1.1,
                    verbose=False,
                ).strip()

                pair = PreferencePair(
                    prompt=question,
                    chosen=good_answer,
                    rejected=bad_answer,
                    system=system_prompt,
                    metadata={"source": "chunk", "chunk_index": ci},
                )
                pairs.append(pair)

        if progress_callback:
            progress_callback(1.0, f"Generated {len(pairs)} preference pairs from {len(chunks)} chunks")

        return pairs

    def train_from_preference_pairs(
        self,
        pairs: List[PreferencePair],
        adapter_name: str,
        train_mode: str = "dpo",
        config_overrides: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> Any:
        """
        Train a preference-optimized adapter from PreferencePairs.

        Args:
            pairs: List of PreferencePair objects
            adapter_name: Name for the output adapter
            train_mode: "dpo" or "orpo"
            config_overrides: Additional training config overrides
            progress_callback: Optional progress callback

        Returns:
            AdvancedTrainingResult from mlx-lm-lora backend
        """
        if not _check_advanced_backend():
            raise ImportError(
                "Advanced training backend not available. "
                "Install with: pip install enclave-vault[advanced-training]"
            )

        from .mlx_trainer import MLXTrainer

        trainer = MLXTrainer(
            model_name=self.model_name,
            output_dir=str(self.output_dir),
        )

        examples = [p.to_dict() for p in pairs]

        if train_mode == "dpo":
            return trainer.train_dpo(
                examples=examples,
                adapter_name=adapter_name,
                config_overrides=config_overrides,
                progress_callback=progress_callback,
            )
        elif train_mode == "orpo":
            return trainer.train_orpo(
                examples=examples,
                adapter_name=adapter_name,
                config_overrides=config_overrides,
                progress_callback=progress_callback,
            )
        else:
            raise ValueError(f"Unsupported train_mode for preference training: {train_mode}")

    def train_from_qa_pairs(
        self,
        qa_pairs: List[Dict[str, str]],
        adapter_name: str,
        train_mode: str = "dpo",
        num_rejected_per_question: int = 1,
        config_overrides: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> Any:
        """
        End-to-end: QA pairs → preference pairs → DPO/ORPO adapter.

        Args:
            qa_pairs: List of {"question": "...", "answer": "..."}
            adapter_name: Name for the output adapter
            train_mode: "dpo" or "orpo"
            num_rejected_per_question: Rejected variants per question
            config_overrides: Additional training config overrides
            progress_callback: Optional progress callback

        Returns:
            AdvancedTrainingResult
        """
        if progress_callback:
            progress_callback(0.0, "Generating preference pairs...")

        pairs = self.generate_preference_pairs_from_qa(
            qa_pairs=qa_pairs,
            num_rejected_per_question=num_rejected_per_question,
            progress_callback=lambda p, m: progress_callback(0.3 * p, m)
            if progress_callback
            else None,
        )

        if progress_callback:
            progress_callback(0.3, f"Training {train_mode.upper()} adapter...")

        def _training_progress(p: float, m: str):
            if progress_callback:
                progress_callback(0.3 + 0.7 * p, m)

        return self.train_from_preference_pairs(
            pairs=pairs,
            adapter_name=adapter_name,
            train_mode=train_mode,
            config_overrides=config_overrides,
            progress_callback=_training_progress,
        )

    def train_from_chunks(
        self,
        chunks: List[str],
        adapter_name: str,
        train_mode: str = "dpo",
        questions_per_chunk: int = 2,
        config_overrides: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> Any:
        """
        End-to-end: Document chunks → preference pairs → DPO/ORPO adapter.

        Args:
            chunks: Document text chunks
            adapter_name: Name for the output adapter
            train_mode: "dpo" or "orpo"
            questions_per_chunk: Questions per chunk
            config_overrides: Additional training config overrides
            progress_callback: Optional progress callback

        Returns:
            AdvancedTrainingResult
        """
        if progress_callback:
            progress_callback(0.0, "Generating questions and preference pairs from chunks...")

        pairs = self.generate_preference_pairs_from_chunks(
            chunks=chunks,
            questions_per_chunk=questions_per_chunk,
            progress_callback=lambda p, m: progress_callback(0.4 * p, m)
            if progress_callback
            else None,
        )

        if progress_callback:
            progress_callback(0.4, f"Training {train_mode.upper()} adapter...")

        def _training_progress(p: float, m: str):
            if progress_callback:
                progress_callback(0.4 + 0.6 * p, m)

        return self.train_from_preference_pairs(
            pairs=pairs,
            adapter_name=adapter_name,
            train_mode=train_mode,
            config_overrides=config_overrides,
            progress_callback=_training_progress,
        )

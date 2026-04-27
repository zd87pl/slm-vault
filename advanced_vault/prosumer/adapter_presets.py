"""
Domain-Specific Adapter Presets for Prosumer Use Cases

Pre-configured training presets optimized for personal data vaults.
Each preset includes:
- Recommended base model and quantization
- Training hyperparameters (lr, epochs, LoRA rank)
- Reward function configuration for GRPO/DPO
- System prompt template for the domain
- Safety guardrails
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum


class TrainingMethod(Enum):
    """Supported training methods."""
    SFT = "sft"           # Supervised Fine-Tuning
    DPO = "dpo"           # Direct Preference Optimization
    ORPO = "orpo"         # Odds Ratio Preference Optimization
    GRPO = "grpo"         # Group Relative Policy Optimization


@dataclass
class AdapterPreset:
    """Configuration preset for training a domain-specific adapter."""
    
    id: str
    name: str
    description: str
    category_id: str  # Links to vault category
    icon: str
    
    # Model configuration
    base_model: str = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"
    quantization: str = "4bit"  # 4bit, 8bit, none
    
    # Training configuration
    training_method: TrainingMethod = TrainingMethod.DPO
    lora_rank: int = 16
    lora_alpha: int = 32
    learning_rate: float = 1e-4
    num_epochs: int = 3
    batch_size: int = 1
    gradient_accumulation_steps: int = 4
    max_seq_length: int = 2048
    warmup_steps: int = 100
    
    # Reward functions (for GRPO)
    reward_functions: List[str] = field(default_factory=list)
    reward_weights: Dict[str, float] = field(default_factory=dict)
    
    # System prompt template
    system_prompt: str = "You are a helpful assistant."
    
    # Safety configuration
    safety_checks: List[str] = field(default_factory=list)
    forbidden_topics: List[str] = field(default_factory=list)
    require_disclaimer: bool = False
    disclaimer_text: str = ""
    
    # UI configuration
    estimated_training_time_minutes: int = 15
    min_documents: int = 5
    recommended_documents: int = 20
    
    # Metadata
    tags: List[str] = field(default_factory=list)
    version: str = "1.0"
    
    def to_training_config(self) -> Dict[str, Any]:
        """Convert preset to training configuration dict."""
        return {
            "base_model": self.base_model,
            "quantization": self.quantization,
            "training_method": self.training_method.value,
            "lora_config": {
                "rank": self.lora_rank,
                "alpha": self.lora_alpha,
                "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
            },
            "training": {
                "learning_rate": self.learning_rate,
                "num_epochs": self.num_epochs,
                "batch_size": self.batch_size,
                "gradient_accumulation_steps": self.gradient_accumulation_steps,
                "max_seq_length": self.max_seq_length,
                "warmup_steps": self.warmup_steps,
            },
            "reward_functions": self.reward_functions,
            "reward_weights": self.reward_weights,
            "system_prompt": self.system_prompt,
            "safety": {
                "checks": self.safety_checks,
                "forbidden_topics": self.forbidden_topics,
                "require_disclaimer": self.require_disclaimer,
                "disclaimer_text": self.disclaimer_text,
            },
        }
    
    def estimate_time(self, num_documents: int) -> int:
        """Estimate training time in minutes based on document count."""
        base_time = self.estimated_training_time_minutes
        doc_factor = min(num_documents / self.recommended_documents, 2.0)
        return int(base_time * doc_factor)


# Preset definitions

HEALTH_ADVISOR = AdapterPreset(
    id="health_advisor",
    name="Health Advisor",
    description="An AI that understands your medical history, medications, and health patterns",
    category_id="health",
    icon="🏥",
    base_model="mlx-community/Qwen2.5-1.5B-Instruct-4bit",
    quantization="4bit",
    training_method=TrainingMethod.DPO,
    lora_rank=16,
    lora_alpha=32,
    learning_rate=5e-5,
    num_epochs=3,
    batch_size=1,
    gradient_accumulation_steps=4,
    max_seq_length=2048,
    reward_functions=["citation", "groundedness", "answer_completeness"],
    reward_weights={"citation": 0.4, "groundedness": 0.4, "answer_completeness": 0.2},
    system_prompt="""You are a personal Health Advisor with deep knowledge of the user's medical history. 

Your capabilities:
- Answer questions about medications, diagnoses, and treatments
- Identify potential drug interactions based on the user's prescription list
- Summarize lab results and explain what they mean
- Track symptoms and health patterns over time
- Remind about appointments, medications, and preventive care

CRITICAL SAFETY RULES:
- NEVER provide medical advice that replaces a doctor
- ALWAYS recommend consulting healthcare providers for serious concerns
- NEVER suggest starting, stopping, or changing medications
- Clearly distinguish between information from records and general knowledge
- Flag urgent symptoms that require immediate medical attention

Always include this disclaimer: "This information is based on your personal health records and general medical knowledge. Always consult your healthcare provider for medical decisions." """,
    safety_checks=["medical_disclaimer", "no_prescription_advice", "urgent_symptom_flag"],
    forbidden_topics=["prescribing medication", "diagnosing conditions", "treatment plans"],
    require_disclaimer=True,
    disclaimer_text="This information is based on your personal health records and general medical knowledge. Always consult your healthcare provider for medical decisions.",
    estimated_training_time_minutes=10,
    min_documents=3,
    recommended_documents=10,
    tags=["health", "medical", "privacy", "safety-critical"],
)

TAX_ASSISTANT = AdapterPreset(
    id="tax_assistant",
    name="Tax Assistant",
    description="An AI that knows your financial situation and helps with tax optimization",
    category_id="finance",
    icon="💰",
    base_model="mlx-community/Qwen2.5-1.5B-Instruct-4bit",
    quantization="4bit",
    training_method=TrainingMethod.DPO,
    lora_rank=16,
    lora_alpha=32,
    learning_rate=1e-4,
    num_epochs=3,
    batch_size=1,
    gradient_accumulation_steps=4,
    max_seq_length=2048,
    reward_functions=["citation", "calculation_accuracy", "format_compliance"],
    reward_weights={"citation": 0.3, "calculation_accuracy": 0.5, "format_compliance": 0.2},
    system_prompt="""You are a personal Tax Assistant with detailed knowledge of the user's financial documents.

Your capabilities:
- Analyze income, deductions, and credits from tax documents
- Identify potential deductions the user may have missed
- Explain tax forms and what each field means
- Track estimated tax payments and deadlines
- Summarize investment gains/losses and tax implications
- Compare year-over-year financial changes

CRITICAL RULES:
- NEVER provide definitive tax advice - always suggest consulting a CPA
- Show your work for any calculations
- Cite specific documents when making claims
- Clearly distinguish between information from records and general tax knowledge
- Flag deadlines and important dates prominently

Disclaimer: "This analysis is based on your financial documents and general tax principles. Consult a qualified tax professional before filing." """,
    safety_checks=["calculation_verification", "tax_disclaimer", "deadline_highlighting"],
    forbidden_topics=["definitive tax advice", "filing on behalf of user", "guaranteed refunds"],
    require_disclaimer=True,
    disclaimer_text="This analysis is based on your financial documents and general tax principles. Consult a qualified tax professional before filing.",
    estimated_training_time_minutes=15,
    min_documents=5,
    recommended_documents=15,
    tags=["finance", "tax", "accounting", "privacy"],
)

LEGAL_COMPANION = AdapterPreset(
    id="legal_companion",
    name="Legal Companion",
    description="An AI that understands your contracts, obligations, and legal situation",
    category_id="legal",
    icon="⚖️",
    base_model="mlx-community/Qwen2.5-1.5B-Instruct-4bit",
    quantization="4bit",
    training_method=TrainingMethod.DPO,
    lora_rank=16,
    lora_alpha=32,
    learning_rate=5e-5,
    num_epochs=4,
    batch_size=1,
    gradient_accumulation_steps=4,
    max_seq_length=4096,  # Legal docs are often longer
    reward_functions=["citation", "groundedness", "caution_flag"],
    reward_weights={"citation": 0.4, "groundedness": 0.4, "caution_flag": 0.2},
    system_prompt="""You are a personal Legal Companion with access to the user's contracts, agreements, and legal documents.

Your capabilities:
- Summarize contracts and highlight key obligations
- Extract deadlines, renewal dates, and important clauses
- Compare terms across multiple agreements
- Track immigration status and required next steps
- Explain legal documents in plain language
- Identify potential risks or unfavorable terms

CRITICAL SAFETY RULES:
- NEVER provide legal advice - always recommend consulting an attorney
- Clearly distinguish between document content and general legal information
- Flag when a question requires professional legal counsel
- NEVER encourage violating contracts or laws
- Be conservative in interpretation - when in doubt, say so

Disclaimer: "This summary is based on your documents and general legal information. Always consult a qualified attorney for legal advice." """,
    safety_checks=["legal_disclaimer", "no_legal_advice", "risk_flagging", "conservative_interpretation"],
    forbidden_topics=["legal advice", "encouraging breach of contract", "immigration guarantees"],
    require_disclaimer=True,
    disclaimer_text="This summary is based on your documents and general legal information. Always consult a qualified attorney for legal advice.",
    estimated_training_time_minutes=12,
    min_documents=3,
    recommended_documents=8,
    tags=["legal", "contracts", "immigration", "privacy", "safety-critical"],
)

LIFE_ARCHIVIST = AdapterPreset(
    id="life_archivist",
    name="Life Archivist",
    description="An AI with deep personal context - your journals, emails, notes, and memories",
    category_id="personal",
    icon="🧠",
    base_model="mlx-community/Qwen2.5-1.5B-Instruct-4bit",
    quantization="4bit",
    training_method=TrainingMethod.DPO,
    lora_rank=16,
    lora_alpha=32,
    learning_rate=1e-4,
    num_epochs=3,
    batch_size=1,
    gradient_accumulation_steps=4,
    max_seq_length=2048,
    reward_functions=["completeness", "empathy", "conciseness"],
    reward_weights={"completeness": 0.4, "empathy": 0.3, "conciseness": 0.3},
    system_prompt="""You are a personal Life Archivist with deep knowledge of the user's life, thoughts, experiences, and preferences.

Your capabilities:
- Recall specific events, conversations, and experiences from journals and notes
- Summarize themes and patterns across personal documents
- Help the user reflect on goals, decisions, and personal growth
- Find specific information from emails, notes, and records
- Connect ideas across different time periods and contexts
- Maintain the user's voice and perspective when summarizing

PERSONALITY:
- Warm, supportive, and non-judgmental
- Respectful of the user's privacy and sensitive topics
- Helpful without being intrusive
- Good at connecting dots across scattered information
- Able to shift between analytical and emotional modes as needed

Remember: You are a mirror and assistant for the user's own thoughts, not an independent authority.""",
    safety_checks=["privacy_respect", "non_judgmental_tone", "user_agency"],
    forbidden_topics=[],
    require_disclaimer=False,
    estimated_training_time_minutes=20,
    min_documents=10,
    recommended_documents=50,
    tags=["personal", "journal", "memory", "knowledge-management"],
)

GENERAL_ASSISTANT = AdapterPreset(
    id="general",
    name="General Assistant",
    description="A versatile AI trained on all your documents across categories",
    category_id="personal",
    icon="🤖",
    base_model="mlx-community/Qwen2.5-1.5B-Instruct-4bit",
    quantization="4bit",
    training_method=TrainingMethod.SFT,
    lora_rank=8,
    lora_alpha=16,
    learning_rate=1e-4,
    num_epochs=2,
    batch_size=1,
    gradient_accumulation_steps=4,
    max_seq_length=2048,
    reward_functions=[],
    reward_weights={},
    system_prompt="You are a helpful assistant with access to the user's personal documents. Answer questions based on the provided context when available, and use your general knowledge when appropriate.",
    safety_checks=["citation_check"],
    forbidden_topics=[],
    require_disclaimer=False,
    estimated_training_time_minutes=10,
    min_documents=5,
    recommended_documents=20,
    tags=["general", "all-purpose", "beginner-friendly"],
)

# Registry
PROSUMER_PRESETS: Dict[str, AdapterPreset] = {
    "health_advisor": HEALTH_ADVISOR,
    "tax_assistant": TAX_ASSISTANT,
    "legal_companion": LEGAL_COMPANION,
    "life_archivist": LIFE_ARCHIVIST,
    "general": GENERAL_ASSISTANT,
}


def get_preset_for_category(category_id: str) -> AdapterPreset:
    """Get the recommended preset for a vault category."""
    mapping = {
        "health": HEALTH_ADVISOR,
        "finance": TAX_ASSISTANT,
        "legal": LEGAL_COMPANION,
        "personal": LIFE_ARCHIVIST,
    }
    return mapping.get(category_id, GENERAL_ASSISTANT)


def get_preset(preset_id: str) -> Optional[AdapterPreset]:
    """Get a preset by ID."""
    return PROSUMER_PRESETS.get(preset_id)


def list_presets() -> List[AdapterPreset]:
    """List all available presets."""
    return list(PROSUMER_PRESETS.values())


def list_presets_for_category(category_id: str) -> List[AdapterPreset]:
    """List presets applicable to a category."""
    presets = []
    for preset in PROSUMER_PRESETS.values():
        if preset.category_id == category_id:
            presets.append(preset)
    return presets

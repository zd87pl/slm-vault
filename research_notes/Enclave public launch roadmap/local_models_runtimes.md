# Local / On-Device LLM Stack for Consumer Laptops & Phones (state as of late September 2026)

Context for the report writer: the product today (verified by grepping this repo on 2026-09-29) defaults to `mlx-community/Qwen2.5-1.5B-Instruct-4bit` (e.g. `DEFAULT_MODEL` / `DEFAULT_PRIVATE_MODEL_NAME`), `intfloat/e5-small-v2` and `BAAI/bge-small-en-v1.5` for embeddings, an optional Ollama path (`llama3.2-vision:11b`, `tinyllama`), and MLX LoRA/DoRA training code under `advanced_vault/training/`. Every model named there came out in 2024 or earlier. Research method: web search (the session hit its 200-search limit partway through) plus direct fetches of primary pages (model cards, vendor blogs, GitHub release pages, Microsoft/Apple/Chrome docs). Where only secondary sources were available, the notes say so. Dates are 2026 unless marked otherwise.

---

## 1. Best small/medium open-weight LLMs for local use (and which are best at grounded, cited answers)

### Takeaway
By September 2026 the default sub-10B local model is **Qwen3.5 (0.8B/2B/4B/9B, Apache 2.0, ~Mar 2026, natively multimodal, 262K context)**. **Gemma 4 (E2B/E4B/12B/26B-A4B/31B, Apache 2.0, Apr 2 2026)** and **IBM Granite 4.1 (3B/8B/30B, Apache 2.0, Apr 29 2026)** are the strongest alternatives. At 24–32 GB, the frontier is 27–35B models: Qwen3.6-27B / 35B-A3B, Qwen3.8-27B, Gemma 4 26B-A4B/31B, and Meta Muse Glimmer 30B. No 2026 benchmark directly ranks these models on citation-grounded RAG. The evidence available points to **non-thinking mode + a strong instruction follower** (Qwen3.5-4B/9B, Gemma 4 E4B/12B, Granite 4.1 8B, Phi-4) as the right choice for faithful answers over retrieved context.

### Cited Findings

**Qwen (Alibaba)**
- Qwen3.5 small series has four sizes (0.8B, 2B, 4B, 9B). Instruct and Base versions are on HF/ModelScope under Apache 2.0. MarkTechPost reported the release on Mar 2 2026 and a secondary source says Mar 1 — [MarkTechPost](https://www.marktechpost.com/2026/03/02/alibaba-just-released-qwen-3-5-small-models-a-family-of-0-8b-to-9b-parameters-built-for-on-device-applications/); [mean.ceo](https://blog.mean.ceo/qwen-3-5-small-model-series-release/). Artificial Analysis dates it Mar 5 2026 and codersera says "Feb 2026". Treat the date as early March 2026 — [Artificial Analysis](https://artificialanalysis.ai/articles/qwen3-5-small-models); [codersera](https://codersera.com/blog/qwen-3-5-complete-guide-2026/)
- The Qwen3.5 small models are dense and support 262K context, native vision, and a unified thinking/non-thinking mode. Artificial Analysis Intelligence Index: 9B = 32 (best under 10B), 4B = 27 (best under 5B), 2B = 16, 0.8B = 9. For comparison, Qwen3 4B-2507 = 18, Qwen3 1.7B ≈ 13, and Qwen3-VL-8B = 17 — [Artificial Analysis](https://artificialanalysis.ai/articles/qwen3-5-small-models)
- **Warning for RAG:** Artificial Analysis found the Qwen3.5 small models use 230–390M output tokens to run the index, which is very verbose. It also measured **80–82% hallucination rates for the 4B and 9B** on its knowledge-hallucination test. That test is closed-book, not RAG — [Artificial Analysis](https://artificialanalysis.ai/articles/qwen3-5-small-models)
- Qwen3.5-4B model card: 32 layers, hybrid Gated-DeltaNet architecture, 262,144 native context (extendable to ~1.01M), 201 languages/dialects, tool calling, vision. MMLU-Pro 79.1, GPQA-D 76.2, IFEval 89.8, BFCL-V4 50.3, AA-LCR 57.0 — [HF Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B). The fetched card summary also mentioned "sparse MoE", which conflicts with Artificial Analysis calling the small models dense. Codersera describes the 3.5/3.6 generation as ~75% Gated DeltaNet linear-attention layers + 25% full attention, which is what makes 256K context affordable — [codersera](https://codersera.com/blog/qwen-3-5-complete-guide-2026/)
- **Conflict on the default mode:** Unsloth says "For Qwen3.5 0.8B, 2B, 4B and 9B, reasoning is disabled by default" and that it can be enabled with `enable_thinking` — [Unsloth Qwen3.5 docs](https://unsloth.ai/docs/models/qwen3.5). The HF card summary says thinking is on by default — [HF](https://huggingface.co/Qwen/Qwen3.5-4B)
- Qwen3.5 total memory (RAM+VRAM) at 4-bit: 0.8B/2B ≈ 3.5 GB, 4B ≈ 5.5 GB, 9B ≈ 6.5 GB, 27B ≈ 17 GB, 35B-A3B ≈ 22 GB. At 3-bit, the 9B needs ≈ 5.5 GB — [Unsloth](https://unsloth.ai/docs/models/qwen3.5). Unsloth also said Qwen3.5 GGUFs did not work in Ollama at the time because of separate mmproj vision files. This may be out of date — [Unsloth](https://unsloth.ai/docs/models/qwen3.5)
- Qwen3.6: 35B-A3B MoE (Apr 16 2026) and 27B dense multimodal (Apr 22 2026), both Apache 2.0. The 27B is described as surpassing Qwen3.5-397B-A17B on coding benchmarks — [Qwen blog 27B](https://qwen.ai/blog?id=qwen3.6-27b); [Qwen blog 35B-A3B](https://qwen.ai/blog?id=qwen3.6-35b-a3b)
- Qwen3.7 stayed closed / API-only (Qwen3.7-Max, May 20). No sub-10B Qwen models have been released since the 3.5 small series — [codersera (secondary)](https://codersera.com/blog/qwen-3-5-complete-guide-2026/)
- Qwen3.8-27B (Aug 14 2026) is a dense multimodal model (text/image/video) with 262K native context (1M via YaRN), a toggleable thinking mode, and Apache 2.0. Qwen3.8-2.4T-A95B open weights followed on Aug 12–13 — [The Decoder](https://the-decoder.com/alibabas-qwen-team-releases-qwen-3-8-models-with-open-weights-under-the-apache-2-0-license/); [MarkTechPost](https://www.marktechpost.com/2026/08/03/alibaba-qwen-releases-qwen3-8-max/). The 2.4T license is reported as Apache 2.0 by The Decoder but "custom" by [codersera](https://codersera.com/blog/qwen-3-5-complete-guide-2026/). The 2.4T model is irrelevant for laptops either way.

**Google Gemma 4**
- Launched **Apr 2 2026** under **Apache 2.0**, with E2B, E4B, 26B MoE and 31B dense. Google says the 31B is the #3 open model on the Arena text leaderboard. Day-one runtimes included llama.cpp, MLX, Ollama, LM Studio, LiteRT-LM, Transformers.js and vLLM — [Google blog](https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/)
- Model card (updated Jul 30 2026):
  - Sizes: E2B = 2.3B effective (5.1B with embeddings); E4B = 4.5B effective (8B with embeddings, Per-Layer Embeddings); **12B "Unified"** (11.95B, added after launch); 26B A4B (25.2B total / 3.8B active, 8 of 128 experts); 31B dense.
  - Context: E2B/E4B 128K; 12B/26B/31B 256K.
  - Modalities: text and image on all sizes; audio on E2B/E4B/12B; video as frames.
  - Thinking is enabled via the `<|think|>` token, and function calling is native. Pre-trained on 140+ languages, 35+ supported out of the box.
  - MMLU-Pro: 31B 85.2, 26B 82.6, 12B 77.2, E4B 69.4, E2B 60.0. GPQA-D: 84.3 / 82.3 / 78.8 / 58.6 / 43.4.
  - Source: [Gemma 4 model card](https://ai.google.dev/gemma/docs/core/model_card_4); [HF gemma-4-E4B](https://huggingface.co/google/gemma-4-E4B)
- Memory (secondary only): smallest model ≈ 4 GB RAM, largest ≈ 19 GB — [gemma4.org (unofficial)](https://gemma4.org/gemma-4-model-sizes). Gemma 4 12B at Q4_K_M uses ~8 GB and is called "the default 16GB pick" — [Atomic Chat](https://atomic.chat/blog/guides/best-local-llm-16gb)
- Gemma 4 on Ollama's MLX engine with multi-token prediction is "up to 90% faster" with coding agents (Jun 29 2026) — [Ollama blog](https://ollama.com/blog)

**Meta**
- Llama 4 (Apr 5 2025): Scout has 109B total / 17B active, Maverick 400B / 17B active, both under the Llama 4 Community License. Neither is laptop-class. In **April 2026 Meta replaced Llama with Muse Spark** in its products — [Wikipedia](https://en.wikipedia.org/wiki/Llama_(language_model))
- **Muse Glimmer** (Aug 10–12 2026; CNBC says Aug 10, Meta's dev blog says Aug 12) is a 30B **dense** model under **Apache 2.0**, text+image, 128K context. It is under 20 GB at ~4-bit and targets a 24–32 GB envelope. It ships a speculative-decoding drafter (recommended 5 tokens/step, 8–10 for code) and runs on llama.cpp, ExecuTorch, Ollama, LM Studio, vLLM and SGLang. Meta positions it against Qwen3.6-27B and Gemma 4 for tool orchestration and long-context memory — [Meta dev blog](https://dev.meta.ai/resources/blog/build-with-muse-glimmer/); [CNBC](https://www.cnbc.com/2026/08/10/meta-muse-glimmer-open-weight-ai.html); [MarkTechPost](https://www.marktechpost.com/2026/08/10/meta-ai-releases-muse-glimmer/)

**Microsoft Phi**
- Phi-4-mini-instruct (Feb 2025): 3.8B, 128K context, **MIT**, 23 languages, function calling. The model card itself says the model "does not have the capacity to store too much factual knowledge" and suggests RAG — [HF](https://huggingface.co/microsoft/Phi-4-mini-instruct)
- Phi-4-reasoning-vision-15B (Mar 4 2026) is open-weight and multimodal. It uses adaptive reasoning, deciding per query whether to think — [Forbes](https://www.forbes.com/sites/janakirammsv/2026/03/06/microsoft-builds-a-compact-ai-model-that-decides-when-to-think/); [Wikipedia](https://en.wikipedia.org/wiki/Phi_(language_model))

**IBM Granite**
- Granite 4.0 (Oct 2 2025) is a hybrid Mamba-2/transformer design with ">70%" memory reduction for long context. Granite 4.0 Nano (350M–1.5B) followed in late Oct 2025. Apache 2.0 and ISO 42001 certified — [InfoWorld](https://www.infoworld.com/article/4067691/ibm-launches-granite-4-0-to-cut-ai-infra-costs-with-hybrid-mamba-transformer-models.html); [VentureBeat](https://venturebeat.com/ai/ibms-open-source-granite-4-0-nano-ai-models-are-small-enough-to-run-locally)
- **Granite 4.1 (Apr 29 2026)** is **dense** 3B/8B/30B with up to **512K context** and Apache 2.0. IBM says the 8B matches or beats Granite 4.0 32B MoE, and that the family is strong at tool calling "without relying on extended reasoning chains", giving predictable latency and token use. Companion models: Granite Vision 4.1, Granite Speech 4.1 (2B, 5.33% WER), Granite Guardian 4.1 (8B, flags hallucinations) and Granite Embedding Multilingual R2 (97M) — [IBM Research](https://research.ibm.com/blog/granite-4-1-ai-foundation-models). A secondary source lists "12 major languages" for the LLMs — [aiproductivity.ai](https://aiproductivity.ai/news/ibm-granite-41-models-3b-8b-30b-release/)

**Mistral**
- Mistral 3 (Dec 2 2025): Ministral 3 in 3B/8B/14B, each with base, instruct and **reasoning** variants. All have image understanding, 40+ languages and Apache 2.0. Ministral 14B reasoning scores 85% on AIME'25 — [Mistral](https://mistral.ai/news/mistral-3/)
- Mistral Small 4 is Apache 2.0 (secondary) — [Serenities AI](https://serenitiesai.com/articles/mistral-ai-models-2026-complete-guide)

**OpenAI gpt-oss**
- gpt-oss-20b: 21B total / 3.6B active MoE, MXFP4, **Apache 2.0**, "can run on edge devices with just 16 GB of memory". Released Aug 5 2025 — [OpenAI](https://openai.com/index/introducing-gpt-oss/); [HF](https://huggingface.co/openai/gpt-oss-20b)
- Unverified: one aggregator claims a June 9 2026 gpt-oss refresh (gpt-oss-8b / 20b-a3b / 120b-a12b) under an "OpenAI Open Weight License 1.0" — [freeainews (secondary)](https://freeainews.com/open-source/openai-gpt-oss-open-weight-2026/). A direct search for "gpt-oss-8b" returned only the 2025 20b/120b models, and OpenAI's help page returned 403. Treat the claim as unconfirmed.

**Liquid AI**
- LFM2.5-1.2B (Jan 5 2026): hybrid of 10 gated-conv + 6 GQA blocks, 32K context, 8 languages, license "lfm1.0". Recommended for "agentic tasks, data extraction, and RAG" and **not** for knowledge-intensive tasks or coding. Decode speed is 116 tok/s on a Ryzen AI 9 HX 370 CPU and 70 tok/s on a Galaxy S25 Ultra. MMLU-Pro 44.35 vs Qwen3-1.7B 42.91 — [Liquid blog](https://www.liquid.ai/blog/introducing-lfm2-5-the-next-generation-of-on-device-ai); [HF](https://huggingface.co/LiquidAI/LFM2.5-1.2B-Instruct)
- LFM2.5-2.6B (Aug 4 2026) has 128K context and native tool calling. LFM2.5-VL-3B followed on Aug 12 2026 — [VentureBeat](https://venturebeat.com/technology/no-cloud-no-gpus-no-problem-liquid-ais-new-model-lfm2-5-2-6b-brings-powerful-ai-agents-to-devices-as-small-as-a-raspberry-pi); [Liquid](https://www.liquid.ai/blog/lfm2-5-vl-3b)

**Hugging Face**
- SmolLM3-3B (Jul 8 2025) is fully open (data and recipe published) with 128K context. No successor had been announced as of Sep 2026 (secondary) — [HF blog](https://huggingface.co/blog/smollm3); [TinyWeights](https://tinyweights.dev/posts/best-small-language-models-2026/)

**Others seen in 2026 runtime release notes**
- NVIDIA Nemotron 3.5 Lightning is a 30B agent model (Ollama, Aug 11 2026). Nemotron 3 Ultra shipped Jun 4 2026 — [Ollama blog](https://ollama.com/blog)

**Grounded / faithful answering evidence**
- Vectara hallucination leaderboard (grounded summarization; README updated Sep 22 2026). Hallucination rates:
  - Phi-4: 3.7%
  - Gemma-3-12B: 4.4%
  - Qwen3-8B: 4.8%
  - Mistral-small-2501: 5.1%
  - Granite-4.0-h-small: 5.2%
  - Qwen3-14B: 5.4%
  - Qwen3-4B: 5.7%
  - Gemma-3-4B: 6.4%
  - Ministral-3B: 7.3%
  - Best overall: finix_s1_32b at 1.8%
  - Source: [Vectara GitHub](https://github.com/vectara/hallucination-leaderboard)
  - No Qwen3.5, Gemma 4 or Granite 4.1 rows appeared in the fetched extract.
- Vectara's harder "next-gen" dataset (Nov 19 2025) has 7,700+ articles up to 32K tokens. On it, **"thinking models … GPT-OSS-120B … Deepseek-R1 all have a hallucination rate > 10%"**, and hallucination grows with document length and complexity — [Vectara blog](https://www.vectara.com/blog/introducing-the-next-generation-of-vectaras-hallucination-leaderboard)
- An academic study found faithfulness in small (<7B) models still has room for improvement even though larger models saturate — [Vectara leaderboard summary](https://www.emergentmind.com/topics/vectara-s-hallucination-leaderboard); [arXiv 2505.04847](https://arxiv.org/pdf/2505.04847)

### Inferences
- Moving from Qwen2.5-1.5B (2024) to **Qwen3.5-2B/4B** is the lowest-risk upgrade. It is the same family and chat conventions, Apache 2.0, has mlx-lm support (see Q5), and is a large capability jump (AA index 16/27 vs ~13 for Qwen3 1.7B, which already beats Qwen2.5-1.5B). The 4B at ~5.5 GB total is a good fit for 16 GB machines.
- For RAG answering, run Qwen3.5 in **non-thinking mode** and cap output length. Thinking models hallucinate more on grounded summarization (Vectara), and Qwen3.5 small models are very verbose (Artificial Analysis). Their weak closed-book knowledge (80%+ hallucination on Artificial Analysis's closed-book test) means prompts must force "answer only from the sources; otherwise say not found".
- **Gemma 4 E4B/12B** is a strong second default: Apache 2.0, Google QA, audio input (voice notes), and fast Ollama/MLX support with MTP. **Granite 4.1 8B** is attractive for enterprise positioning (Apache 2.0, ISO 42001 heritage, 512K context, predictable non-reasoning tool calls, Guardian model for hallucination checks).
- **gpt-oss-20b** (Apache 2.0, 16 GB) is the reasoning-heavy option for 24 GB+ Macs, but it is a thinking model and so a weaker default for faithful summarization.
- **LFM2.5-1.2B** is a candidate for background extraction/tagging jobs on 8 GB machines, not for answering from knowledge. Its "lfm1.0" license needs legal review.
- Llama is no longer the family to track for local. Meta's local-relevant open model is now Muse Glimmer 30B, which needs 24–32 GB.

### Gaps
- No 2026 head-to-head benchmark of citation-grounded QA (answer + correct citation spans) across Qwen3.5 / Gemma 4 / Granite 4.1 / Phi-4-mini was found. Vectara's rows for these 2026 models were not visible. The team should run its own eval on vault documents.
- LFM "lfm1.0" commercial terms (a revenue threshold is rumoured) were not confirmed from a primary page.
- No reliable 2026 information on DeepSeek distills for local use was gathered (search budget exhausted).
- Exact Gemma 4 Q4 memory per size from Google (vs community figures) was not found. Whether Google ships QAT checkpoints for Gemma 4 was not confirmed.
- MLX LoRA/DoRA *training* support for Gated-DeltaNet (Qwen3.5) and Gemma 4 PLE architectures was not verified. This matters for the app's fine-tuning features.

---

## 2. Best local embedding and reranker models (2026)

### Takeaway
There was no Qwen3.5-based text embedder as of Sept 2026, so the permissively licensed quality leaders are still **Qwen3-Embedding (0.6B/4B/8B, Apache 2.0, 32K context)** and **Qwen3-Reranker (0.6B/4B/8B, Apache 2.0)**. EmbeddingGemma-300M, nomic-embed-v2-moe and IBM Granite Embedding R2 (97M) are the lightweight picks. Jina's v5 embeddings and v3 reranker score best in the sub-1B class but are **CC-BY-NC-4.0**, so they cannot ship in a commercial app without a license. The app's current E5-small (English-centric, 2023-era) is well behind.

### Cited Findings
- **Qwen3-Embedding** (June 2025, Apache 2.0):
  - Sizes 0.6B/4B/8B; dims 1024/2560/4096 with MRL (custom dims).
  - Instruction-aware, 32K sequence length, 100+ languages including code.
  - The 8B was #1 on MTEB multilingual at 70.58 (Jun 5 2025).
  - Reranker 8B: MTEB-R 69.02, MTEB-Code 81.22.
  - Source: [Qwen blog](https://qwenlm.github.io/blog/qwen3-embedding/)
- As of 2026 the Qwen3-Embedding/Reranker text line is still built on Qwen3, and there is an open GitHub issue asking for a Qwen3.5-based version — [GitHub issue #192](https://github.com/QwenLM/Qwen3-Embedding/issues/192)
- Qwen3-VL-Embedding and Qwen3-VL-Reranker exist for multimodal retrieval (Jan 2026 paper) — [arXiv 2601.04720](https://arxiv.org/pdf/2601.04720); [Qwen blog](https://qwen.ai/blog?id=qwen3-vl-embedding)
- **EmbeddingGemma** (~300M / 308M, Sept 2025): 2K context; MRL at 768/512/256/128.
  - MTEB Multilingual v2: 61.15 (768d) and 58.23 (128d). MTEB English v2: 69.67. Code: 68.76.
  - QAT Q4_0/Q8_0 variants lose little quality, and it runs in <200 MB RAM quantized.
  - Source: [Google model card](https://ai.google.dev/gemma/docs/embeddinggemma/model_card); [Google Dev Blog](https://developers.googleblog.com/en/introducing-embeddinggemma/)
  - **License conflict:** the 2025 launch and secondary sources say Gemma Terms of Use — [Medium analysis](https://shubh7.medium.com/a-definitive-analysis-of-embeddinggemma-c043a5c14034). The current model card (fetched Sep 2026) indicates Apache 2.0, in line with Gemma 4's license change — [model card](https://ai.google.dev/gemma/docs/embeddinggemma/model_card). Verify on HF before shipping.
- **jina-embeddings-v5-text-small** (Feb 18 2026): 677M, Qwen3-0.6B base, 1024-d MRL down to 32, 32K context, 93 languages. MMTEB 67.0 ("highest among models under 1B"), MTEB-En 71.7. GGUF and MLX builds exist. **License CC-BY-NC-4.0.** A nano variant also exists — [Jina](https://jina.ai/models/jina-embeddings-v5-text-small/); [arXiv 2602.15547](https://arxiv.org/html/2602.15547v2)
- **nomic-embed-text-v2-moe** (Feb 2025): 475M total / 305M active, Apache 2.0 with open training data, ~100 languages, **512-token max**, MRL 768→256.
  - BEIR 52.86, MIRACL 65.80.
  - For comparison: BGE-M3 (568M) BEIR 48.80 / MIRACL 69.20; Arctic Embed v2 Large (568M) BEIR 55.65 / MIRACL 66.00.
  - Source: [HF](https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe)
- IBM **Granite Embedding Multilingual R2** is a 97M-parameter variant released with Granite 4.1 (Apr 29 2026), Apache 2.0 family — [IBM Research](https://research.ibm.com/blog/granite-4-1-ai-foundation-models)
- KaLM-Embedding-V2 claims SOTA among <1B embedders — [arXiv 2506.20923](https://arxiv.org/pdf/2506.20923). Stella-400M-v5 is described as the strongest sub-500M retriever (secondary) — [PremAI](https://www.premai.io/blog/best-embedding-models-for-rag-2026-ranked-by-mteb-score-cost-and-self-hosting/)
- **Rerankers:**
  - jina-reranker-v3: 0.6B on Qwen3-0.6B, listwise "last but not late interaction", up to 64 docs in a 131K window. BEIR 61.94, MIRACL 66.83, CoIR 70.64. GGUF/MLX available. **CC-BY-NC-4.0** — [HF](https://huggingface.co/jinaai/jina-reranker-v3); [arXiv 2509.25085](https://arxiv.org/html/2509.25085v2)
  - Qwen3-Reranker is Apache 2.0, 100+ languages, 32K context. Secondary guides recommend the 4B as the default open reranker in 2026 — [futureagi](https://futureagi.com/blog/best-rerankers-for-rag-2026/); [Mixpeek](https://mixpeek.com/curated-lists/best-rerankers)
  - mxbai-rerank-v2 is Apache 2.0 and small/fast; BGE reranker v2-m3 is the multilingual OSS default (secondary) — [futureagi](https://futureagi.com/blog/best-rerankers-for-rag-2026/)
- Leaderboard caveat: MTEB is a starting point, but performance on your own corpus should decide (MRR/nDCG on your own data) — [PremAI](https://www.premai.io/blog/best-embedding-models-for-rag-2026-ranked-by-mteb-score-cost-and-self-hosting/)
- Transformers.js v4 (Feb 2026) reports up to 4x faster BERT-style embedding models on WebGPU — [roboaidigest (secondary)](https://roboaidigest.com/posts/2026-02-11-transformers-js-v4-webgpu/). llama.cpp added multimodal input to its embeddings endpoint (build b11240, Sep 28 2026) — [llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases)

### Inferences
- Recommended default embedder for a commercial multilingual vault: **Qwen3-Embedding-0.6B**. It is Apache 2.0, and its 32K context makes chunk size flexible. MRL means 256–512-d vectors can shrink the index. The 1024-d output is larger than E5-small's, so a vector re-index plus migration path is needed.
- Low-RAM tier: **EmbeddingGemma-300M (QAT)** if its Apache 2.0 license is confirmed, otherwise Granite Embedding R2 (97M) or nomic-v2-moe. Note nomic's 512-token cap.
- Reranking is a cheap quality win. Qwen3-Reranker-0.6B reranking the top 20–50 chunks fits 8–16 GB machines, and the 4B suits 24 GB+. Avoid Jina models unless the company licenses them commercially.
- A single Qwen3 backbone family for LLM, embedder and reranker keeps tokenizer and runtime support simple across MLX, llama.cpp and ONNX.

### Gaps
- No measured CPU / Apple Silicon throughput (chunks/sec) for Qwen3-Embedding-0.6B vs EmbeddingGemma vs E5-small was found.
- Late-interaction/ColBERT-style models for 2026 (e.g. ModernBERT-based ColBERT, mxbai edge ColBERT) were not researched; the search budget ran out.
- The current live MTEB leaderboard (MMTEB v2 ranking as of Sep 2026) was not fetched directly.

---

## 3. Vision-language models for local document understanding

### Takeaway
Local document understanding now splits into two paths:
- **Tiny specialist parsers** (IBM Granite-Docling 258M, PaddleOCR-VL 0.9B, dots.ocr, DeepSeek-OCR) turn PDFs and scans into structured Markdown/JSON for indexing.
- **General VLMs** answer questions over page images. Qwen3.5 small models are natively multimodal, and Qwen3-VL 2B/4B/8B, Gemma 4, Ministral 3, LFM2.5-VL-3B and Apple's Foundation Models (image input in 2026) all qualify.

A vault should parse with a specialist at ingest time and use the general VLM only for ad-hoc visual questions.

### Cited Findings
- **Granite-Docling-258M** (Sep 17 2025, Apache 2.0): SigLIP2 encoder + Granite 165M LM, outputs DocTags for export to Markdown/HTML via Docling. Handles tables (TEDS 0.97 vs SmolDocling 0.82), equations and code. English primary; Japanese/Arabic/Chinese experimental. Runs on MLX, transformers, vLLM, llama.cpp and ONNX — [HF](https://huggingface.co/ibm-granite/granite-docling-258M)
- **PaddleOCR-VL-1.6**: ~0.9B, Apache 2.0, 100+ languages, OmniDocBench v1.6 96.33, ~2 GB VRAM FP16 — [Spheron](https://www.spheron.network/blog/best-open-source-ocr-vlm-self-host-gpu-cloud-2026/); [arXiv 2606.03264](https://arxiv.org/pdf/2606.03264)
- **DeepSeek-OCR**: ~3B MoE (~570M active), MIT, ~8 GB VRAM. **dots.ocr**: ~1.7B, MIT. **GOT-OCR 2.0**: ~580M, Apache 2.0 — [Spheron](https://www.spheron.network/blog/best-open-source-ocr-vlm-self-host-gpu-cloud-2026/)
- On OmniDocBench v1.5, GLM-OCR leads at 94.62 with PaddleOCR-VL-1.5 at 94.5 — [Regolo](https://regolo.ai/deepseek-ocr-vs-glm-ocr-vs-paddleocr-benchmark-2026/). LlamaIndex argues OmniDocBench is now saturated — [LlamaIndex](https://www.llamaindex.ai/blog/omnidocbench-is-saturated-what-s-next-for-ocr-benchmarks)
- **Qwen3.5 small** models accept images natively. MMMU-Pro: 9B 69.2%, 4B 65.4%, 0.8B 25.8% — [Artificial Analysis](https://artificialanalysis.ai/articles/qwen3-5-small-models)
- **Qwen3-VL** 2B/4B/8B/32B dense (Oct 2025), 256K context, OCR/video. The 2B is ~1.9 GB, viable on 8 GB laptops. Q4_K_M needs ~6 GB (4B) and ~12 GB (8B) (secondary). MLX builds run via mlx-vlm; llama.cpp needs a separate mmproj — [codersera](https://codersera.com/blog/qwen3-vl-4b-vs-qwen3-vl-8b-benchmarks-vram-guide/); [mlx-vlm](https://github.com/Blaizzy/mlx-vlm)
- **Gemma 4**: all sizes take images, and E2B/E4B/12B also take audio — [model card](https://ai.google.dev/gemma/docs/core/model_card_4)
- **LFM2.5-VL-3B** (Aug 12 2026, 3.1B): screen understanding, grounding, multi-image, function calling. The **DSpark** drafter (~280M, Sep 25 2026) makes decoding up to 3.13x faster without changing outputs — [Liquid](https://www.liquid.ai/blog/lfm2-5-vl-3b); [MarkTechPost](https://www.marktechpost.com/2026/09/25/liquid-ai-releases-lfm2-5-vl-3b-dspark-speculative-decoding-for-vision-language-models-with-up-to-3-13x-faster-decoding/)
- **Ministral 3** (3B/8B/14B) all include image understanding — [Mistral](https://mistral.ai/news/mistral-3/). **Phi-4-reasoning-vision-15B** (Mar 2026) pairs a SigLIP-2 encoder with the Phi-4-Reasoning backbone — [Forbes](https://www.forbes.com/sites/janakirammsv/2026/03/06/microsoft-builds-a-compact-ai-model-that-decides-when-to-think/). **Granite Vision 4.1** targets tables, charts and key-value extraction — [IBM Research](https://research.ibm.com/blog/granite-4-1-ai-foundation-models)
- **Apple Foundation Models (WWDC26)** now accept images (UIImage/NSImage/CGImage/CVPixelBuffer/file URLs). The Vision framework's OCR and barcode readers can be called as on-device tools — [Apple WWDC26 guide](https://developer.apple.com/wwdc26/guides/apple-intelligence/); [dev.to](https://dev.to/hariharanjagan/whats-new-in-apples-foundation-models-framework-at-wwdc-2026-5227)
- A known bug: mlx-vlm's TurboQuant KV cache can corrupt long-context generation (issue #2162) — [GitHub](https://github.com/Blaizzy/mlx-vlm/issues/2162)

### Inferences
- Ingest pipeline: **Docling + Granite-Docling-258M** (Apache 2.0, ~0.5 GB, MLX-native, English-first) as the default. Add **PaddleOCR-VL** for multilingual or scanned-heavy vaults. Both are small enough to run in the background on 8 GB machines.
- Visual Q&A: the default LLM (Qwen3.5-4B/9B or Gemma 4 E4B/12B) is itself multimodal in 2026. That removes the need for the separate `llama3.2-vision:11b` Ollama path currently in the codebase.

### Gaps
- No head-to-head of Granite-Docling vs PaddleOCR-VL on Apple Silicon (pages/min) was found.
- Licensing for GLM-OCR and MinerU was not verified. olmOCR, SmolDocling (as a separate model) and MiniCPM-V 2026 status were not researched.

---

## 4. Local speech: speech-to-text (voice input) and TTS ("audio overview")

### Takeaway
STT:
- **NVIDIA Parakeet TDT 0.6B v3**: fastest and most accurate for 25 European languages, CC-BY-4.0.
- **Whisper large-v3-turbo**: the MIT-licensed default for 99 languages.
- **Moonshine**: smallest edge option.

Gemma 4 E2B/E4B and Apple AFM 3 add built-in audio understanding and dictation. TTS:
- **Kokoro-82M** (Apache 2.0) is still the safe lightweight default.
- **Chatterbox** (MIT) handles voice cloning.
- **Qwen3-TTS** and newer 2026 models push quality up at larger sizes.

### Cited Findings
- **Parakeet TDT 0.6B v3** (Aug 14 2025): 600M, **CC-BY-4.0**, 25 European languages. Average Open ASR WER 6.34% (1.93% LibriSpeech-clean to 11.42% Earnings-22). Punctuation, capitalization and word/segment timestamps; up to 3 h of audio with local attention — [HF](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)
- Other Open ASR leaderboard results:

  | Model | Size | WER | RTFx | Languages | License |
  |---|---|---|---|---|---|
  | Canary-Qwen-2.5B | 2.5B | 5.63% | 418 | English | CC-BY-4.0 |
  | Whisper large-v3 | 1.55B | 7.4% | — | 99 | MIT |
  | Whisper large-v3-turbo | 809M | 7.75% | 216 | 99 | MIT |
  | Distil-Whisper large-v3 | 756M | ~7.4% | — | English | — |

  Moonshine goes as small as 27M; Northflank lists its license as "proprietary", which needs verification — [Northflank, Jan 7 2026](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks)
- Parakeet v3 is ~3,332x real time. Whisper-turbo tends to win on accented or technical long-form speech in production (secondary) — [onresonant](https://www.onresonant.com/resources/local-stt-models-2026); [snailtext](https://snailtext.app/blog/parakeet-vs-whisper-turbo-vs-qwen3-asr/)
- IBM Granite Speech 4.1 2B reports 5.33% WER — [IBM Research](https://research.ibm.com/blog/granite-4-1-ai-foundation-models)
- ONNX Runtime GenAI v0.17.0 (Sep 28 2026) added **Moonshine streaming ASR** and LFM2 audio support — [GitHub](https://github.com/microsoft/onnxruntime-genai/releases)
- Gemma 4 E2B/E4B have native audio input for speech recognition (~300M audio encoder in E4B) — [Google blog](https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/); [HF E4B](https://huggingface.co/google/gemma-4-E4B)
- Apple **AFM 3 Core Advanced** (on-device, high-end Apple silicon) adds TTS (MOS 4.15 general / 4.24 conversational vs 3.87/3.82 previously) and dictation (44.7% preferred vs 17.6%) — [Apple ML Research, Jun 8 2026](https://machinelearning.apple.com/research/introducing-third-generation-of-apple-foundation-models)
- **Kokoro-82M**: Apache 2.0, v1.0 (Jan 27 2025), 8 languages / 54 voices, trained only on permissive/synthetic audio — [HF](https://huggingface.co/hexgrad/Kokoro-82M)
- 2026 TTS landscape (secondary):
  - Qwen3-TTS (Jan 2026) is called the most capable open TTS.
  - Chatterbox (MIT) clones a voice from 5 s of audio.
  - Breeze TTS 2 (Aug 25 2026) is claimed at 1,215 Elo on the Artificial Analysis Speech Arena, running on a 12 GB GPU.
  - Fish Audio S2 Pro, F5-TTS, XTTS v2 (17 languages), Piper/MeloTTS (CPU/RPi-class) are also options.
  - Sources: [BentoML](https://www.bentoml.com/blog/exploring-the-world-of-open-source-text-to-speech-models); [OpenVox](https://openvoxai.com/blog/best-free-local-tts-models-2026); [localaimaster](https://localaimaster.com/blog/kokoro-vs-xtts-vs-chatterbox)

### Inferences
- Voice input: ship **Whisper large-v3-turbo** (MIT, multilingual; whisper.cpp or MLX) as the baseline and **Parakeet v3** as the fast European-language option. CC-BY-4.0 needs attribution, which is fine commercially.
- "Audio overview": generate the script with the local LLM and render it with **Kokoro-82M**. That is small, Apache 2.0 and CPU-feasible. Treat higher-quality two-voice "podcast" TTS (Qwen3-TTS/Breeze/Chatterbox) as an optional download for 16 GB+ machines, and check each license.

### Gaps
- Sesame CSM, Orpheus, Dia and similar conversational TTS models were not researched in 2026 form (search budget).
- Moonshine's current license (MIT vs community license by language/version) was not confirmed from the primary repo.
- No 2026 Apple Silicon RTF numbers for whisper.cpp vs MLX-Whisper vs Parakeet (CoreML/FluidAudio) came from primary sources.

---

## 5. Inference runtimes and OS-level AI frameworks (status Sep 2026) and the best cross-platform choice

### Takeaway
- **llama.cpp/GGUF** is the universal engine: every OS and backend, releases several times a day, MTP in beta.
- **MLX** is the fastest path on Apple Silicon and uses M5 Neural Accelerators. Ollama and LM Studio both switched to it on Macs.
- **Ollama** has grown into a local+cloud platform with accounts and pricing.
- **Microsoft Foundry Local** (ONNX Runtime) now runs on **Windows, macOS and Linux** as a ~20 MB embeddable runtime and is the NPU path on Windows.
- **Apple Foundation Models** (macOS/iOS 27) gives free on-device ~3B access, plus a Python SDK and free PCC for small developers.

For a Python desktop app on Mac/Windows/Linux, the practical architecture keeps the **MLX backend on macOS and adds a llama.cpp (llama-server/GGUF) backend for Windows/Linux**, both behind one OpenAI-compatible interface. Foundry Local / Windows ML is an optional NPU accelerator on Copilot+ PCs.

### Cited Findings

**llama.cpp**
- Build **b11256** landed on Sep 29 2026. Backends: CUDA 12.8/13.4, Vulkan, ROCm, Metal, SYCL, OpenVINO, OpenCL (Adreno). CPUs: x64/arm64. Platforms: Windows x64/arm64, macOS, Linux, iOS, Android. Recent builds added multimodal inputs to the embeddings endpoint (b11240) and fixed Muse Glimmer JSON-schema handling (b11246) — [GitHub releases](https://github.com/ggml-org/llama.cpp/releases)
- **Multi-token prediction** merged May 16 2026 (PR #22673) as beta behind `--mtp` for llama-cli/llama-server. It only helps models trained with MTP heads. Qwen3.6-27B Q4_K_M on an RTX 5090 went from 38 to 65 tok/s (1.71x), with smaller wins on bandwidth-bound machines — [llmrequirements](https://llmrequirements.com/news/2026-05-17-llama-cpp-mtp-merged)
- Jan v0.8.0 (May 22 2026), built on llama.cpp, ships MTP, a llama.cpp router mode, and inline MCP tool approval with citation cards — [Jan changelog](https://www.jan.ai/changelog/2026-05-22-jan-v0.8.0)

**Ollama**
- v0.19 (Mar 30 2026) replaced the llama.cpp Metal backend with **MLX** (preview; required a Mac with >32 GB). Qwen3.5-35B-A3B NVFP4 went from 1,154 to 1,810 tok/s prefill and 58 to 112 tok/s decode — [Ollama blog](https://ollama.com/blog/mlx)
- On Jun 11 2026, NVFP4 ran "up to 20% faster" than q4_K_M and "roughly halves the quality loss". Ollama also added prefix caching and snapshotting for agents — [Ollama blog](https://ollama.com/blog/mlx-performance)
- v0.40.0-rc0 (Sep 25 2026): "model architectures supported by the MLX runtime will automatically run on MLX". v0.35.0 (Sep 28) added "decision models" (`/v1/systemone`). v0.34.2 (Sep 15) added **first-run sign-in** — [GitHub releases](https://github.com/ollama/ollama/releases)
- Ollama now includes Anthropic Messages API compatibility (Jan 2026), cloud models (Sep 2025), a web search API, **per-token pricing plans (Aug 31 2026)** and an $88M funding round (Jul 2026) — [Ollama blog](https://ollama.com/blog)
- "Some models run on your GPU, others are routed to Ollama's own infrastructure, with the API remaining identical" (secondary) — [angelo-lima](https://angelo-lima.fr/en/ollama-2026-state-of-the-art-en/)

**MLX / mlx-lm / mlx-vlm**
- mlx-lm v0.30.7 (Feb 2026) added Qwen 3.5; v0.31.0 (Mar 2026) added Qwen3.5 tensor parallelism and server caching; v0.31.2 (Apr 2026) added Gemma 4 with tool calling and system-prompt caching; latest tag seen is v0.31.3. The GitHub page mislabeled the years, but the model support shows these are 2026 releases — [GitHub](https://github.com/ml-explore/mlx-lm/releases)
- Apple research (Nov 19 2025): on M5, MLX uses the GPU Neural Accelerators and needs macOS 26.2+. Time-to-first-token is 3.3–4.1x faster than M4 (Qwen 14B 4-bit 4.06x) and generation is 1.19–1.27x faster. Bandwidth is 153 GB/s vs 120 GB/s — [Apple ML Research](https://machinelearning.apple.com/research/exploring-llms-mlx-m5)
- MLX and llama.cpp are about equal on 1–7B models; MLX is 10–20% faster on 14–32B (secondary, Jul 2026) — [Presenc](https://presenc.ai/research/mlx-vs-llama-cpp-throughput-benchmarks-2026)

**LM Studio**
- 0.4.24 (Sep 9 2026) includes the **llmster** headless daemon, the `lms` CLI, TypeScript/Python SDKs, an MLX engine and continuous batching. It is free for personal and commercial use (secondary) — [promptquorum](https://www.promptquorum.com/power-local-llm/lm-studio-review); [codersera](https://codersera.com/blog/lm-studio-complete-guide-2026/)

**ONNX Runtime GenAI**
- v0.16.0 (Sep 22 2026): continuous batching, paged attention, speculative decoding (DFlash2/DSpark), tool calling and constrained decoding, Qwen3.5 / Qwen3-VL support, AMDGPU EP, WebGPU exports, INT4/INT8/FP8 KV cache.
- v0.17.0 (Sep 28 2026): prefix caching, LFM2 vision/audio, Moonshine streaming ASR.
- Source: [GitHub](https://github.com/microsoft/onnxruntime-genai/releases)

**Microsoft Foundry on Windows** (doc dated Aug 5 2026)
- **Windows AI APIs** (Phi Silica, OCR, semantic search) mostly require a Copilot+ PC.
- **Foundry Local** offers 20+ OSS LLMs and speech models through an OpenAI-compatible API on any Windows hardware.
- **Windows ML** (new) is the ONNX Runtime-based path for any model on CPU/GPU/NPU.
- **DirectML is in sustained engineering**, replaced by IHV execution providers.
- Copilot+ PC means an NPU with 40+ TOPS and 16 GB+ RAM.
- Microsoft recommends a three-tier fallback: Windows AI APIs → Foundry Local → Azure.
- Source: [MS Learn](https://learn.microsoft.com/en-us/windows/ai/windows-ai-comparison)

**Foundry Local** (updated Aug 2026)
- Supports **Windows, macOS (Apple silicon), and Linux**. The runtime is ~20 MB, with SDKs for C#, JS, Rust and Python.
- It auto-selects GPU/NPU/CPU execution providers and exposes an OpenAI-compatible API including the Responses format, with an optional local server.
- The curated, versioned catalog includes gpt-oss, Qwen, DeepSeek, Mistral, Phi and Whisper.
- Inference is local; the network is used only for model/EP downloads and optional diagnostics.
- Source: [MS Learn](https://learn.microsoft.com/en-us/azure/ai-foundry/foundry-local/what-is-foundry-local)
- AnythingLLM Desktop v1.16.1 embeds Foundry Local on Windows — [AnythingLLM](https://anythingllm.com/blog/foundry-local)

**Apple Foundation Models framework** (WWDC26, Jun 2026; OS 27)
- The on-device model is rebuilt, accepts images, and has **8,192-token context** (secondary) — [dev.to](https://dev.to/hariharanjagan/whats-new-in-apples-foundation-models-framework-at-wwdc-2026-5227)
- **Private Cloud Compute access for developers** has 32K context (secondary). It is **free for App Store Small Business Program developers with <2M first-time downloads** — [Apple WWDC26 guide](https://developer.apple.com/wwdc26/guides/apple-intelligence/)
- A `LanguageModel` protocol lets Claude/Gemini Swift packages sit behind the same session API. Other additions: Dynamic Profiles, an evaluations framework, the `fm` CLI and a **Python SDK** — [Apple WWDC26 guide](https://developer.apple.com/wwdc26/guides/apple-intelligence/)
- Utilities are "going open source this summer" with Linux support (secondary) — [dev.to](https://dev.to/hariharanjagan/whats-new-in-apples-foundation-models-framework-at-wwdc-2026-5227)
- **AFM 3** (Jun 8 2026) comes in two on-device versions:
  - Core: 3B dense.
  - Core Advanced: 20B sparse MoE with 1–4B active, experts streamed from NAND flash, multimodal plus TTS/dictation, for the "most capable Apple silicon" only.
- Server models: AFM 3 Cloud runs on Apple silicon in PCC. **AFM 3 Cloud Pro runs "on NVIDIA GPUs in Google Cloud"** — [Apple ML Research](https://machinelearning.apple.com/research/introducing-third-generation-of-apple-foundation-models)
- The 2025 baseline was a ~3B model with 2-bit QAT and 37.5% KV-cache savings, competitive with Qwen3-4B/Gemma-3-4B in English — [Apple ML Research 2025](https://machinelearning.apple.com/research/apple-foundation-models-2025-updates)
- A new **Core AI** framework is for running other local models (embedders, classifiers) on Apple silicon (secondary) — [Callstack](https://www.callstack.com/blog/on-device-ai-after-wwdc-2026-whats-new)

**Chrome built-in AI (Gemini Nano)**
- The Prompt API supports text/image/audio input and JSON-schema `responseConstraint`. It needs 16 GB RAM + 4 cores or a >4 GB VRAM GPU, plus 22 GB free disk. It runs on Windows 10/11, macOS 13+, Linux and Chromebook Plus. Docs updated Aug 26 2026 — [Chrome docs](https://developer.chrome.com/docs/ai/prompt-api)
- Status conflict: the docs cite Chrome 138 as stable (originally extension-scoped). Secondary sources say **Chrome 148 (Q2 2026) stabilized it for web pages** — [pasqualepillitteri](https://pasqualepillitteri.it/en/news/3145/gemini-nano-chrome-built-in-ai-client-side-en)

**Android**
- Gemini Nano 4, based on Gemma 4, is in the AICore Developer Preview for "flagship devices later this year". The ML Kit Prompt API is getting Structured Output and Prefix Caching.
- LiteRT-LM supports bring-your-own SLMs. Firebase AI Logic hybrid inference offers `PREFER_ON_DEVICE` / `ONLY_ON_DEVICE` / `PREFER_CLOUD` modes, and AppFunctions ("Android MCP") is new.
- Source: [Android Developers Blog, May 2026](https://android-developers.googleblog.com/2026/05/android-ai-intelligence-system.html)

**WebGPU / in-browser**
- Transformers.js v4 (Feb 2026) rewrote its WebGPU runtime, runs gpt-oss-20b at ~60 tok/s on high-end Macs, and supports MoE/Mamba/MLA. All four major browser engines now ship WebGPU by default, covering ~77% of users (secondary) — [roboaidigest](https://roboaidigest.com/posts/2026-02-11-transformers-js-v4-webgpu/); [TianPan](https://tianpan.co/blog/2026-04-17-browser-native-llm-inference-webgpu)

### Inferences
- **Recommended runtime architecture for Enclave (Python desktop app):**
  1. Keep **mlx-lm/mlx-vlm in-process on macOS**. It is the fastest path, uses the M5 Neural Accelerators, and fits the existing code and LoRA training.
  2. Add a **llama.cpp backend** for Windows/Linux. Either bundle `llama-server` as a sidecar with the platform-appropriate Vulkan/CUDA/CPU build, or use Python bindings, with GGUF weights for the same model family.
  3. Abstract both behind an OpenAI-compatible chat/embeddings interface. Local runtimes (llama-server, Foundry Local, LM Studio, Ollama) all speak it, so users can also plug in their own.
  4. Optionally detect Copilot+ NPUs and route through **Foundry Local**. It is cross-platform, ~20 MB and OpenAI-compatible, but its catalog is curated rather than arbitrary.
- **Don't make Ollama a hard dependency.** In 2026 it is a separately installed daemon with sign-in, cloud routing and pricing, which complicates a "nothing leaves your machine" promise. Support it as an optional "bring your own local server" endpoint instead.
- **Apple Foundation Models via the Python SDK** can give Mac users a zero-download model for summarize/extract/title tasks. Its 8K context is too small to be the main RAG answerer.
- Browser/Chrome Prompt API and WebLLM matter only for the browser extension, which exists in this repo. The 16 GB / 22 GB-disk requirement limits reach.

### Gaps
- Ollama's current license was not re-verified this session (historically MIT). Neither were its MCP support and exactly which models are cloud-routed by default.
- The Apple Foundation Models Python SDK's requirements (macOS 27 only? Apple Intelligence enabled? M1+?) and whether a non-App-Store Python app can use free PCC were not confirmed.
- Whether Foundry Local on macOS/Linux uses Metal/CUDA acceleration or only CPU was not stated on the fetched page.
- No primary source confirmed the Chrome 148 web-page stabilization.

---

## 6. Performance techniques that went mainstream by 2026

### Takeaway
The 2026 local stack routinely combines:
- 4-bit weights, with newer **NVFP4/MXFP4** formats and QAT replacing plain Q4_K_M.
- **Speculative decoding / MTP**: model-native MTP heads (Gemma 4, Qwen3.6) or small drafters (Muse Glimmer, LFM DSpark), typically 1.5–3x decode.
- **Prefix/prompt caching** everywhere.
- **Quantized KV caches.**
- **Hybrid linear-attention architectures** (Gated DeltaNet, Mamba-2, gated conv) that make 128K–256K context feasible.
- **Small-active-parameter MoE** (3–4B active) for 24 GB+ machines.

### Cited Findings
- **MTP / speculative decoding:**
  - llama.cpp `--mtp` beta gave 1.71x on Qwen3.6-27B — [llmrequirements](https://llmrequirements.com/news/2026-05-17-llama-cpp-mtp-merged)
  - Gemma 4 MTP on Ollama/MLX is up to 90% faster for coding agents — [Ollama](https://ollama.com/blog)
  - Muse Glimmer ships a drafter (5 tokens/step default) — [Meta](https://dev.meta.ai/resources/blog/build-with-muse-glimmer/)
  - LFM2.5-VL DSpark drafter gives up to 3.13x — [MarkTechPost](https://www.marktechpost.com/2026/09/25/liquid-ai-releases-lfm2-5-vl-3b-dspark-speculative-decoding-for-vision-language-models-with-up-to-3-13x-faster-decoding/)
  - LM Studio speculative decoding gives 20–50% (secondary) — [codersera](https://codersera.com/blog/lm-studio-complete-guide-2026/)
  - ONNX GenAI supports draft-model speculative decoding plus DFlash2/DSpark — [GitHub](https://github.com/microsoft/onnxruntime-genai/releases)
- **Prefix/prompt caching:**
  - Ollama MLX cross-conversation cache reuse and checkpoints — [Ollama](https://ollama.com/blog/mlx)
  - mlx-lm system-prompt caching (v0.31.2) — [GitHub](https://github.com/ml-explore/mlx-lm/releases)
  - ONNX GenAI prefix caching (v0.17) — [GitHub](https://github.com/microsoft/onnxruntime-genai/releases)
  - Android ML Kit Prefix Caching — [Android blog](https://android-developers.googleblog.com/2026/05/android-ai-intelligence-system.html)
- **KV-cache quantization:**
  - ONNX GenAI INT4/INT8/FP8 KV caches — [GitHub](https://github.com/microsoft/onnxruntime-genai/releases)
  - Google DeepMind's **TurboQuant** (ICLR 2026) does 2–4-bit KV (TQ3 ≈ 4.9x, TQ4 ≈ 3.8x vs FP16). It is still a proposed llama.cpp integration and a community fork, and mlx-vlm ships a TurboQuantKVCache. It lacks sink-token protection, and one MLX write-up called it "practically premature" without custom kernels — [llama.cpp discussion #20969](https://github.com/ggml-org/llama.cpp/discussions/20969); [TurboQuant fork](https://github.com/AmesianX/TurboQuant); [mlx-vlm #2162](https://github.com/Blaizzy/mlx-vlm/issues/2162)
- **Weight formats:**
  - NVFP4 roughly halves the quality loss of q4_K_M and runs up to 20% faster on MLX — [Ollama](https://ollama.com/blog/mlx-performance)
  - gpt-oss ships natively in MXFP4 — [HF blog](https://huggingface.co/blog/welcome-openai-gpt-oss)
  - Apple on-device models use QAT (2-bit in 2025) — [Apple 2025](https://machinelearning.apple.com/research/apple-foundation-models-2025-updates)
  - EmbeddingGemma ships QAT Q4_0/Q8_0 — [model card](https://ai.google.dev/gemma/docs/embeddinggemma/model_card)
- **Hybrid attention / SSM:**
  - Qwen3.5/3.6 use ~75% Gated DeltaNet with a fixed-size state instead of a growing KV cache — [codersera](https://codersera.com/blog/qwen-3-5-complete-guide-2026/)
  - Granite 4.0 hybrid Mamba-2 gives >70% memory reduction for long context — [InfoWorld](https://www.infoworld.com/article/4067691/ibm-launches-granite-4-0-to-cut-ai-infra-costs-with-hybrid-mamba-transformer-models.html)
  - LFM2.5 uses a gated-conv + GQA hybrid — [HF](https://huggingface.co/LiquidAI/LFM2.5-1.2B-Instruct)
- **MoE for local:**
  - Qwen3.6-35B-A3B needs ~22 GB at 4-bit — [Unsloth](https://unsloth.ai/docs/models/qwen3.5)
  - Gemma 4 26B-A4B has 3.8B active — [model card](https://ai.google.dev/gemma/docs/core/model_card_4)
  - gpt-oss-20b has 3.6B active and runs in 16 GB — [OpenAI](https://openai.com/index/introducing-gpt-oss/)
  - Apple AFM 3 Core Advanced is a 20B sparse model with 1–4B active and experts loaded from flash on demand — [Apple](https://machinelearning.apple.com/research/introducing-third-generation-of-apple-foundation-models)
- Long context degrades faithfulness: Vectara found hallucination rises with article length up to 32K tokens — [Vectara](https://www.vectara.com/blog/introducing-the-next-generation-of-vectaras-hallucination-leaderboard)

### Inferences
- **Usable context on a 16 GB laptop** is an estimate, not measured. A 4B hybrid-attention model at 4-bit (~5.5 GB total per Unsloth) leaves room for 32K–64K tokens of context. The practical limit is **prefill time** on base M-series chips, not memory, and faithfulness also drops with length (Vectara). For RAG, 8–16K tokens of retrieved context with reranking is the sweet spot. Reserve 128K+ for explicit "read the whole document" features on 24 GB+ Macs.
- Use prefix caching for the static system prompt and instructions in every RAG call. It is cheap and supported by mlx-lm and llama-server.
- Enable MTP/speculative decoding only for models that ship heads or drafters (Gemma 4, Qwen3.6+, Muse Glimmer). For 1–4B models the gain is smaller because bandwidth is not the bottleneck.
- Treat TurboQuant-style 2–3-bit KV as experimental in 2026. 8-bit KV (llama.cpp q8_0, ONNX INT8) is the safe choice.

### Gaps
- No primary benchmark of prefill tok/s on base M1–M5 for 4B/9B models at 16–32K context was found. The context-length guidance above is an estimate.
- Whether mlx-lm (vs Ollama's MLX engine) exposes MTP for Gemma 4 was not verified.

---

## 7. Hardware reality: RAM tiers, tokens/sec, NPUs, and who can run what

### Takeaway
16 GB is the modal machine and the effective floor for a "good" local LLM experience. Copilot+ PCs and Chrome's Gemini Nano both set 16 GB as their minimum. 8 GB machines are a shrinking minority that can only run ≤2B models well. On Apple Silicon, decode speed is set by memory bandwidth: a base M5 has 153 GB/s, an M5 Pro 307 GB/s and an M5 Max 614 GB/s.

### Cited Findings
- **Steam Hardware Survey, Aug 2026** (gaming PCs, skews high-end): 8 GB 7.00%, 12 GB 2.43%, **16 GB 41.07%**, 24 GB 2.04%, **32 GB 38.47%**, 64 GB 3.97%, >64 GB 0.53%. Windows 11 is 75.53% of Windows users — [Steam](https://store.steampowered.com/hwsurvey/Steam-Hardware-Software-Survey-Welcome-to-Steam?platform=pc). 16 GB gained share in mid-2026 as DRAM prices rose — [Guru3D](https://www.guru3d.com/story/steam-june-survey-16gb-ram-gains-ground-as-32gb-adoption-slows/); [PCGamesN](https://www.pcgamesn.com/steam/hardware-survey-march-2026)
- Copilot+ PC = 40+ TOPS NPU **and 16 GB+ RAM** — [MS Learn](https://learn.microsoft.com/en-us/windows/ai/windows-ai-comparison). Chrome Gemini Nano needs 16 GB RAM or >4 GB VRAM — [Chrome docs](https://developer.chrome.com/docs/ai/prompt-api)
- 16 GB is now the sensible starting point for Macs; 8 GB is fine only for basic use (secondary) — [Box.co.uk](https://box.co.uk/blog/how-much-ram-needed-macbook); [Setapp](https://setapp.com/lifestyle/how-much-ram-do-you-need)
- **Apple Silicon speeds:**
  - M5 vs M4 on MLX: time-to-first-token 3.3–4.1x faster, decode 1.19–1.27x faster. Base M5 has 153 GB/s bandwidth — [Apple ML Research](https://machinelearning.apple.com/research/exploring-llms-mlx-m5)
  - M5 Pro (307 GB/s) runs Llama 3.1 8B Q4 at 50–60 tok/s; M5 Max (614 GB/s) at 100–120 tok/s. MLX is 20–50% faster than llama.cpp on M5 (secondary) — [promptquorum](https://www.promptquorum.com/local-llms/m5-pro-max-llm-benchmarks-2026)
  - M4 Pro 24 GB runs 14B models at ~35–55 tok/s (secondary, same source)
  - Qwen3.5-35B-A3B NVFP4 decodes at 112 tok/s and prefills at 1,810 tok/s on a top M5-series Mac with Ollama 0.19 — [Ollama](https://ollama.com/blog/mlx)
  - 7B models run at 50–80 tok/s on M3/M4/M5 MacBook Pros (secondary) — [Atomic/StorageReview summary](https://www.storagereview.com/best/laptops-local-ai)
- **CPU/phone:** LFM2.5-1.2B decodes at 116 tok/s on a Ryzen AI 9 HX 370 CPU and 70 tok/s on a Galaxy S25 Ultra — [Liquid](https://www.liquid.ai/blog/introducing-lfm2-5-the-next-generation-of-on-device-ai)
- **NPUs:** On Windows, NPU access goes through Windows AI APIs (Phi Silica) or Foundry Local / Windows ML execution providers. DirectML is deprecated in favor of IHV EPs — [MS Learn](https://learn.microsoft.com/en-us/windows/ai/windows-ai-comparison). Some reviewers still question how useful NPUs are for LLMs vs GPUs (secondary) — [DigitalApplied](https://www.digitalapplied.com/blog/ai-pc-npu-copilot-plus-local-ai-2026-buyers-guide)
- A MacBook Air with 24 GB often runs 7B models faster than a gaming laptop with a dGPU, because of unified memory (secondary) — [storagereview/pristren summary](https://pristren.com/blog/best-local-llm-2026/)

### Inferences
- **Estimated decode speeds.** Rule of thumb: decode tok/s ≈ 60–75% of bandwidth ÷ bytes read per token. On a base M5 (153 GB/s) that gives roughly:
  - 1–2B at 4-bit: ~80–120 tok/s
  - 4B: ~40–50 tok/s
  - 8–9B: ~20–25 tok/s
  - 12–14B: ~12–15 tok/s
  - 3–4B-active MoE (Qwen3.6-35B-A3B, gpt-oss-20b, Gemma 4 26B-A4B): ~35–50 tok/s, but only if the ~16–22 GB of weights fit.
  - Base M1/M2 (68–100 GB/s) run at about half these rates.
  - These are estimates. Validate them with the app's own benchmarks.
- **Who can run what** (estimate, using Steam as a proxy and discounting for non-gamer users having less RAM):
  - About 10% of users are at ≤12 GB and should get 0.8–2B models only.
  - About 40–50% are at 16 GB and should get 4B by default, with 9B as a "quality" option when memory headroom is available.
  - About 40% are at 24–32 GB+ and can run 9–14B dense or MoE at 20–35B.
  - The mainstream consumer (non-Steam) base likely has more 8–16 GB machines than Steam's numbers show.

### Gaps
- No primary data on the Mac installed base by RAM configuration was found. The claim that Apple's base configurations moved to 16 GB in late 2024 was not verified this session.
- No primary benchmark gave tok/s for 1B/4B/8B/14B/20B on *base* M1–M4 chips or Snapdragon X / Lunar Lake / Strix Point NPUs for 2026 models.

---

## 8. Hybrid patterns: when local is not enough

### Takeaway
The 2026 hybrid patterns, from most to least private:
1. On-device only.
2. **Attested confidential cloud**: Apple Private Cloud Compute, now open to third-party apps via Foundation Models; Google Private AI Compute (first-party only); GPU-TEE providers such as Phala on OpenRouter.
3. **Zero-data-retention routing** (OpenRouter ZDR, per-request or account-wide).
4. **Bring-your-own-key** to frontier APIs.

Platform vendors now ship explicit routing modes (Firebase `ONLY_ON_DEVICE`/`PREFER_ON_DEVICE`; the Windows three-tier fallback; Apple's `LanguageModel` protocol).

### Cited Findings
- **Apple PCC for third-party developers:**
  - Access is through the Foundation Models framework with no API keys or account setup, and is **free for Small Business Program developers under 2M first-time downloads** — [Apple WWDC26 guide](https://developer.apple.com/wwdc26/guides/apple-intelligence/); [dev.to](https://dev.to/hariharanjagan/whats-new-in-apples-foundation-models-framework-at-wwdc-2026-5227)
  - The same `LanguageModel` protocol wraps Claude/Gemini packages, with OAuth/Keychain auth and billing — [dev.to](https://dev.to/hariharanjagan/whats-new-in-apples-foundation-models-framework-at-wwdc-2026-5227); [Apple video 339](https://developer.apple.com/videos/play/wwdc2026/339/)
  - **Caveat:** Apple's own paper says AFM 3 Cloud Pro runs "on NVIDIA GPUs in Google Cloud", while AFM 3 Cloud runs on Apple silicon — [Apple ML Research](https://machinelearning.apple.com/research/introducing-third-generation-of-apple-foundation-models)
- **Google Private AI Compute** (Nov 11 2025): Gemini on TPUs inside **Titanium Intelligence Enclaves** with remote attestation and encryption. It powers Pixel Magic Cue and Recorder. No third-party developer access was stated — [Google blog](https://blog.google/technology/ai/google-private-ai-compute/)
- **OpenRouter ZDR:**
  - OpenRouter itself does not retain prompts unless the user opts into logging.
  - ZDR can be enforced account-wide, per model group, per API key (guardrails) or per request (`zdr` parameter).
  - BYOK keys follow ZDR rules and can be declared ZDR.
  - Source: [OpenRouter docs](https://openrouter.ai/docs/features/zdr)
  - ZDR providers via OpenRouter include Google Vertex, Amazon Bedrock and DeepInfra (secondary) — [blog](https://abubakarsiddik.site/blog/zero-data-retention-llm-providers)
- **GPU TEEs:**
  - Phala runs models (e.g. DeepSeek R1) inside GPU TEEs with remote attestation, available via OpenRouter — [Phala](https://phala.com/posts/GPU-TEEs-is-Alive-on-OpenRouter)
  - The OpenPcc paper (Jun 2026) describes open, PCC-style confidential LLM serving on commodity TEEs — [arXiv 2606.11145](https://arxiv.org/html/2606.11145v1)
  - The TEE must extend to GPU memory (a Compute Protected Region) — [brics-econ guide](https://brics-econ.org/confidential-computing-for-privacy-preserving-llm-inference-a-practical-guide)
- **Local-remote collaboration:** Stanford's Minions (Feb 2025) and "Secure Minions" (Jun 2025) protocols let a local model handle the long context and send only minimal, encrypted queries to a cloud model — [Ollama blog](https://ollama.com/blog)
- **Platform routing patterns:**
  - Firebase AI Logic hybrid inference modes `PREFER_ON_DEVICE`, `PREFER_CLOUD`, `ONLY_ON_DEVICE`, `ONLY_CLOUD` — [Android blog](https://android-developers.googleblog.com/2026/05/android-ai-intelligence-system.html)
  - Microsoft's documented Windows AI APIs → Foundry Local → Azure fallback — [MS Learn](https://learn.microsoft.com/en-us/windows/ai/windows-ai-comparison)
- **Counter-example (implicit cloud):** Ollama routes some models to its own cloud behind an identical API and added sign-in and pricing in 2026 — [Ollama blog](https://ollama.com/blog); [GitHub releases](https://github.com/ollama/ollama/releases)
- **UX precedent:** Jan 0.8.0 added *inline MCP tool approval with citation cards* — [Jan changelog](https://www.jan.ai/changelog/2026-05-22-jan-v0.8.0)

### Inferences
- A privacy-first vault should default to **`ONLY_ON_DEVICE`** and treat cloud as an explicit, per-request escalation that shows what will be sent. The tiers are:
  - (a) Apple PCC on Macs. It is attested, free for small developers and needs no keys. The product must still disclose that some Apple server tiers run on Google Cloud GPUs.
  - (b) BYOK/OpenRouter with ZDR enforced via the `zdr` flag, optionally restricted to TEE-attested providers.
  - (c) Direct BYOK to Anthropic, OpenAI or Google.
- Minions-style escalation, where the local model extracts minimal snippets and only those go to the cloud, fits a document vault better than sending whole documents. The app's existing redaction/PII tooling (if any) would support it.
- Avoid depending on runtimes that can silently route to a vendor cloud (Ollama cloud models). If supported, show a clear "local vs cloud" badge.

### Gaps
- No reliable examples were collected of how leading privacy-first consumer apps (e.g. Proton Lumo, Brave Leo, Jan, AnythingLLM, Obsidian plugins) present the local/cloud choice in UI. The search budget ran out.
- Whether PCC access works for a Python / non-App-Store macOS app, and its rate limits, were not confirmed.
- Pricing and availability of TEE-attested models on OpenRouter as of Sep 2026 were not verified.

---

## 9. Synthesis: recommended defaults per hardware tier (for the report writer)

### Takeaway
Replace Qwen2.5-1.5B + E5-small with a **Qwen3.5 + Qwen3-Embedding/Reranker stack sized by available RAM**. Keep MLX on Mac and add llama.cpp/GGUF for Windows/Linux. Offer Gemma 4 and Granite 4.1 as alternates, and use Granite-Docling for ingest. Every recommended default below is Apache 2.0 or MIT.

### Cited Findings (basis for the tiering)
- Qwen3.5 4-bit total memory: 2B ≈ 3.5 GB, 4B ≈ 5.5 GB, 9B ≈ 6.5 GB, 27B ≈ 17 GB, 35B-A3B ≈ 22 GB — [Unsloth](https://unsloth.ai/docs/models/qwen3.5)
- Qwen3.5 AA Intelligence Index: 2B 16 / 4B 27 / 9B 32 — [Artificial Analysis](https://artificialanalysis.ai/articles/qwen3-5-small-models)
- Gemma 4 12B Q4 ≈ 8 GB (secondary) — [Atomic Chat](https://atomic.chat/blog/guides/best-local-llm-16gb). gpt-oss-20b runs in 16 GB — [OpenAI](https://openai.com/index/introducing-gpt-oss/). Muse Glimmer is <20 GB at 4-bit for a 24–32 GB machine — [Meta](https://dev.meta.ai/resources/blog/build-with-muse-glimmer/)
- Licenses: Qwen3.5/3.6/3.8-27B, Gemma 4, Granite 4.1, Ministral 3 and Muse Glimmer are Apache 2.0; Phi-4-mini is MIT; Jina v5/v3 are CC-BY-NC — sources as cited in Q1–Q2.

### Inferences (recommendations; estimates, to be validated with in-app benchmarks)

| Tier | Share of users (rough) | Default answer LLM (non-thinking for RAG) | Alternates | Embedder | Reranker | Doc parsing / voice |
|---|---|---|---|---|---|---|
| 8 GB (M1/M2 base, older Windows) | ~10% | Qwen3.5-2B 4-bit (~3.5 GB) | Gemma 4 E2B; LFM2.5-1.2B for extraction only (license check) | EmbeddingGemma-300M QAT or Granite Embedding R2 97M | none, or Qwen3-Reranker-0.6B on top-20 | Granite-Docling-258M; Whisper-turbo or Moonshine |
| 16 GB (modal) | ~40–50% | **Qwen3.5-4B 4-bit (~5.5 GB)** | Gemma 4 E4B (audio in); Granite 4.1 3B; Phi-4-mini (MIT); Qwen3.5-9B "quality mode" (~6.5 GB) when headroom allows | **Qwen3-Embedding-0.6B** (MRL to 512-d) | Qwen3-Reranker-0.6B | Granite-Docling; Parakeet v3 / Whisper-turbo; Kokoro TTS |
| 24–32 GB | ~35–40% | **Qwen3.5-9B** or **Gemma 4 12B** | Granite 4.1 8B; gpt-oss-20b (reasoning); Qwen3.6-35B-A3B (32 GB only, ~22 GB) | Qwen3-Embedding-0.6B (or 4B) | Qwen3-Reranker-4B | + PaddleOCR-VL for multilingual scans |
| 36 GB+ / Pro-Max | small | Qwen3.8-27B / Qwen3.6-27B (~17 GB) or Gemma 4 26B-A4B | Muse Glimmer 30B (with drafter); Gemma 4 31B | Qwen3-Embedding-4B | Qwen3-Reranker-4B | + larger TTS (Qwen3-TTS/Chatterbox) |
| Mac, macOS 27, zero-download | all Apple Intelligence Macs | Apple Foundation Models on-device (~3B, 8K context) for titles, summaries, extraction | AFM 3 Core Advanced on top-end Apple silicon; PCC (32K) as the attested escalation | — | — | Vision-framework OCR tool |

- **Runtime per OS:**
  - macOS: MLX (mlx-lm/mlx-vlm, in-process; macOS 26.2+ unlocks the M5 Neural Accelerators).
  - Windows/Linux: llama.cpp (llama-server sidecar; Vulkan/CUDA/CPU builds) with GGUF of the same models.
  - Optional: Foundry Local on Copilot+ NPUs.
  - Optional user-supplied OpenAI-compatible endpoint (Ollama/LM Studio/Jan).
- **Settings:** non-thinking mode for grounded answering; a cached system prompt; 8–16K tokens of reranked context; 8-bit KV cache for long-document modes; MTP/drafter only for models that ship one.
- **Migration risks:**
  - The switch re-embeds the vault because vector dimensions change.
  - Fine-tuning code (MLX LoRA/DoRA) must be re-validated on Qwen3.5's Gated-DeltaNet architecture.
  - Qwen3.5 verbosity needs output caps.
  - Build a small internal faithfulness/citation eval before switching defaults, since no public 2026 benchmark ranks these models on cited RAG.

### Gaps
- The tier shares are rough estimates from Steam (gamer-skewed) data. Real Enclave user telemetry, or opt-in hardware stats, would be needed.
- No primary source confirmed the RAM Apple Foundation Models needs, or which Macs get AFM 3 Core Advanced.

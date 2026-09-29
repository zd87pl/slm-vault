# Document Ingestion, Retrieval & Grounded Answering: Local SOTA as of September 2026

*Scope: what a private, local-first personal-document vault (8–32 GB Mac/Windows/Linux laptops) can do today. Research date 2026-09-29. Many benchmark numbers are self-reported by vendors or re-run by competitors. Where sources disagree, both are given. Items marked [OLDER] predate 2026. Items marked [SECONDARY] come from aggregator or vendor blogs rather than primary papers or repos.*

---

## 1. Document parsing / OCR in 2026: which tools run locally, and how accurate are they?

### Takeaway
Small (0.3–1.2B) end-to-end document VLMs now top the main public parsing benchmark. On OmniDocBench v1.6 they beat frontier cloud models such as Gemini 3 Pro and GPT-5.2: TeleOCR 1.2B, OvisOCR2 0.8B, PaddleOCR-VL-1.6 0.9B, MinerU2.5-Pro 1.2B and GLM-OCR 0.9B all score 95–97. However, every model loses about 12 points on real photographed or shared documents, and licenses vary widely. For a local vault, the practical stack is:
- OS-native OCR as the fast first pass: Apple Vision `RecognizeDocumentsRequest` on macOS 26, and the Windows AI `TextRecognizer` on Copilot+ PCs.
- A small permissively licensed VLM (GLM-OCR, Granite-Docling, PaddleOCR-VL) as the "hard page" path for tables and scans.
- Docling as the multi-format container. It covers DOCX, XLSX, PPTX, EML/MSG and audio.

### Cited Findings

**Benchmark leaderboards (accuracy)**
- **OmniDocBench v1.6** (latest major eval update 2026-04-10; results added through 2026-09-11). Overall score / text edit distance / table TEDS / parameters:

  | Model | Overall | Text edit dist. | Table TEDS | Params |
  |---|---|---|---|---|
  | TeleOCR | 96.91 | 0.0267 | 96.82 | 1.2B |
  | OvisOCR2 | 96.47 | 0.0265 | 94.58 | 0.8B |
  | PaddleOCR-VL-1.6 | 96.34 | 0.0326 | 94.76 | 0.9B |
  | MinerU2.5-Pro | 95.75 | 0.036 | 93.42 | 1.2B |
  | GLM-OCR | 95.22 | 0.044 | 92.83 | 0.9B |
  | PaddleOCR-VL-1.5 | 94.93 | — | 91.67 | 0.9B |
  | PaddleOCR-VL | 94.18 | — | — | 0.9B |
  | MinerU2.5 | 93.04 | — | 87.88 | 1.2B |
  | Gemini-3-Pro | 92.91 | — | — | cloud |
  | dots.ocr | 90.77 | — | — | 3B |
  | DeepSeek-OCR-2 | 90.25 | — | — | 3B |
  | HunyuanOCR | 89.95 | — | — | 1B |
  | Qwen3-VL | 89.78 | — | — | 235B |
  | MonkeyOCR-pro | 88.57 | — | — | 3B |
  | GPT-5.2 | 86.59 | — | — | cloud |
  | Marker | 78.44 | — | 65.77 | — |

  — [OmniDocBench GitHub](https://github.com/opendatalab/OmniDocBench)
- OmniDocBench news: v1.7 added a Qianfan-OCR leaderboard and "skills-based evaluation" (2026-04-30). An EvalScope integration for OpenAI-compatible endpoints was added 2026-07-27. — [OmniDocBench GitHub](https://github.com/opendatalab/OmniDocBench)
- **Conflicting versions.** Scores differ between OmniDocBench v1.5 and v1.6, so always cite the version:
  - GLM-OCR: 94.62 on v1.5 ([HF model card via search](https://huggingface.co/zai-org/GLM-OCR)) vs 95.22 on v1.6.
  - PaddleOCR-VL: 92.56 on v1.5 ([emergentmind](https://www.emergentmind.com/topics/paddleocr-vl-0-9b)) vs 94.18 on v1.6.
  - DeepSeek-OCR 2: 91.09 on v1.5 ([TechNode](https://technode.com/2026/01/28/deepseek-releases-ocr-2-with-new-visual-encoding-architecture-targeting-more-human-like-machine-vision/)) vs 90.25 on v1.6.
  - A separate aggregator lists "Kimi K3 leading at 0.911". That is apparently a different scale or protocol and is not reconcilable. — [llm-stats](https://llm-stats.com/benchmarks/omnidocbench)
- **PureDocBench (arXiv 2605.07492, May 2026): parsing is far from solved on real-world captures.**
  - Covers 1,475 pages, 10 domains and 58 models, under Clean, Digital-degraded and Real (actual capture or sharing) conditions.
  - Best average score is 79.69/100; the mean across all models is 63.84.
  - Scores drop 3.34 points on Digital and **11.61 points on Real** vs Clean.
  - Top model per condition: TeleOCR (Clean), GLM-5.3-Flash (Digital), Gemini 3.6 Flash (Real).
  — [arXiv 2605.07492](https://arxiv.org/abs/2605.07492)
- **olmOCR-bench** (1,402–1,403 PDFs, ~7,010 unit tests). Scores vary by who runs them:
  - From the PaddleOCR/MinerU papers: PaddleOCR-VL 80.0±1.0, Youtu-Parsing 80.5, dots.ocr 79.1, MinerU2.5 77.5, DeepSeek-OCR 75.7. — [search summary of PaddleOCR-VL paper](https://arxiv.org/pdf/2510.14528)
  - MinerU2.5 paper: MinerU2.5 75.2 vs dots.ocr 73.6. — [MinerU2.5 paper](https://arxiv.org/pdf/2509.22186)
- Ai2's olmOCR 2 (7B) scores 82.4 on olmOCR-bench, vs Marker 76.1 and MinerU 75.8 in Ai2's run. — [Ai2 blog](https://allenai.org/blog/olmocr-2)
- **Chandra OCR 2** (Datalab, 5B, Qwen3.5 base):
  - olmOCR-bench 85.8±0.8. Sub-scores: tables 92.1, old-scan math 89.1, long tiny text 93.7.
  - Supports handwriting, checkbox forms and 90+ languages (43-language average 77.8%).
  - About 1.44 pages/s on one H100 with vLLM. GGUF builds exist for llama.cpp, Ollama and LM Studio.
  - **License is a modified OpenRAIL-M:** "free for research, personal use, and startups under $2M funding/revenue", with no use competitive with Datalab's API.
  — [HF model card](https://huggingface.co/datalab-to/chandra-ocr-2)
- **Marker 2** (Datalab, released 2026-07-21), from Datalab's own runs:
  - olmOCR-bench 76.0% overall, 83.5% on born-digital.
  - Speed: 2.9 pg/s "balanced" on a B200 GPU; 7.4 pg/s "fast"; **23.7 pg/s on CPU with OCR disabled**.
  - Same comparison: MinerU pipeline backend 72.7% at 0.54 pg/s; Docling 50.3% (64.0% born-digital) at 2.1 pg/s; LlamaIndex LiteParse (Rust) 22.4% at 1,721 pg/s on CPU with OCR off ("collapses on non-linear layouts").
  - Full-page VLM references in the same run: Chandra 2 85.8, dots.ocr 1.5 83.9, olmOCR 2 82.4, Gemini Flash 3.5 76.4.
  - [SECONDARY] — [Lumien summary](https://lumienai.com/news/marker-2-vs-mineru-docling-liteparse-olmocr-bench-benchmark); [MarkTechPost](https://www.marktechpost.com/2026/07/24/datalab-marker-v2-vs-mineru-docling-and-liteparse-benchmark-breakdown/)

**Individual models: size, license, local fit**
- **GLM-OCR** (Z.ai, released 2026-02-02):
  - 0.9B parameters. Weights MIT; code and the PP-DocLayoutV3 layout stage Apache-2.0.
  - Runs on vLLM, SGLang and **Ollama**. Two-stage design: layout analysis, then parallel recognition.
  — [HF card via search](https://huggingface.co/zai-org/GLM-OCR); [Z.ai docs](https://docs.z.ai/guides/vlm/glm-ocr)
  - Reported ~1.86 PDF pages/s (hardware unspecified) and ~$0.09 per 1,000 pages hosted. [SECONDARY] — [bestaiweb](https://www.bestaiweb.ai/mineru-2-5-glm-ocr-and-gemini-3-pro-the-2026-omnidocbench-race-for-document-parsing-supremacy/)
- **PaddleOCR-VL-1.5** (Baidu, Jan 2026):
  - 0.9B parameters; 94.5% on OmniDocBench v1.5.
  - Introduces **Real5-OmniDocBench** (scanning, skew, warping, screen photography, illumination), where it claims SOTA.
  - Adds seal recognition and text spotting.
  - arXiv lists CC BY 4.0, which is likely the *paper* license. Model license not verified here.
  — [arXiv 2601.21957](https://arxiv.org/abs/2601.21957)
  - PaddleOCR-VL-1.6 followed (arXiv 2606.03264). — [arXiv](https://arxiv.org/pdf/2606.03264)
- **MinerU2.5** (1.2B):
  - Decoupled two-stage design: global layout on a downsampled image, then native-resolution crops.
  - The 2509-1.2B weights are **AGPL-3.0**. The MinerU project has since moved to a custom "MinerU Open Source License" based on Apache 2.0.
  — [HF](https://huggingface.co/opendatalab/MinerU2.5-2509-1.2B); [MinerU discussion](https://github.com/opendatalab/MinerU/discussions/3781)
- **Granite-Docling-258M** (IBM, Sept 2025) [OLDER]:
  - Apache 2.0. Architecture: SigLIP2 plus a Granite 165M LM.
  - The MLX build runs at "200–300 tokens/sec" on Apple Silicon. Reported 2.5×–17.4× faster than Transformers/MPS.
  - Docling auto-selects the MLX build on Macs.
  — [HF MLX card](https://huggingface.co/ibm-granite/granite-docling-258M-mlx); [HF card](https://huggingface.co/ibm-granite/granite-docling-258M)
- **Docling** (MIT, LF AI):
  - Formats: PDF, DOCX, PPTX, XLSX, HTML, EPUB, Apple Pages, images, LaTeX, EML/MSG email, and WAV/MP3/WebVTT via ASR.
  - Produces a unified `DoclingDocument`.
  — [Docling supported formats](https://docling-project.github.io/docling/usage/supported_formats/)
  - Heron layout models: heron-101 reaches 78% mAP at 28 ms/image on an A100.
  — [arXiv 2509.11720](https://arxiv.org/abs/2509.11720)
- **DeepSeek-OCR 2** (2026-01-27): 3B; DeepEncoder V2 with "visual causal flow"; 256–1,120 visual tokens per page. — [TechNode](https://technode.com/2026/01/28/deepseek-releases-ocr-2-with-new-visual-encoding-architecture-targeting-more-human-like-machine-vision/)
- **Surya** (Datalab):
  - GPL-3.0, with commercial dual licensing available.
  - Designed for printed text: "not handwriting (though it may work on some)".
  - CPU runs are reported as 10–50× slower than GPU. [SECONDARY for the CPU claim]
  — [surya GitHub](https://github.com/datalab-to/surya); [SoloSoft](https://www.solosoft.dev/post/surya-ocr-2026/)
- **Mistral OCR 3** (cloud, Dec 2025) [OLDER, vendor claims]:
  - $2 per 1,000 pages ($1 via batch).
  - 74% win rate vs competitors on forms, scans, complex tables and handwriting.
  - Handwriting 88.9% vs Azure 78.2% vs DeepSeek 57.2%.
  — [VentureBeat](https://venturebeat.com/technology/mistral-launches-ocr-3-to-digitize-enterprise-documents-touts-74-win-rate); [Mistral](https://mistral.ai/news/mistral-ocr-3)
- **NuExtract3** (NuMind, 2026): 4B, Apache 2.0, based on Qwen3.5-4B. Does image-to-Markdown plus structured extraction for receipts, invoices, forms, contracts and tables; 18 quantized variants. — [HF](https://huggingface.co/numind/NuExtract3)

**OS-native OCR (zero model download)**
- **Apple Vision `RecognizeDocumentsRequest`** (WWDC25, macOS/iOS 26):
  - Returns document structure: paragraphs, **tables with rows, cells and spanning**, lists, QR codes and barcodes.
  - Runs DataDetection for dates, money and currency, addresses, phone, email, URLs, tracking numbers, payment IDs and flight numbers.
  - 26 languages, entirely on-device. The WWDC session does not mention handwriting.
  — [WWDC25 session 272](https://developer.apple.com/videos/play/wwdc2025/272/); [Apple docs: recognizing tables](https://developer.apple.com/documentation/Vision/recognize-tables-within-a-document)
- **Windows AI `TextRecognizer`** (Windows App SDK):
  - Returns words, lines, polygon bounds and per-word confidence.
  - **Runs only on devices with an NPU (Copilot+ PCs).** Microsoft positions it as more accurate than the legacy `Windows.Media.Ocr.OcrEngine`, which remains the fallback elsewhere.
  - No table-structure output is documented. Doc dated 2026-07-16.
  — [Microsoft Learn](https://learn.microsoft.com/en-us/windows/ai/apis/text-recognition)

**Handwriting / receipts / forms**
- Roboflow's OCR benchmark (updated 2026-09-22) is led by a frontier cloud model (Claude Fable 5, 94.0%). Its open-weight entries include MiMo V2.6 and GLM 5.3 Flash. The snippet reports both "59 models" and "89 models" tested, which is inconsistent. [SECONDARY] — [Roboflow](https://playground.roboflow.com/models/task/ocr)
- Vendor blogs claim "most handwriting OCR tools ~64% accuracy vs ~90% for LLM-powered" and that print-style handwriting scores 10–15% above cursive. Low reliability, vendor marketing. — [imagetotable.ai](https://imagetotable.ai/blog/best-handwriting-ocr-software-2026); [Extend](https://www.extend.ai/resources/best-handwriting-ocr-tools-business)

**Audio notes**
- **Parakeet TDT 0.6B v3:**
  - English WER 6.34% on the Open ASR Leaderboard, vs ~7.4% for Whisper large-v3 and 7.83% for large-v3-turbo.
  - About 60× realtime on Apple Silicon. INT8 ONNX runs on any CPU via sherpa-onnx.
  - Does not hallucinate during silence.
  - Limitation: only 25 European languages, vs 99 for Whisper.
  - [SECONDARY] — [OpenWhispr](https://openwhispr.com/blog/parakeet-vs-whisper-vs-nemotron); [Spokenly](https://spokenly.app/blog/parakeet-vs-whisper)
- **Whisper large-v3-turbo** with faster-whisper INT8 runs at about 8–12× realtime on CPU. [SECONDARY] — [Arun Baby](https://www.arunbaby.com/speech-tech/0073-whisper-vs-parakeet-asr-decision/)

### Inferences
- **Recommended cascade:**
  1. Born-digital PDF, DOCX, XLSX or email: parse the text layer directly (Docling, or a PyMuPDF-class parser). No OCR; 20+ pg/s on CPU.
  2. Scans and photos: OS OCR first (Apple Vision gives tables plus DataDetection amounts and dates for free).
  3. Escalate to a 0.9B VLM (GLM-OCR MIT, or Granite-Docling Apache on Mac) only for pages with tables, low OCR confidence or complex layout.
  4. Optionally escalate to a cloud OCR (Mistral OCR 3) with explicit user consent.
- **Licensing:**
  - Safest for commercial shipping: GLM-OCR (MIT/Apache), Granite-Docling (Apache), Docling (MIT), NuExtract3 (Apache).
  - Avoid or negotiate: Chandra 2 (revenue cap, no competitive use), Surya/Marker (GPL or dual), MinerU2.5-2509 weights (AGPL).
  - Verify PaddleOCR-VL, dots.ocr, DeepSeek-OCR 2, TeleOCR and OvisOCR2 model-card licenses directly.
- **Throughput (rough estimate, not measured):** at Granite-Docling's 200–300 tok/s, a dense page of ~1,000–1,500 output tokens takes ~4–7 s. Re-OCRing 10k scanned pages is therefore an overnight-to-multi-night background job. This is why a "text layer first, OS OCR second, VLM only on hard pages" design matters.
- PureDocBench's 11.6-point drop means phone photos of receipts and lab reports are exactly where errors pile up. Plan UX for "low-confidence field → show the image crop" rather than trusting parsed text.

### Gaps
- No reliable, like-for-like CPU-only or Apple Silicon pages/sec benchmarks for GLM-OCR, PaddleOCR-VL, MinerU2.5 or dots.ocr. Published speeds are on A100/H100/B200.
- No independent handwriting benchmark numbers for open local models. WildHandBench (arXiv 2608.22959) exists, but numbers were not retrieved.
- LlamaParse, Unstructured, GOT-OCR and Nougat: no 2026 comparative data found. GOT-OCR and Nougat are 2024-era [OLDER] and absent from 2026 top leaderboards.
- Licenses for TeleOCR, OvisOCR2, dots.ocr, DeepSeek-OCR 2 and PaddleOCR-VL weights were not verified.
- Apple Vision's accuracy on OmniDocBench-style benchmarks is unpublished.

---

## 2. Visual document retrieval (ColPali family): when to use it vs text pipelines, and what it costs locally

### Takeaway
Visual late-interaction retrievers (ColQwen, ColSmol, Nemotron ColEmbed) beat OCR-text retrievers on visually rich enterprise pages. However:
- Text rerankers add far more than visual rerankers do.
- The best end-to-end answers come from hybrid text+image context.
- Storage is heavy: ~256 KB/page unpooled.

For a personal vault, visual retrieval is best treated as an optional second index for chart-, table- and photo-heavy pages, not the primary index.

### Cited Findings
- **ViDoRe V3** (arXiv 2601.08620): 10 datasets, ~26,000 pages, 3,099 human-verified queries, 6 languages. Findings:
  - "Visual retrievers outperform textual ones."
  - "Late-interaction models and textual reranking substantially improve performance."
  - "Hybrid or purely visual contexts enhance answer generation."
  - Models "still struggle with non-textual elements, open-ended queries, and fine-grained visual grounding."
  — [arXiv 2601.08620](https://arxiv.org/abs/2601.08620)
- Textual rerankers boost retrieval far more than visual rerankers (+13.2 vs +0.2 NDCG@10). Page image + OCR text as generator input gives ~6.5% better accuracy than image alone. Numbers come from search snippets of the paper/HF blog and are not verified in the abstract. — [HF blog: ViDoRe v3 pipelines](https://huggingface.co/blog/antoineedy/vidore-v3-pipeline-framework-and-leaderboard)
- On the ViDoRe v3 pipeline leaderboard:
  - Best at release: Jina embeddings v4 + ZeRank2.
  - "Very low parameter" models (mxbai-edge-colbert-v0 32M, Llama-Nemotron-Embed-VL-1B) show "surprisingly good performance" at ultra-low latency.
  - Adding a reranker "increases search latency quite a lot."
  — [HF blog](https://huggingface.co/blog/antoineedy/vidore-v3-pipeline-framework-and-leaderboard)
- Leaderboard top: Nemotron ColEmbed V2 8B, NDCG@10 63.42 on ViDoRe V3 (Feb 2026). ColQwen3.5-4.5B-v3 was #6 as of 2026-04-20. — [arXiv 2602.03992](https://arxiv.org/html/2602.03992v2); [HF](https://huggingface.co/athrael-soju/colqwen3.5-4.5B-v3)
- **ColVision model zoo** (ViDoRe v1/v2-style scores), all Apache 2.0 unless noted:

  | Model | Score | Notes |
  |---|---|---|
  | ColQwen3.5-4.5B | 90.9 | |
  | Tomoro-ColQwen3 | 90.6 | 320-dim embeddings |
  | ColQwen2.5-v0.2 (3B) | 89.4 | |
  | ColQwen2 | 89.3 | |
  | ColPali-v1.3 | 84.8 | Gemma license |
  | ColSmol-500M | 82.3 | |
  | ColSmol-256M | 80.1 | |

  - Supports Apple MPS. `colpali-engine` is deprecated in favor of Sentence Transformers v6+.
  — [illuin-tech/colpali](https://github.com/illuin-tech/colpali)
- **Storage and pooling:**
  - ColPali stores ~1,031 × 128-dim vectors per page, about 256–258 KB/page in bf16. One million pages is ≈0.25 TB before indexing.
  - Hierarchical token pooling at factor 3 cuts vectors 66.7% and keeps 97.8% of quality (≈85 KB/page). Factor 4 keeps ≈97%.
  - MUVERA approximates MaxSim with single-vector ANN, then reranks with MaxSim.
  — [arXiv 2409.14683 token pooling](https://arxiv.org/pdf/2409.14683); [colpali repo](https://github.com/illuin-tech/colpali)
- **Qwen3-VL-Embedding / Reranker** (2B and 8B):
  - Maps text, images, document images and video into one space. 30+ languages, 32k inputs, MRL dimensions.
  - The 8B scored 77.8 on MMEB-V2 (#1 at release).
  — [arXiv 2601.04720](https://arxiv.org/abs/2601.04720)
- "Lost in OCR Translation?" (arXiv 2505.05666) studies vision-based retrieval robustness vs OCR pipelines on degraded documents; details not retrieved. — [arXiv](https://arxiv.org/pdf/2505.05666)

### Inferences
- **Storage math for a vault (estimate):**
  - 10k pages × 256 KB ≈ 2.6 GB; 100k pages ≈ 26 GB unpooled; pooled ×3 ≈ 8.5 GB.
  - Text vectors for the same corpus are 10–100× smaller.
  - So on a 256–512 GB laptop, visual multi-vector indexing should be opt-in, pooled, or limited to image-heavy pages.
- **Encoding cost:** ColSmol-256M/500M (Apache) is the realistic laptop encoder. 3–4.5B ColQwen models are feasible on 32 GB Apple Silicon but slow to index 100k pages.
- **Suggested design:** a text-first hybrid index. For pages flagged "visual" (charts, photos, tables with low OCR confidence), add a pooled ColSmol index, and pass page image + OCR text to a VLM generator.

### Gaps
- No measured CPU/MPS pages-per-second numbers for ColSmol or ColQwen encoding on laptops.
- Unverified whether ViDoRe V3's "visual beats text" holds against the strongest *text* pipelines with contextual chunking and hybrid BM25. The HF blog suggests the top text pipeline beat visual-only pipelines, which conflicts with the headline.

---

## 3. Chunking & indexing: what measurably helps?

### Takeaway
Measured wins, in order:
1. Contextual chunk headers or contextual embeddings plus BM25 plus reranking (Anthropic: −49% to −67% retrieval failures).
2. Sensible structure-aware chunks: recursive ~512 tokens, or page-level for paginated PDFs.
3. Hierarchical/summary trees (RAPTOR) for long single-document questions.

Semantic chunking and proposition/agentic chunking have repeatedly *failed* to justify their cost in 2025–2026 studies. Late chunking is cheap and gives modest gains.

### Cited Findings
- **Anthropic Contextual Retrieval** (Sept 2024) [OLDER, still the reference]. Top-20 retrieval failure rate:
  - 5.7% → 3.7% (−35%) with contextual embeddings.
  - → 2.9% (−49%) adding contextual BM25.
  - → 1.9% (−67%) adding reranking.
  - Context prefixes are 50–100 tokens per chunk. Cost is ~$1.02 per million document tokens with prompt caching.
  - Top-20 chunks beat top-5 or top-10.
  - "If your knowledge base is smaller than 200,000 tokens (about 500 pages)… just include the entire knowledge base in the prompt."
  — [Anthropic](https://www.anthropic.com/news/contextual-retrieval)
- **FloTorch/Vecta, Feb 2026** (50 papers, 906k tokens), end-to-end answer accuracy:
  - Recursive 512-token splitting 69%; fixed 512 67%; **semantic 54%** (fragments averaged 43 tokens).
  - Proposition/agentic chunking ranked "among worst."
  - [SECONDARY summary] — [PremAI summary](https://www.premai.io/blog/rag-chunking-strategies-the-2026-benchmark-guide/) citing [Vecta](https://www.runvecta.com/blog/we-benchmarked-7-chunking-strategies-most-advice-was-wrong)
- **Chroma** found semantic chunking had the best *token-level retrieval recall* (91.9%). This measures a different stage than end-to-end accuracy. — [Chroma research](https://research.trychroma.com/evaluating-chunking) (via [PremAI](https://www.premai.io/blog/rag-chunking-strategies-the-2026-benchmark-guide/))
- **NVIDIA 2024** [OLDER]: page-level chunking was best (0.648 accuracy, lowest variance) across 5 datasets including FinanceBench. — [NVIDIA blog](https://developer.nvidia.com/blog/finding-the-best-chunking-strategy-for-accurate-ai-responses/) (via PremAI)
- **Vectara, NAACL 2025:** "The computational costs associated with semantic chunking are not justified by consistent performance gains." — [arXiv 2410.13070](https://arxiv.org/abs/2410.13070)
- **Late chunking** (Jina): embed the whole document with a long-context model, then mean-pool token spans per chunk. No training needed. — [arXiv 2409.04701](https://arxiv.org/abs/2409.04701)
  - Reported gains: SciFact +1.9% nDCG@10, TREC-COVID +1.34%, NFCorpus +6.52%. [SECONDARY] — [Denser](https://denser.ai/blog/rag-chunking-strategies/)
- **Late chunking vs contextual retrieval** (ECIR 2025 workshop): contextual retrieval "preserves semantic coherence more effectively" but needs more compute. Late chunking is more efficient but "tends to sacrifice relevance and completeness." — [arXiv 2504.19754](https://arxiv.org/abs/2504.19754)
- **RAPTOR** [OLDER, ICLR 2024]: recursive embed → cluster → summarize tree. +20% absolute accuracy on QuALITY with GPT-4. — [arXiv 2401.18059](https://arxiv.org/abs/2401.18059)
- **Dense X / propositions** [OLDER]: proposition-level indexing "significantly outperforms passage-level" retrieval, especially for unsupervised retrievers. Exact numbers not retrieved. Contradicted in end-to-end tests by FloTorch 2026 (above). — [arXiv 2312.06648](https://arxiv.org/abs/2312.06648)
- A June 2026 paper, "Chunking Methods on RAG — Effectiveness vs Computational Cost", exists; its content was not retrieved. — [arXiv 2606.00881](https://arxiv.org/pdf/2606.00881)

### Inferences
- **For personal documents:**
  - Chunk by document structure (Docling or Apple Vision paragraphs, table rows, pages). Keep each table as one chunk and also as row-level records.
  - Prepend a **deterministic contextual header**: file name, doc type, issuer, date, section path, page number. This captures much of the "contextual retrieval" benefit at zero LLM cost.
  - Reserve LLM-generated context for high-value docs (contracts, medical).
- **Cost of full LLM contextualization locally (estimate, assumed speed):** 1M chunks × 75 generated tokens is ~75M tokens. At an assumed 30–60 tok/s decode on a laptop 4B model, that is weeks of compute. Do it selectively, lazily or in the background.
- **Parent-child retrieval** (retrieve small chunk, return page or section) aligns with page-level chunking's measured win and with the need for page-anchored citations.

### Gaps
- No primary 2026 study of parent-child retrieval specifically.
- No retrieval benchmark on *personal* document types (receipts, statements, lab reports). All studies use papers, finance filings or BEIR.
- Late chunking's actual gain with the 32K-context Qwen3-Embedding was not measured in sources found.

---

## 4. Retrieval stack & local vector DBs (hybrid, rerankers, embeddings, encryption at rest)

### Takeaway
The 2026 evidence strongly favors **BM25 as a first-class citizen**: hybrid BM25 + dense with RRF, then a small cross-encoder or listwise reranker. BM25 is the strongest scalable default in a 2026 scaling study, and Anthropic's gains stack BM25 + contextual embeddings + rerank.

Best permissive small models:
- Embeddings: Qwen3-Embedding-0.6B (Apache 2.0, 32K context, MRL down to 32-dim).
- Late interaction: LFM2.5-ColBERT-350M or mxbai-edge-colbert.
- Rerankers: note that jina-reranker-v3 is **non-commercial** (CC BY-NC-SA).

For storage, **SQLite + FTS5 + sqlite-vec under SQLCipher** is the simplest encrypted-at-rest single-file design. DuckDB 1.4 also has native AES-GCM encryption. LanceDB OSS does not.

### Cited Findings

**Retrieval method evidence**
- **"BM25 Wins at Scale"** (arXiv 2607.26497, Jul 2026): compares BM25, dense, graph indexing and a file-system agent across 28 nested corpus tiers spanning ~450×.
  - The agent wins at small scale but uses 39× more query tokens.
  - Around **10M corpus tokens BM25 overtakes it**, leading by ~20 points at full scale.
  - Dense is efficient but less accurate. Graph methods hit "construction walls."
  - BM25 is "the strongest scalable default." Agentic reasoning works best "after ranked discovery rather than in place of it."
  — [arXiv 2607.26497](https://arxiv.org/abs/2607.26497)
- Anthropic: BM25 adds ~14 percentage points of relative failure reduction on top of contextual embeddings (−35% → −49%). — [Anthropic](https://www.anthropic.com/news/contextual-retrieval)
- **Local 7B agentic ablation:** fixed hybrid retrieval beat adaptive routing by +1.8 EM. Rule-based routing over-chose BM25 on entity-heavy queries. — [arXiv 2606.21553](https://arxiv.org/abs/2606.21553)
- **CUBO** (arXiv 2602.03731): a self-contained RAG system for 16 GB laptops.
  - Hard 15.5 GB RAM ceiling, 10 GB corpora.
  - "Tiered hybrid retrieval," 185 ms p50 retrieval, BEIR Recall@10 of 0.48–0.97 by domain.
  - Streaming ingestion with O(1) buffer; 37k LOC, open source.
  — [arXiv 2602.03731](https://arxiv.org/abs/2602.03731)

**Embedding models (local, small)**
- **Qwen3-Embedding-0.6B:**
  - Apache 2.0, 32K context, 100+ languages, output dimension 32–1024 (MRL), instruction-aware (+1–5%).
  - MTEB multilingual 64.33; MTEB English v2 70.70. For comparison, the 4B scores 69.45 / 74.60 and the 8B 70.58 / 75.22.
  — [HF](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)
- **EmbeddingGemma-300M:**
  - Gemma license (terms acceptance), **2,048-token context**, 768-dim with MRL at 512/256/128.
  - MTEB v2 multilingual 61.15 (58.23 at 128-dim); English 69.67 (66.66 at 128-dim).
  - Q4/Q8 quantization costs only ~0.5–1.0 MTEB points.
  — [HF](https://huggingface.co/google/embeddinggemma-300m)
- **LFM2.5-Embedding-350M and LFM2.5-ColBERT-350M** (Liquid AI):
  - NanoBEIR multilingual NDCG@10 0.577 / 0.605.
  - p50 query embedding 7.3–8.2 ms on an M4 Max via llama.cpp.
  - GGUF available. License not stated in blog.
  — [Liquid AI](https://www.liquid.ai/blog/lfm2-5-retrievers)
- **mxbai-edge-colbert-v0** (17M and 32M): the 17M beats ColBERTv2 and stores up to 3× less on CPU for 32k-token docs. — [Mixedbread](https://www.mixedbread.com/blog/edge-v0); [arXiv 2510.14880](https://arxiv.org/pdf/2510.14880)
- **Multi-vector index size** [OLDER]: a 2-bit PLAID index of 760 MB drops to 260 / 195 / 131 MB with pool factors 3 / 4 / 6. — [search summary of arXiv 2409.14683](https://arxiv.org/pdf/2409.14683)

**Rerankers**
- **jina-reranker-v3:** 0.6B listwise ("last but not late"), BEIR nDCG@10 61.94 vs bge-reranker-v2-m3 56.51. **License CC BY-NC-SA 4.0 (non-commercial).** — [arXiv 2509.25085](https://arxiv.org/abs/2509.25085)
- Qwen3-Reranker-0.6B scores lower on BEIR than both bge-reranker-v2-m3 and jina-v3, per Jina's paper. — [arXiv html](https://arxiv.org/html/2509.25085v1)
- jina-reranker-v3 hit 81.33% Hit@1 at 188 ms in one comparison. [SECONDARY] — [AIMultiple](https://aimultiple.com/rerankers)
- LightRAG recommends bge-reranker-v2-m3 for local use and notes reranking "can significantly improve query quality" at 1–2 s of added latency (hardware unspecified). — [LightRAG README](https://github.com/HKUDS/LightRAG)

**Local vector stores**
- **sqlite-vec:**
  - Pure C, no dependencies; float, int8 and binary vectors in `vec0` virtual tables.
  - Latest stable v0.1.9 (2026-03-31). The project revived with v0.1.7 (2026-03-17).
  - ANN (DiskANN, experimental IVF, "rescore") exists only in the **v0.1.10-alpha** series (alpha.4 on 2026-05-18).
  — [GitHub releases](https://github.com/asg017/sqlite-vec/releases); [issue #25](https://github.com/asg017/sqlite-vec/issues/25)
  - Brute force takes 5–15 ms at 100k vectors (AVX2). 100k vectors at 1-bit take 19.2 MB.
  - Supports FTS5 + vector RRF in one SQL query. [SECONDARY] — [llms.blog](https://www.llms.blog/posts/embedded-vector-databases-in-production-comparing-lancedb-sqlite-vec-duckdb-vss-and-chroma)
- **LanceDB:**
  - Embedded Rust library; IVF-PQ index (optional IVF-HNSW).
  - Roughly 0.5–1.2 GB RAM per 1M 1536-dim vectors; disk ~0.8 GB (PQ) to 2.8 GB (raw).
  - Columnar pre-filtering. [SECONDARY] — [llms.blog](https://www.llms.blog/posts/embedded-vector-databases-in-production-comparing-lancedb-sqlite-vec-duckdb-vss-and-chroma)
  - **Encryption at rest is an Enterprise feature, not OSS embedded.** — [LanceDB Enterprise docs](https://docs.lancedb.com/enterprise)
- **DuckDB-VSS:** HNSW via usearch, ~3.5–5 GB RAM per 1M 1536-dim vectors. [SECONDARY] — [llms.blog](https://www.llms.blog/posts/embedded-vector-databases-in-production-comparing-lancedb-sqlite-vec-duckdb-vss-and-chroma)
  - **DuckDB 1.4.0 (Sept 2025) adds AES-256-GCM encryption** of the main DB, WAL and temp files, with the key passed at `ATTACH`. OpenSSL is much faster than mbedtls. — [DuckDB 1.4.0 announcement](https://duckdb.org/2025/09/16/announcing-duckdb-140.html)
- **Chroma:** HNSWlib, ~6–8 GB RAM per 1M vectors; comfortable under ~250k vectors. [SECONDARY] — [llms.blog](https://www.llms.blog/posts/embedded-vector-databases-in-production-comparing-lancedb-sqlite-vec-duckdb-vss-and-chroma)
- **Qdrant Edge:** in-process embedded engine ("like SQLite but for vector search") with hybrid and multimodal search. Announced as **private beta** 2025-07-29; 2026 GA status not confirmed. — [Qdrant blog](https://qdrant.tech/blog/qdrant-edge/)
- **SQLCipher:** 256-bit AES full-database encryption, a fork of SQLite. — [GitHub](https://github.com/sqlcipher/sqlcipher)
  - Real projects combine SQLCipher with sqlite-vec and additionally AES-256-GCM-encrypt sidecar vector files per row. — [memvara PR #235](https://github.com/memvara/memvara/pull/235)
- An official SQLite "Vec1" vector extension page exists at sqlite.org/vec1, but it returned HTTP 503. Contents unverified. — [sqlite.org/vec1](https://sqlite.org/vec1)

### Inferences
- **Scale math (estimate):**
  - A 100k-document vault might be ~1M chunks. Qwen3-Embedding-0.6B at 1024-dim float32 is ~4 GB; MRL-256 int8 is ~256 MB; binary 1024-dim is ~128 MB.
  - sqlite-vec brute force (5–15 ms per 100k) extrapolates to ~50–150 ms per 1M. That is acceptable, especially with binary prefilter + float rescore, without waiting for the alpha ANN.
- **Recommended default stack:**
  - One encrypted SQLite file (SQLCipher) holding documents, chunks, FTS5 BM25, sqlite-vec vectors, extracted-entity tables and citation anchors.
  - Hybrid RRF → rerank the top 30–50 with bge-reranker-v2-m3 (Apache) or Qwen3-Reranker-0.6B → top ~10–20 to the generator.
  - Use DuckDB (encrypted) for the analytical "structured personal data" side if SQL analytics are needed.
- Keep embedding-model choice stable. LightRAG notes switching embedders forces a full re-embed.

### Gaps
- **SPLADE / learned sparse** for local use: no 2026 source gathered. BM25 evidence may suffice.
- **HyDE / query rewriting** with small local models: no 2026 measurements gathered.
- **Time-aware retrieval** for "latest statement", "last year's taxes": no benchmark found. Handled in practice via metadata filters on extracted dates (see Q5/Q8).
- pgvector, usearch and hnswlib: no 2026 laptop-specific numbers gathered.
- Whether sqlite-vec loads cleanly into SQLCipher builds on all platforms: not documented officially. One project does it.

---

## 5. Knowledge graphs & structured extraction ("structured personal data")

### Takeaway
Full GraphRAG (Microsoft-style) is too expensive for local indexing and often doesn't beat vanilla RAG on fact lookup. Graphs help mainly on multi-hop reasoning and corpus-level summarization, by about 10–13 points.

The high-value, feasible pattern for a personal vault is **schema-driven structured extraction with source grounding**: medications, lab values over time, tax figures, contract dates and obligations go into typed SQL tables with a pointer to the exact span or page. Useful tools:
- NuExtract3 (4B, Apache 2.0).
- Google's LangExtract (local via Ollama; character-offset grounding).
- Apple DataDetection for money, dates and addresses.

Light graph methods (HippoRAG 2) are ~12× cheaper to build than GraphRAG, but still trail BM25 at large scale.

### Cited Findings
- **GraphRAG-Bench** (ICLR 2026): "GraphRAG frequently underperforms vanilla RAG on many real-world tasks." — [arXiv 2506.05690](https://arxiv.org/abs/2506.05690); [GitHub](https://github.com/GraphRAG-Bench/GraphRAG-Benchmark)
  - Reported task split: fact retrieval chunks 60.9 vs graph 60.1 (tie); complex reasoning graph 53.4 vs 42.9 (+10); contextual summarization 64.4 vs 51.3 (+13). [SECONDARY] — [VentureBeat](https://venturebeat.com/orchestration/stop-graphing-everything-when-graphrag-actually-beats-vector-rag); [Medium practitioner guide](https://medium.com/graph-praxis/graph-rag-in-2026-a-practitioners-guide-to-what-actually-works-dca4962e7517)
- **Cost spread** (Novel split, total query tokens):
  - MS-GraphRAG (global) ~331,375; LightRAG ~100,832; Fast-GraphRAG ~4,204; HippoRAG 2 ~1,008; vanilla RAG ~879.
  - Index build: HippoRAG 2 ~9.2M tokens vs GraphRAG ~115.5M (~12×).
  - At 100k docs, MS-GraphRAG construction costs ~$10,000 vs ~$100 for a compact domain-adapted engine (RAGU).
  - [SECONDARY via search] — [arXiv 2607.11683 RAGU](https://arxiv.org/pdf/2607.11683); [arXiv 2607.26497](https://arxiv.org/pdf/2607.26497)
- **HippoRAG 2:** personalized-PageRank memory; ~7% improvement on associative-memory tasks over SOTA embedding retrieval; beats standard RAG on factual, sense-making and associative tasks. — [arXiv 2502.14802](https://arxiv.org/abs/2502.14802)
  - At 155M corpus tokens, its build scores ~15 points below BM25. — [arXiv 2607.26497 via search](https://arxiv.org/pdf/2607.26497)
- **LightRAG:** extraction needs strong models. The README recommends cloud minis or a **locally deployed Qwen3-30B-A3B-Instruct**, and advises non-thinking models for extraction.
  - Supports incremental insert, selective deletion (reusing cached LLM outputs) and citations.
  - Recommends bge-m3 embeddings and bge-reranker-v2-m3 locally.
  — [LightRAG README](https://github.com/HKUDS/LightRAG)
- **NuExtract3** (2026): 4B, Apache 2.0, Qwen3.5-4B base. Scores 0.651±0.019 on NuMind's extraction benchmark, beating Gemma-4-E4B, Qwen3.5-9B and GLM-4.6V-Flash.
  - Takes text, images and multi-page PDFs (as page images) with a JSON template. 131K context; reasoning and non-reasoning modes.
  — [HF](https://huggingface.co/numind/NuExtract3)
  - NuExtract 2.0-2B is based on Qwen2-VL specifically for a commercially usable license. — [HF](https://huggingface.co/numind/NuExtract-2.0-8B)
- **LangExtract** (Google, open source): schema from few-shot examples. "Maps every extraction to its exact location in the source text", with interactive highlighting. Supports local models via Ollama. Uses chunking plus parallel multi-pass extraction for long documents. — [GitHub](https://github.com/google/langextract); [Google Developers Blog](https://developers.googleblog.com/introducing-langextract-a-gemini-powered-information-extraction-library/)
- **Apple Vision DataDetection** returns dates, money and currency, addresses and payment identifiers directly from scanned documents on-device. — [WWDC25](https://developer.apple.com/videos/play/wwdc2025/272/)
- SLMs deliver "80–90% of frontier quality on scoped tasks (classification, RAG, extraction)" but lag on open-ended multi-hop reasoning. [SECONDARY] — [FutureAGI](https://futureagi.com/blog/small-language-models-agentic-ai-2025/)

### Inferences
- The "structured personal data" feature should be an **extraction layer, not a graph layer**. Per document type (lab report, bank statement, pay stub, 1099/W-2, prescription, lease or contract, insurance EOB), run a JSON template with NuExtract3 or a 4–8B general model plus LangExtract-style span grounding. Write rows such as:
  - `lab_results(test, value, unit, ref_range, date, source_doc, page, bbox)`
  - `transactions(...)`
  - `obligations(party, action, due_date, source_span)`

  This enables exact answers to "how has my LDL changed since 2022?" via SQL, with every value clickable back to its source.
- Graph-style entity linking (the same doctor, landlord or employer across docs) can be a lightweight entity table plus co-occurrence, not full community summarization.
- LightRAG's own recommendation of a 30B-A3B model implies graph extraction on 8–16 GB machines is marginal. Schema extraction with a 4B specialist is the feasible path.

### Gaps
- No benchmark specifically on personal-document extraction (lab reports, bank statements) for small models.
- NuExtract3's benchmark is vendor-run.
- Field-level accuracy of small models on tables spanning pages (multi-page bank statements) is unknown.

---

## 6. Agentic RAG / deep research over personal docs; long context vs RAG for 4B–20B local models

### Takeaway
On local models, a **short fixed loop** captures most of the agentic gain: hybrid retrieve → (optional decompose) → rerank → at most 2 iterations. Adaptive routers and deep loops add little and cost latency.

Long context is not a substitute for retrieval on small models:
- Context rot and "lost in the middle" degrade accuracy well before advertised windows.
- Apple's on-device model reportedly has only a 4K window.

Use long context for "chat with this one document" and retrieval for the vault.

### Cited Findings
- **Dissecting Agentic RAG with a local 7B** (Qwen2.5-7B-Instruct, 5,000 HotpotQA questions):
  - Full pipeline EM 53.2 / F1 61.6 vs single-pass dense 43.1 / 54.0.
  - **Two retrieval iterations captured 95% of gains** vs five.
  - Fixed hybrid beat adaptive routing by +1.8 EM.
  - Query decomposition and cross-encoder reranking each gave "statistically significant but modest" gains.
  - "Most of the gain comes from running a short retrieval loop."
  — [arXiv 2606.21553](https://arxiv.org/abs/2606.21553)
- The file-system agent (grep/read-style) is competitive at small corpus scale but needs 39× the query tokens and loses to BM25 beyond ~10M corpus tokens. — [arXiv 2607.26497](https://arxiv.org/abs/2607.26497)
- **Tool-calling reliability:**
  - Small models "break down on long chains (6+ sequential calls)."
  - Ministral 8B BFCL overall 51.8, multi-turn 11.4.
  - [SECONDARY] — [FutureAGI](https://futureagi.com/blog/small-language-models-agentic-ai-2025/)
  - Nanbeige4.2-3B (Jul 2026) targets agentic capability at 3B; numbers not retrieved. — [arXiv 2607.22083](https://arxiv.org/pdf/2607.22083)
- **Context rot** (Chroma, 18 LLMs including GPT-4.1, Claude 4, Gemini 2.5):
  - Performance drops with input length even on simple tasks.
  - Distractors compound errors.
  - LongMemEval-focused (~300 tokens) prompts beat full (~113k tokens) prompts by large margins.
  - Claude models abstained more; GPT models answered confidently wrong.
  — [Chroma research](https://www.trychroma.com/research/context-rot)
- Open models degrade earlier: Llama 3.1 405B drops beyond ~32K tokens (Databricks study). One claim says a 35-open-model study found long-context hallucinations "triple from 32K to 128K", with every model above 10% fabrication at 200K. [SECONDARY, primary not verified] — [Wire blog](https://usewire.io/blog/long-context-vs-rag-what-the-data-shows/)
- Anthropic's threshold for Claude: under ~200K tokens, just put everything in the prompt. — [Anthropic](https://www.anthropic.com/news/contextual-retrieval)
- **Local model context windows:**
  - Gemma 4 (released 2026-04-02): E2B/E4B have 128K context and native audio; 26B-A4B MoE and 31B dense have 256K; a 12B followed 2026-06-03. — [Gemma 4 model card](https://ai.google.dev/gemma/docs/core/model_card_4); [Wikipedia](https://en.wikipedia.org/wiki/Gemma_(language_model))
  - Apple Foundation Models framework on-device model: reported 4,096-token shared input+output window, with escalation to Private Cloud Compute at 32K. [SECONDARY] — [dev.to WWDC26 summary](https://dev.to/hariharanjagan/whats-new-in-apples-foundation-models-framework-at-wwdc-2026-5227)
  - Apple's research page describes AFM 3 Core (3B dense) and AFM 3 Core Advanced (20B sparse, 1–4B active, experts paged from flash) but does not state context length. — [Apple ML Research](https://machinelearning.apple.com/research/introducing-third-generation-of-apple-foundation-models)

### Inferences
- **Default "Ask" pipeline:**
  1. Parse the query (entities, dates, doc types) → metadata filter + SQL over extracted tables.
  2. Hybrid retrieve + rerank.
  3. Generate with citations.
  4. If the answer is insufficient, do one follow-up retrieval using a model-proposed sub-query.

  Cap at 2 loops.
- **"Deep research" mode** (multi-doc reports, e.g., "summarize all my insurance claims in 2025") should run as a background job with a progress UI rather than inline chat.
- For a single long document (a 60-page contract), feed it whole to a 128K-capable local model only if it fits well under ~32K. Otherwise retrieve within the document.

### Gaps
- No 2026 multi-hop benchmark results for Gemma 4 E4B, Qwen3.5-4B/9B or gpt-oss-20b in a RAG loop.
- Primary source for the "35 open models / 172B tokens" long-context hallucination study not located.
- Apple on-device context window not confirmed from a primary Apple source.

---

## 7. Grounding & citations: sentence-level citations, verification, abstention; hallucination rates of small models

### Takeaway
Current best practice:
1. Pre-segment sources into sentences or blocks with stable IDs.
2. Have the model cite IDs (as Claude's Citations API does).
3. **Programmatically verify** that each cited span exists and supports the claim.
4. Render hover-previews that jump to the exact page or passage (NotebookLM-style).

Small open models are now fairly faithful when summarizing supplied text: 4–6% hallucination on Vectara HHEM for Qwen3-4B/8B and Gemma-3-12B. However, **prompt-only abstention fails under misleading context**: 3.8–8B models still answered 41.6% of misleading questions. Verification must be a separate step.

### Cited Findings
- **Claude Citations API:**
  - Documents are chunked into sentences.
  - Citations return `char_location` (0-indexed char range, plain text), `page_location` (1-indexed pages, PDFs) or `content_block_location` (custom chunks), each with `cited_text` and `document_index`.
  - `cited_text` does not count toward output tokens.
  — [Claude docs](https://platform.claude.com/docs/en/build-with-claude/citations)
  - Up to 15% better recall accuracy vs custom implementations. Endex cut source hallucinations "from 10% to 0%" and got 20% more references per response. — [Claude blog](https://claude.com/blog/introducing-citations-api)
- **NotebookLM:** answers carry numbered inline citations. Hover previews the quoted text; click opens the source at that passage. — [FSU help article](https://servicecenter.fsu.edu/s/article/How-do-NotebookLM-s-inline-citations-work-and-why-are-they-important); [LearnPrompting](https://learnprompting.org/blog/notebooklm-guide)
- **Vectara HHEM hallucination leaderboard** (updated 2026-09-22), grounded-summarization hallucination rate / answer rate:

  | Model | Hallucination rate | Answer rate |
  |---|---|---|
  | Phi-4 | 3.7% | **80.7%** |
  | Gemma-3-12B | 4.4% | 97.4% |
  | Qwen3-8B | 4.8% | 99.9% |
  | Mistral-Small-2501 | 5.1% | 97.9% |
  | Granite-4.0-h-small | 5.2% | 100% |
  | Qwen3-4B | 5.7% | 99.9% |
  | Gemma-3-4B | 6.4% | **67.3%** |
  | Ministral-3B | 7.3% | 99.9% |
  | gpt-oss-120b | 14.2% | 99.9% |
  | finix_s1_32b (best overall) | 1.8% | — |

  — [Vectara GitHub](https://github.com/vectara/hallucination-leaderboard)
  - Range across 105 models is 1.8%–24.2%; Phi-4-mini is 23.5%. [SECONDARY] — [CodingFleet](https://codingfleet.com/blog/ai-model-hallucination-rates-2026/)
- **FACTS Grounding** (DeepMind/Kaggle): 1,719 examples with up to 32K-token documents. — [arXiv 2501.03200](https://arxiv.org/abs/2501.03200); [Kaggle](https://www.kaggle.com/benchmarks/google/facts-grounding)
  - As of 2026-09-11, reportedly GPT-6 Astra 82.0%, **Gemma 4 26B-A4B 80.9%**, Gemma 4 31B 80.7%. [SECONDARY aggregator, not verified on Kaggle] — [llm-stats](https://llm-stats.com/benchmarks/facts-grounding)
- **Abstention under misleading context** (GRAB-RAG, arXiv 2608.22228): three frozen 3.8B–8B models.
  - Despite abstention instructions they "still answer 41.6% of misleading questions, with 63% of those answers echoing the planted wrong entity verbatim."
  - A generator-side conflict check cut this to 13.3% but discarded correct answers.
  - "Prompt-based abstention asks whether context is sufficient, not whether it is correct."
  — [arXiv 2608.22228](https://arxiv.org/abs/2608.22228)
- **LongCite:** an SFT dataset (LongCite-45k) of sentence-level citations lets 8B/9B models surpass GPT-4o on citation quality. — [arXiv 2409.02897](https://arxiv.org/abs/2409.02897) [OLDER]
  - Citation F1 72.0 for an 8B vs 65.6 for GPT-4o, not verified in the abstract. — [search snippet](https://futureagi.com/blog/evaluating-llm-citation-attribution-2026/)
- Sub-sentence citations: sentence-level citations can include irrelevant content or omit what is needed for verification. The paper proposes "concise and sufficient" sub-sentence citations. — [arXiv 2509.20859](https://arxiv.org/html/2509.20859v1)
- Citation hallucination rates of 11%–57% across commercial models and deep-research agents. [SECONDARY] — [FutureAGI](https://futureagi.com/blog/evaluating-llm-citation-attribution-2026/); related: [arXiv 2604.03173](https://arxiv.org/pdf/2604.03173), [arXiv 2605.06635](https://arxiv.org/html/2605.06635v1)

### Inferences
- **Citation pipeline for the vault:**
  1. Every chunk stores (doc_id, page, bbox or char range, sentence IDs).
  2. The generator emits `[S123]`-style IDs.
  3. A deterministic verifier checks that each cited ID was in context, and does fuzzy string matching for any quoted number or date.
  4. An optional small NLI or HHEM-style check verifies entailment per claim.
  5. Drop or flag unsupported sentences.
  6. The UI shows a hover snippet and opens the PDF at the page with the bbox highlighted.
- **Numbers must be verified.** For amounts, dates and lab values, require exact-match of the number in the cited span. This is cheap and catches the most damaging hallucinations in finance and medical documents.
- **Abstention:** prompt-only won't do. Combine a retrieval-score threshold, a "no supporting span found" rule from the verifier, and conflict detection when multiple docs disagree (e.g., two different policy numbers). Surface "I found conflicting documents" as a first-class answer.
- **Answer rate matters:** Gemma-3-4B's 67% and Phi-4's 81% answer rates show that low hallucination can come from refusing. Track both rates.

### Gaps
- How Perplexity renders or verifies citations: no source gathered.
- No published faithfulness numbers for Gemma 4 E4B or Qwen3.5 small models on Vectara (not in the extracted list).
- No open, small NLI verifier benchmark on personal-document claims found.

---

## 8. Memory systems for personal AI (Mem0, Letta, Zep/Graphiti, Supermemory, Cognee, Apple personal context)

### Takeaway
Memory-layer benchmarks (LoCoMo, LongMemEval, BEAM) are noisy and mostly self-reported. Scores range from ~49% to ~95% for the same systems depending on protocol.

The transferable patterns for a document vault are:
- Extract atomic facts with ADD/UPDATE/INVALIDATE semantics.
- Keep **bi-temporal validity** (when a fact was true vs when it was learned), e.g. current address, current medications.
- Retrieve with multiple signals (semantic + BM25 + entity).
- Keep raw sources as the ground truth. Letta's "files + simple tools" baseline was competitive.

Apple shipped Siri AI with on-device personal context over messages, email and photos (Sept 14, 2026, beta, not EU/China). That raises user expectations for "ask my stuff."

### Cited Findings
- **Mem0 paper** (arXiv 2504.19413) [OLDER]: 26% relative improvement over OpenAI Memory on LoCoMo (LLM-judge), 91% lower p95 latency and >90% token savings vs full context. The graph variant (Mem0g) is ~2% higher. — [arXiv](https://arxiv.org/abs/2504.19413)
- **Mem0 2026 self-reported:**
  - LoCoMo 92.5, LongMemEval 94.4, BEAM-1M 64.1, BEAM-10M 48.6, at ~6.7–7K tokens per query.
  - New "multi-signal retrieval" (semantic + BM25 + entity match, fused).
  - Temporal +29.6 points, multi-hop +23.1 points.
  - Open problems: temporal abstraction at scale (−25% from 1M to 10M), **memory staleness** ("outdated facts remain confidently wrong after life changes").
  — [Mem0 blog](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- **Zep/Graphiti** (arXiv 2501.13956) [OLDER]: a temporally aware knowledge graph over episodes, entities and communities. DMR 94.8% vs MemGPT 93.4%; LongMemEval accuracy up to +18.5% with 90% lower latency. — [arXiv](https://arxiv.org/abs/2501.13956)
- **Letta:** a filesystem-based agent (plain files + search tools, GPT-4o-mini) scored 74.0% on LoCoMo vs Mem0's reported 68.5% for its graph variant. Argument: "simpler tools are more likely to be in the training data… and used effectively." — [Letta blog](https://www.letta.com/blog/benchmarking-ai-agent-memory)
- **LongMemEval results and caveats:**
  - Mastra OM 94.87% (gpt-5-mini), Hindsight 91.40%, Supermemory 84.60% (self-reported), Zep 71.20% (gpt-4o), full-context 60.20%, Mem0 49% in one comparison.
  - This conflicts with Mem0's own 94.4%.
  - "Mem0's self-reported 2026 score (92.5%) and Zep's 2026 claim (94.7%) use different models and evaluation setups — not directly comparable."
  - [SECONDARY] — [dev.to comparison](https://dev.to/varun_pratapbhardwaj_b13/5-ai-agent-memory-systems-compared-mem0-zep-letta-supermemory-superlocalmemory-2026-benchmark-59p3); [Mem0 benchmark guide](https://mem0.ai/blog/ai-memory-benchmarks-in-2026)
- **Apple Siri AI** (released in beta 2026-09-14):
  - Surfaces info from "messages, emails, photos, and more."
  - Uses an on-device Spotlight index and App Toolbox, with Private Cloud Compute for server models.
  - English first; French, Japanese, Korean, Portuguese and Spanish next month; **not initially in EU or China**. Requires M1+ Macs, iPhone 15 Pro or later.
  — [Apple Newsroom](https://www.apple.com/newsroom/2026/09/siri-ai-a-profoundly-more-capable-and-personal-assistant-is-here/)
  - Developers can populate the Spotlight semantic index via `CSSearchableIndex.indexAppEntities`. [SECONDARY] — [WWDC26 App Intents](https://developer.apple.com/videos/play/wwdc2026/343/)

### Inferences
- **Memory layer for the vault:** treat extracted facts (Q5) as a "memory" with fields `valid_from`, `valid_to`, `superseded_by` and `source_span`.
  - Example: a new insurance card invalidates the old policy number.
  - Answer "current X" questions from the latest valid fact, and show history on request. This directly addresses Mem0's "memory staleness" open problem.
- User conversation memory (preferences, "my kid's name is…") should be a small separate store. It must never be cited as if it were a document.
- **Apple integration opportunity (speculative):** exposing vault entities to the Spotlight semantic index would let Siri AI surface them. This conflicts with an "encrypted private vault" posture, so it would need to be opt-in, per-collection.

### Gaps
- No primary data found on Cognee or Supermemory architecture or benchmarks beyond self-reported LongMemEval 84.6%.
- Apple's exact personal-context scope for arbitrary files and PDFs in Siri AI is not stated.
- No independent, protocol-controlled memory benchmark was found.

---

## 9. Evaluation: how to benchmark a local RAG app, and what consumers perceive

### Takeaway
Use a three-layer evaluation:
1. **Retrieval:** BEIR-style Recall@k and nDCG on a custom golden set drawn from representative personal documents, plus ViDoRe-style visual pages.
2. **Generation:** RAGAS-style faithfulness, context precision/recall and answer correctness, with a *strong* judge offline and a small judge only for CI. ARES-style prediction-powered inference makes a few hundred human labels statistically useful.
3. **Parsing:** OmniDocBench or olmOCR-bench-style unit tests on your own degraded scans. PureDocBench shows clean-benchmark scores overstate real-world accuracy by about 12 points.

### Cited Findings
- **RAGAS:** faithfulness, answer relevance, context precision and context recall. Separates retriever failures from generator failures. Can run judges locally via Ollama, but "using a weak judge model produces noisy metrics… judge must be at least as capable as the system being evaluated." Use a small judge for CI and a stronger judge for periodic audits. [SECONDARY] — [QASkills](https://qaskills.sh/blog/ragas-faithfulness-answer-relevancy-context-precision-recall-reference-2026); [FutureAGI](https://futureagi.com/blog/rag-evaluation-metrics-2025/)
- **ARES** (NAACL 2024) [OLDER]: context relevance, answer faithfulness and answer relevance, using lightweight judges fine-tuned on synthetic data plus prediction-powered inference with "a small set of human-annotated datapoints". Robust to domain shift. — [arXiv 2311.09476](https://arxiv.org/abs/2311.09476)
- **Laptop RAG evaluation example:** CUBO reports BEIR Recall@10 0.48–0.97 across domains and 185 ms p50 under a 16 GB RAM budget. — [arXiv 2602.03731](https://arxiv.org/abs/2602.03731)
- **Parsing evaluation:**
  - PureDocBench: clean vs digital vs real captures; −11.61 points on real. — [arXiv 2605.07492](https://arxiv.org/abs/2605.07492)
  - olmOCR-bench uses 7,010 binary unit tests (text presence, reading order, table cells). — [olmocr bench](https://github.com/allenai/olmocr/tree/main/olmocr/bench)
- **Multimodal RAG evaluation:** ViDoRe V3 (3,099 human-verified queries, commercially permissive license). — [arXiv 2601.08620](https://arxiv.org/abs/2601.08620); MiRAGE — [arXiv 2510.24870](https://arxiv.org/pdf/2510.24870)
- **Grounding evaluation:**
  - Vectara HHEM (open model) for hallucination rate. — [Vectara](https://github.com/vectara/hallucination-leaderboard)
  - FACTS Grounding for long-form grounding. — [arXiv 2501.03200](https://arxiv.org/abs/2501.03200)
- **Chunking evaluation lesson:** retrieval recall and end-to-end accuracy can rank strategies oppositely. Semantic chunking was 91.9% recall-best in one study but 54% vs 69% on answers in another. — [PremAI summary](https://www.premai.io/blog/rag-chunking-strategies-the-2026-benchmark-guide/)

### Inferences
- **Golden set design:** 200–500 questions across doc types (receipts, statements, lab reports, contracts, emails, audio notes). Tag each by type:
  - lookup ("what was my deductible?")
  - aggregation ("total medical spend 2025")
  - temporal ("latest A1C")
  - multi-doc
  - unanswerable
  - misleading or conflicting

  Label gold doc, page and span so citation *precision* (was the cited span correct?) can be scored, not just answer text.
- **Consumer-perceived metrics (proposed, not sourced):**
  - Answer correctness on the user's own documents.
  - Citation click-through leading to the exact highlighted spot.
  - Time to first token and to full answer (<2–3 s retrieval + streaming).
  - Graceful "I couldn't find that" instead of wrong answers.
  - Time until newly dropped files are searchable.
  - Battery and fan impact during indexing.

### Gaps
- No published study found on which RAG quality metrics consumers actually perceive or value. The metric list above is inference.
- No public golden dataset of synthetic *personal* documents (bank statements, lab reports) was found. It would need to be built.

---

## 10. Incremental indexing at 10k–100k documents on a laptop (watchers, dedup, change detection, battery)

### Takeaway
The established pattern:
- Content-hash-based change detection.
- A per-file lineage graph so only changed chunks are re-parsed and re-embedded, and stale chunks are deleted.
- Memoization keyed on (input hash, pipeline version).
- A streaming, memory-bounded ingestion queue.

CocoIndex and LightRAG implement versions of this, and CUBO shows it fits in 16 GB. Battery- and thermal-aware scheduling is an engineering choice with no published benchmarks.

### Cited Findings
- **CocoIndex:**
  1. A source detects changes via filesystem watcher, S3 event or polling.
  2. The engine computes which chunks depend on the changed document.
  3. It recomputes only affected chunks and embeddings, reusing cached results.
  4. It deletes stale entries via lineage tracking.

  Memoization is keyed on hash(input) + hash(code), so changing a transformation invalidates exactly the right portion of the index. — [CocoIndex blog](https://cocoindex.io/blogs/incremental-processing/); [DEV review](https://dev.to/andrew-ooo/cocoindex-review-incremental-rag-engine-for-ai-agents-248b)
- **LightRAG:** incremental insert and selective deletion, with deletion reusing cached LLM extraction outputs to rebuild affected entities. Changing the embedding model requires re-embedding everything, "a process currently lacking automated tooling." — [LightRAG README](https://github.com/HKUDS/LightRAG)
- **CUBO:** streaming ingestion with O(1) buffer overhead under a 15.5 GB RAM ceiling for 10 GB corpora on a 16 GB laptop. — [arXiv 2602.03731](https://arxiv.org/abs/2602.03731)
- **Throughput anchors for a cost model:**
  - Text-layer parsing at 23.7 pg/s on CPU (Marker 2, OCR disabled); LiteParse at 1,721 pg/s but poor layout. — [Lumien](https://lumienai.com/news/marker-2-vs-mineru-docling-liteparse-olmocr-bench-benchmark)
  - Granite-Docling MLX at 200–300 tok/s. — [HF](https://huggingface.co/ibm-granite/granite-docling-258M-mlx)
  - LFM2.5 query embedding at ~7–8 ms on an M4 Max. — [Liquid AI](https://www.liquid.ai/blog/lfm2-5-retrievers)
  - Parakeet ASR at ~60× realtime on Apple Silicon. [SECONDARY] — [OpenWhispr](https://openwhispr.com/blog/parakeet-vs-whisper-vs-nemotron)

### Inferences
- **Suggested indexing design:**
  1. Watch folders with OS watchers (FSEvents / ReadDirectoryChangesW / inotify), plus a periodic reconciliation scan.
  2. Key files by SHA-256 of content to dedupe copies and renames. Also near-duplicate detection (e.g., MinHash on text) for re-downloaded statements.
  3. Store per-file status (parsed / ocr / embedded / extracted), with `pipeline_version` so upgrades re-process lazily.
  4. **Stage work by cost:**
     - Stage A (seconds): text layer + BM25 → searchable immediately.
     - Stage B (minutes): embeddings.
     - Stage C (hours, background): VLM OCR for hard pages, LLM contextual headers, structured extraction, optional visual index.
  5. Run heavy stages only on AC power / when idle / below thermal thresholds. Show "N documents still being understood" in the UI.
- **Time estimate for 100k docs (rough):** text-layer parse is under ~1–2 h at ~20 pg/s for born-digital pages. Full VLM OCR of scanned pages and LLM extraction are the long tail: days, not hours. Progressive availability is essential.

### Gaps
- No published measurements of battery drain or thermals for local indexing workloads on laptops.
- No benchmark of near-duplicate detection strategies for personal documents.
- OS file-watcher reliability at 100k+ files (FSEvents coalescing, Windows buffer overflows) was not researched in sources gathered.

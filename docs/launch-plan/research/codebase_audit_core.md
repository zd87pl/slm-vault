# Enclave (slm-vault) Core Engine Audit — state of the non-GUI code as of 2026-09-29

Scope: everything outside `advanced_vault/gui/` (a separate agent covers GUI, UX and packaging). The GUI is mentioned only where the engine's data flow runs through it.
Method: I read the code, ran the tests and lint, and ran the product end to end on Linux x86_64 with Python 3.11.15 at commit `40b6d50`, branch `claude/wizardly-cori-ezq020`. I modified no tracked files. All scratch work is in the session scratchpad.

Evidence markers:
- **[RUN]**: I executed it and saw the result.
- **[READ]**: I verified it by reading the code.
- **[DOC]**: it is only claimed in docs.

Sources are given as `path:line` instead of URLs, per the assignment.

---

## Q1. What is the actual end-to-end data flow for "drop a document → ask a question → get a cited answer" (GUI/CLI path and MCP path)?

### Takeaway
There are two separate RAG stacks that don't share data.
- **GUI/CLI path.** It goes through the `PrivateModelManager` "profile" code: a per-profile encrypted SQLite index and a per-profile key file. Ingest and retrieval work (verified).
- **MCP path (`agent_query`).** It reads a different index, `$VAULT_PATH/rag.db`, which the product's own ingest paths never write to.

Result: documents added in the GUI or CLI are invisible to Claude/Cursor over MCP (verified). Citations are document-name lists attached after retrieval. They are not grounded inline citations, and there are no page numbers.

### Cited Findings

**GUI/CLI path (works)**
1. **Entry.** The GUI calls `session.ingest_paths()` or `session.add_document()` (`advanced_vault/gui/vault_app.py:900-957`, `:5603-5614`). The CLI calls `enclave model ingest <profile> <paths>` (`advanced_vault/cli/main.py:529-557`). [READ]
2. **Parser.** `PrivateModelSession._read_file_content` (`advanced_vault/private_models/manager.py:749-757`) routes as follows. [READ]
   - PDF goes to `extract_pdf_text` (pypdf first, LiteParse fallback when text quality is poor; `advanced_vault/parsing/document_parser.py:71-138`).
   - CSV is flattened to comma-joined lines.
   - Everything else is read as UTF-8 text.
3. **Supported types.** Only the 23 extensions in `SUPPORTED_EXTENSIONS` (`manager.py:48-71`): txt/md/pdf/csv/html/json plus source-code types.
   - There is **no .docx, .xlsx, .pptx, .eml, images/OCR-only files or .epub**. [READ]
   - A `.docx` in an ingested folder is silently dropped: it is counted in neither `added` nor `skipped`. [RUN: 2 added / 0 skipped, `notes.docx` absent]
4. **Chunker.** A recursive character splitter (`advanced_vault/training/rag_index.py:368-519`).
   - Chunk size is 450 "tokens" × 4 = 1,800 chars with 200-char overlap (`rag_index.py:40-41, 185-186`).
   - Separators run from paragraph down to space (`rag_index.py:46`).
   - Chunk metadata is always `{}` (`rag_index.py:600`), so page numbers and headings are never kept.
5. **Embedder.** `EmbeddingEngine`, using sentence-transformers `intfloat/e5-small-v2`, 384-dim, with "query:"/"passage:" prefixes (`advanced_vault/training/embeddings.py:39, 353-354, 457-458`). [READ]
   - It fell back to CPU in my run.
   - It loads online: I counted about 30 HF Hub HEAD/GET requests per model load. There is no `HF_HUB_OFFLINE` or `local_files_only` on the embedder (grep found `local_files_only` only in `gui/local_inference.py:345,356`). [RUN]
6. **Index.** An SQLite `documents`/`chunks` store with ChaCha20-Poly1305-encrypted text, plus a vector index (`rag_index.py:314-366`).
   - The vector index is hnswlib when installed. Otherwise it is a brute-force JSON index (`advanced_vault/training/vector_index.py:402-429`).
   - hnswlib is only in the `mac-performance` extra (`pyproject.toml:103-108`), so a Linux/Windows base install uses brute force. [RUN: "hnswlib not available, falling back to brute-force"]
   - `stats()` still reports `hnsw_enabled: True` in that case. [RUN]
7. **Retriever.** Pure dense cosine top-k (`rag_index.py:656-687`). There is no BM25, no reranker and no query rewriting. [READ]
   - The threshold is 0.25–0.3 (`manager.py:451-453`; `advanced_vault/mcp_server/agent.py:30-32`). With e5 that is effectively no filter: irrelevant docs scored 0.72–0.79 and were returned. [RUN: `insurance.md` returned at 0.793 for "How much is the security deposit?"]
8. **Prompt.** `_compose_context` puts `[Document: <name>]\n<chunk>` blocks together, up to 12,000 chars (`manager.py:645-659`). `_build_prompt` then builds one flat string (`manager.py:661-684`): profile system prompt + "Keep citations to document names only" + last 6 Q/A turns + context + question. [READ]
9. **LLM.** `LocalInferenceEngine` or `MultiAdapterEngine` from `advanced_vault/gui/*` (`manager.py:24-45, 580-627`). The core depends on the GUI package here. [READ]
10. **Output.** `{"answer", "sources":[{document_name, document_id, score, excerpt≤180 chars}]}` (`manager.py:524-529, 759-768`). [READ]
    - "Citations" means the retrieval list plus whatever the model writes. There is no chunk-ID or page citation, and no check that the answer is supported.
11. **Live run on Linux** (torch backend, TinyLlama-1.1B-Chat): `enclave model chat home "When does the boiler warranty expire?"` retrieved the right doc (score 0.933). The model returned a rambling regurgitation of the prompt and never stated the date in the document ("12 March 2031"). [RUN]

**MCP path (broken integration)**
1. **Transport and startup.** `enclave-mcp` runs `create_vault_server(os.environ["VAULT_PATH"] or "~/.vault")` over **stdio** (`advanced_vault/mcp_server/server.py:1593-1610`). [READ]
2. **Handler.** `agent_query`/`query_knowledge` goes to `LocalAgent.query` (`server.py:1101-1154`). That uses `RAGIndex(db_path=vault_path/"rag.db")` with key `vault_path/"master.key"` (`agent.py:92-125`). [READ]
3. **Nothing writes that index.** Grep found no non-test caller of `LocalAgent.add_document`. GUI and CLI ingest go to `~/.vault/private_models/<profile>/vault/rag.db` with a separate `master.key` (`manager.py:301-319`). [READ]
4. **Reproduced.** After `enclave model ingest home docs/`, `LocalAgent(vault_path=same).list_documents()` returned `[]`. `query()` then answered a generic hallucinated boiler-warranty text with `sources: []`. [RUN]
   - The files on disk: `vault/rag.db` + `vault/master.key` versus `vault/private_models/home/vault/{rag.db,master.key}`.
5. **Wrong model name reported.** `model_used` said `mlx-community/Qwen2.5-1.5B-Instruct-4bit` even though TinyLlama ran on torch. `agent.py:241` always reports `MLX_MODEL_NAME`. [RUN+READ]
6. **Double chat template.** `LocalAgent.query` applies the tokenizer chat template itself (`agent.py:266-285`). It then calls `engine.generate()`, which wraps the already-templated string as a user message and templates it again (`advanced_vault/gui/local_inference.py:588-625, 659-662`). [READ]
7. **Context has no document names.** The MCP prompt passes only raw chunk text, with no document names (`agent.py:207-220`). Yet it tells the model to "cite which documents the information comes from" (`agent.py:244-248`).
8. **What the MCP caller sees.** Only a "Sources consulted: • name (relevance: score)" footer (`server.py:1134-1138`). [READ]
9. **The GUI chat also has a fallback chain** (`vault_app.py:6414-6500`): Private Model profile → legacy `LocalAgent` → base model with no context → opt-in cloud adapter inference (sends `encryption_key_hex` to the training manager). [READ]

### Inferences
- The "drop a PDF in the app, then ask Claude about it" promise is broken in two independent ways:
  - the index split (Q1 MCP path), and
  - mcp 2.x incompatibility (Q6).
  The CLI's own success message after `enclave mcp install` ("Restart Claude and ask it about your documents", `cli/main.py:1580-1582`) cannot currently come true.
- Answer quality off Apple Silicon is unusable, based on one run with TinyLlama. On Apple Silicon the default is Qwen2.5-1.5B-Instruct-4bit (`local_inference.py:147-155`). That is small for grounded QA, but I could not verify it here.

### Gaps
- No Apple Silicon hardware was available, so the MLX path (Qwen2.5-1.5B 4-bit), MLX adapter hot-swap and MLX answer quality are unverified.
- The LiteParse/OCR path was not exercised (needs npx/network).

---

## Q2. Which RAG techniques are implemented vs claimed (hybrid/BM25, rerankers, late chunking, contextual retrieval, KV cache)?

### Takeaway
What runs is basic naive RAG: recursive char chunking, e5-small dense retrieval, top-k, and prompt stuffing. The embedding cache is also real.

"Late chunking", "KV cache/TurboRAG", "FastEmbed/ONNX" and "HNSW 10-30x" are either unused modules or optional extras. There is no hybrid/BM25, no reranker, no contextual retrieval, no evaluation set and no retrieval-quality test.

### Cited Findings
- **Nothing hybrid in the code.** Grep for `bm25|rerank|cross-encoder|fts5|rrf|contextual retrieval|hyde|mmr` over `advanced_vault/` returned no matches. [READ]
- **Late chunking is dead code.**
  - `late_chunking.py` is imported only by `training/__init__.py:18`. No production code calls `LateChunker`/`create_late_chunker` (grep). [READ]
  - `LateChunker` just mean-pools caller-supplied token embeddings, and nothing supplies them (`late_chunking.py:90-157`).
  - `JinaLateChunker` POSTs document text to `https://api.jina.ai/v1/embeddings` (`late_chunking.py:262-281`). That is a cloud egress path inside a "private" product, though unused.
- **KV cache is dead code.** `kv_cache.py` (`RAGCache`/`QueryCache`/`ChunkKVCache`) has no production callers (grep). [READ]
  - `QueryCache` would store the query and generated response in plaintext SQLite (`kv_cache.py:70-90, 141-168`).
  - `ChunkKVCache` stores numpy arrays and never touches the LLM's actual KV cache.
- **FastEmbed/ONNX is dead code.** `FastEmbeddingEngine` (`embeddings.py:614-700`) is only exported. `export_onnx` (`embeddings.py:547-592`) is never called. [READ]
- **Embedding cache is real.** A two-level cache (in-memory plus `~/.enclave/embedding_cache.db`) keyed by a 16-hex-char SHA-256 prefix of chunk text (`embeddings.py:53-213, 320-322`). [READ]
- **HNSW** (`vector_index.py:62-315`, `M`/`ef` parameters) is real when hnswlib is installed.
  - `max_elements` is fixed at 100,000 (`rag_index.py:258-262`). `_resize` exists (`vector_index.py:228`).
  - Re-adding a document with an identical hash deletes old chunk rows but not their HNSW vectors (`rag_index.py:563-570` vs `:633-639`), leaving orphan vectors. [READ]
- **The metadata filter does nothing.** Search filters on *chunk* metadata (`rag_index.py:733-742`), but chunks are always stored with `{}` (`rag_index.py:600`). Any non-empty filter drops every result. [READ]
- **Chunk size.** The 1,800-char chunks can exceed e5-small's 512-token window for dense text, which means silent truncation. That is an inference from the parameters (`rag_index.py:40, 185`).
- **README claims vs reality** [DOC]:
  - "HNSW Index: 10-30x faster" and "E5-small Embeddings: +15% retrieval quality vs MiniLM" (`README.md:94-95`) are not measured in-repo.
  - The comment "E5-small has 100% top-5 accuracy vs MiniLM's 56%" cites a blog (`embeddings.py:37-38`).
- **No eval, only mocks.** No retrieval or answer evaluation harness exists. The "E2E" tests mock both RAG and LLM (`tests/test_e2e_flow.py`: 16 Mock/patch uses across 6 tests; `mcp_server/tests/test_agent.py`: 55 across 13 tests). [READ]

### Inferences
- For a consumer doc vault, the gaps that matter most, in order:
  1. no keyword/hybrid search (IDs, names and numbers like "ZX-99812" need lexical matching),
  2. no reranker,
  3. no page/section-aware chunking or citations,
  4. no .docx/email support,
  5. no eval harness.
- The dead RAG "accelerator" modules (late_chunking, kv_cache, FastEmbed) add surface and imply features that don't exist. Delete them rather than finish them.

### Gaps
- I did not run a retrieval benchmark. Quality claims beyond the 4-query smoke test are unmeasured.

---

## Q3. Which local LLM runtimes and default models are supported, and is there cross-platform inference?

### Takeaway
There are two backends, both inside the GUI package:
- **mlx-lm** (Apple Silicon), default Qwen2.5-1.5B-Instruct-4bit with a 6-model fallback list;
- **HF transformers/torch**, hard-coded to TinyLlama-1.1B-Chat for everything else.

There is no Ollama, llama.cpp or GGUF path for chat. Ollama appears only for vision-OCR PDF extraction and QA generation in the GUI. Linux, Windows and Intel-Mac inference technically runs but produces unusable answers (verified on Linux).

### Cited Findings
- **Backends.** `LocalInferenceEngine` picks MLX if `mlx`/`mlx_lm` import succeeds. Otherwise it uses torch, and raises if neither is present (`advanced_vault/gui/local_inference.py:97-131, 224-258`). [READ]
- **MLX candidates** (`local_inference.py:147-155`), in order: Qwen2.5-1.5B-Instruct-4bit, Qwen3-0.6B-4bit, Phi-4-mini-instruct-4bit, Llama-3.2-1B-Instruct-4bit, SmolLM3-3B-Instruct-4bit, TinyLlama-1.1B-Chat-8bit. [READ]
- **Torch model.** `MODEL_NAME = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"` (`local_inference.py:142`), loaded fp32 on CPU or fp16 on CUDA (`:336-356`). [READ]
  - Verified on Linux: it silently downloaded about 2.2 GB into `~/.cache` on the first MCP query, and the answers were poor. [RUN]
- **No other runtime.**
  - Grep for `ollama|11434|llama_cpp|gguf` in non-GUI code found nothing.
  - Ollama is used only by `gui/pdf_processor.py:242-256` (default `llama3.2-vision:11b` for OCR) and `gui/ollama_setup.py`/`gui/qa_generator.py`. [READ]
- **Temperature ignored on newer mlx-lm.** MLX generation passes `temperature=`. If newer mlx-lm raises `TypeError`, it retries without temperature (`local_inference.py:630-650`), so the setting is silently dropped. [READ]
- **Layering violation.** The core engine imports inference from the GUI package: `mcp_server/agent.py:131` and `private_models/manager.py:28-45` import `advanced_vault.gui.local_inference` / `gui.multi_adapter_engine`. [READ]
- **Doctor messaging.** `enclave doctor` on Linux says "MLX local inference is Apple Silicon only; RAG/vault features still work", then "Ready to go". [RUN]
- **README vs reality.** README advertises "Native macOS/Windows/Linux application" and "Windows, or Linux" support (`README.md:89, 311`). [DOC]
  - On Windows, MCP consent always returns DENY or None (`advanced_vault/mcp_server/consent.py:330-345`), so every consented MCP tool is denied there. [READ]

### Inferences
- A cross-platform v1 needs one runtime abstraction with llama.cpp (GGUF) and/or an Ollama client as the non-Mac default, plus a modern 3–8B instruct model. Keep MLX as the Apple Silicon fast path. Move the inference engine out of `gui/` into the core.
- The two-runtime split also forces the fine-tuning/adapter stack to be MLX-only (Q4).

### Gaps
- MLX quality and latency on real Apple Silicon (M1–M4) is untested here.
- Windows was not tested.

---

## Q4. Is fine-tuning/adapters (DoRA, DPO, GRPO, QAT, WDVA) a realistic consumer feature or a research detour? How coupled is it to the core?

### Takeaway
It is a research detour for v1. It is MLX-only and wraps internal mlx-lm / mlx-lm-lora APIs that break easily across versions. Training data is synthetic (generated QA plus synthetic "rejected" answers). There is no evaluation showing adapters beat RAG.

It is coupled to the core at import level and in the chat path (adapter engine selection, keyword weight boosting). It should be quarantined into an optional "lab" plugin.

### Cited Findings
- **`mlx_trainer.py`.** Imports `mlx_lm.tuner.trainer`, `mlx_lm.tuner.datasets`, `mlx_lm.tuner.utils` at runtime (`advanced_vault/training/mlx_trainer.py:242-245`). Default model is Qwen2.5-1.5B-Instruct-4bit with DoRA on (`:21-34`). [READ]
- **`mlx_lora_backend.py`.** Imports `mlx_lm_lora.train`, `trainer.sft_trainer`, `trainer.dpo_trainer`, etc. (`advanced_vault/training/mlx_lora_backend.py:316-460`). It exposes sft/dpo/cpo/orpo/grpo modes and QAT flags (`:20-30, 73-78`). [READ]
- **DPO "rejected" answers** come from heuristic `REJECTION_STRATEGIES` picked with `random.choice` (`advanced_vault/training/document_dpo_pipeline.py:108, 141-169`). [READ]
- **GRPO rewards** are regex/heuristic scorers: citation, conciseness, format, groundedness, completeness (`advanced_vault/training/grpo_rewards.py:48-300`). [READ]
- **Coupling.**
  - `private_models/manager.py:17` imports `MLXTrainer` at module top. `training/__init__.py:14-34` eagerly imports every training module alongside `RAGIndex`.
  - `PrivateModelSession._ensure_engine` switches to `MultiAdapterEngine` whenever a profile has adapters (`manager.py:588-612`), and `ask()` keyword-boosts adapter weights on every query (`manager.py:501-507, 691-735`). [READ]
- **Two incompatible packaging formats** exist for encrypted adapters: `private_models/adapter_packaging.py` (random key file plus HKDF) and `training/adapter_packager.py` (password → a **single unsalted SHA-256** → HKDF, `adapter_packager.py:207, 329`). There is also HKDF decryption code in `gui/local_inference.py:406`, `gui/multi_adapter_engine.py:340-358` and `gui/mlx_dora_inference.py:271-272`. [READ]
- **Tests.** 6 `mlx_lora_backend` tests and about 15 MLX tests skip off-Mac. Coverage: `mlx_trainer.py` 26%, `mlx_lora_backend.py` 33% (coverage run below). [RUN]
- **Privacy caveat.** README markets sharing trained adapters as "not your raw documents … What's NOT included: Your raw documents, filenames, or personal data" (`README.md:226, 245`). [DOC]
  - Fine-tuned adapters can memorize training text. No memorization or DP safeguards exist in code (grep found no differential-privacy code in `advanced_vault/`). [READ; memorization risk is inference]

### Inferences
- For consumers, fine-tuning a 1.5B model on synthetic QA rarely beats good retrieval plus a stronger base model. It also adds minutes to hours of on-device training, MLX lock-in, version fragility and a data-leak vector through shared adapters.
- Recommend moving `training/{mlx_trainer, mlx_lora_backend, document_dpo_pipeline, grpo_rewards, adapter_packager}`, `private_models/adapter_packaging.py`, `prosumer/adapter_*` and the GUI adapter engines into an optional `enclave-lab` extra or separate repo. Revisit only after RAG plus eval is solid.

### Gaps
- No evidence either way on adapter quality, since there is no eval harness. Training was not executed (no Apple Silicon).

---

## Q5. Cryptography and security: key derivation, key storage, AEAD/nonce use, plaintext leakage, key-zeroing, spec vs code, and the top real risks

### Takeaway
The AEAD usage itself is sound: ChaCha20-Poly1305 via `cryptography`, 96-bit random nonces, AAD bound to row IDs. But the system has **no user secret**:
- A random 32-byte master key is written in plaintext next to the database, in at least 5 duplicated code paths.
- There is no passphrase or KDF, and no OS keychain.

Filenames, full paths, content hashes, folder metadata, embeddings, the embedding cache, query logs and audit logs are all plaintext on disk. "Key zeroing" is ineffective in Python. The crypto spec doc describes a different, mostly nonexistent system.

The most severe live issue is a **shell-command injection in the Linux consent dialog that runs before consent** (verified).

### Cited Findings

**Key management**
- **Five duplicate "load or create" key paths.** Each writes `os.urandom(32)` to a plain `master.key` file, then `chmod 0600` afterwards. The file is created with the default umask first. [READ]
  - `advanced_vault/cli/main.py:35-47`
  - `advanced_vault/gui/vault_app.py:6904-6914`
  - `advanced_vault/mcp_server/server.py:100-113`
  - `advanced_vault/mcp_server/agent.py:92-110`
  - `advanced_vault/private_models/manager.py:304-314`
- **No KDF or keychain for the vault key.** Grep found `keyring|Keychain|Argon2|scrypt` absent. PBKDF2 appears only for GUI folder-lock hashes (`gui/folder_manager.py:64, 219`, which also uses a non-constant-time `==` compare at `:221`). [READ]
- **Key next to data.** Verified on disk: `pm/test/vault/master.key` (0600) sits beside `rag.db` (0644), `rag.brute.json` (0644) and `~/.enclave/embedding_cache.db` (0644). [RUN]
  - At-rest encryption therefore protects only against someone who copies `rag.db` without the sibling key file. It gives nothing against malware running as the user, a backup or sync of the folder, or a stolen unlocked disk.
- **Windows.** `os.chmod(…, 0o600)` is effectively a no-op on Windows (inference).

**AEAD usage (sound)**
- `ChaCha20Poly1305` (IETF, 12-byte nonce) with `os.urandom(12)` per encryption. [READ]
  - AAD = doc_id / chunk_id (`advanced_vault/training/rag_index.py:212-251, 570, 615`).
  - In the KV store, AAD = service name only (`advanced_vault/encrypted_kv/storage.py:150-160`), so ciphertexts can be swapped between entries of the same service. Minor.
- Random 96-bit nonces are safe at consumer volumes (inference: far below 2^32 messages per key).

**Plaintext leakage**, verified by inspecting files after ingest [RUN]:
- `documents.name`, `source_path` (absolute path), `content_hash` (unsalted SHA-256 of full plaintext) and `metadata` (`{"folder": "/abs/path"}`) are stored in clear (`rag_index.py:327-339, 583-585`). The unsalted hash allows confirmation attacks ("does this vault contain file X?").
- Embeddings are stored in clear:
  - in the `chunks.embedding` BLOB (`rag_index.py:627`),
  - in HNSW `.hnsw` plus `.meta.json` or in `.brute.json` (`vector_index.py:234-262, 362-376`),
  - in the global `~/.enclave/embedding_cache.db` together with 64-bit text-hash prefixes (`embeddings.py:61-95, 320-322`).
  - Text-embedding inversion attacks (e.g., vec2text-style) can partially reconstruct text from sentence embeddings (inference from the literature, not tested here).
- **Deleted content persists.** After `delete_document` on all docs, `embedding_cache.db` still held all rows (2 before, 2 after). Deleted documents' embeddings persist indefinitely. [RUN]
- **Logs.**
  - `activity.jsonl` stores the external agent's query previews in plaintext (`advanced_vault/mcp_server/activity_logger.py:69-106`).
  - On a policy deny, the MCP server writes the **full tool arguments**, for example the secret `content` of `vault_store`, into the audit DB (`server.py:653-662`).
- **KV store.** `service`, `tags`, `description` and `folder` are plaintext by design (`encrypted_kv/storage.py:72-87`).

**Key zeroing**
- `RAGIndex` and `EncryptedKVStore` copy the key into a `bytearray` and zero it on `close()` (`rag_index.py:177-179, 1136-1140`; `storage.py:58-60`). [READ]
- This is ineffective:
  - `bytes(self._master_key)` makes an immutable copy that is handed to the cipher object.
  - The caller's original `bytes` stays alive in `HybridVault.master_key` (`core/hybrid_vault.py:65`), `LocalAgent._master_key` (`agent.py:86-88`), `VaultMCPServer._master_key` (`server.py:104`) and the CLI/GUI objects.
- README's "Key zeroing: Encryption keys securely wiped from memory after use" (`README.md:279`) is therefore not true in practice. [READ vs DOC]

**Spec vs code** (`docs/architecture/CRYPTOGRAPHIC_SPECS.md`) [DOC]
- The spec says **XChaCha20-Poly1305 with 24-byte nonces** (`:11-18`). Its own sample passes a 24-byte nonce to `ChaCha20Poly1305` (`:22-45`), which raises in `cryptography`. The code uses IETF ChaCha20-Poly1305 with 12-byte nonces.
- It describes things that don't exist in `advanced_vault/`: an HKDF key hierarchy (user/audit/admin/consent keys, `:59-72`), HSM, Intel SGX / ARM TrustZone (`:132-210`), "cryptographic right-to-be-forgotten" with deletion proofs (`:212-255`), ZK proofs (`:257`), homomorphic encryption (`:286`) and constant-time/side-channel mitigations (`:312-354`).
- README's "ChaCha20-Poly1305 encryption for all data at rest" (`README.md:85, 275`) is contradicted by the plaintext findings above.

**Top 5 real risks** (verified unless noted)
1. **Pre-consent shell-command injection on Linux (MCP), critical.**
   - `_show_notification` builds a `bash -c` script with the caller-controlled query preview inside double quotes. It strips `"` and `\` but not `$(…)` or backticks (`consent.py:255-262, 301-316`).
   - It runs *before* the user decides, and even when zenity is absent.
   - Reproduced: calling it with the preview `What is my $(touch PWNED) key?` created the file `PWNED`, and the decision still came back DENY. [RUN]
   - Reachable through any allowed tool whose argument lands in the preview, e.g. `agent_query`'s `question[:50]` or `vault_recall`'s `query` (`server.py:588-606, 671-675`).
   - Because the arguments are LLM-generated, a prompt-injected web page or document can turn into RCE.
2. **No user secret; key stored beside data** (see above).
3. **Raw-data exfiltration paths contradict "they never see your documents."**
   - `vault_recall` returns raw KV plaintext, including secrets and "knowledge" notes. It uses loose keyword overlap: any query word matching a service name returns that secret (`core/hybrid_vault.py:334-356`; `server.py:840-865`).
   - Reproduced: for an "unknown" client after consent, `vault_recall("tell me about stripe")` returned `sk_live_REALSECRET123`. [RUN]
   - `sheriff_read` returns up to 20k chars of arbitrary files (`server.py:1312-1340`), but the default runtime policy denies the `security` module to all MCP identities (`enclave_control/config.py`, DEFAULT_POLICY_TOML; reproduced as "Agent 'unknown' is not allowed to use module 'security'"). [RUN]
   - The local LLM can quote chunks verbatim. There is no output redaction or filter (`agent.py:281-287`).
4. **Consent model is weak.**
   - Identity is a heuristic on env vars or the parent-process name, collapsing to `"unknown"` (`consent.py:189-238`).
   - "Always Allow" sets per-app `auto_approve` for **all** tools with no expiry (`consent.py:373-378, 416-423`).
   - The granular `AgentPermission` model (scope, allowed/denied tools, `expires_at`, `max_queries_per_hour`) and `check_permission()` exist (`consent.py:39-134, 562-603`) but are **never called**. Grep found only a GUI display at `vault_app.py:10633-10646`.
   - So time-limited access shown in the GUI never expires.
   - Mitigation that does work: the shared `EnclaveRuntime.evaluate_action` allow-list runs first (`server.py:644-669`; `enclave_control/runtime.py:92-109`). By default `claude-desktop`/`cursor` get only `agent_*`, `query_knowledge`, `agent_status` and 4 mock-wallet tools. `default`/`unknown` gets `vault_*` too (`enclave_control/config.py` DEFAULT_POLICY_TOML).
5. **Indirect prompt injection from documents.**
   - Retrieved chunks are concatenated into the local prompt with no delimiting, quoting or instruction hierarchy (`agent.py:207-255`; `manager.py:645-684`).
   - The output goes straight back to the external AI.
   - A malicious PDF (a received invoice, say) can steer the local model to emit instructions to Claude, e.g. "call vault_store / request_purchase". [READ; attack is inference]

**Other notable issues** [READ]
- LiteParse fallback defaults to `npx -y @llamaindex/liteparse` (`parsing/document_parser.py:254-259`). That downloads and executes npm code at parse time.
- The GUI PDF path pip-installs packages at runtime (`gui/pdf_processor.py:140-175`).
- Models load online every time (Q1).
- The adapter-package password KDF is a single SHA-256 (`adapter_packager.py:207, 329`), which is GPU-brute-forceable.
- Profile names are used unsanitized as paths (`manager.py:298-299`).

### Inferences
- The v1 security baseline should be:
  - a passphrase → Argon2id-derived KEK wrapping a random DEK, stored in the OS keychain (macOS Keychain / Windows DPAPI / libsecret) with an optional "remember" setting;
  - encrypted metadata (names, paths) and a keyed-HMAC content hash;
  - encrypted or at least co-located-and-purged embeddings (SQLCipher or sqlite-vec inside an encrypted DB is simpler than per-field AEAD);
  - no plaintext logs of arguments;
  - removing every `bash -c`/shell path;
  - a threat model doc that replaces CRYPTOGRAPHIC_SPECS.md.
- Drop the "never see raw documents" absolute claim or enforce it with output checks (n-gram overlap limits and secret-pattern redaction), and remove secret-returning tools from the default MCP surface.

### Gaps
- I did not test macOS osascript dialog injection. The escaping of `\` and `"` looks sufficient for AppleScript string literals (`consent.py:270-273`), but it is unverified.
- Embedding inversion against e5-small-v2 was not tested.

---

## Q6. MCP server: what tools are exposed, SDK version and spec features, transport, and how "synthesized answers" is enforced

### Takeaway
The server uses the **low-level `mcp.server.Server` decorator API from the v1 Python SDK** over stdio. It advertises **28 tools** across four unrelated domains: secrets vault, doc agent, file "Sheriff" and a mock wallet.

`pyproject.toml` pins only `mcp>=1.0.0`. A fresh install today resolves **mcp 2.2.0**, where `Server.list_tools` no longer exists, so **`enclave-mcp` crashes on startup and 17 tests fail**. The same code passes all 49 MCP tests on mcp 1.30.0.

"Synthesized answers only" rests on prompt wording plus not printing excerpts. It is not technically enforced.

### Cited Findings
- **SDK and transport.** `from mcp.server import Server`, `from mcp.types import Tool, TextContent` (`server.py:18-19`). Handlers are registered with `@self.server.list_tools()` / `@self.server.call_tool()` (`server.py:130, 580`). Transport is stdio only (`server.py:1596, 1605-1610`). [READ]
- **Fresh install breaks it.**
  - `pip install -e ".[dev]"` resolved `mcp 2.2.0` (`pyproject.toml:50`). `enclave-mcp` then fails with `AttributeError: 'Server' object has no attribute 'list_tools'`. [RUN]
  - The mcp 2.x migration note says FastMCP was renamed to MCPServer and other APIs changed, and advises pinning `mcp<2` to keep running v1 code (from the SDK import error text). [RUN]
  - With `mcp==1.30.0` on an isolated PYTHONPATH: `advanced_vault/mcp_server` tests pass 49/49. [RUN]
- **CI would also break.** `.github/workflows/ci.yml:114-127` constructs the server in a "smoke" job, which would now fail. I did not check GitHub run status.
- **`enclave doctor` doesn't catch it.** It prints "Ready to go" while the MCP server cannot start. Doctor never constructs the server (`cli/doctor.py`; run output). [RUN]
- **The 28 tools** (`server.py:131-578`; count via grep):
  - vault_store, vault_recall, vault_list_entries, vault_delete, vault_stats;
  - langchain_get_secret, langchain_query_knowledge (cloud, inert unless `ENCLAVE_API_KEY` + `ENCLAVE_API_BASE_URL` are set, `server.py:67-71, 1012-1016`);
  - query_knowledge, agent_query, agent_summarize, agent_draft, agent_status;
  - 8 `sheriff_*` tools;
  - create_envelope, list_envelopes, check_budget, request_purchase, approve_purchase, get_transactions, freeze_all, unfreeze_all (wallet is "Mock-only", `advanced_vault/wallet/__init__.py:1`; `MockWalletProvider` at `wallet/provider.py:40`). [READ]
- **Spec features unused.**
  - There are no resources, prompts, tool annotations (`readOnlyHint`/`destructiveHint`), `outputSchema`/structured content, progress, elicitation or sampling. Grep found none in `server.py`. [READ]
  - Handlers are `async` but run blocking work inline: model load and generation, embedding, and a 30-second modal `osascript`/`zenity` consent dialog (`server.py:1117-1122`; `consent.py:278-316`). There is no `asyncio.to_thread`, so a slow model load or pending dialog blocks the whole stdio session.
- **Tools advertised then denied by default.**
  - All 8 sheriff tools are listed, but the default policy denies module `security` to every MCP identity. [RUN]
  - `approve_purchase`, `freeze_all` and `unfreeze_all` are listed but not allow-listed for claude-desktop or cursor (`enclave_control/config.py` defaults). [READ]
  - If an operator widened the policy, `approve_purchase` lets the agent approve its own request, with `approver` defaulting to `"user"` in the audit log (`server.py` `_handle_wallet_approve_purchase`; `wallet/service.py:226-240`). [READ]
- **How "synthesized answers" works in practice.** [READ]
  - `agent_query` output prints only the answer plus document names and scores. The 180-char excerpts in `result["sources"]` are not printed (`server.py:1130-1143` vs `agent.py:210-218`). That is the one real control.
  - Everything else is instructions in the prompt: "Return only the final answer…" (`agent.py:244-260`).
  - `agent_summarize` feeds up to 8,000 chars of a whole document, matched by filename substring (`agent.py:329-344`), and returns the model's text unfiltered.
  - `agent_status` returns up to 20 document names (`agent.py:520-524`).
  - `vault_recall` returns raw stored plaintext (Q5).
- **Prompt-injection exposure.** Covered under Q5 risks #1 and #5. Also: a DENY is returned as `❌ Access denied … Please approve the notification` text, which invites the external agent to retry (`server.py:684-689`). [READ]

### Inferences
- For v1, trim the server to about 4–5 read-only document tools: `ask` (answer + citations), `search_documents` (titles, snippets and page refs, under an explicit user policy), `list_documents`, `get_status`, and possibly `summarize_document`.
- Also for v1:
  - migrate to mcp 2.x `MCPServer`, or pin `mcp>=1.x,<2` immediately as a hotfix;
  - add tool annotations and structured output;
  - move all blocking work off the event loop;
  - drop wallet, sheriff and secrets tools from the default server.
- A focused MCP surface is also the main differentiator versus desktop RAG apps without MCP. Getting it working is the highest-leverage fix.

### Gaps
- I did not test with a real MCP client (Claude Desktop/Cursor) or check behavior against the latest MCP spec revision (authorization, streamable HTTP). I also did not verify whether the owner's GitHub CI is currently red.

---

## Q7. Code health: module sizes, duplication, dead code, layering/circular imports, lint debt, test health and coverage

### Takeaway
The repo is large and shows several product pivots stacked on each other:
- `advanced_vault/` is about 57k Python lines, 31k of them in `gui/` (16,145 in `vault_app.py` alone).
- There are about 10.7k more lines of legacy `src/` and roughly 17.8k lines of Markdown across 67 docs.

The core is modest. Tests are mostly unit tests with mocks: 29% line coverage, zero coverage of the real inference path, and no quality evals. Lint debt is large but 87% auto-fixable.

### Cited Findings
- **Largest non-GUI modules** (wc -l) [RUN]: `cli/main.py` 1,618; `mcp_server/server.py` 1,615; `training/rag_index.py` 1,154; `backend/api/langchain.py` 1,025; `private_models/manager.py` 768; `training/embeddings.py` 700; `backend/api/training.py` 697; `mcp_server/consent.py` 696; `training/mlx_trainer.py` 678; `training/mlx_lora_backend.py` 656.
- **Lines per package** [RUN]: gui 31,352 · training 6,365 · mcp_server 4,329 · backend 4,297 · cli 1,935 · prosumer 1,701 · sheriff 1,343 · wallet 1,254 · private_models 1,197 · core 1,163 · encrypted_kv 1,083 · enclave_control 818 · parsing 277. Four packages are empty 1-line stubs: `federated`, `homomorphic`, `threshold_crypto`, `speculative`.
- **Duplication** [READ]:
  - master-key load/create ×5 (Q5);
  - `_sanitize_model_output` ×3 (`agent.py:46`, `manager.py:79`, `gui/local_inference.py:33`);
  - two separate "ask" pipelines with different prompts, context formats and thresholds (`agent.py:161-298` vs `manager.py:457-529`);
  - adapter HKDF decrypt ×4 (Q4) and two adapter package formats;
  - three default data roots: `~/.vault` (CLI/GUI/MCP), `~/.enclave` (LocalAgent default, embedding cache, `policies.toml` at `enclave_control/runtime.py:22`) and per-profile `private_models/<name>/vault`.
- **Dead code** [READ]:
  - `training/late_chunking.py`, `training/kv_cache.py`, `FastEmbeddingEngine`, `export_onnx`;
  - `consent.py` granular-permission methods (`set_tool_restrictions`, `set_time_limited_access`, `check_permission`, `set_document_access`, which have no callers);
  - `_try_extension_consent`, which always returns None ("placeholder", `consent.py:646-694`);
  - `sheriff/enforcement.py`, a self-described "stub" with `enabled=False` and `mode="simulate"` (`:17-44`);
  - `core/runpod_client.py`; `core/hybrid_vault.py` "Layer 2" that imports `src/ephemeral_inference` via a `sys.path` hack (`hybrid_vault.py:96-100`, and `src/` isn't in the wheel per `pyproject.toml:159-160`);
  - `macos_app/vault_app.py` (needs `rumps`, which is not declared in any extra);
  - the 4 empty packages.
- **Layering** [READ]:
  - core → gui imports (`agent.py:131`, `manager.py:28-45`);
  - `cli/main.py:15` and `macos_app/vault_app.py:14` insert the repo root into `sys.path`;
  - `training/__init__.py` eagerly imports all training modules.
  - No import cycles were observed: importing `advanced_vault.training` took about 0.11 s, and all four top-level modules imported cleanly. [RUN]
- **Lint** (ruff 0.15.8, `ruff check advanced_vault/ --statistics`) [RUN]:
  - 4,252 findings, 3,712 auto-fixable;
  - top: W293 blank-line whitespace 2,432 · UP006 655 · UP045 466 · UP035 156 · F401 unused-import 142 · I001 137 · B904 66 · F541 51 · F841 unused-variable 31 · E722 bare-except 3 · B023 loop-closure 3;
  - excluding `gui/`: 1,557.
  - CI gates only `F821,F811,F823,E9,F63,F7`, and the full lint is `continue-on-error` (`.github/workflows/ci.yml:33-37`).
- **Tests with the fresh-install resolver** (mcp 2.2.0), `pytest tests/ advanced_vault/ --timeout=120`, 281 collected [RUN]:
  - **242 passed, 22 skipped, 2 failed, 15 errors in 58.7 s**;
  - every failure and error is in `mcp_server/tests/test_server.py` (the `list_tools` AttributeError).
  - With `-x` the run stops at 208 passed / 22 skipped / 1 error.
- **Tests with mcp 1.30.0** [RUN]:
  - **259 passed, 22 skipped** in 50.6 s;
  - coverage **29%** of 20,732 statements.
  - Per-module: `gui/vault_app.py` 0% · `gui/local_inference.py` 0% · `cli/doctor.py` 0% · `mcp_server/server.py` 28% · `cli/main.py` 31% · `consent.py` 31% · `parsing/document_parser.py` 16% · `private_models/manager.py` 49% · `embeddings.py` 54% · `rag_index.py` 66% · `agent.py` 69% · `encrypted_kv/storage.py` 76% · `smart_router.py` 98%.
- **Skips** [RUN]: 6 × "mlx-lm-lora not installed", about 15 × "MLX not available", 1 PDF fixture. `tests/conftest.py` also collect-ignores 9 legacy `src/` test files when torch/safetensors/zstandard/pycryptodome are missing.
- **Test realism** [READ]: "end-to-end" and RAG→MCP tests mock the RAG index and LLM (Q2). There are no retrieval or answer-quality evals, no Linux consent test, and no test that GUI-ingested docs are visible over MCP. Those are exactly the gaps behind the bugs verified above.
- **CI matrix.** Python 3.11 only, ubuntu only (`ci.yml:16-22, 41-47`). No macOS runner, even though MLX is the flagship path. [READ]

### Inferences
- A single `ruff --fix` plus a format pass would remove about 87% of findings, which is cheap signal for OSS contributors.
- The key testing investment is:
  1. an integration test that ingests through the same API the GUI uses and queries through MCP,
  2. a small golden QA eval set (retrieval recall@k plus answer faithfulness),
  3. a macOS CI job.

### Gaps
- GUI test health is out of scope (another agent covers it). I did not run the `langchain-enclave/` or `advanced_vault/backend/tests/` suites (not in the default testpaths collection).

---

## Q8. Dependencies, install size and Python constraints

### Takeaway
The *core* install pulls sentence-transformers, and on Linux x86_64 that drags in full CUDA torch: **about 4.7 GB added to site-packages**. That is before the 130 MB embedding model and the 1–2 GB LLM download. Two constraints are unbounded and have already broken the flagship feature (`mcp>=1.0.0`). Python 3.10 is claimed but untested and likely broken.

### Cited Findings
- **Core deps** (`pyproject.toml:39-67`): click, pydantic, cryptography, `mcp>=1.0.0`, sqlalchemy (only referenced by `cli/doctor.py` as an import check; RAG/KV use `sqlite3` directly), requests, httpx, `sentence-transformers>=2.2.0`, numpy, pypdf, zstandard. [READ]
- **Measured install** [RUN]:
  - `pip install -e ".[dev]"` first failed after 1m57s: "Cannot uninstall PyJWT 2.7.0 … installed by debian". That is environment-specific, triggered by mcp 2.x's pyjwt dependency.
  - The retry with `--ignore-installed PyJWT` succeeded in 1m44s.
  - site-packages grew from 1.3 GB to 6.0 GB: `nvidia/*` CUDA 13 libs 3.2 GB, `torch` 2.14.0 1.2 GB, `triton` 897 MB, `transformers` 5.17.0 118 MB, scipy 113 MB, sklearn 51 MB.
  - Resolved versions: sentence-transformers 6.1.0, numpy 2.4.6, cryptography 50.0.1, mcp 2.2.0.
- **Optional extras** (`pyproject.toml:69-126`): `mlx`, `advanced-training` (mlx-lm-lora, datasets), `cuda` (torch, peft, bitsandbytes), `gui` (flet pinned `>=0.28.3,<0.29`), `liteparse`, `mac-performance` (hnswlib, fastembed), `mac`, `backend` (fastapi, uvicorn), `build` (pyinstaller). [READ]
- **Python.** `requires-python=">=3.10"` with classifiers 3.10–3.12 (`pyproject.toml:11, 33-35`), but CI tests 3.11 only.
  - `enclave_control/config.py` falls back to `import tomli as tomllib` on Python < 3.11, and `tomli` is not a declared dependency. A core install on 3.10 would therefore likely fail when importing `enclave_control`, which the CLI and MCP server both import. [READ; failure is inference, not run on 3.10]
- **Undeclared deps** [READ]:
  - `psutil` (used for app identification, `consent.py:221-236`; failure is silent);
  - `supabase` (`gui/auth_screen.py:12`);
  - `rumps` (`macos_app`);
  - `win10toast` (`consent.py:333`).

### Inferences
- **Size fix.** Swap sentence-transformers/torch for an ONNX embedder (fastembed or onnxruntime + tokenizers), or reuse the LLM runtime's embedding endpoint (llama.cpp or Ollama). That cuts the core install from GBs to roughly 100–200 MB.
- **Pinning.** Pin upper bounds on `mcp`, `mlx-lm` and `mlx-lm-lora`, and ship a lockfile (uv) for reproducibility.

### Gaps
- macOS arm64 install size was not measured. Torch wheels there carry no CUDA and are much smaller (inference).

---

## Q9. Experimental and sprawl directories: real or stub, on the critical path, keep / move / delete?

### Takeaway
Most of the non-core surface belongs to earlier product directions that no longer fit a consumer doc vault:
- a cloud RunPod/Supabase "WDVA" encrypted-adapter service,
- a LangChain secrets SaaS,
- a browser API-key extension,
- a genomics/fitness "health SLM",
- a file DLP "Sheriff",
- an agent wallet.

None of it is on the critical path, and several parts contradict the local-only pitch.

### Cited Findings

| Area | Real or stub | Evidence | On v1 critical path? | Recommendation |
|---|---|---|---|---|
| `federated/`, `homomorphic/`, `threshold_crypto/`, `speculative/` | Empty (1 comment line each) | [RUN] `cat` | No | Delete; also drop the roadmap claims (`advanced_vault/__init__.py:11-15`) |
| `backend/` (FastAPI + Supabase + RunPod, 4.3k lines) | Real but cloud; `/knowledge/query` calls RunPod and has a TODO about needing the user's key (`backend/api/langchain.py:552-661`) | [READ] | No; contradicts local-only | Move to a separate archived repo |
| `src/` legacy (RunPod handler, axolotl, DoRA crypto, genomics/evo2 fitness optimizer, OpenAI GPT marketplace gateway; 10.7k lines) | Real legacy, cloud/GPU | `src/rp_handler.py:1-7`, `src/genomics/evo2_optimizer.py:1-5`, `src/openai_gpt_integration.py:1-4` | No. Only `hybrid_vault` Layer-2 reaches it via a `sys.path` hack | Archive in a separate repo; delete from the main tree |
| `langchain-enclave/` | Real client for the cloud backend (`base_url="https://your-backend.railway.app"`, `langchain_enclave/secrets.py:36`, `knowledge.py:40`) | [READ] | No | Move out / archive |
| `browser-extension/` | Real MV3 "API key storage" extension; `host_permissions` to a hard-coded Railway URL; content script on `<all_urls>` (`browser-extension/manifest.json`) | [READ] | No; consent bridge is unimplemented (`consent.py:646-694`) | Archive |
| `integrations/openclaw-enclave/` | Real thin Node plugin plus Python bridge over PrivateModelManager/Sheriff (`integrations/openclaw-enclave/README.md`) | [READ] | No, but a potential distribution channel | Move to a separate repo depending on a stable core API |
| `sheriff/` (1.3k lines) | Real file-risk scanner and lease manager; OS enforcement is a stub; `.ssh/id_ed25519` is labeled NORMAL (content scan only for text suffixes, `sheriff/risk_scanner.py:50-54, 84-94`) and NORMAL is ALLOW by default (`sheriff/policy_engine.py:104`) | [RUN+READ] | No | Separate product / repo |
| `wallet/` (1.25k lines) | Mock-only | `wallet/__init__.py:1` | No | Delete or separate repo |
| `enclave_control/` (818 lines) | Real policy allow-list, kill switch and audit | [READ] | Partly: it is the only effective MCP gate today | Keep a slimmed version (per-client tool allow-list plus audit) |
| `core/hybrid_vault.py` + `smart_router.py` + `encrypted_kv/` | Real secrets KV with keyword routing | [READ] | Not for a doc vault; `vault_recall` is an exfil risk | Quarantine (optional "secrets" plugin) or delete |
| `prosumer/` (1.7k lines) | Real categories, keyword classifier and adapter presets; `__init__` says "Copyright © 2025 Zygmunt Dyras. All rights reserved." (`prosumer/__init__.py`) despite the Apache-2.0 LICENSE (the same header appears in `src/wdva/*`, `src/genomics/*`) | [READ] | Categories are useful UX; adapter presets are not | Keep categories/classifier; fix the license headers before OSS launch |
| `training/{mlx_*, document_dpo_pipeline, grpo_rewards, adapter_packager}` | Real but MLX-only research | Q4 | No | Move to an optional `enclave-lab` extra |
| `training/{late_chunking, kv_cache}` | Unused | Q2 | No | Delete |
| `macos_app/` | Orphaned rumps menubar app over HybridVault | [READ] | No | Delete |

### Inferences
- Cutting the table above removes roughly 25–30k lines of Python/JS and most of the 67 Markdown docs from the main repo. That makes the project understandable to OSS contributors.
- The license-header conflict ("All rights reserved" inside an Apache-2.0 repo) must be resolved before promoting it as open source.

### Gaps
- I did not assess `scripts/`, the Dockerfiles or `docker-compose.yml` in depth (packaging agent scope).

---

## Q10. How do the author's roadmap and status docs compare with reality?

### Takeaway
The status docs describe earlier, cloud-centric architectures as "complete" or "Alpha Release Ready". The roadmap is a 2025 plan for a secrets vault with team, homomorphic and federated features that were never built. Neither describes the current local doc-vault direction or its real blockers.

### Cited Findings
- **`advanced_vault/docs/ROADMAP.md`** [DOC]: "Start Date: 2025-10-26 … Status: 🚧 Planning Phase" (`:3-5`).
  - Phases: encrypted KV plus a smart router (built); MCP plus consent (built, but see Q5/Q6); speculative decryption, Shamir team vaults and key rotation (not built, empty packages); homomorphic search and federated learning (not built).
  - Its ✅ marks are success criteria, not completion status (`:45-48, 86-88`).
- **`advanced_vault/docs/BASELINE.md`** [DOC]: "Last Verified: 2025-10-26 … ✅ All tests passing, RunPod deployment working". It documents `src/train_dora.py` TinyLlama DoRA training on RunPod as the "proven baseline" (`:1-40`). That is the legacy cloud stack.
- **`docs/implementation/STATUS.md`** [DOC]: "Last Updated: 2025-01-30 · Status: Alpha Release Ready ✅" (`:3-4`). "Complete" phases include RunPod user isolation, GUI **cloud sync** ("Encrypted entries synced to cloud automatically … conflict resolution (cloud wins)"), PDF upload and RunPod training (`:14-115`). All of it is cloud-first.
- **README vs code**: overclaims include "encryption for all data at rest", "key zeroing", "Windows/Linux", "never see your raw data" and the adapter-sharing privacy claims (Q5, Q3, Q4). [DOC vs READ]
- **Git history.** The local clone has 68 commits from 2026-01-15 to 2026-09-29 (probably a shallow clone). The most recent is "MVP beta readiness: fix broken entry points and flagship MCP tool…" (`b492c3a`). Yet the MCP server does not start on a fresh install today. [RUN]

### Inferences
- The owner should replace ROADMAP/STATUS/BASELINE with a single honest `STATUS.md` plus a public roadmap reflecting the doc-vault focus. Stale "Alpha Ready" docs will damage credibility with OSS reviewers.

### Gaps
- There is no written product requirements doc for the current direction. The intended v1 scope is inferred from README and pyproject.

---

## Q11. What minimal core should a focused v1 be built on, and what should be cut or quarantined?

### Takeaway
There is a small, salvageable core of roughly 3–4k lines:
- the parsing helper,
- `RAGIndex` + `EmbeddingEngine` + `VectorIndex`,
- `PrivateModelSession` (ingest/ask),
- a trimmed MCP server and agent,
- a slimmed policy/audit layer,
- the CLI `model` / `mcp` / `doctor` commands.

It needs to be unified into **one data root, one key, one index, one "ask" pipeline, served identically to the GUI, CLI and MCP**. Everything else should be deleted, moved out or put behind an optional plugin boundary.

### Cited Findings (the building blocks and their verified state)
- **Works today** [RUN]: profile create, ingest (txt/md/pdf), encrypted storage, dense retrieval, sources list (`private_models/manager.py`, `training/rag_index.py`, `embeddings.py`, `vector_index.py`, `parsing/document_parser.py`).
- **Broken or blocked today** [RUN]:
  - MCP startup on mcp 2.x (`server.py:130`);
  - MCP ↔ GUI index split (`agent.py:112-125` vs `manager.py:316-319`);
  - Linux consent RCE (`consent.py:301-316`);
  - non-Mac answer quality (TinyLlama, `local_inference.py:142`).
- **Needs a redesign** [READ]:
  - key management (5 copies, plaintext key file);
  - plaintext metadata, embeddings and embedding cache;
  - consent identity and granularity;
  - the double chat template (`agent.py:272-285`);
  - core → gui imports.

### Inferences — proposed v1 core and cut list
**Keep and refactor into the `enclave` core package, with no GUI imports:**
1. `ingest`: `parsing/document_parser.py` plus new .docx/.eml/.html parsers. Make LiteParse opt-in, with no auto-npx.
2. `index`: `RAGIndex` → a single store per vault; add SQLite FTS5 (BM25) hybrid search with RRF, keep page/section metadata per chunk, and encrypt names and paths.
3. `embed`: `EmbeddingEngine` behind an interface. Default to ONNX/fastembed to drop torch. Offline-first model loading.
4. `llm`: a runtime interface with MLX (Mac), llama.cpp/Ollama (all platforms) and a model registry defaulting to a stronger 3–8B instruct model.
5. `answer`: one `ask()` pipeline: retrieve → optional rerank → prompt with delimited, quoted context → answer with chunk-ID citations → verify citations. The GUI, CLI and MCP all call it.
6. `mcp`: an SDK-2.x `MCPServer` with about 4–5 read-only document tools, annotations and structured output, work off the event loop, and a per-client allow-list (from `enclave_control`) plus a consent UI with no shell interpolation.
7. `keys`: passphrase + Argon2id + OS keychain; one key-loading module.

**Quarantine as optional extras or plugins:** fine-tuning/adapters (`training/mlx_*`, DPO/GRPO/QAT, adapter packagers, GUI adapter engines), prosumer adapter presets, the secrets KV (`encrypted_kv`, `hybrid_vault`, `smart_router`) as an optional "secrets" plugin with no raw-return MCP tool.

**Move to separate or archived repos:** `backend/`, `src/`, `langchain-enclave/`, `browser-extension/`, `integrations/openclaw-enclave/`, `sheriff/`, `wallet/`.

**Delete:** the 4 empty packages, `late_chunking.py`, `kv_cache.py`, `FastEmbeddingEngine`, `macos_app/`, `core/runpod_client.py`, the dead consent methods, and stale ROADMAP/STATUS/BASELINE/CRYPTOGRAPHIC_SPECS docs (replace with an honest threat model).

**Immediate hotfixes, before any public push:**
1. Pin `mcp<2` or migrate.
2. Remove the `bash -c` consent path.
3. Point MCP at the same profile index as the GUI/CLI.
4. Have doctor actually start the MCP server.
5. Fix the double templating and the `model_used` misreport.
6. Stop claiming "all data encrypted" and "key zeroing" until true.

### Gaps
- Effort estimates were not produced. They depend on the GUI audit and the chosen runtime (llama.cpp vs Ollama). I also did not benchmark alternatives (fastembed, sqlite-vec, FTS5) inside this repo.

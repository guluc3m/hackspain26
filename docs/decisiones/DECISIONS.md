# DECISIONS.md

Decision log for the local OCR hosting project. Verified against primary sources
(HF repo READMEs / file trees) on **2026-09-18**.

---

## D-001 — OCR engine selection for low-power self-hosting

### Requirements

- Commercially usable license (clean Apache-2.0 / MIT — no NC, no use restrictions).
- Hosted on a small machine: **8 CPU cores, 12 GB RAM, no GPU**.
- Must run easily: minimal dependencies, no tuning required.
- Broad language support (multilingual documents).

### Decision

**Use `PaddlePaddle/PaddleOCR-VL-1.6` GGUF served by `llama.cpp` (`llama-server`), CPU-only.**

- Model: `PaddlePaddle/PaddleOCR-VL-1.6-GGUF` — https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6-GGUF
  - `PaddleOCR-VL-1.6-GGUF.gguf` (0.94 GB) + `PaddleOCR-VL-1.6-GGUF-mmproj.gguf` (0.88 GB)
- Base model: https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6
- License: **Apache-2.0** (verified in repo frontmatter; official PaddlePaddle release).
- Serving: `llama-server` (OpenAI-compatible `/v1` endpoint), CPU build of llama.cpp.

```
llama-server \
  -m PaddleOCR-VL-1.6-GGUF.gguf \
  --mmproj PaddleOCR-VL-1.6-GGUF-mmproj.gguf \
  --temp 0 --threads 6 --host 0.0.0.0 --port 8080
```

### Rationale

- **SOTA quality**: 96.33 on OmniDocBench v1.6 — highest overall score among the
  candidates at decision time; handles text, tables, formulas, charts, seals.
- **Language coverage**: 109 languages — the broadest of the small commercial models
  (GLM-OCR lists ~8; dots.ocr ~100).
- **Footprint**: ~1.8 GB weights + ~1 GB KV/activations → ~3 GB peak RSS on CPU.
  Comfortable on 12 GB with headroom for larger context / image pixel caps.
- **Minimal stack**: one llama.cpp binary + two model files. No Python, no CUDA,
  no PaddlePaddle dependency for basic serving.
- **Client contract**: OpenAI-compatible HTTP API; element prompts are
  `OCR:`, `Formula Recognition:`, `Table Recognition:`, `Chart Recognition:`,
  `Seal Recognition:`, `Spotting:` (Spotting needs mmproj
  `clip.vision.image_max_pixels` = 1605632; default is 1003520).

### Alternatives considered

| Alternative | License | Verdict |
|---|---|---|
| `zai-org/GLM-OCR` (0.9B) | MIT | Runner-up. #1 OmniDocBench v1.5 (94.62) but ~8 listed languages vs 109; GGUF only Q8/f16. Kept as fallback. |
| `rednote-hilab/dots.ocr` (1.7B) | MIT | Good unified layout+recognition, but larger footprint and less language coverage than PaddleOCR-VL. |
| `deepseek-ai/DeepSeek-OCR-2` (~3B) | Apache-2.0 | Strong, but overkill for a CPU-only 8-core box. |
| `baidu/Unlimited-OCR` (~3.3B) | MIT | Good, but 2× the size; FP8 community quants useless without FP8 hardware. |
| `allenai/olmOCR-2-7B-1025` | Apache-2.0 | Best-quality 7B tier, far too slow on CPU-only. |
| `jinaai/jina-ocr-v1` | CC-BY-NC-4.0 | **Rejected** — non-commercial. |
| `datalab-to/chandra-ocr-2` | OpenRAIL | Rejected — commercial use allowed only with use restrictions; not clean. |
| PaddleOCR classic PP-OCRv5 CPU pipeline | Apache-2.0 | Fastest on tiny hardware, but no table/formula/layout understanding. Revisit only if workload is plain text at scale. |

### Notes / caveats

- Expect ~10–30 s per typical page on 8 slow CPU cores; tables are the slow case.
- Use `--temp 0` (deterministic OCR) and `--threads 6-7` (leave one core for the OS).
- Assumption to validate after first deploy: default image pixel cap (1003520)
  is sufficient for the target documents; raise to 1605632 only if needed.
- If later scaling up on GPU hardware, prefer BF16 or GGUF/EXL3 quants —
  the box's GPUs (modified RTX 3080 20 GB ×2) have no FP8/NVFP4 support.

---

## D-002 — Engine choice (mainline llama.cpp) and quantization level (full Q8)

Date: 2026-09-18

### Context

Host box: 8 CPU cores / 12 GB RAM. Goals: save RAM where free, keep OCR quality
intact, use a CPU-tailored engine if it doesn't cost support/quality.

### Quantization impact on OCR quality (researched, primary sources)

- `cstr/paddleocr-vl-1.6-GGUF` (tested its own quants vs the f16 reference):
  - **q8_0** — "transcribes fully and matches the fp16 reference" → no quality hit.
  - **q4_k** — "noticeably lossy — tends to terminate early" (truncated transcripts).
- Conclusion: **Q8_0 is the safe floor** for both text and mmproj (vision encoder)
  on this 0.9B model; anything below Q8 on the mmproj is where OCR visibly degrades.
- Correction to D-001: the official `PaddlePaddle/PaddleOCR-VL-1.6-GGUF` files are
  text **bf16** (0.936 GB) + mmproj **f16** (0.882 GB), not Q8.

### Decision

1. **Quantization: full Q8_0** (text q8_0 + mmproj q8_0). No 4-bit.
2. **Engine: mainline llama.cpp (`llama-server`)** — not ik_llama.cpp or other forks.

### Ready-made full-Q8 files (no self-conversion needed)

**Use `Mungert/PaddleOCR-VL-1.6-GGUF`** — https://huggingface.co/Mungert/PaddleOCR-VL-1.6-GGUF
Verified file tree contains both:

- `PaddleOCR-VL-1.6-q8_0.gguf` — 0.498 GB (text, q8_0)
  https://huggingface.co/Mungert/PaddleOCR-VL-1.6-GGUF/resolve/main/PaddleOCR-VL-1.6-q8_0.gguf
- `PaddleOCR-VL-1.6-q8_0.mmproj` — 0.598 GB (vision encoder, q8_0)
  https://huggingface.co/Mungert/PaddleOCR-VL-1.6-GGUF/resolve/main/PaddleOCR-VL-1.6-q8_0.mmproj

Total weights **1.10 GB** vs 1.82 GB official → **~0.72 GB RAM saved**, at the
highest safe precision. Built with llama.cpp @ `7c158fbb4` (standard
llama-quantize output, no exotic formats).

```
llama-server \
  -m PaddleOCR-VL-1.6-q8_0.gguf \
  --mmproj PaddleOCR-VL-1.6-q8_0.mmproj \
  --temp 0 --threads 6 --host 0.0.0.0 --port 8080
```

Expected peak RSS: ~2.0–2.5 GB (well within 12 GB).

### Rejected alternatives

- **ik_llama.cpp** — https://github.com/ikawrakow/ik_llama.cpp — has multimodal/mtmd support (PRs #798/#901) but its arch
  table has no `paddleocr` arch (mainline has `LLM_ARCH_PADDLEOCR`; ik only has
  `ernie4_5` text). Zero ik issues/PRs mention paddleocr; its vision path has
  open bugs (#2486 mmproj/fit, #2464 CPU vision hallucinations). Its IQK kernel
  gains matter for large MoE CPU inference, not a 0.9B dense model.
- **Text Q4_K / Q4_K_M** — saves ~0.1–0.2 GB more but documented lossy
  (early-terminated transcripts on this model). Not worth it.
- **mmproj below Q8_0** — vision encoder is the accuracy-critical path for OCR;
  low-bit mmproj is where VLM OCR quality visibly breaks.

### Notes / caveats

- Validate the Mungert q8 mmproj against the official f16 mmproj on a handful of
  real documents during first deploy (expect identical transcripts; fall back to
  the official bf16+f16 pair, or a local `llama-quantize` Q8 pass, if not).
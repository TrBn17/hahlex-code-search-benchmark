<div align="center">
  <img src="https://img3.pixhost.to/images/6977/800059020_image.png" alt="Jason Lab Banner" width="100%" />
  <h1>Hahlex Code Search Benchmark</h1>
</div>

Empirical benchmark evaluating code search tools and strategies (`Baseline`, `ripgrep`, `CodeGraph`, `Graphify`, and `Adaptive Search`) for AI Coding Agents on **Hahlex LMS** (`education-platform` NestJS/TypeScript + `ai-platform` Python/FastAPI). Across four phases (134 total runs/sessions), **`ripgrep` (`rg`)** was selected as the default code-search strategy in `AGENTS.md`:

| Phase | Question it answers | Headline outcome |
|---|---|---|
| `Phase 1` (60 tool runs) | Which search CLI is fastest, lightest, and most accurate standalone? | `ripgrep` wins: **83.8 ms** median latency, **0.7445 F1**, **100% (5/5)** task success, **9 MB** RAM |
| `Phase 2` (20 agent sessions) | How do tools affect real AI agent completion, tokens, and recall? | `Adaptive` reaches **23.4s** context time & **0.933** recall; `Baseline` hits **100%** success (`n=5`) |
| `Phase 3` (30 agent sessions) | Does `Graphify` or `Adaptive v1/v2` beat `ripgrep` for `flash` agents? | `Adaptive v1` hits **100%** success & **0.983** recall but at **123.6s** E2E; `Graphify` is **146.2s** E2E & **60%** success |
| `Phase 4` (24 agent sessions) | Does `Adaptive v1` (`rg` + `CodeGraph` on-demand) beat `ripgrep-only`? | **No escalation needed:** `12/12` `Adaptive v1` runs stayed on `rg` (**0** CodeGraph calls); both arms hit **100% (12/12)** pass rate |

## How it works

```
5 LMS tasks (T1–T5) ──▶ isolated `flash` subagents ──▶ transcript.jsonl ──▶ analyze_phase*.py ──▶ docs/code-search-*.md
  (ground truth)          (randomized arm order)         (tokens, latency)     (P/R/F1, rubric)      (final AGENTS.md rule)
```

- **Grounded in real LMS tasks (`T1–T5`):** Feature discovery (`ai-grading-estimate`), API→Service→DB trace (`publishGradebook`), cross-module bug triage (`CreditMetering` / `plan-features` / `feature-refusal`), blast-radius impact (`offsetPage`), and cross-repo auth consistency (`ServicePrincipalGuard` / `service_auth`).
- **Isolated, randomized runs:** Every agent session starts with a clean context, receives no ground truth, runs in randomized wave order, and has its telemetry (`input_tokens`, `cache_read_tokens`, `output_tokens`, timestamps, tool calls, duplicate reads) parsed directly from `transcript.jsonl`.
- **Two-level scoring:** Retrieval Quality (`Precision`, `Recall`, `F1`, missed critical files, time to relevant context) is scored separately from Agent Task Quality (acceptance rubric & evidence verification).

## Results

### Phase 4 — Final Validation: `ripgrep` vs `Adaptive v1` (24 sessions, `flash`, T2–T5 × 3 reps)

| Metric | Arm B (`ripgrep-only`, n=12) Mean \| Med \| Min–Max | Arm D (`Adaptive v1`, n=12) Mean \| Med \| Min–Max |
|---|---|---|
| **Task Pass Rate** | **12/12 (100%)** | **12/12 (100%)** |
| **Missed Critical Files** | **0.00** \| 0.0 \| 0–0 | **0.00** \| 0.0 \| 0–0 |
| **Retrieval Precision** | 0.436 \| 0.408 \| 0.250–0.619 | 0.469 \| 0.427 \| 0.310–0.722 |
| **Retrieval Recall** | 0.869 \| 0.857 \| 0.667–1.000 | 0.860 \| 0.857 \| 0.667–1.000 |
| **Retrieval F1** | 0.576 \| 0.545 \| 0.370–0.765 | 0.600 \| 0.567 \| 0.439–0.839 |
| **Time to Relevant Context** | 20.8s \| 14.5s \| 3.0–68.0s | 13.4s \| 4.5s \| 3.0–58.0s |
| **E2E Completion Time** | 89.7s \| 88.0s \| 38.0–144.0s | 92.5s \| 65.5s \| 41.0–197.0s |
| **LLM Turns / Tool Calls** | 11.3 / 24.8 | 11.2 / 23.9 |
| **CodeGraph Calls / Time** | 0.00 / 0.0s | **0.00 / 0.0s (0/12 sessions called CodeGraph)** |
| **Input / Output Tokens** | 90,065 / 10,235 | 75,351 / 9,857 |
| **Duplicate File Reads** | 3.42 \| 3.0 \| 0–9 | 3.17 \| 2.5 \| 0–9 |
| **API Cost (USD)** | `N/A` (internal `flash` pricing not exposed) | `N/A` |

<details>
<summary>Phase 4 per-task breakdown (n = 3 per cell)</summary>

| Task × Arm | Pass | P / R / F1 (Mean) | Context Time Mean (Med) | E2E Mean (Med, Min–Max) | Turns / Tools | Input / Output Tokens | Dup Reads |
|---|---:|---|---|---|---|---|---|
| `T2_ripgrep` | 3/3 | 0.454 / 0.778 / 0.571 | 6.7s (6.0s) | 66.3s (62.0s, 38–99s) | 9.0 / 18.3 | 63,686 / 6,889 | 5.33 |
| `T2_adaptive_v1` | 3/3 | 0.481 / 0.778 / 0.591 | 3.3s (3.0s) | 54.7s (56.0s, 41–67s) | 10.0 / 23.7 | 67,963 / 7,983 | 7.67 |
| `T3_ripgrep` | 3/3 | 0.350 / 0.809 / 0.487 | 36.7s (26.0s) | 109.0s (116.0s, 95–116s) | 13.0 / 27.7 | 125,247 / 10,900 | 2.33 |
| `T3_adaptive_v1` | 3/3 | 0.421 / 0.857 / 0.564 | 42.0s (38.0s) | 173.7s (164.0s, 160–197s) | 14.0 / 31.7 | 90,338 / 11,346 | 3.00 |
| `T4_ripgrep` | 3/3 | 0.592 / 1.000 / 0.743 | 36.3s (23.0s) | 110.0s (107.0s, 79–144s) | 11.3 / 24.7 | 71,782 / 10,538 | 5.00 |
| `T4_adaptive_v1` | 3/3 | 0.657 / 1.000 / 0.791 | 3.7s (3.0s) | 58.3s (61.0s, 50–64s) | 8.3 / 13.0 | 52,627 / 8,350 | 0.00 |
| `T5_ripgrep` | 3/3 | 0.349 / 0.889 / 0.501 | 3.7s (4.0s) | 73.3s (71.0s, 68–81s) | 12.0 / 28.7 | 99,544 / 12,613 | 1.00 |
| `T5_adaptive_v1` | 3/3 | 0.315 / 0.806 / 0.452 | 4.7s (5.0s) | 83.3s (85.0s, 55–110s) | 12.7 / 27.3 | 90,475 / 11,751 | 2.00 |

</details>

### Phase 3 — Graphify vs CodeGraph vs ripgrep vs Adaptive (30 sessions, `n = 5` per arm)

| Arm (`n = 5`) | Task Success | Recall / Precision / F1 | Mean Context Time | Mean E2E (Median) | LLM Turns / Tools | Input / Output Tokens |
|---|---:|---|---:|---:|---:|---:|
| **Baseline** | 60% | 0.733 / 0.313 / 0.436 | 17.2s | **53.4s** (43.0s) | 7.8 / 16.0 | 76,366 / 7,856 |
| **ripgrep** | 80% | 0.917 / **0.474** / **0.613** | 34.4s | 58.2s (46.0s) | 8.8 / 15.6 | 77,417 / 9,806 |
| **CodeGraph** | 80% | 0.867 / 0.409 / 0.547 | 33.8s | 103.8s (89.0s) | 9.8 / 18.8 | 83,993 / 11,452 |
| **Adaptive v1** | **100%** | **0.983** / 0.463 / **0.626** | **12.8s** | 123.6s (112.0s) | 12.6 / 26.2 | 92,497 / 10,972 |
| **Graphify** | 60% | 0.791 / 0.475 / 0.591 | 72.0s | 146.2s (137.0s) | 12.0 / 21.0 | 82,548 / 15,639 |
| **Adaptive v2** | 80% | 0.767 / 0.334 / 0.451 | 46.2s | 114.0s (101.0s) | 12.0 / 27.2 | 125,682 / 9,826 |

### Phase 2 — Agent-Level Benchmark (20 sessions, `n = 5` per arm)

| Arm (`n = 5`) | Task Success | Recall / Precision | Mean Context Time | Mean E2E | LLM Turns / Tools | Input / Output Tokens |
|---|---:|---|---:|---:|---:|---:|
| **Baseline** | **100%** | **0.938** / **0.487** | 39.0s | **79.8s** | 8.4 / 16.0 | 72,302 / 10,467 |
| **ripgrep** | 60% | 0.814 / 0.438 | 28.6s | 103.6s | 9.8 / 20.8 | **70,222** / 10,379 |
| **CodeGraph** | 60% | 0.867 / 0.465 | 45.6s | 126.8s | 10.2 / 16.8 | 82,823 / 12,882 |
| **Adaptive** | 80% | 0.933 / 0.418 | **23.4s** | 92.2s | 11.2 / 23.6 | 82,034 / **9,448** |

### Phase 1 — Tool-Level Benchmark (60 runs, 5 Tasks × 4 Methods × 3 reps)

| Metric | Baseline (`git grep`) | ripgrep (`rg`) | CodeGraph (`codegraph`) | Hybrid (`rg` + `codegraph`) |
|---|---:|---:|---:|---:|
| **Median Search Latency** | 427.00 ms | **83.81 ms** | 1,208.94 ms | 974.96 ms |
| **Median Tool E2E** | 428.18 ms | **85.21 ms** | 1,208.94 ms | 977.63 ms |
| **Context Payload Tokens (Mean)** | 7,990.4 | **7,800.8** | 11,327.0 | 9,412.6 |
| **Tool Calls (Mean)** | 10.80 | 7.00 | **2.00** | 4.00 |
| **Precision / Recall (Mean)** | 0.6225 / 0.8381 | **0.6425 / 0.9048** | 0.3738 / 0.7747 | 0.3849 / 0.8714 |
| **F1 Score (Mean)** | 0.7111 | **0.7445** | 0.4973 | 0.5288 |
| **Task Success Rate** | 80% (4/5) | **100% (5/5)** | 60% (3/5) | 80% (4/5) |
| **Peak RAM (Median RSS)** | 45.18 MB | **8.99 MB** | 430.09 MB | 428.47 MB |

## Quick start (reproduce analysis)

```powershell
# Re-run Phase 1 tool-level benchmark (requires Hahlex LMS workspace + rg + codegraph)
python benchmarks/code-search/run_benchmark.py

# Re-compute Phase 2–4 metrics from recorded transcripts
python benchmarks/code-search/analyze_agent_runs.py
python benchmarks/code-search/phase3/analyze_phase3.py
python benchmarks/code-search/phase4/analyze_phase4.py
```

## More

- [`benchmarks/code-search/tasks.json`](benchmarks/code-search/tasks.json): 5 representative LMS tasks (`T1–T5`) and verified ground-truth files.
- [`docs/code-search-benchmark.md`](docs/code-search-benchmark.md): Phase 1 tool-level report.
- [`docs/code-search-agent-benchmark.md`](docs/code-search-agent-benchmark.md): Phase 2 agent-level & Adaptive Search report.
- [`docs/code-search-graphify-benchmark.md`](docs/code-search-graphify-benchmark.md): Phase 3 Graphify vs CodeGraph vs ripgrep report.
- [`docs/code-search-final-benchmark.md`](docs/code-search-final-benchmark.md): Phase 4 final validation & `AGENTS.md` decision report.

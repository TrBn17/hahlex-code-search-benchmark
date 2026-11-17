# Hahlex LMS — Code Search Benchmark (Phases 1–4)

Benchmark scripts, raw telemetry/results, and evaluation reports comparing code search strategies (`Baseline`, `ripgrep`, `CodeGraph`, `Graphify`, and `Adaptive v1`/`v2`) for AI Coding Agents on the Hahlex LMS codebase (`education-platform` + `ai-platform`).

## Reports

- **Phase 1 (Tool-level, 60 runs):** [docs/code-search-benchmark.md](docs/code-search-benchmark.md)
- **Phase 2 (Agent-level, 20 sessions):** [docs/code-search-agent-benchmark.md](docs/code-search-agent-benchmark.md)
- **Phase 3 (Graphify vs CodeGraph vs ripgrep, 30 sessions):** [docs/code-search-graphify-benchmark.md](docs/code-search-graphify-benchmark.md)
- **Phase 4 (Final Validation: ripgrep vs Adaptive v1, 24 sessions):** [docs/code-search-final-benchmark.md](docs/code-search-final-benchmark.md)

## Data & Scripts

- [benchmarks/code-search/tasks.json](benchmarks/code-search/tasks.json) — 5 representative LMS tasks (`T1–T5`) & ground truth
- [benchmarks/code-search/run_benchmark.py](benchmarks/code-search/run_benchmark.py) — Phase 1 tool-level runner
- [benchmarks/code-search/analyze_agent_runs.py](benchmarks/code-search/analyze_agent_runs.py) — Phase 2 agent transcript analyzer
- [benchmarks/code-search/phase3/analyze_phase3.py](benchmarks/code-search/phase3/analyze_phase3.py) — Phase 3 analyzer
- [benchmarks/code-search/phase4/analyze_phase4.py](benchmarks/code-search/phase4/analyze_phase4.py) — Phase 4 analyzer (`results.json`, `summary.json`)

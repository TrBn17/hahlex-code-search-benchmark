import json
import math
import re
import statistics
from datetime import datetime
from pathlib import Path

import tiktoken

ROOT = Path(r"D:\Projects\hahlex-edu")
TASKS_FILE = ROOT / "benchmarks" / "code-search" / "tasks.json"
OUT_RESULTS = ROOT / "benchmarks" / "code-search" / "phase3" / "phase3_results.json"
OUT_SUMMARY = ROOT / "benchmarks" / "code-search" / "phase3" / "phase3_summary.json"

ENC = tiktoken.get_encoding("cl100k_base")

RUNS = [
    # T1 (order: E, B, F, A, C, D)
    ("T1", "graphify", "428a7e2c-a23d-425f-ad41-1c0aa34d4d83"),
    ("T1", "ripgrep", "2bc05713-3b87-48dc-a98a-8f2a5c5647ab"),
    ("T1", "adaptive_v2", "e90b2824-7715-4ef9-a718-80845001cad8"),
    ("T1", "baseline", "28af26c1-5062-48b5-b3ee-9eb08050f78b"),
    ("T1", "codegraph", "c09b4f73-2ebb-4fa3-8a2f-00e5a4584ccd"),
    ("T1", "adaptive_v1", "a9bd4294-aa8e-42c4-a417-e452b5ac1809"),
    # T2 (order: C, F, A, E, D, B)
    ("T2", "codegraph", "1bf5043a-e9cf-4e91-83a7-6be48eda792e"),
    ("T2", "adaptive_v2", "90c1c98f-6a86-4b08-af04-eb80cb0f692a"),
    ("T2", "baseline", "77933881-3a33-41f5-b99e-66435b70f6a6"),
    ("T2", "graphify", "2d2c4538-9bff-46b3-a0c9-f306fa75185a"),
    ("T2", "adaptive_v1", "b0de725c-a024-45fb-a222-32e58b9ff93b"),
    ("T2", "ripgrep", "1b5a903b-aa85-4a0e-bf6e-89e5d2b980ed"),
    # T3 (order: F, D, E, B, A, C)
    ("T3", "adaptive_v2", "be64da5b-961a-4836-8311-61af4a3a1e9e"),
    ("T3", "adaptive_v1", "0a0c1dd4-d658-4b82-bc62-ec9b5a9475fc"),
    ("T3", "graphify", "94720b42-305e-4473-9d32-0bb2c6384614"),
    ("T3", "ripgrep", "e2dfb473-5365-4ee4-8c11-80d19e1e5b10"),
    ("T3", "baseline", "cb4057f2-b319-4f1b-9b6c-7ee89297c95f"),
    ("T3", "codegraph", "938b38ce-ebec-4830-ad2f-e153dbc6a946"),
    # T4 (order: B, E, A, C, F, D)
    ("T4", "ripgrep", "f9610ea2-812e-46ad-b6d9-c9e91d281ca5"),
    ("T4", "graphify", "98fca83f-6fed-438b-93cb-a7b0f891d5af"),
    ("T4", "baseline", "adba4cb1-4825-43b8-9606-5a74afa19438"),
    ("T4", "codegraph", "eb9aca05-ae3b-452f-8dd6-7f3ac16a3379"),
    ("T4", "adaptive_v2", "11def517-b1db-43b5-9fbc-26050f303f16"),
    ("T4", "adaptive_v1", "2466cef1-dca8-4285-a4cc-6bba0a81a8cd"),
    # T5 (order: D, A, C, F, B, E)
    ("T5", "adaptive_v1", "2314256a-daa7-43a2-b327-7113fb6bb5b8"),
    ("T5", "baseline", "a4bba2f3-91ff-456f-94b0-e7250ae5b86f"),
    ("T5", "codegraph", "b20a272e-1709-4436-b195-a8d026e2147a"),
    ("T5", "adaptive_v2", "af4a726c-e468-4237-8cff-5c76b7e6eea1"),
    ("T5", "ripgrep", "a2f2b36f-898a-4257-bbe5-ba2c0c465298"),
    ("T5", "graphify", "1db2c943-b3db-4e69-8f93-e8677756bd9f"),
]

PATH_RE = re.compile(
    r"(?:education-platform|ai-platform)[\\/][A-Za-z0-9_.\-\\/]+\.(?:ts|tsx|js|jsx|py)"
)


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def count_tokens(text: str) -> int:
    return len(ENC.encode(text, disallowed_special=()))


def extract_paths(text: str) -> set[str]:
    out = set()
    for m in PATH_RE.findall(text):
        out.add(m.replace("\\", "/"))
    for m in re.findall(r"\bapps/(?:api|web)/[A-Za-z0-9_.\-/]+\.(?:ts|tsx|js|jsx)", text):
        out.add("education-platform/" + m)
    for m in re.findall(r"\bsrc/(?:ai_platform|education_ai|ai_engine)/[A-Za-z0-9_.\-/]+\.py", text):
        out.add("ai-platform/" + m)
    return out


def load_steps(conv_id: str) -> list[dict]:
    base = Path(rf"C:\Users\Admin\.gemini\antigravity-cli\brain\{conv_id}\.system_generated\logs")
    compact = base / "transcript.jsonl"
    full = base / "transcript_full.jsonl"
    full_lines = full.read_text(encoding="utf-8").splitlines() if full.exists() else []
    steps = []
    for idx, line in enumerate(compact.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj.get("truncated_fields") and idx < len(full_lines) and full_lines[idx].strip():
            obj = json.loads(full_lines[idx])
        steps.append(obj)
    return steps


def analyze_run(task: dict, method: str, conv_id: str) -> dict:
    steps = load_steps(conv_id)
    t0 = parse_ts(steps[0]["created_at"])
    t_end = parse_ts(steps[-1]["created_at"])
    final_msgs = []
    last_planner_text = ""

    llm_turns = 0
    tool_calls_total = 0
    search_calls = 0
    read_calls = 0
    rg_calls = 0
    cg_calls = 0
    gf_calls = 0
    git_grep_calls = 0
    read_paths = []

    input_tokens = 0
    cache_read_tokens = 0
    output_tokens = 0
    payload_tokens = 0

    crit = set(task["critical_files"])
    gt = set(task["ground_truth_files"])
    seen_crit = set()
    t_rel_context = None

    for s in steps:
        stype = s.get("type")
        if stype == "PLANNER_RESPONSE":
            llm_turns += 1
            input_tokens += s.get("input_tokens") or 0
            cache_read_tokens += s.get("cache_read_tokens") or 0
            output_tokens += s.get("output_tokens") or 0
            if isinstance(s.get("content"), str) and s["content"].strip():
                last_planner_text = s["content"]
            for c in s.get("tool_calls") or []:
                name = c.get("name", "")
                args = c.get("args") or {}
                args_str = str(args)
                if name == "send_message":
                    t_end = parse_ts(s["created_at"])
                    m_arg = args.get("Message", "")
                    if isinstance(m_arg, str):
                        if m_arg.startswith('"') and m_arg.endswith('"'):
                            try:
                                m_arg = json.loads(m_arg)
                            except Exception:
                                pass
                        final_msgs.append(m_arg)
                else:
                    tool_calls_total += 1
                    if name == "run_command":
                        search_calls += 1
                        if "codegraph" in args_str:
                            cg_calls += 1
                        if "graphify" in args_str:
                            gf_calls += 1
                        if "rg" in args_str or "ripgrep" in args_str:
                            rg_calls += 1
                        if "git " in args_str and "grep" in args_str:
                            git_grep_calls += 1
                    elif name == "read_file":
                        read_calls += 1
                        rp = str(args.get("Path", "")).strip('"').replace("\\", "/")
                        if rp:
                            read_paths.append(rp)
        elif s.get("step_index", 0) > 0 and stype != "USER_INPUT":
            content = s.get("content") or ""
            if isinstance(content, str):
                payload_tokens += count_tokens(content)
                found_here = extract_paths(content)
                seen_crit |= (found_here & crit)
                if t_rel_context is None and seen_crit == crit:
                    t_rel_context = (parse_ts(s["created_at"]) - t0).total_seconds()

    duplicate_reads = len(read_paths) - len(set(read_paths))
    final_msg = "\n".join(final_msgs) if final_msgs else last_planner_text

    reported_files = extract_paths(final_msg)
    reported_prod = {f for f in reported_files if ".spec." not in f and ".test." not in f and "/test/" not in f}
    tp = len(gt & reported_prod)
    missed = sorted(gt - reported_prod)
    crit_hit = crit.issubset(reported_prod)
    recall = tp / len(gt) if gt else 0.0
    precision = tp / len(reported_prod) if reported_prod else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    t_comp = (t_end - t0).total_seconds()
    if t_rel_context is None:
        t_rel_context = t_comp

    tools_used = sum(1 for x in (rg_calls, cg_calls, gf_calls, git_grep_calls) if x > 0)

    return {
        "task_id": task["id"],
        "method": method,
        "conv_id": conv_id,
        "time_to_relevant_context_s": round(t_rel_context, 2),
        "time_to_completion_s": round(t_comp, 2),
        "llm_turns": llm_turns,
        "tool_calls": tool_calls_total,
        "search_calls": search_calls,
        "read_calls": read_calls,
        "duplicate_reads": duplicate_reads,
        "rg_calls": rg_calls,
        "cg_calls": cg_calls,
        "gf_calls": gf_calls,
        "git_grep_calls": git_grep_calls,
        "tools_used_count": tools_used,
        "input_tokens": input_tokens,
        "cache_read_tokens": cache_read_tokens,
        "output_tokens": output_tokens,
        "payload_tokens": payload_tokens,
        "gt_count": len(gt),
        "gt_found": tp,
        "reported_prod_count": len(reported_prod),
        "precision_prod": round(precision, 4),
        "recall_gt": round(recall, 4),
        "f1": round(f1, 4),
        "missed_gt_files": missed,
        "critical_all_found": crit_hit,
        "task_success": crit_hit and recall >= 0.80,
    }


def p95(vals: list[float]) -> float:
    s = sorted(vals)
    idx = min(len(s) - 1, math.ceil(0.95 * len(s)) - 1)
    return round(s[idx], 2)


def main():
    tasks = {t["id"]: t for t in json.loads(TASKS_FILE.read_text(encoding="utf-8"))["tasks"]}
    rows = [analyze_run(tasks[tid], m, cid) for tid, m, cid in RUNS]
    OUT_RESULTS.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = {}
    for m in ("baseline", "ripgrep", "codegraph", "adaptive_v1", "graphify", "adaptive_v2"):
        sub = [r for r in rows if r["method"] == m]
        n = len(sub)
        ctx = [r["time_to_relevant_context_s"] for r in sub]
        e2e = [r["time_to_completion_s"] for r in sub]
        inp = [r["input_tokens"] for r in sub]
        cac = [r["cache_read_tokens"] for r in sub]
        out = [r["output_tokens"] for r in sub]
        tcs = [r["tool_calls"] for r in sub]
        summary[m] = {
            "runs": n,
            "mean_ctx_s": round(statistics.mean(ctx), 2),
            "median_ctx_s": round(statistics.median(ctx), 2),
            "p95_ctx_s": p95(ctx),
            "mean_e2e_s": round(statistics.mean(e2e), 2),
            "median_e2e_s": round(statistics.median(e2e), 2),
            "p95_e2e_s": p95(e2e),
            "stdev_e2e_s": round(statistics.stdev(e2e), 2) if n > 1 else 0.0,
            "mean_llm_turns": round(statistics.mean(r["llm_turns"] for r in sub), 2),
            "mean_tool_calls": round(statistics.mean(tcs), 2),
            "median_tool_calls": round(statistics.median(tcs), 2),
            "mean_search_calls": round(statistics.mean(r["search_calls"] for r in sub), 2),
            "mean_read_calls": round(statistics.mean(r["read_calls"] for r in sub), 2),
            "total_duplicate_reads": sum(r["duplicate_reads"] for r in sub),
            "mean_input_tokens": round(statistics.mean(inp), 1),
            "median_input_tokens": round(statistics.median(inp), 1),
            "mean_cache_read_tokens": round(statistics.mean(cac), 1),
            "mean_output_tokens": round(statistics.mean(out), 1),
            "mean_payload_tokens": round(statistics.mean(r["payload_tokens"] for r in sub), 1),
            "mean_recall_gt": round(statistics.mean(r["recall_gt"] for r in sub), 4),
            "mean_precision_prod": round(statistics.mean(r["precision_prod"] for r in sub), 4),
            "mean_f1": round(statistics.mean(r["f1"] for r in sub), 4),
            "total_missed_gt": sum(len(r["missed_gt_files"]) for r in sub),
            "task_success_rate": round(sum(1 for r in sub if r["task_success"]) / n, 4),
        }

    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("\n--- PER TASK ---")
    for r in rows:
        print(
            f"{r['task_id']} {r['method']:11s} | ctx={r['time_to_relevant_context_s']:5.1f}s "
            f"e2e={r['time_to_completion_s']:5.1f}s | turns={r['llm_turns']:2d} tools={r['tool_calls']:2d} "
            f"(S={r['search_calls']},R={r['read_calls']},dup={r['duplicate_reads']}) | "
            f"in={r['input_tokens']:6d} cache={r['cache_read_tokens']:7d} out={r['output_tokens']:5d} | "
            f"R={r['recall_gt']:.2f} F1={r['f1']:.2f} missed={len(r['missed_gt_files'])} ok={r['task_success']}"
        )


if __name__ == "__main__":
    main()

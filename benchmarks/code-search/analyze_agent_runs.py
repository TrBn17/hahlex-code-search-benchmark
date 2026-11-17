import json
import re
from datetime import datetime
from pathlib import Path

import tiktoken

ROOT = Path(r"D:\Projects\hahlex-edu")
TASKS_FILE = ROOT / "benchmarks" / "code-search" / "tasks.json"
OUT_RESULTS = ROOT / "benchmarks" / "code-search" / "agent_results.json"
OUT_SUMMARY = ROOT / "benchmarks" / "code-search" / "agent_summary.json"

ENC = tiktoken.get_encoding("cl100k_base")

RUNS = [
    # T1
    ("T1", "baseline", "b025e2d2-cb03-4ebb-bf4a-63bfb01e19ae"),
    ("T1", "ripgrep", "8db781b5-b668-4e10-80ed-b4cd863c2179"),
    ("T1", "codegraph", "ce6f23ca-68e5-41b1-ab23-6bb18836d521"),
    ("T1", "adaptive", "3fbce30e-3cf4-4756-ad7e-3bee31b5d71d"),
    # T2
    ("T2", "baseline", "4742a5c8-7c96-4630-bdc3-643c7744cabe"),
    ("T2", "ripgrep", "4363c190-2e5d-4242-9892-386f8ea651b4"),
    ("T2", "codegraph", "93d83891-a930-4c14-be69-6898582425d1"),
    ("T2", "adaptive", "99040a22-c3f2-4f75-bc1e-50c4f207df89"),
    # T3
    ("T3", "baseline", "86000606-6d85-420d-b542-0cd1c46723f0"),
    ("T3", "ripgrep", "fbf6f021-200e-4e56-8edc-b7ffc808ee72"),
    ("T3", "codegraph", "ccf5fd6c-a5d1-46be-abf8-5dc44e7d8649"),
    ("T3", "adaptive", "6e6589eb-0155-4997-b3db-f4074b04b6fc"),
    # T4
    ("T4", "baseline", "1b087eda-7af0-430d-858b-7d0b19e4bfb6"),
    ("T4", "ripgrep", "36a6ee86-19b2-463f-b02a-93f5cf9e1582"),
    ("T4", "codegraph", "b0847e9e-3794-4360-93e2-36fd998ebe93"),
    ("T4", "adaptive", "c18aa98e-f1ad-438a-8b40-50f091059917"),
    # T5
    ("T5", "baseline", "be749d6c-b817-4c4a-b51a-026854eefd71"),
    ("T5", "ripgrep", "f458b8eb-45dc-4e76-bab4-30f08a8a6787"),
    ("T5", "codegraph", "79cac923-62fb-4816-bf5e-e1676a57e45b"),
    ("T5", "adaptive", "1528e33f-06d6-4f7c-93ac-4223f7fc0394"),
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
        p = m.replace("\\", "/")
        # Normalize if agent wrote apps/api/... without education-platform/ (not matched by regex)
        out.add(p)
    # Also catch apps/api/... or src/... relative to education-platform / ai-platform if mentioned
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
    # Find send_message step as completion
    t_end = parse_ts(steps[-1]["created_at"])
    final_msg = ""
    llm_turns = 0
    tool_calls_total = 0
    search_calls = 0
    read_calls = 0
    rg_calls = 0
    cg_calls = 0
    git_grep_calls = 0

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
            for c in s.get("tool_calls") or []:
                name = c.get("name", "")
                args_str = str(c.get("args", ""))
                if name == "send_message":
                    t_end = parse_ts(s["created_at"])
                    # extract message
                    m_arg = c.get("args", {}).get("Message", "")
                    if isinstance(m_arg, str):
                        final_msg = m_arg
                else:
                    tool_calls_total += 1
                    if name == "run_command":
                        search_calls += 1
                        if "codegraph" in args_str:
                            cg_calls += 1
                        if "rg" in args_str or "ripgrep" in args_str:
                            rg_calls += 1
                        if "git " in args_str and "grep" in args_str:
                            git_grep_calls += 1
                    elif name == "read_file":
                        read_calls += 1
        elif s.get("source") == "SYSTEM" or stype in ("TOOL_RESPONSE", "FUNCTION_RESPONSE"):
            content = s.get("content") or ""
            if isinstance(content, str):
                payload_tokens += count_tokens(content)
                found_here = extract_paths(content)
                seen_crit |= (found_here & crit)
                if t_rel_context is None and seen_crit == crit:
                    t_rel_context = (parse_ts(s["created_at"]) - t0).total_seconds()
        else:
            # Check content on any non-planner step (tool outputs)
            if s.get("step_index", 0) > 0 and s.get("type") != "USER_INPUT":
                content = s.get("content") or ""
                if isinstance(content, str):
                    payload_tokens += count_tokens(content)
                    found_here = extract_paths(content)
                    seen_crit |= (found_here & crit)
                    if t_rel_context is None and seen_crit == crit:
                        t_rel_context = (parse_ts(s["created_at"]) - t0).total_seconds()

    # Fallback if final_msg wasn't parsed from JSON stringified arg
    if not final_msg:
        for s in steps:
            for c in s.get("tool_calls") or []:
                if c.get("name") == "send_message":
                    raw = c.get("args", {}).get("Message", "")
                    if raw.startswith('"') and raw.endswith('"'):
                        try:
                            raw = json.loads(raw)
                        except Exception:
                            pass
                    final_msg = raw

    if final_msg.startswith('"') and final_msg.endswith('"'):
        try:
            final_msg = json.loads(final_msg)
        except Exception:
            pass

    reported_files = extract_paths(final_msg)
    # Only count production files against production ground truth (keep test files separate)
    reported_prod = {f for f in reported_files if ".spec." not in f and ".test." not in f and "/test/" not in f}
    tp = len(gt & reported_prod)
    missed = sorted(gt - reported_prod)
    crit_hit = crit.issubset(reported_prod)
    recall = tp / len(gt) if gt else 0.0
    precision = tp / len(reported_prod) if reported_prod else 0.0
    t_comp = (t_end - t0).total_seconds()
    if t_rel_context is None:
        t_rel_context = t_comp

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
        "rg_calls": rg_calls,
        "cg_calls": cg_calls,
        "git_grep_calls": git_grep_calls,
        "input_tokens": input_tokens,
        "cache_read_tokens": cache_read_tokens,
        "output_tokens": output_tokens,
        "total_api_tokens": input_tokens + output_tokens,
        "payload_tokens": payload_tokens,
        "gt_count": len(gt),
        "gt_found": tp,
        "reported_prod_count": len(reported_prod),
        "reported_total_count": len(reported_files),
        "precision_prod": round(precision, 4),
        "recall_gt": round(recall, 4),
        "missed_gt_files": missed,
        "critical_all_found": crit_hit,
        "task_success": crit_hit and recall >= 0.80,
    }


def main():
    tasks = {t["id"]: t for t in json.loads(TASKS_FILE.read_text(encoding="utf-8"))["tasks"]}
    rows = [analyze_run(tasks[tid], m, cid) for tid, m, cid in RUNS]
    OUT_RESULTS.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = {}
    for m in ("baseline", "ripgrep", "codegraph", "adaptive"):
        sub = [r for r in rows if r["method"] == m]
        n = len(sub)
        summary[m] = {
            "mean_time_to_context_s": round(sum(r["time_to_relevant_context_s"] for r in sub) / n, 2),
            "mean_time_to_completion_s": round(sum(r["time_to_completion_s"] for r in sub) / n, 2),
            "mean_llm_turns": round(sum(r["llm_turns"] for r in sub) / n, 2),
            "mean_tool_calls": round(sum(r["tool_calls"] for r in sub) / n, 2),
            "mean_search_calls": round(sum(r["search_calls"] for r in sub) / n, 2),
            "mean_read_calls": round(sum(r["read_calls"] for r in sub) / n, 2),
            "mean_input_tokens": round(sum(r["input_tokens"] for r in sub) / n, 1),
            "mean_cache_read_tokens": round(sum(r["cache_read_tokens"] for r in sub) / n, 1),
            "mean_output_tokens": round(sum(r["output_tokens"] for r in sub) / n, 1),
            "mean_payload_tokens": round(sum(r["payload_tokens"] for r in sub) / n, 1),
            "mean_recall_gt": round(sum(r["recall_gt"] for r in sub) / n, 4),
            "mean_precision_prod": round(sum(r["precision_prod"] for r in sub) / n, 4),
            "total_missed_gt": sum(len(r["missed_gt_files"]) for r in sub),
            "task_success_rate": round(sum(1 for r in sub if r["task_success"]) / n, 4),
        }

    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("\n--- PER TASK ---")
    for r in rows:
        print(
            f"{r['task_id']} {r['method']:9s} | ctx={r['time_to_relevant_context_s']:5.1f}s "
            f"e2e={r['time_to_completion_s']:5.1f}s | turns={r['llm_turns']:2d} tools={r['tool_calls']:2d} "
            f"(S={r['search_calls']},R={r['read_calls']}) | in={r['input_tokens']:6d} cache={r['cache_read_tokens']:6d} "
            f"out={r['output_tokens']:4d} | R={r['recall_gt']:.2f} missed={len(r['missed_gt_files'])} ok={r['task_success']}"
        )


if __name__ == "__main__":
    main()

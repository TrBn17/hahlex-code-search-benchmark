#!/usr/bin/env python3
"""Analyze Phase 4 (24-session) ripgrep vs Adaptive v1 benchmark transcripts."""

from __future__ import annotations

import json
import os
import re
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(r"D:\Projects\hahlex-edu")
TASKS_PATH = WORKSPACE_ROOT / "benchmarks" / "code-search" / "tasks.json"
PHASE4_DIR = WORKSPACE_ROOT / "benchmarks" / "code-search" / "phase4"
BRAIN_DIR = Path(r"C:\Users\Admin\.gemini\antigravity-cli\brain")

# (task_id, arm, rep, conversation_id, wave_order_idx)
SESSIONS: list[tuple[str, str, int, str, int]] = [
    # Wave 1: T2 [D, B, B, D, D, B]
    ("T2", "adaptive_v1", 1, "59a5ec2e-8105-44cc-a709-055ec2ee7249", 1),
    ("T2", "ripgrep", 1, "2f6c2814-5504-481c-b458-edf7183e9b38", 2),
    ("T2", "ripgrep", 2, "b8602594-be36-4624-8982-c0fd3bf5c016", 3),
    ("T2", "adaptive_v1", 2, "436a5130-2674-443c-92c1-02e7767a3f6a", 4),
    ("T2", "adaptive_v1", 3, "4a4e3525-48fc-48a4-9b70-a692282f31fc", 5),
    ("T2", "ripgrep", 3, "c902d574-7aa5-4a23-8067-1d75e3729ce9", 6),
    # Wave 2: T3 [B, D, D, B, B, D]
    ("T3", "ripgrep", 1, "ec88823a-1729-4832-aa77-4ea666715e97", 1),
    ("T3", "adaptive_v1", 1, "459ec14b-f364-43ac-879e-21cb26aa446d", 2),
    ("T3", "adaptive_v1", 2, "812a6ccc-b20c-43e3-adb2-077b8f85e823", 3),
    ("T3", "ripgrep", 2, "3705e7f9-dff4-4005-91d4-730d26250374", 4),
    ("T3", "ripgrep", 3, "38a076bf-309c-4f20-90dc-057c091d59c2", 5),
    ("T3", "adaptive_v1", 3, "a4bc2d6e-d4f1-455f-9838-bb0c41de9f27", 6),
    # Wave 3: T4 [D, D, B, D, B, B]
    ("T4", "adaptive_v1", 1, "58a0a233-08a9-4a09-b0d0-65afb35176e2", 1),
    ("T4", "adaptive_v1", 2, "aec0afe2-8b84-40ea-9f0d-6ff1fea7f877", 2),
    ("T4", "ripgrep", 1, "be3ebe1d-f07c-46e6-8104-0eff7257ae44", 3),
    ("T4", "adaptive_v1", 3, "b88917f3-b9a7-4cc4-a4a2-d077add6f1cb", 4),
    ("T4", "ripgrep", 2, "0c788092-25d4-4d9c-b17c-b43d21922361", 5),
    ("T4", "ripgrep", 3, "27048dbf-63f7-426a-9929-d28beba18420", 6),
    # Wave 4: T5 [B, D, B, B, D, D]
    ("T5", "ripgrep", 1, "608bf08a-da30-4084-aa81-402b79df51c9", 1),
    ("T5", "adaptive_v1", 1, "91cf35a0-601f-4776-a6b1-a986d5627b98", 2),
    ("T5", "ripgrep", 2, "76d07d94-2bfe-4133-80ee-2f063bea966b", 3),
    ("T5", "ripgrep", 3, "352e0148-c6e9-4b18-9be1-31f2677cff5b", 4),
    ("T5", "adaptive_v1", 2, "e12eebc2-0fa0-4cdb-ada3-0328ef09338c", 5),
    ("T5", "adaptive_v1", 3, "fa57ab55-dc6c-4bc4-9e9c-074fb7c8efba", 6),
]

PATH_RE = re.compile(
    r"(?:education-platform|ai-platform)/[A-Za-z0-9_.\-/]+\.(?:ts|tsx|py|js|jsx)"
)
SHORT_API_RE = re.compile(
    r"(?<![A-Za-z0-9_/\-])(apps/api/src/[A-Za-z0-9_.\-/]+\.(?:ts|tsx|js))"
)
SHORT_AI_RE = re.compile(
    r"(?<![A-Za-z0-9_/\-])(src/(?:ai_platform|education_ai|ai_engine)/[A-Za-z0-9_.\-/]+\.py)"
)


def parse_ts(iso_str: str | None) -> datetime | None:
    if not iso_str:
        return None
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))


def unquote_arg(val: Any) -> str:
    s = str(val or "").strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        try:
            decoded = json.loads(s)
            if isinstance(decoded, str):
                s = decoded
        except Exception:
            s = s[1:-1]
    return s


def norm_path(p: str) -> str:
    p = unquote_arg(p).replace("\\", "/").strip()
    for prefix in ("D:/Projects/hahlex-edu/", "d:/Projects/hahlex-edu/"):
        if p.startswith(prefix):
            p = p[len(prefix) :]
    if p.startswith("apps/api/"):
        p = "education-platform/" + p
    elif p.startswith("src/ai_platform/") or p.startswith("src/education_ai/") or p.startswith("src/ai_engine/"):
        p = "ai-platform/" + p
    return p


def load_transcript(conv_id: str) -> list[dict[str, Any]]:
    log_dir = BRAIN_DIR / conv_id / ".system_generated" / "logs"
    compact_path = log_dir / "transcript.jsonl"
    full_path = log_dir / "transcript_full.jsonl"

    compact_steps: list[dict[str, Any]] = []
    with compact_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                compact_steps.append(json.loads(line))

    needs_full = any(s.get("truncated_fields") for s in compact_steps)
    if not needs_full or not full_path.exists():
        return compact_steps

    full_by_idx: dict[int, dict[str, Any]] = {}
    with full_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                obj = json.loads(line)
                full_by_idx[obj["step_index"]] = obj

    merged: list[dict[str, Any]] = []
    for s in compact_steps:
        idx = s["step_index"]
        merged.append(full_by_idx.get(idx, s) if s.get("truncated_fields") else s)
    return merged


def extract_cited_files(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for pattern in (PATH_RE, SHORT_API_RE, SHORT_AI_RE):
        for m in pattern.findall(text):
            np = norm_path(m)
            if np not in seen:
                seen.add(np)
                found.append(np)
    return found


def score_task_quality(task_id: str, answer: str) -> dict[str, Any]:
    low = answer.lower()
    checks: dict[str, bool] = {}
    if task_id == "T2":
        checks = {
            "controller_endpoint": "gradebook.controller.ts" in answer and "publish" in low,
            "kernel_publish": "publish.ts" in answer and "publishgradebook" in low,
            "calc_or_load": ("calc.ts" in answer or "load.ts" in answer),
            "refusals_or_gates": "refusals.ts" in answer or "refusal" in low,
            "db_tables": "schema.ts" in answer and "gradebook_publications" in low,
        }
    elif task_id == "T3":
        checks = {
            "credit_metering": "ai-grading-credits.ts" in answer and "creditmetering" in low,
            "plan_features": "plan-features.ts" in answer and "planfeatures" in low,
            "feature_refusal": "feature-refusal.ts" in answer and "parsefeaturenotintoplan" not in low and ("parsefeaturenotinplan" in low or "feature_not_in_plan" in low),
            "client_bridge": "ai-platform.client.ts" in answer,
            "mismatch_explanation": ("fail-open" in low or "fail open" in low or "fails open" in low) and ("ttl" in low or "cache" in low),
        }
    elif task_id == "T4":
        checks = {
            "definition": "page-query.ts" in answer and "offsetpage" in low,
            "education_controllers": all(
                x in answer
                for x in (
                    "catalog.controller.ts",
                    "enrollment-lifecycle.controller.ts",
                    "staff.controller.ts",
                    "submission-staff.controller.ts",
                    "teacher-profiles.controller.ts",
                )
            ),
            "organizations_bridge": "member-page-query.ts" in answer and "onboarding.controller.ts" in answer,
            "platform_controllers": all(
                x in answer
                for x in (
                    "platform.controller.ts",
                    "platform-dashboard.controller.ts",
                    "platform-survey.controller.ts",
                    "platform-broadcasts.controller.ts",
                )
            ),
            "support_controllers": "support.controller.ts" in answer and "platform-support.controller.ts" in answer,
        }
    elif task_id == "T5":
        checks = {
            "ts_guard": "service-principal.guard.ts" in answer and "serviceauthenticator" in low,
            "ts_internal_controllers": all(
                x in answer
                for x in (
                    "internal-education.controller.ts",
                    "internal-imports.controller.ts",
                    "internal-lessons.controller.ts",
                    "internal-platform-events.controller.ts",
                    "internal-view-as.controller.ts",
                )
            ),
            "mcp_and_delegation": "mcp.controller.ts" in answer and "service-delegation.ts" in answer,
            "py_service_auth": "service_auth.py" in answer and "require_education_service" in low,
            "consistency_analysis": ("x-hahlex-service-authorization" in low) and ("authorization" in low),
        }
    passed = sum(1 for v in checks.values() if v)
    total = len(checks)
    return {
        "checks": checks,
        "score": passed,
        "max_score": total,
        "quality_pct": round(100.0 * passed / total, 1) if total else 0.0,
        "task_passed": passed == total and bool(answer.strip()),
    }


def summarize(vals: list[float | int]) -> dict[str, float]:
    if not vals:
        return {"mean": 0.0, "median": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": round(statistics.mean(vals), 3),
        "median": round(statistics.median(vals), 3),
        "min": round(min(vals), 3),
        "max": round(max(vals), 3),
    }


def analyze_session(
    task: dict[str, Any], arm: str, rep: int, conv_id: str, wave_order: int
) -> dict[str, Any]:
    steps = load_transcript(conv_id)
    gt_files = set(task["ground_truth_files"])
    crit_files = set(task["critical_files"])

    t0 = parse_ts(steps[0].get("created_at")) if steps else None
    send_msg_ts: datetime | None = None
    final_answer = ""

    planner_turns = 0
    input_tokens = 0
    cache_read_tokens = 0
    output_tokens = 0

    tool_calls_total = 0
    tool_breakdown = {
        "rg": 0,
        "codegraph": 0,
        "read_file": 0,
        "manage_task": 0,
        "send_message": 0,
        "other_cmd": 0,
    }
    codegraph_time_s = 0.0
    total_tool_overhead_s = 0.0
    time_to_relevant_context_s: float | None = None

    read_files_seq: list[str] = []
    read_file_ranges: list[tuple[str, int | None, int | None]] = []
    runtime_errors: list[str] = []
    protocol_violations: list[str] = []

    for idx, step in enumerate(steps):
        if step.get("status") == "ERROR":
            runtime_errors.append(f"step_{step.get('step_index')}_error")

        if step.get("type") == "PLANNER_RESPONSE":
            planner_turns += 1
            input_tokens += int(step.get("input_tokens") or 0)
            cache_read_tokens += int(step.get("cache_read_tokens") or 0)
            output_tokens += int(step.get("output_tokens") or 0)

            step_ts = parse_ts(step.get("created_at"))
            next_ts = parse_ts(steps[idx + 1].get("created_at")) if idx + 1 < len(steps) else None
            step_elapsed = (
                max(0.0, (next_ts - step_ts).total_seconds())
                if (step_ts and next_ts)
                else 0.0
            )

            tcalls = step.get("tool_calls") or []
            if tcalls:
                total_tool_overhead_s += step_elapsed

            has_cg_in_step = False
            for tc in tcalls:
                tool_calls_total += 1
                name = tc.get("name", "")
                args = tc.get("args") or {}

                if name == "read_file":
                    tool_breakdown["read_file"] += 1
                    p = norm_path(str(args.get("Path", "")))
                    read_files_seq.append(p)
                    read_file_ranges.append((p, args.get("StartLine"), args.get("EndLine")))
                    if p in gt_files and time_to_relevant_context_s is None and t0 and step_ts:
                        time_to_relevant_context_s = round((step_ts - t0).total_seconds(), 2)
                elif name == "run_command":
                    cmd = unquote_arg(args.get("CommandLine", ""))
                    if re.search(r"\bcodegraph\b", cmd.lower()):
                        tool_breakdown["codegraph"] += 1
                        has_cg_in_step = True
                        if arm == "ripgrep":
                            protocol_violations.append("used_codegraph_in_arm_b")
                    elif re.search(r"(?:^|[;&|\s])graphify(?:\s|$)", cmd.lower()):
                        protocol_violations.append("used_graphify")
                        tool_breakdown["other_cmd"] += 1
                    elif "rg" in cmd.lower() or "ripgrep" in cmd.lower():
                        tool_breakdown["rg"] += 1
                    else:
                        tool_breakdown["other_cmd"] += 1
                elif name == "manage_task":
                    tool_breakdown["manage_task"] += 1
                elif name == "send_message":
                    tool_breakdown["send_message"] += 1
                    msg = unquote_arg(args.get("Message", ""))
                    if len(msg) > len(final_answer):
                        final_answer = msg
                        send_msg_ts = step_ts
                else:
                    tool_breakdown["other_cmd"] += 1

            if has_cg_in_step:
                codegraph_time_s += step_elapsed

        # Also check tool responses (GENERIC steps) for first ground-truth hit in rg/codegraph output
        if step.get("type") == "GENERIC" and time_to_relevant_context_s is None and t0:
            step_ts = parse_ts(step.get("created_at"))
            content = str(step.get("content") or "")
            for gt in gt_files:
                if Path(gt).name in content and step_ts:
                    time_to_relevant_context_s = round((step_ts - t0).total_seconds(), 2)
                    break

    last_ts = send_msg_ts or (parse_ts(steps[-1].get("created_at")) if steps else None)
    e2e_duration_s = round((last_ts - t0).total_seconds(), 2) if (t0 and last_ts) else 0.0

    unique_files_read = len(set(read_files_seq))
    duplicate_file_reads = len(read_files_seq) - unique_files_read
    exact_duplicate_reads = len(read_file_ranges) - len(set(read_file_ranges))

    cited_files = extract_cited_files(final_answer)
    cited_gt_hits = len(set(cited_files) & gt_files)
    read_or_cited_gt = (set(cited_files) | set(read_files_seq)) & gt_files

    # Retrieval quality on cited files (consistent with Phase 3)
    precision = round(cited_gt_hits / len(cited_files), 4) if cited_files else 0.0
    recall = round(cited_gt_hits / len(gt_files), 4) if gt_files else 0.0
    f1 = (
        round(2 * precision * recall / (precision + recall), 4)
        if (precision + recall) > 0
        else 0.0
    )
    missed_critical = sorted(crit_files - set(cited_files))

    quality = score_task_quality(task["id"], final_answer)

    return {
        "task_id": task["id"],
        "arm": arm,
        "rep": rep,
        "wave_order": wave_order,
        "conversation_id": conv_id,
        "e2e_duration_s": e2e_duration_s,
        "time_to_relevant_context_s": time_to_relevant_context_s,
        "planner_turns": planner_turns,
        "tool_calls_total": tool_calls_total,
        "tool_breakdown": tool_breakdown,
        "codegraph_calls": tool_breakdown["codegraph"],
        "codegraph_time_s": round(codegraph_time_s, 2),
        "total_tool_overhead_s": round(total_tool_overhead_s, 2),
        "input_tokens": input_tokens,
        "cache_read_tokens": cache_read_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "api_cost_usd": "N/A",
        "total_read_calls": len(read_files_seq),
        "unique_files_read": unique_files_read,
        "duplicate_file_reads": duplicate_file_reads,
        "exact_duplicate_reads": exact_duplicate_reads,
        "cited_files_count": len(cited_files),
        "ground_truth_count": len(gt_files),
        "cited_gt_hits": cited_gt_hits,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "missed_critical_files": missed_critical,
        "missed_critical_count": len(missed_critical),
        "task_quality": quality,
        "task_passed": quality["task_passed"],
        "runtime_errors": runtime_errors,
        "protocol_violations": protocol_violations,
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {}
    metrics = [
        "e2e_duration_s",
        "time_to_relevant_context_s",
        "planner_turns",
        "tool_calls_total",
        "codegraph_calls",
        "codegraph_time_s",
        "total_tool_overhead_s",
        "input_tokens",
        "cache_read_tokens",
        "output_tokens",
        "total_tokens",
        "unique_files_read",
        "duplicate_file_reads",
        "precision",
        "recall",
        "f1",
        "missed_critical_count",
    ]
    out: dict[str, Any] = {
        "sessions": n,
        "task_pass_count": sum(1 for r in rows if r["task_passed"]),
        "task_pass_rate": round(sum(1 for r in rows if r["task_passed"]) / n, 4),
        "avg_quality_pct": round(
            statistics.mean(r["task_quality"]["quality_pct"] for r in rows), 2
        ),
        "runtime_error_sessions": sum(1 for r in rows if r["runtime_errors"]),
        "protocol_violation_sessions": sum(1 for r in rows if r["protocol_violations"]),
        "api_cost_usd": "N/A",
    }
    for m in metrics:
        vals = [r[m] for r in rows if r[m] is not None]
        out[m] = summarize(vals)
    return out


def main() -> None:
    PHASE4_DIR.mkdir(parents=True, exist_ok=True)
    tasks_data = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    tasks_by_id = {t["id"]: t for t in tasks_data["tasks"]}

    results: list[dict[str, Any]] = []
    for task_id, arm, rep, conv_id, wave_order in SESSIONS:
        results.append(
            analyze_session(tasks_by_id[task_id], arm, rep, conv_id, wave_order)
        )

    summary = {
        "meta": {
            "phase": "phase4",
            "model": "flash",
            "arms": ["ripgrep", "adaptive_v1"],
            "tasks": ["T2", "T3", "T4", "T5"],
            "repetitions_per_task_arm": 3,
            "total_sessions": len(results),
            "pricing_note": "N/A - internal Antigravity flash model token pricing is not exposed",
        },
        "overall_by_arm": {
            arm: aggregate([r for r in results if r["arm"] == arm])
            for arm in ("ripgrep", "adaptive_v1")
        },
        "by_task_and_arm": {
            f"{tid}_{arm}": aggregate(
                [r for r in results if r["task_id"] == tid and r["arm"] == arm]
            )
            for tid in ("T2", "T3", "T4", "T5")
            for arm in ("ripgrep", "adaptive_v1")
        },
    }

    (PHASE4_DIR / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (PHASE4_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("=== PHASE 4 OVERALL BY ARM ===")
    for arm in ("ripgrep", "adaptive_v1"):
        s = summary["overall_by_arm"][arm]
        print(
            f"{arm:12s} | n={s['sessions']} pass={s['task_pass_count']}/{s['sessions']} "
            f"| F1={s['f1']['mean']:.4f} (med {s['f1']['median']:.4f}) "
            f"| P={s['precision']['mean']:.4f} R={s['recall']['mean']:.4f} "
            f"| E2E={s['e2e_duration_s']['mean']:.1f}s (med {s['e2e_duration_s']['median']:.1f}s) "
            f"| Turns={s['planner_turns']['mean']:.1f} Tools={s['tool_calls_total']['mean']:.1f} "
            f"| CG={s['codegraph_calls']['mean']:.2f} ({s['codegraph_time_s']['mean']:.1f}s) "
            f"| InTok={s['input_tokens']['mean']:.0f} OutTok={s['output_tokens']['mean']:.0f} "
            f"| DupReads={s['duplicate_file_reads']['mean']:.2f} MissedCrit={s['missed_critical_count']['mean']:.2f}"
        )


    print("\n=== PHASE 4 BY TASK AND ARM ===")
    for tid in ("T2", "T3", "T4", "T5"):
        for arm in ("ripgrep", "adaptive_v1"):
            k = f"{tid}_{arm}"
            s = summary["by_task_and_arm"][k]
            print(
                f"{k:16s} | pass={s['task_pass_count']}/{s['sessions']} "
                f"| P={s['precision']['mean']:.3f} R={s['recall']['mean']:.3f} F1={s['f1']['mean']:.3f} "
                f"| ctx={s['time_to_relevant_context_s']['mean']:.1f}s (med {s['time_to_relevant_context_s']['median']:.1f}s) "
                f"| e2e={s['e2e_duration_s']['mean']:.1f}s (med {s['e2e_duration_s']['median']:.1f}s, {s['e2e_duration_s']['min']:.0f}-{s['e2e_duration_s']['max']:.0f}) "
                f"| turns={s['planner_turns']['mean']:.1f} tools={s['tool_calls_total']['mean']:.1f} "
                f"| in={s['input_tokens']['mean']:.0f} out={s['output_tokens']['mean']:.0f} "
                f"| dup={s['duplicate_file_reads']['mean']:.2f}"
            )


if __name__ == "__main__":
    main()

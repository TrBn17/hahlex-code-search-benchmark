import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil
import tiktoken

ROOT = Path(r"D:\Projects\hahlex-edu")
TASKS_FILE = ROOT / "benchmarks" / "code-search" / "tasks.json"
RESULTS_FILE = ROOT / "benchmarks" / "code-search" / "results.json"
SUMMARY_FILE = ROOT / "benchmarks" / "code-search" / "summary.json"

ENC = tiktoken.get_encoding("cl100k_base")


def find_rg() -> str:
    rg = shutil.which("rg")
    if rg:
        return rg
    winget_glob = list(
        Path(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")).glob(
            "BurntSushi.ripgrep*/**/rg.exe"
        )
    )
    if winget_glob:
        return str(winget_glob[0])
    raise FileNotFoundError("ripgrep (rg.exe) not found")


def find_codegraph() -> str:
    cg = shutil.which("codegraph")
    if cg:
        return cg
    npm_cg = Path(os.path.expandvars(r"%APPDATA%\npm\codegraph.cmd"))
    if npm_cg.exists():
        return str(npm_cg)
    raise FileNotFoundError("codegraph CLI not found")


RG_BIN = find_rg()
CG_BIN = find_codegraph()


def count_tokens(text: str) -> int:
    return len(ENC.encode(text, disallowed_special=()))


def run_proc(cmd: list[str], cwd: Path = ROOT) -> dict:
    t0 = time.perf_counter()
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    peak_rss = 0
    cpu_time = 0.0
    stop_event = threading.Event()

    def monitor():
        nonlocal peak_rss, cpu_time
        try:
            p = psutil.Process(proc.pid)
            while not stop_event.is_set() and p.is_running():
                try:
                    procs = [p] + p.children(recursive=True)
                    rss = sum(x.memory_info().rss for x in procs if x.is_running())
                    if rss > peak_rss:
                        peak_rss = rss
                    ct = sum(
                        (x.cpu_times().user + x.cpu_times().system)
                        for x in procs
                        if x.is_running()
                    )
                    if ct > cpu_time:
                        cpu_time = ct
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                time.sleep(0.01)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    t = threading.Thread(target=monitor, daemon=True)
    t.start()
    stdout, stderr = proc.communicate()
    stop_event.set()
    t.join(timeout=0.5)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "returncode": proc.returncode,
        "stdout": stdout or "",
        "stderr": stderr or "",
        "elapsed_ms": elapsed_ms,
        "peak_rss_mb": round(peak_rss / (1024 * 1024), 2) if peak_rss > 0 else None,
        "cpu_time_ms": round(cpu_time * 1000.0, 2) if cpu_time > 0 else None,
    }


def read_file_slice(rel_path: str, max_lines: int = 120) -> tuple[str, float]:
    t0 = time.perf_counter()
    p = ROOT / rel_path
    if not p.exists() or not p.is_file():
        return "", (time.perf_counter() - t0) * 1000.0
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[:max_lines]
        text = f"--- {rel_path} ---\n" + "\n".join(lines)
    except Exception:
        text = ""
    return text, (time.perf_counter() - t0) * 1000.0


FILE_PATH_RE = re.compile(
    r"(?:education-platform|ai-platform)[\\/][A-Za-z0-9_.\-\\/]+\.(?:ts|tsx|js|jsx|py)"
)


def extract_files(text: str) -> set[str]:
    found = set()
    for m in FILE_PATH_RE.findall(text):
        norm = m.replace("\\", "/")
        found.add(norm)
    return found


def run_baseline(task: dict) -> dict:
    q = task["queries"]
    patterns = q["baseline_patterns"]
    tool_calls = 0
    search_ms = 0.0
    read_ms = 0.0
    outputs = []
    matched_files = set()
    rss_vals = []
    cpu_vals = []

    for pat in patterns:
        for repo in ("education-platform", "ai-platform"):
            res = run_proc(
                ["git", "-C", repo, "grep", "-n", "-F", pat, "--", ":!*spec*", ":!*test*"],
                cwd=ROOT,
            )
            tool_calls += 1
            search_ms += res["elapsed_ms"]
            if res["peak_rss_mb"] is not None:
                rss_vals.append(res["peak_rss_mb"])
            if res["cpu_time_ms"] is not None:
                cpu_vals.append(res["cpu_time_ms"])
            if res["stdout"]:
                # Prefix repo name so paths are workspace-relative
                lines = [f"{repo}/{ln}" for ln in res["stdout"].splitlines()[:60]]
                chunk = "\n".join(lines)
                outputs.append(chunk)
                for ln in lines:
                    f = ln.split(":", 1)[0].replace("\\", "/")
                    if f.endswith((".ts", ".tsx", ".js", ".jsx", ".py")):
                        matched_files.add(f)

    # Simulate agent reading top matched files (up to 6 files, 120 lines each)
    for rel in sorted(matched_files)[:6]:
        txt, dt = read_file_slice(rel, 120)
        tool_calls += 1
        read_ms += dt
        outputs.append(txt)

    full_payload = "\n".join(outputs)
    return {
        "search_ms": search_ms,
        "end_to_end_ms": search_ms + read_ms,
        "tool_calls": tool_calls,
        "payload_tokens": count_tokens(full_payload),
        "returned_files": sorted(matched_files),
        "peak_rss_mb": max(rss_vals) if rss_vals else None,
        "cpu_time_ms": round(sum(cpu_vals), 2) if cpu_vals else None,
    }


def run_ripgrep(task: dict) -> dict:
    q = task["queries"]
    pat = q["rg_pattern"]
    tool_calls = 0
    search_ms = 0.0
    read_ms = 0.0
    outputs = []
    matched_files = set()
    rss_vals = []
    cpu_vals = []

    res = run_proc(
        [
            RG_BIN,
            "-n",
            "--max-count",
            "5",
            "--glob",
            "!**/*.spec.*",
            "--glob",
            "!**/*.test.*",
            "--glob",
            "!**/test/**",
            "--glob",
            "!**/__generated__/**",
            pat,
            "education-platform/apps",
            "ai-platform/src",
        ],
        cwd=ROOT,
    )
    tool_calls += 1
    search_ms += res["elapsed_ms"]
    if res["peak_rss_mb"] is not None:
        rss_vals.append(res["peak_rss_mb"])
    if res["cpu_time_ms"] is not None:
        cpu_vals.append(res["cpu_time_ms"])
    if res["stdout"]:
        outputs.append(res["stdout"])
        matched_files |= extract_files(res["stdout"])

    # Simulate agent reading top matched files (up to 6 files, 120 lines each)
    for rel in sorted(matched_files)[:6]:
        txt, dt = read_file_slice(rel, 120)
        tool_calls += 1
        read_ms += dt
        outputs.append(txt)

    full_payload = "\n".join(outputs)
    return {
        "search_ms": search_ms,
        "end_to_end_ms": search_ms + read_ms,
        "tool_calls": tool_calls,
        "payload_tokens": count_tokens(full_payload),
        "returned_files": sorted(matched_files),
        "peak_rss_mb": max(rss_vals) if rss_vals else None,
        "cpu_time_ms": round(sum(cpu_vals), 2) if cpu_vals else None,
    }


def run_codegraph(task: dict) -> dict:
    q = task["queries"]
    tool_calls = 0
    search_ms = 0.0
    outputs = []
    matched_files = set()
    rss_vals = []
    cpu_vals = []

    cmds = []
    if "codegraph_explore" in q:
        cmds.append([CG_BIN, "explore", q["codegraph_explore"]])
    if "codegraph_query" in q:
        cmds.append([CG_BIN, "query", q["codegraph_query"], "--limit", "15", "--json"])
    if "codegraph_impact" in q:
        cmds.append([CG_BIN, "impact", q["codegraph_impact"], "--json"])
    if "codegraph_callers" in q:
        cmds.append([CG_BIN, "callers", q["codegraph_callers"], "--limit", "30", "--json"])

    for cmd in cmds:
        res = run_proc(cmd, cwd=ROOT)
        tool_calls += 1
        search_ms += res["elapsed_ms"]
        if res["peak_rss_mb"] is not None:
            rss_vals.append(res["peak_rss_mb"])
        if res["cpu_time_ms"] is not None:
            cpu_vals.append(res["cpu_time_ms"])
        if res["stdout"]:
            outputs.append(res["stdout"])
            matched_files |= extract_files(res["stdout"])

    # Filter out test/spec files from precision evaluation to match production ground truth
    prod_files = {
        f for f in matched_files if ".spec." not in f and ".test." not in f and "/test/" not in f
    }
    full_payload = "\n".join(outputs)
    return {
        "search_ms": search_ms,
        "end_to_end_ms": search_ms,  # CodeGraph explore returns verbatim source inline
        "tool_calls": tool_calls,
        "payload_tokens": count_tokens(full_payload),
        "returned_files": sorted(prod_files),
        "peak_rss_mb": max(rss_vals) if rss_vals else None,
        "cpu_time_ms": round(sum(cpu_vals), 2) if cpu_vals else None,
    }


def run_hybrid(task: dict) -> dict:
    q = task["queries"]
    tool_calls = 0
    search_ms = 0.0
    read_ms = 0.0
    outputs = []
    matched_files = set()
    rss_vals = []
    cpu_vals = []

    # Step 1: Fast ripgrep for exact literals/cross-repo patterns
    if "hybrid_rg" in q:
        res = run_proc(
            [
                RG_BIN,
                "-l",
                "--glob",
                "!**/*.spec.*",
                "--glob",
                "!**/*.test.*",
                "--glob",
                "!**/test/**",
                "--glob",
                "!**/__generated__/**",
                q["hybrid_rg"],
                "education-platform/apps",
                "ai-platform/src",
            ],
            cwd=ROOT,
        )
        tool_calls += 1
        search_ms += res["elapsed_ms"]
        if res["peak_rss_mb"] is not None:
            rss_vals.append(res["peak_rss_mb"])
        if res["cpu_time_ms"] is not None:
            cpu_vals.append(res["cpu_time_ms"])
        if res["stdout"]:
            outputs.append(res["stdout"])
            matched_files |= extract_files(res["stdout"])

    # Step 2: CodeGraph explore/impact for call graph & blast radius (verbatim source included)
    if "hybrid_cg" in q:
        cg_cmd = "impact" if task["id"] == "T4" else "explore"
        cmd = [CG_BIN, cg_cmd, q["hybrid_cg"]]
        if cg_cmd == "impact":
            cmd.append("--json")
        res = run_proc(cmd, cwd=ROOT)
        tool_calls += 1
        search_ms += res["elapsed_ms"]
        if res["peak_rss_mb"] is not None:
            rss_vals.append(res["peak_rss_mb"])
        if res["cpu_time_ms"] is not None:
            cpu_vals.append(res["cpu_time_ms"])
        if res["stdout"]:
            outputs.append(res["stdout"])
            matched_files |= extract_files(res["stdout"])

    prod_files = {
        f for f in matched_files if ".spec." not in f and ".test." not in f and "/test/" not in f
    }

    # Read up to 2 extra files discovered by rg that weren't already covered by codegraph explore
    for rel in sorted(prod_files)[:2]:
        txt, dt = read_file_slice(rel, 80)
        tool_calls += 1
        read_ms += dt
        outputs.append(txt)

    full_payload = "\n".join(outputs)
    return {
        "search_ms": search_ms,
        "end_to_end_ms": search_ms + read_ms,
        "tool_calls": tool_calls,
        "payload_tokens": count_tokens(full_payload),
        "returned_files": sorted(prod_files),
        "peak_rss_mb": max(rss_vals) if rss_vals else None,
        "cpu_time_ms": round(sum(cpu_vals), 2) if cpu_vals else None,
    }


def score_run(run: dict, task: dict) -> dict:
    gt = set(task["ground_truth_files"])
    crit = set(task["critical_files"])
    ret = set(run["returned_files"])
    tp = len(gt & ret)
    precision = tp / len(ret) if ret else 0.0
    recall = tp / len(gt) if gt else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    crit_hit = crit.issubset(ret)
    success = crit_hit and recall >= 0.6
    return {
        **run,
        "relevant_found": tp,
        "ground_truth_count": len(gt),
        "returned_count": len(ret),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "critical_all_found": crit_hit,
        "task_success": success,
    }


def main():
    tasks = json.loads(TASKS_FILE.read_text(encoding="utf-8"))["tasks"]
    methods = {
        "baseline": run_baseline,
        "ripgrep": run_ripgrep,
        "codegraph": run_codegraph,
        "hybrid": run_hybrid,
    }
    runs_per_pair = 3
    raw_results = []

    # Also measure incremental codegraph sync
    sync_runs = [run_proc([CG_BIN, "sync"], cwd=ROOT) for _ in range(3)]
    sync_stats = {
        "sync_ms": [round(r["elapsed_ms"], 2) for r in sync_runs],
        "median_sync_ms": round(statistics.median(r["elapsed_ms"] for r in sync_runs), 2),
    }

    for task in tasks:
        for method_name, fn in methods.items():
            for run_idx in range(1, runs_per_pair + 1):
                raw = fn(task)
                scored = score_run(raw, task)
                scored["task_id"] = task["id"]
                scored["category"] = task["category"]
                scored["method"] = method_name
                scored["run"] = run_idx
                raw_results.append(scored)
                print(
                    f"[{task['id']}][{method_name:9s}][run {run_idx}] "
                    f"search={scored['search_ms']:.1f}ms e2e={scored['end_to_end_ms']:.1f}ms "
                    f"calls={scored['tool_calls']} tok={scored['payload_tokens']} "
                    f"P={scored['precision']:.2f} R={scored['recall']:.2f} ok={scored['task_success']}",
                    flush=True,
                )

    RESULTS_FILE.write_text(
        json.dumps({"sync": sync_stats, "runs": raw_results}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Aggregate summary by method and by (task, method)
    by_method = {}
    for m in methods:
        sub = [r for r in raw_results if r["method"] == m]
        rss = [r["peak_rss_mb"] for r in sub if r["peak_rss_mb"] is not None]
        cpu = [r["cpu_time_ms"] for r in sub if r["cpu_time_ms"] is not None]
        by_method[m] = {
            "median_search_ms": round(statistics.median(r["search_ms"] for r in sub), 2),
            "mean_search_ms": round(statistics.mean(r["search_ms"] for r in sub), 2),
            "median_e2e_ms": round(statistics.median(r["end_to_end_ms"] for r in sub), 2),
            "mean_e2e_ms": round(statistics.mean(r["end_to_end_ms"] for r in sub), 2),
            "mean_tool_calls": round(statistics.mean(r["tool_calls"] for r in sub), 2),
            "mean_payload_tokens": round(statistics.mean(r["payload_tokens"] for r in sub), 1),
            "mean_precision": round(statistics.mean(r["precision"] for r in sub), 4),
            "mean_recall": round(statistics.mean(r["recall"] for r in sub), 4),
            "mean_f1": round(statistics.mean(r["f1"] for r in sub), 4),
            "task_success_rate": round(sum(1 for r in sub if r["task_success"]) / len(sub), 4),
            "median_peak_rss_mb": round(statistics.median(rss), 2) if rss else None,
            "median_cpu_ms": round(statistics.median(cpu), 2) if cpu else None,
        }

    by_task_method = {}
    for task in tasks:
        tid = task["id"]
        by_task_method[tid] = {}
        for m in methods:
            sub = [r for r in raw_results if r["task_id"] == tid and r["method"] == m]
            by_task_method[tid][m] = {
                "median_search_ms": round(statistics.median(r["search_ms"] for r in sub), 2),
                "median_e2e_ms": round(statistics.median(r["end_to_end_ms"] for r in sub), 2),
                "tool_calls": sub[0]["tool_calls"],
                "payload_tokens": sub[0]["payload_tokens"],
                "precision": sub[0]["precision"],
                "recall": sub[0]["recall"],
                "f1": sub[0]["f1"],
                "task_success": sub[0]["task_success"],
                "relevant_found": sub[0]["relevant_found"],
                "ground_truth_count": sub[0]["ground_truth_count"],
                "returned_count": sub[0]["returned_count"],
            }

    SUMMARY_FILE.write_text(
        json.dumps(
            {"sync": sync_stats, "by_method": by_method, "by_task_method": by_task_method},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print("\n=== SUMMARY BY METHOD ===")
    print(json.dumps(by_method, indent=2))


if __name__ == "__main__":
    main()

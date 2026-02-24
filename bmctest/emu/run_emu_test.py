#!/usr/bin/env python3
"""
Batch EMU/fuzzer test runner for standalone rocket-chip modules.

Workflow per module:
  1. Build the fuzzer (or EMU) binary via bmctest/emu/Makefile
  2. Run the binary with specified parameters
  3. Parse coverage output from stderr
  4. Collect results into a JSON report

Usage:
  python run_emu_test.py --module timer --max-cycles 10000
  python run_emu_test.py --all --jobs 8
  python run_emu_test.py --module broadcast --mode emu -v trace.vcd
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
MAKEFILE = SCRIPT_DIR / "Makefile"
BUILD_BASE = SCRIPT_DIR.parent / "build"

MODULE_CONFIG: Dict[str, Tuple[str, str]] = {
    "broadcast":   ("StandaloneBroadcast.sv",  "StandaloneBroadcast"),
    "xbar":        ("StandaloneXbar.sv",       "StandaloneXbar"),
    "plic":        ("StandalonePLIC.sv",       "StandalonePLIC"),
    "sram_ecc":    ("StandaloneSRAMECC.sv",    "StandaloneSRAMECC"),
    "toaxi4":      ("StandaloneToAXI4.sv",     "StandaloneToAXI4"),
    "fragmenter":  ("StandaloneFragmenter.sv", "StandaloneFragmenter"),
    "atomic":      ("StandaloneAtomic.sv",     "StandaloneAtomic"),
    "timer":       ("Timer.sv",                "Timer"),
    "idpool":      ("IDPool.sv",               "IDPool"),
    "jtag_fsm":    ("JtagStateMachine.sv",     "JtagStateMachine"),
    "arbiter":     ("HellaCountingArbiter.sv", "HellaCountingArbiter"),
    "reorder_q":   ("ReorderQueue.sv",         "ReorderQueue"),
    "ecc":         ("ECCModule.sv",            "ECCModule"),
    "replacement": ("ReplacementModule.sv",    "ReplacementModule"),
}

EXCLUDED_MODULES = {"axi4xbar", "async_queue"}

ALL_MODULES = sorted(k for k in MODULE_CONFIG if k not in EXCLUDED_MODULES)

# Standalone modules have built-in stimulus (io_start/io_finished)
STANDALONE_MODULES = {
    "broadcast", "xbar", "plic", "sram_ecc", "toaxi4", "fragmenter", "atomic",
}


def _parse_coverage(stderr_text: str) -> Dict[str, dict]:
    """
    Parse COVERAGE lines from emulator stderr.

    Expected format:
        COVERAGE: <type>, <hit> / <total> (<pct>%)
        COVERAGE TOTAL: <hit> / <total> (<pct>%)
    """
    result: Dict[str, dict] = {}

    for m in re.finditer(
        r"COVERAGE:\s+(\w+),\s+(\d+)\s*/\s*(\d+)\s*\(([0-9.]+)%\)", stderr_text
    ):
        name = m.group(1)
        hit = int(m.group(2))
        total = int(m.group(3))
        pct = float(m.group(4))
        result[name] = {"hit": hit, "total": total, "pct": pct}

    m_total = re.search(
        r"COVERAGE TOTAL:\s+(\d+)\s*/\s*(\d+)\s*\(([0-9.]+)%\)", stderr_text
    )
    if m_total:
        result["_total"] = {
            "hit": int(m_total.group(1)),
            "total": int(m_total.group(2)),
            "pct": float(m_total.group(3)),
        }

    return result


def build_module(
    module: str,
    mode: str = "fuzzer",
    trace: bool = False,
) -> Tuple[bool, str]:
    """Build the EMU or fuzzer binary for a module."""
    target = "fuzzer" if mode == "fuzzer" else "emu"
    cmd = [
        "make", "-f", str(MAKEFILE),
        target,
        f"MODULE={module}",
    ]
    if mode == "fuzzer":
        cmd.append("BMCFUZZ=1")
    if trace:
        cmd.append("EMU_TRACE=1")

    proc = subprocess.run(
        cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT),
    )
    if proc.returncode != 0:
        return False, proc.stderr
    return True, ""


def run_module(
    module: str,
    mode: str = "fuzzer",
    max_cycles: int = 10000,
    fuzz_iters: int = 100,
    timeout_secs: int = 300,
    input_file: Optional[str] = None,
    vcd_file: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
) -> dict:
    """Run a single module's EMU/fuzzer and collect results."""
    if mode == "fuzzer":
        binary = BUILD_BASE / module / "fuzzer"
    else:
        binary = BUILD_BASE / module / "emu"

    if not binary.exists():
        return {
            "module": module,
            "status": "BUILD_MISSING",
            "error": f"Binary not found: {binary}",
        }

    cmd = [str(binary)]

    if mode == "emu":
        cmd.extend(["-m", str(max_cycles)])
        if input_file:
            cmd.extend(["-i", input_file])
        if vcd_file:
            cmd.extend(["-v", vcd_file])
    else:
        corpus_arg = input_file if input_file else "random"
        cmd.extend(["--fuzzing", "--only-fuzz", "--continue-on-errors",
                    f"--max-iters={fuzz_iters}",
                    f"--corpus-input={corpus_arg}",
                    "--", "-m", str(max_cycles)])

    if extra_args:
        cmd.extend(extra_args)

    env = os.environ.copy()
    if mode == "fuzzer":
        build_dir = BUILD_BASE / module
        env.setdefault("COVER_POINTS_OUT", str(build_dir))
        env.setdefault("NOOP_HOME", str(build_dir))
        (build_dir / "tmp").mkdir(parents=True, exist_ok=True)
        (build_dir / "corpus").mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_secs,
            cwd=str(BUILD_BASE / module),
            env=env,
        )
        elapsed = round(time.time() - t0, 2)
        exit_code = proc.returncode
        stderr_text = proc.stderr
    except subprocess.TimeoutExpired:
        elapsed = round(time.time() - t0, 2)
        return {
            "module": module,
            "status": "TIMEOUT",
            "elapsed_secs": elapsed,
            "timeout_limit": timeout_secs,
        }
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        return {
            "module": module,
            "status": "ERROR",
            "error": str(e),
            "elapsed_secs": elapsed,
        }

    coverage = _parse_coverage(stderr_text)

    if exit_code == 0:
        status = "PASS"
    elif exit_code == 2:
        status = "TIMEOUT_SIM"
    else:
        status = "FAIL"

    return {
        "module": module,
        "status": status,
        "exit_code": exit_code,
        "elapsed_secs": elapsed,
        "max_cycles": max_cycles,
        "coverage": coverage,
        "stderr_tail": stderr_text[-500:] if stderr_text else "",
    }


def run_pipeline(
    module: str,
    mode: str = "fuzzer",
    max_cycles: int = 10000,
    fuzz_iters: int = 100,
    timeout_secs: int = 300,
    skip_build: bool = False,
    trace: bool = False,
    input_file: Optional[str] = None,
    vcd_file: Optional[str] = None,
) -> dict:
    """Full pipeline: build → run → collect for one module."""
    print(f"[{module}] {'=' * 50}")

    if not skip_build:
        print(f"[{module}] Building {mode}...")
        ok, err = build_module(module, mode=mode, trace=trace)
        if not ok:
            print(f"[{module}] BUILD FAILED")
            if err:
                for line in err.strip().split("\n")[-10:]:
                    print(f"  {line}")
            return {
                "module": module,
                "status": "BUILD_FAILED",
                "error": err[-500:] if err else "",
            }
        print(f"[{module}] Build OK")

    print(f"[{module}] Running ({mode}, max_cycles={max_cycles}, "
          f"fuzz_iters={fuzz_iters})...")
    result = run_module(
        module,
        mode=mode,
        max_cycles=max_cycles,
        fuzz_iters=fuzz_iters,
        timeout_secs=timeout_secs,
        input_file=input_file,
        vcd_file=vcd_file,
    )

    cov = result.get("coverage", {})
    if "_total" in cov:
        t = cov["_total"]
        print(f"[{module}] Coverage: {t['hit']}/{t['total']} ({t['pct']:.1f}%)")
    elif cov:
        for name, c in cov.items():
            print(f"[{module}] {name}: {c['hit']}/{c['total']} ({c['pct']:.1f}%)")

    print(f"[{module}] Status: {result['status']} "
          f"({result.get('elapsed_secs', '?')}s)")
    return result


def print_summary(results: List[dict]) -> None:
    """Print a cross-module summary table."""
    W = 70
    print(f"\n{'=' * W}")
    print("  Module EMU/Fuzzer — Summary")
    print(f"{'=' * W}")

    hdr = (f"  {'Module':<15s} {'Status':<12s} {'Time':>8s} "
           f"{'Hit':>6s} {'Total':>6s} {'Rate':>7s}")
    print(hdr)
    print(f"  {'-' * 15} {'-' * 12} {'-' * 8} {'-' * 6} {'-' * 6} {'-' * 7}")

    for r in sorted(results, key=lambda x: x["module"]):
        cov = r.get("coverage", {}).get("_total", {})
        hit = cov.get("hit", "—")
        total = cov.get("total", "—")
        pct = f"{cov['pct']:.1f}%" if "pct" in cov else "—"
        elapsed = r.get("elapsed_secs", "—")
        if isinstance(elapsed, (int, float)):
            elapsed = f"{elapsed:.1f}s"

        print(f"  {r['module']:<15s} {r['status']:<12s} {elapsed:>8s} "
              f"{str(hit):>6s} {str(total):>6s} {pct:>7s}")

    passed = sum(1 for r in results if r["status"] == "PASS")
    print(f"\n  {passed}/{len(results)} modules PASSED")
    print(f"{'=' * W}")


def save_report(results: List[dict], output_path: Path) -> None:
    """Save results as JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Report saved: {output_path}")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Batch EMU/fuzzer runner for standalone rocket-chip modules",
    )
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument(
        "--module", choices=sorted(MODULE_CONFIG.keys()),
        help="Test a single module",
    )
    grp.add_argument(
        "--all", action="store_true",
        help="Test all 14 modules",
    )

    p.add_argument("--mode", choices=["fuzzer", "emu"], default="fuzzer",
                   help="Run mode (default: fuzzer)")
    p.add_argument("--max-cycles", type=int, default=10000,
                   help="Max simulation cycles per iteration (default: 10000)")
    p.add_argument("--fuzz-iters", type=int, default=100,
                   help="Fuzzer iteration count (fuzzer mode only, default: 100)")
    p.add_argument("--timeout", type=int, default=300,
                   help="Per-module wall-clock timeout in seconds (default: 300)")
    p.add_argument("--jobs", "-j", type=int, default=1,
                   help="Parallel module count (default: 1, only with --all)")
    p.add_argument("--skip-build", action="store_true",
                   help="Skip build step (use existing binaries)")
    p.add_argument("--trace", action="store_true",
                   help="Enable VCD trace (EMU mode)")
    p.add_argument("-i", "--input", default=None,
                   help="Input binary file for fuzz bytes")
    p.add_argument("-v", "--vcd", default=None,
                   help="VCD output file (EMU mode)")
    p.add_argument("--report", type=Path,
                   default=SCRIPT_DIR.parent / "reports" / "emu_results.json",
                   help="JSON report output path")
    return p


def main():
    args = build_arg_parser().parse_args()

    modules = ALL_MODULES if args.all else [args.module]

    results: List[dict] = []

    if args.jobs > 1 and len(modules) > 1:
        max_workers = min(args.jobs, len(modules), os.cpu_count() or 1)
        print(f"Running {len(modules)} modules with {max_workers} workers\n")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    run_pipeline,
                    mod,
                    mode=args.mode,
                    max_cycles=args.max_cycles,
                    fuzz_iters=args.fuzz_iters,
                    timeout_secs=args.timeout,
                    skip_build=args.skip_build,
                    trace=args.trace,
                    input_file=args.input,
                ): mod
                for mod in modules
            }
            for future in as_completed(futures):
                mod = futures[future]
                try:
                    result = future.result()
                except Exception as e:
                    result = {"module": mod, "status": "ERROR", "error": str(e)}
                results.append(result)
    else:
        for mod in modules:
            result = run_pipeline(
                mod,
                mode=args.mode,
                max_cycles=args.max_cycles,
                fuzz_iters=args.fuzz_iters,
                timeout_secs=args.timeout,
                skip_build=args.skip_build,
                trace=args.trace,
                input_file=args.input,
                vcd_file=args.vcd,
            )
            results.append(result)

    if len(results) > 1:
        print_summary(results)

    save_report(results, args.report)


if __name__ == "__main__":
    main()

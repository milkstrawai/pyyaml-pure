#!/usr/bin/env python3
"""
Comprehensive comparison of PyYAML vs PyYAML-Pure.

This script runs both performance benchmarks and test suite comparisons,
producing a complete report of both implementations.

Usage:
    python benchmarks/compare_all.py [--iterations N]
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_benchmarks(iterations: int = 5) -> dict:
    """Run performance benchmarks."""
    print("=" * 70)
    print("PERFORMANCE BENCHMARKS")
    print("=" * 70)

    benchmark_script = Path(__file__).parent / "run_benchmark.py"
    result = subprocess.run(
        [sys.executable, str(benchmark_script), str(iterations)],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    # Load results
    results_file = Path(__file__).parent / "benchmark_results.json"
    if results_file.exists():
        return json.loads(results_file.read_text())
    return {}


def run_test_suite_comparison() -> dict:
    """Run test suite comparison."""
    print("\n" + "=" * 70)
    print("TEST SUITE COMPARISON")
    print("=" * 70)

    comparison_script = Path(__file__).parent.parent / "tests" / "test_implementation_comparison.py"
    result = subprocess.run(
        [sys.executable, str(comparison_script)],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    # Parse results from output
    lines = result.stdout.split("\n")
    results = {
        "pyyaml": {"passed": 0, "failed": 0, "skipped": 0, "pass_rate": 0.0},
        "pure": {"passed": 0, "failed": 0, "skipped": 0, "pass_rate": 0.0},
    }

    for line in lines:
        if "Pass Rate" in line and "%" in line:
            # Line format: "Pass Rate                   76.3%           93.5%          +17.2%"
            parts = [p for p in line.split() if "%" in p]
            if len(parts) >= 2:
                try:
                    results["pyyaml"]["pass_rate"] = float(parts[0].rstrip("%"))
                    results["pure"]["pass_rate"] = float(parts[1].rstrip("%"))
                except ValueError:
                    pass
        elif "Passed" in line:
            parts = line.split()
            for i, part in enumerate(parts):
                try:
                    val = int(part)
                    if results["pyyaml"]["passed"] == 0:
                        results["pyyaml"]["passed"] = val
                    elif results["pure"]["passed"] == 0:
                        results["pure"]["passed"] = val
                    break
                except ValueError:
                    continue

    return results


def generate_report(benchmark_results: dict, test_results: dict) -> str:
    """Generate comprehensive markdown report."""
    lines = []
    lines.append("# PyYAML vs PyYAML-Pure Comprehensive Comparison\n")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Platform:** {platform.platform()}")
    lines.append(f"**Python:** {platform.python_version()}\n")

    # Executive Summary
    lines.append("## Executive Summary\n")
    lines.append("| Aspect | PyYAML | PyYAML-Pure | Winner |")
    lines.append("|--------|--------|-------------|--------|")

    # Performance
    if benchmark_results.get("results"):
        valid = [r for r in benchmark_results["results"] if r.get("speedup", 0) > 0]
        if valid:
            avg_speedup = sum(r["speedup"] for r in valid) / len(valid)
            if avg_speedup > 1:
                perf_winner = "PyYAML-Pure"
                perf_desc = f"{avg_speedup:.1f}x faster"
            else:
                perf_winner = "PyYAML"
                perf_desc = f"{1/avg_speedup:.1f}x faster"
            lines.append(f"| Performance | {perf_desc if perf_winner == 'PyYAML' else '-'} | {perf_desc if perf_winner == 'PyYAML-Pure' else '-'} | **{perf_winner}** |")

    # Correctness
    pyyaml_rate = test_results.get("pyyaml", {}).get("pass_rate", 0)
    pure_rate = test_results.get("pure", {}).get("pass_rate", 0)
    if pyyaml_rate > pure_rate:
        corr_winner = "PyYAML"
    elif pure_rate > pyyaml_rate:
        corr_winner = "PyYAML-Pure"
    else:
        corr_winner = "Tie"
    lines.append(f"| Test Suite Pass Rate | {pyyaml_rate:.1f}% | {pure_rate:.1f}% | **{corr_winner}** |")

    # Other aspects
    lines.append("| Pure Python | No (C extension) | Yes | **PyYAML-Pure** |")
    lines.append("| YAML 1.2 Support | Partial | Better | **PyYAML-Pure** |")
    lines.append("| Installation | Requires C compiler | Pure pip | **PyYAML-Pure** |")
    lines.append("")

    # Recommendation
    lines.append("## Recommendation\n")
    lines.append("**Choose PyYAML-Pure when:**")
    lines.append("- Correctness is more important than speed")
    lines.append("- You need pure Python (no C dependencies)")
    lines.append("- You're parsing complex YAML that PyYAML fails on")
    lines.append("- You need better YAML 1.2 compliance\n")
    lines.append("**Choose PyYAML when:**")
    lines.append("- Raw performance is critical")
    lines.append("- Processing large volumes of YAML")
    lines.append("- C extensions are acceptable in your environment\n")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Comprehensive PyYAML comparison")
    parser.add_argument("--iterations", "-i", type=int, default=5, help="Benchmark iterations")
    args = parser.parse_args()

    print("=" * 70)
    print("PyYAML vs PyYAML-Pure Comprehensive Comparison")
    print("=" * 70)
    print()

    # Run benchmarks
    benchmark_results = run_benchmarks(args.iterations)

    # Run test suite comparison
    test_results = run_test_suite_comparison()

    # Generate report
    report = generate_report(benchmark_results, test_results)
    report_path = Path(__file__).parent / "COMPARISON_REPORT.md"
    report_path.write_text(report)
    print(f"\nFull report saved to: {report_path}")


if __name__ == "__main__":
    main()

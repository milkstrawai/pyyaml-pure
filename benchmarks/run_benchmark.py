#!/usr/bin/env python3
"""
Simple benchmark runner that works around module shadowing.

This script benchmarks both PyYAML and PyYAML-Pure by running them in
separate processes to avoid import conflicts.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Benchmark data generators
GENERATORS = {
    "simple_dict_100": """
lines = []
for i in range(100):
    lines.append(f"key_{i}: value_{i}")
yaml_content = "\\n".join(lines)
""",
    "simple_dict_1000": """
lines = []
for i in range(1000):
    lines.append(f"key_{i}: value_{i}")
yaml_content = "\\n".join(lines)
""",
    "nested_dict": """
def build_level(d, indent=0):
    lines = []
    prefix = "  " * indent
    if d == 0:
        for i in range(5):
            lines.append(f"{prefix}leaf_{i}: value")
    else:
        for i in range(5):
            lines.append(f"{prefix}level_{d}_{i}:")
            lines.extend(build_level(d - 1, indent + 1))
    return lines
yaml_content = "\\n".join(build_level(5))
""",
    "list_of_dicts_100": """
lines = []
for i in range(100):
    lines.append(f"- id: {i}")
    lines.append(f"  name: User {i}")
    lines.append(f"  email: user{i}@example.com")
    lines.append(f"  active: {'true' if i % 2 == 0 else 'false'}")
yaml_content = "\\n".join(lines)
""",
    "list_of_dicts_500": """
lines = []
for i in range(500):
    lines.append(f"- id: {i}")
    lines.append(f"  name: User {i}")
    lines.append(f"  email: user{i}@example.com")
yaml_content = "\\n".join(lines)
""",
    "multiline_strings": """
lines = []
for i in range(50):
    lines.append(f"text_{i}: |")
    lines.append(f"  Line 1 of block {i}.")
    lines.append(f"  Line 2 with content.")
    lines.append(f"  Line 3 final.")
yaml_content = "\\n".join(lines)
""",
    "anchors_aliases": """
lines = ["defaults: &defaults", "  adapter: postgres", "  host: localhost", ""]
for i in range(50):
    lines.append(f"db_{i}:")
    lines.append("  <<: *defaults")
    lines.append(f"  name: db_{i}")
yaml_content = "\\n".join(lines)
""",
    "flow_style": """
lines = []
for i in range(100):
    lines.append(f"item_{i}: {{a: 1, b: 2, c: [{i}, {i+1}]}}")
yaml_content = "\\n".join(lines)
""",
    "large_list_1000": """
lines = [f"- item_{i}" for i in range(1000)]
yaml_content = "\\n".join(lines)
""",
    "config_file": '''
yaml_content = """
app:
  name: MyApp
  version: 1.0.0
  debug: false
server:
  host: 0.0.0.0
  port: 8080
  workers: 4
database:
  driver: postgresql
  host: db.example.com
  port: 5432
  pool:
    min: 5
    max: 20
logging:
  level: INFO
  handlers:
    - type: console
    - type: file
      path: /var/log/app.log
features:
  feature_a: true
  feature_b: false
"""
''',
}

BENCHMARK_TEMPLATE = '''
import gc
import time
import sys

# Generator code
{generator}

# Number of iterations
iterations = {iterations}

# Warmup
yaml.safe_load(yaml_content)

# Benchmark
times = []
for _ in range(iterations):
    gc.collect()
    start = time.perf_counter()
    yaml.safe_load(yaml_content)
    end = time.perf_counter()
    times.append(end - start)

import json
print(json.dumps({{
    "times": times,
    "data_size": len(yaml_content),
    "mean": sum(times) / len(times),
    "min": min(times),
    "max": max(times),
}}))
'''


def run_pyyaml_benchmark(generator_code: str, iterations: int) -> dict:
    """Run benchmark with original PyYAML."""
    code = f"import yaml\n{BENCHMARK_TEMPLATE.format(generator=generator_code, iterations=iterations)}"

    # Run in subprocess with clean environment
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd="/",  # Run from root to avoid local yaml shadowing
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )

    if result.returncode != 0:
        print(f"PyYAML error: {result.stderr}")
        return {"times": [], "mean": 0, "data_size": 0}

    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        print(f"PyYAML output: {result.stdout}")
        return {"times": [], "mean": 0, "data_size": 0}


def run_pure_benchmark(generator_code: str, iterations: int) -> dict:
    """Run benchmark with PyYAML-Pure."""
    package_dir = Path(__file__).parent.parent
    code = f"""
import sys
sys.path.insert(0, {str(package_dir)!r})
import yaml
{BENCHMARK_TEMPLATE.format(generator=generator_code, iterations=iterations)}
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd="/",
    )

    if result.returncode != 0:
        print(f"Pure error: {result.stderr}")
        return {"times": [], "mean": 0, "data_size": 0}

    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        print(f"Pure output: {result.stdout}")
        return {"times": [], "mean": 0, "data_size": 0}


def run_dump_benchmark_pyyaml(data_code: str, iterations: int) -> dict:
    """Run dump benchmark with PyYAML."""
    code = f"""
import yaml
import gc
import time
import json

{data_code}

iterations = {iterations}

# Warmup
yaml.safe_dump(data)

times = []
for _ in range(iterations):
    gc.collect()
    start = time.perf_counter()
    yaml.safe_dump(data)
    end = time.perf_counter()
    times.append(end - start)

print(json.dumps({{"times": times, "mean": sum(times)/len(times)}}))
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd="/")
    if result.returncode != 0:
        return {"times": [], "mean": 0}
    try:
        return json.loads(result.stdout.strip())
    except:
        return {"times": [], "mean": 0}


def run_dump_benchmark_pure(data_code: str, iterations: int) -> dict:
    """Run dump benchmark with PyYAML-Pure."""
    package_dir = Path(__file__).parent.parent
    code = f"""
import sys
sys.path.insert(0, {str(package_dir)!r})
import yaml
import gc
import time
import json

{data_code}

iterations = {iterations}

# Warmup
yaml.safe_dump(data)

times = []
for _ in range(iterations):
    gc.collect()
    start = time.perf_counter()
    yaml.safe_dump(data)
    end = time.perf_counter()
    times.append(end - start)

print(json.dumps({{"times": times, "mean": sum(times)/len(times)}}))
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd="/")
    if result.returncode != 0:
        return {"times": [], "mean": 0}
    try:
        return json.loads(result.stdout.strip())
    except:
        return {"times": [], "mean": 0}


def main():
    iterations = 10
    if len(sys.argv) > 1:
        iterations = int(sys.argv[1])

    print("=" * 70)
    print("PyYAML vs PyYAML-Pure Benchmark")
    print("=" * 70)
    print(f"Platform: {platform.platform()}")
    print(f"Python: {platform.python_version()}")
    print(f"Iterations: {iterations}")
    print()

    results = []

    # Loading benchmarks
    print("Running loading benchmarks...")
    print()
    print(f"{'Benchmark':<30} {'PyYAML (ms)':<15} {'Pure (ms)':<15} {'Speedup':<15}")
    print("-" * 75)

    for name, generator in GENERATORS.items():
        pyyaml_result = run_pyyaml_benchmark(generator, iterations)
        pure_result = run_pure_benchmark(generator, iterations)

        pyyaml_ms = pyyaml_result["mean"] * 1000
        pure_ms = pure_result["mean"] * 1000

        if pure_ms > 0:
            speedup = pyyaml_ms / pure_ms
            speedup_str = f"{speedup:.2f}x"
        else:
            speedup = 0
            speedup_str = "N/A"

        print(f"{name:<30} {pyyaml_ms:<15.3f} {pure_ms:<15.3f} {speedup_str:<15}")

        results.append({
            "name": name,
            "category": "loading",
            "pyyaml_ms": pyyaml_ms,
            "pure_ms": pure_ms,
            "speedup": speedup,
            "data_size": pyyaml_result.get("data_size", 0),
        })

    # Dump benchmarks
    print()
    print("Running dump benchmarks...")
    print()
    print(f"{'Benchmark':<30} {'PyYAML (ms)':<15} {'Pure (ms)':<15} {'Speedup':<15}")
    print("-" * 75)

    dump_tests = {
        "dump_simple_dict": "data = {f'key_{i}': f'value_{i}' for i in range(100)}",
        "dump_nested_dict": "data = {'a': {'b': {'c': {'d': {'e': 'value'}}}}}",
        "dump_list_of_dicts": "data = [{'id': i, 'name': f'item_{i}'} for i in range(100)]",
    }

    for name, data_code in dump_tests.items():
        pyyaml_result = run_dump_benchmark_pyyaml(data_code, iterations)
        pure_result = run_dump_benchmark_pure(data_code, iterations)

        pyyaml_ms = pyyaml_result["mean"] * 1000
        pure_ms = pure_result["mean"] * 1000

        if pure_ms > 0:
            speedup = pyyaml_ms / pure_ms
            speedup_str = f"{speedup:.2f}x"
        else:
            speedup = 0
            speedup_str = "N/A"

        print(f"{name:<30} {pyyaml_ms:<15.3f} {pure_ms:<15.3f} {speedup_str:<15}")

        results.append({
            "name": name,
            "category": "dumping",
            "pyyaml_ms": pyyaml_ms,
            "pure_ms": pure_ms,
            "speedup": speedup,
        })

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    valid_results = [r for r in results if r["speedup"] > 0]
    if valid_results:
        avg_speedup = sum(r["speedup"] for r in valid_results) / len(valid_results)
        faster = sum(1 for r in valid_results if r["speedup"] > 1)
        slower = sum(1 for r in valid_results if r["speedup"] < 1)

        print(f"Total benchmarks: {len(valid_results)}")
        print(f"Average speedup: {avg_speedup:.2f}x")
        print(f"PyYAML-Pure faster: {faster}")
        print(f"PyYAML-Pure slower: {slower}")
        print()

        if avg_speedup > 1:
            print(f"PyYAML-Pure is {avg_speedup:.2f}x FASTER on average")
        else:
            print(f"PyYAML-Pure is {1/avg_speedup:.2f}x SLOWER on average")

    # Save results
    output_dir = Path(__file__).parent
    results_file = output_dir / "benchmark_results.json"

    output_data = {
        "metadata": {
            "generated": datetime.now().isoformat(),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "iterations": iterations,
        },
        "results": results,
    }

    results_file.write_text(json.dumps(output_data, indent=2))
    print(f"\nResults saved to: {results_file}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
PyYAML vs PyYAML-Pure Benchmark Suite.

This script provides comprehensive benchmarks comparing PyYAML-Pure against
the original PyYAML implementation across various scenarios.

Usage:
    python benchmarks/benchmark.py [--iterations N] [--output FILE]

Requirements:
    - PyYAML installed (pip install pyyaml)
    - PyYAML-Pure in the current directory
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import platform
import random
import statistics
import string
import sys
import time
import tracemalloc
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


@dataclass
class BenchmarkResult:
    """Result of a single benchmark."""

    name: str
    category: str
    pyyaml_times: list[float] = field(default_factory=list)
    pure_times: list[float] = field(default_factory=list)
    pyyaml_memory: int = 0
    pure_memory: int = 0
    data_size: int = 0
    description: str = ""

    @property
    def pyyaml_mean(self) -> float:
        return statistics.mean(self.pyyaml_times) if self.pyyaml_times else 0

    @property
    def pure_mean(self) -> float:
        return statistics.mean(self.pure_times) if self.pure_times else 0

    @property
    def pyyaml_stdev(self) -> float:
        return statistics.stdev(self.pyyaml_times) if len(self.pyyaml_times) > 1 else 0

    @property
    def pure_stdev(self) -> float:
        return statistics.stdev(self.pure_times) if len(self.pure_times) > 1 else 0

    @property
    def speedup(self) -> float:
        """Speedup factor (>1 means PyYAML-Pure is faster)."""
        if self.pure_mean == 0:
            return 0
        return self.pyyaml_mean / self.pure_mean

    @property
    def memory_ratio(self) -> float:
        """Memory ratio (<1 means PyYAML-Pure uses less memory)."""
        if self.pyyaml_memory == 0:
            return 0
        return self.pure_memory / self.pyyaml_memory


def get_pyyaml_module():
    """Get the original PyYAML module."""
    # Save current state
    original_path = sys.path.copy()
    original_modules = {k: v for k, v in sys.modules.items() if k == "yaml" or k.startswith("yaml.")}

    # Remove pyyaml-pure from path
    sys.path = [p for p in sys.path if "pyyaml-pure" not in p]

    # Clear yaml modules
    for mod in list(sys.modules.keys()):
        if mod == "yaml" or mod.startswith("yaml."):
            del sys.modules[mod]

    try:
        import yaml as pyyaml

        # Verify it's the original
        if hasattr(pyyaml, "_parser"):
            raise ImportError("Got pyyaml-pure instead of PyYAML")
        return pyyaml
    finally:
        # Restore path
        sys.path = original_path


def get_pure_module():
    """Get the PyYAML-Pure module."""
    # Clear yaml modules first
    for mod in list(sys.modules.keys()):
        if mod == "yaml" or mod.startswith("yaml."):
            del sys.modules[mod]

    # Add package to path
    package_dir = Path(__file__).parent.parent
    if str(package_dir) not in sys.path:
        sys.path.insert(0, str(package_dir))

    import yaml as pure

    # Verify it's pyyaml-pure
    if not hasattr(pure, "_parser"):
        raise ImportError("Got PyYAML instead of pyyaml-pure")
    return pure


# ============================================================================
# Test Data Generators
# ============================================================================


def generate_simple_dict(size: int = 100) -> str:
    """Generate a simple flat dictionary."""
    lines = []
    for i in range(size):
        lines.append(f"key_{i}: value_{i}")
    return "\n".join(lines)


def generate_nested_dict(depth: int = 10, breadth: int = 5) -> str:
    """Generate a deeply nested dictionary."""

    def build_level(d: int, indent: int = 0) -> list[str]:
        lines = []
        prefix = "  " * indent
        if d == 0:
            for i in range(breadth):
                lines.append(f"{prefix}leaf_{i}: value")
        else:
            for i in range(breadth):
                lines.append(f"{prefix}level_{d}_{i}:")
                lines.extend(build_level(d - 1, indent + 1))
        return lines

    return "\n".join(build_level(depth))


def generate_list_of_dicts(count: int = 100) -> str:
    """Generate a list of dictionaries (common API response pattern)."""
    lines = []
    for i in range(count):
        lines.append(f"- id: {i}")
        lines.append(f"  name: User {i}")
        lines.append(f"  email: user{i}@example.com")
        lines.append(f"  active: {'true' if i % 2 == 0 else 'false'}")
        lines.append(f"  score: {i * 1.5}")
    return "\n".join(lines)


def generate_multiline_strings(count: int = 50) -> str:
    """Generate YAML with multiline strings."""
    lines = []
    for i in range(count):
        lines.append(f"text_{i}: |")
        lines.append(f"  This is line 1 of text block {i}.")
        lines.append(f"  This is line 2 with some content.")
        lines.append(f"  And a third line to make it interesting.")
    return "\n".join(lines)


def generate_anchors_aliases(count: int = 50) -> str:
    """Generate YAML with anchors and aliases."""
    lines = ["defaults: &defaults"]
    lines.append("  adapter: postgres")
    lines.append("  host: localhost")
    lines.append("  port: 5432")
    lines.append("")

    for i in range(count):
        lines.append(f"database_{i}:")
        lines.append("  <<: *defaults")
        lines.append(f"  database: db_{i}")
    return "\n".join(lines)


def generate_mixed_types(size: int = 100) -> str:
    """Generate YAML with various data types."""
    lines = []
    for i in range(size):
        lines.append(f"item_{i}:")
        lines.append(f"  string: 'hello world {i}'")
        lines.append(f"  integer: {i * 100}")
        lines.append(f"  float: {i * 3.14159}")
        lines.append(f"  boolean: {'true' if i % 2 == 0 else 'false'}")
        lines.append(f"  null_value: null")
        lines.append(f"  date: 2024-01-{(i % 28) + 1:02d}")
        lines.append(f"  list: [1, 2, 3, {i}]")
    return "\n".join(lines)


def generate_large_list(size: int = 1000) -> str:
    """Generate a large flat list."""
    lines = []
    for i in range(size):
        lines.append(f"- item_{i}")
    return "\n".join(lines)


def generate_flow_style(size: int = 100) -> str:
    """Generate YAML with flow style collections."""
    lines = []
    for i in range(size):
        lines.append(f"flow_{i}: {{a: 1, b: 2, c: [{i}, {i+1}, {i+2}]}}")
    return "\n".join(lines)


def generate_unicode_content(size: int = 100) -> str:
    """Generate YAML with unicode content."""
    unicode_samples = [
        "Hello World",
        "Bonjour le monde",
        "Hallo Welt",
        "Ciao mondo",
        "Olá mundo",
        "Привет мир",
        "مرحبا بالعالم",
        "שלום עולם",
        "こんにちは世界",
        "你好世界",
        "안녕하세요 세계",
        "🌍🌎🌏",
    ]
    lines = []
    for i in range(size):
        text = unicode_samples[i % len(unicode_samples)]
        lines.append(f"text_{i}: \"{text}\"")
    return "\n".join(lines)


def generate_multi_document(doc_count: int = 10, items_per_doc: int = 20) -> str:
    """Generate multi-document YAML."""
    docs = []
    for d in range(doc_count):
        lines = [f"---"]
        lines.append(f"document: {d}")
        lines.append("items:")
        for i in range(items_per_doc):
            lines.append(f"  - name: item_{d}_{i}")
            lines.append(f"    value: {d * items_per_doc + i}")
        docs.append("\n".join(lines))
    return "\n".join(docs)


def generate_config_file() -> str:
    """Generate a realistic configuration file."""
    return """
# Application Configuration
app:
  name: MyApplication
  version: 1.2.3
  debug: false

server:
  host: 0.0.0.0
  port: 8080
  workers: 4
  timeout: 30
  ssl:
    enabled: true
    cert: /etc/ssl/cert.pem
    key: /etc/ssl/key.pem

database:
  primary:
    driver: postgresql
    host: db.example.com
    port: 5432
    name: myapp_production
    pool:
      min: 5
      max: 20
      timeout: 30
  replica:
    driver: postgresql
    host: db-replica.example.com
    port: 5432
    name: myapp_production
    readonly: true

cache:
  backend: redis
  host: cache.example.com
  port: 6379
  ttl: 3600
  prefix: "myapp:"

logging:
  level: INFO
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  handlers:
    - type: console
      level: DEBUG
    - type: file
      level: INFO
      path: /var/log/myapp/app.log
      max_size: 10485760
      backup_count: 5

features:
  feature_a: true
  feature_b: false
  feature_c:
    enabled: true
    config:
      threshold: 0.75
      max_items: 100

security:
  cors:
    enabled: true
    origins:
      - https://example.com
      - https://www.example.com
    methods:
      - GET
      - POST
      - PUT
      - DELETE
    headers:
      - Content-Type
      - Authorization
  rate_limit:
    enabled: true
    requests: 100
    period: 60

monitoring:
  metrics:
    enabled: true
    port: 9090
  health_check:
    path: /health
    interval: 30
"""


# ============================================================================
# Benchmark Runner
# ============================================================================


def measure_time(func: Callable, iterations: int = 10) -> list[float]:
    """Measure execution time over multiple iterations."""
    times = []
    for _ in range(iterations):
        gc.collect()
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        times.append(end - start)
    return times


def measure_memory(func: Callable) -> int:
    """Measure peak memory usage."""
    gc.collect()
    tracemalloc.start()
    func()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak


def run_benchmark(
    name: str,
    category: str,
    yaml_content: str,
    pyyaml: Any,
    pure: Any,
    iterations: int = 10,
    description: str = "",
    multi_doc: bool = False,
) -> BenchmarkResult:
    """Run a single benchmark."""
    result = BenchmarkResult(
        name=name,
        category=category,
        data_size=len(yaml_content),
        description=description,
    )

    # Define load functions
    if multi_doc:
        pyyaml_func = lambda: list(pyyaml.safe_load_all(yaml_content))
        pure_func = lambda: list(pure.safe_load_all(yaml_content))
    else:
        pyyaml_func = lambda: pyyaml.safe_load(yaml_content)
        pure_func = lambda: pure.safe_load(yaml_content)

    # Warm up
    try:
        pyyaml_func()
        pure_func()
    except Exception as e:
        print(f"  Warning: {name} failed: {e}")
        return result

    # Measure time
    result.pyyaml_times = measure_time(pyyaml_func, iterations)
    result.pure_times = measure_time(pure_func, iterations)

    # Measure memory (single run)
    result.pyyaml_memory = measure_memory(pyyaml_func)
    result.pure_memory = measure_memory(pure_func)

    return result


def run_dump_benchmark(
    name: str,
    category: str,
    data: Any,
    pyyaml: Any,
    pure: Any,
    iterations: int = 10,
    description: str = "",
) -> BenchmarkResult:
    """Run a dump/serialize benchmark."""
    result = BenchmarkResult(
        name=name,
        category=category,
        data_size=len(str(data)),
        description=description,
    )

    pyyaml_func = lambda: pyyaml.safe_dump(data)
    pure_func = lambda: pure.safe_dump(data)

    # Warm up
    try:
        pyyaml_func()
        pure_func()
    except Exception as e:
        print(f"  Warning: {name} failed: {e}")
        return result

    # Measure time
    result.pyyaml_times = measure_time(pyyaml_func, iterations)
    result.pure_times = measure_time(pure_func, iterations)

    # Measure memory
    result.pyyaml_memory = measure_memory(pyyaml_func)
    result.pure_memory = measure_memory(pure_func)

    return result


# ============================================================================
# Main Benchmark Suite
# ============================================================================


def run_all_benchmarks(iterations: int = 10) -> list[BenchmarkResult]:
    """Run the complete benchmark suite."""
    print("Loading implementations...")
    pyyaml = get_pyyaml_module()
    pure = get_pure_module()

    print(f"PyYAML version: {pyyaml.__version__}")
    print(f"PyYAML-Pure: pyyaml-pure")
    print(f"Iterations per benchmark: {iterations}")
    print()

    results = []

    # =========================================================================
    # Category: Simple Structures
    # =========================================================================
    print("Running: Simple Structures...")

    results.append(
        run_benchmark(
            "Simple Dict (100 keys)",
            "Simple Structures",
            generate_simple_dict(100),
            pyyaml,
            pure,
            iterations,
            "Flat dictionary with 100 key-value pairs",
        )
    )

    results.append(
        run_benchmark(
            "Simple Dict (1000 keys)",
            "Simple Structures",
            generate_simple_dict(1000),
            pyyaml,
            pure,
            iterations,
            "Flat dictionary with 1000 key-value pairs",
        )
    )

    results.append(
        run_benchmark(
            "Large List (1000 items)",
            "Simple Structures",
            generate_large_list(1000),
            pyyaml,
            pure,
            iterations,
            "Simple list with 1000 string items",
        )
    )

    results.append(
        run_benchmark(
            "Large List (5000 items)",
            "Simple Structures",
            generate_large_list(5000),
            pyyaml,
            pure,
            iterations,
            "Simple list with 5000 string items",
        )
    )

    # =========================================================================
    # Category: Nested Structures
    # =========================================================================
    print("Running: Nested Structures...")

    results.append(
        run_benchmark(
            "Nested Dict (depth=5, breadth=5)",
            "Nested Structures",
            generate_nested_dict(5, 5),
            pyyaml,
            pure,
            iterations,
            "Nested dictionary with depth 5 and breadth 5",
        )
    )

    results.append(
        run_benchmark(
            "Nested Dict (depth=10, breadth=3)",
            "Nested Structures",
            generate_nested_dict(10, 3),
            pyyaml,
            pure,
            iterations,
            "Deeply nested dictionary",
        )
    )

    results.append(
        run_benchmark(
            "List of Dicts (100 items)",
            "Nested Structures",
            generate_list_of_dicts(100),
            pyyaml,
            pure,
            iterations,
            "List of 100 dictionaries (API response pattern)",
        )
    )

    results.append(
        run_benchmark(
            "List of Dicts (500 items)",
            "Nested Structures",
            generate_list_of_dicts(500),
            pyyaml,
            pure,
            iterations,
            "List of 500 dictionaries",
        )
    )

    # =========================================================================
    # Category: String Processing
    # =========================================================================
    print("Running: String Processing...")

    results.append(
        run_benchmark(
            "Multiline Strings (50 blocks)",
            "String Processing",
            generate_multiline_strings(50),
            pyyaml,
            pure,
            iterations,
            "50 literal block scalars with 3 lines each",
        )
    )

    results.append(
        run_benchmark(
            "Unicode Content (100 items)",
            "String Processing",
            generate_unicode_content(100),
            pyyaml,
            pure,
            iterations,
            "100 strings with various unicode content",
        )
    )

    # =========================================================================
    # Category: Special Features
    # =========================================================================
    print("Running: Special Features...")

    results.append(
        run_benchmark(
            "Anchors & Aliases (50 refs)",
            "Special Features",
            generate_anchors_aliases(50),
            pyyaml,
            pure,
            iterations,
            "50 documents using anchor/alias references",
        )
    )

    results.append(
        run_benchmark(
            "Flow Style (100 items)",
            "Special Features",
            generate_flow_style(100),
            pyyaml,
            pure,
            iterations,
            "100 items using flow style notation",
        )
    )

    results.append(
        run_benchmark(
            "Mixed Types (100 items)",
            "Special Features",
            generate_mixed_types(100),
            pyyaml,
            pure,
            iterations,
            "100 items with various YAML types",
        )
    )

    results.append(
        run_benchmark(
            "Multi-Document (10 docs)",
            "Special Features",
            generate_multi_document(10, 20),
            pyyaml,
            pure,
            iterations,
            "10 YAML documents in single stream",
            multi_doc=True,
        )
    )

    # =========================================================================
    # Category: Real-World Scenarios
    # =========================================================================
    print("Running: Real-World Scenarios...")

    results.append(
        run_benchmark(
            "Config File",
            "Real-World",
            generate_config_file(),
            pyyaml,
            pure,
            iterations,
            "Realistic application configuration file",
        )
    )

    # Generate a larger config by repeating
    large_config = generate_config_file() * 10
    results.append(
        run_benchmark(
            "Large Config File",
            "Real-World",
            large_config,
            pyyaml,
            pure,
            iterations,
            "Large configuration file (10x config)",
        )
    )

    # =========================================================================
    # Category: Dumping/Serialization
    # =========================================================================
    print("Running: Dumping/Serialization...")

    # Prepare data for dumping
    simple_data = {f"key_{i}": f"value_{i}" for i in range(100)}
    results.append(
        run_dump_benchmark(
            "Dump Simple Dict (100 keys)",
            "Serialization",
            simple_data,
            pyyaml,
            pure,
            iterations,
            "Serialize flat dictionary",
        )
    )

    nested_data = pyyaml.safe_load(generate_nested_dict(5, 5))
    results.append(
        run_dump_benchmark(
            "Dump Nested Dict",
            "Serialization",
            nested_data,
            pyyaml,
            pure,
            iterations,
            "Serialize nested dictionary",
        )
    )

    list_data = [{f"key_{j}": j for j in range(10)} for i in range(100)]
    results.append(
        run_dump_benchmark(
            "Dump List of Dicts (100 items)",
            "Serialization",
            list_data,
            pyyaml,
            pure,
            iterations,
            "Serialize list of dictionaries",
        )
    )

    return results


# ============================================================================
# Reporting
# ============================================================================


def print_results(results: list[BenchmarkResult]) -> None:
    """Print benchmark results to console."""
    print("\n" + "=" * 100)
    print("BENCHMARK RESULTS")
    print("=" * 100)

    # Group by category
    categories: dict[str, list[BenchmarkResult]] = {}
    for r in results:
        if r.category not in categories:
            categories[r.category] = []
        categories[r.category].append(r)

    for category, cat_results in categories.items():
        print(f"\n## {category}\n")
        print(
            f"{'Benchmark':<35} {'PyYAML (ms)':<15} {'Pure (ms)':<15} {'Speedup':<12} {'Memory Ratio':<12}"
        )
        print("-" * 89)

        for r in cat_results:
            pyyaml_ms = r.pyyaml_mean * 1000
            pure_ms = r.pure_mean * 1000
            speedup = f"{r.speedup:.2f}x"
            if r.speedup > 1:
                speedup = f"+{speedup}"
            elif r.speedup < 1 and r.speedup > 0:
                speedup = f"{r.speedup:.2f}x"

            mem_ratio = f"{r.memory_ratio:.2f}x" if r.memory_ratio > 0 else "N/A"

            print(f"{r.name:<35} {pyyaml_ms:<15.3f} {pure_ms:<15.3f} {speedup:<12} {mem_ratio:<12}")

    # Summary statistics
    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)

    valid_results = [r for r in results if r.pyyaml_mean > 0 and r.pure_mean > 0]
    if valid_results:
        avg_speedup = statistics.mean([r.speedup for r in valid_results])
        faster_count = sum(1 for r in valid_results if r.speedup > 1)
        slower_count = sum(1 for r in valid_results if r.speedup < 1)

        print(f"\nTotal benchmarks: {len(valid_results)}")
        print(f"Average speedup: {avg_speedup:.2f}x")
        print(f"PyYAML-Pure faster in: {faster_count} benchmarks")
        print(f"PyYAML-Pure slower in: {slower_count} benchmarks")

        # Memory summary
        valid_memory = [r for r in results if r.pyyaml_memory > 0 and r.pure_memory > 0]
        if valid_memory:
            avg_memory_ratio = statistics.mean([r.memory_ratio for r in valid_memory])
            print(f"Average memory ratio: {avg_memory_ratio:.2f}x")


def generate_markdown_report(results: list[BenchmarkResult], output_path: Path) -> None:
    """Generate a detailed markdown report."""
    lines = []
    lines.append("# PyYAML vs PyYAML-Pure Benchmark Report\n")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # System info
    lines.append("## System Information\n")
    lines.append(f"- **Platform:** {platform.platform()}")
    lines.append(f"- **Python:** {platform.python_version()}")
    lines.append(f"- **Processor:** {platform.processor() or 'Unknown'}")
    lines.append(f"- **CPU Count:** {os.cpu_count()}")
    lines.append("")

    # Summary
    valid_results = [r for r in results if r.pyyaml_mean > 0 and r.pure_mean > 0]
    if valid_results:
        avg_speedup = statistics.mean([r.speedup for r in valid_results])
        faster_count = sum(1 for r in valid_results if r.speedup > 1)
        slower_count = sum(1 for r in valid_results if r.speedup < 1)

        lines.append("## Executive Summary\n")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Total Benchmarks | {len(valid_results)} |")
        lines.append(f"| Average Speedup | {avg_speedup:.2f}x |")
        lines.append(f"| PyYAML-Pure Faster | {faster_count} benchmarks |")
        lines.append(f"| PyYAML-Pure Slower | {slower_count} benchmarks |")

        valid_memory = [r for r in results if r.pyyaml_memory > 0 and r.pure_memory > 0]
        if valid_memory:
            avg_memory_ratio = statistics.mean([r.memory_ratio for r in valid_memory])
            lines.append(f"| Average Memory Ratio | {avg_memory_ratio:.2f}x |")
        lines.append("")

        # Performance interpretation
        lines.append("### Interpretation\n")
        if avg_speedup > 1:
            lines.append(
                f"PyYAML-Pure is on average **{avg_speedup:.2f}x faster** than PyYAML across all benchmarks.\n"
            )
        elif avg_speedup < 1:
            lines.append(
                f"PyYAML-Pure is on average **{1/avg_speedup:.2f}x slower** than PyYAML across all benchmarks.\n"
            )
        else:
            lines.append("PyYAML-Pure has **comparable performance** to PyYAML.\n")

    # Detailed results by category
    lines.append("## Detailed Results\n")

    categories: dict[str, list[BenchmarkResult]] = {}
    for r in results:
        if r.category not in categories:
            categories[r.category] = []
        categories[r.category].append(r)

    for category, cat_results in categories.items():
        lines.append(f"### {category}\n")
        lines.append("| Benchmark | Data Size | PyYAML (ms) | Pure (ms) | Speedup | Memory Ratio |")
        lines.append("|-----------|-----------|-------------|-----------|---------|--------------|")

        for r in cat_results:
            pyyaml_ms = r.pyyaml_mean * 1000
            pure_ms = r.pure_mean * 1000
            size_kb = r.data_size / 1024

            if r.speedup >= 1:
                speedup_str = f"**{r.speedup:.2f}x** faster"
            else:
                speedup_str = f"{1/r.speedup:.2f}x slower"

            mem_str = f"{r.memory_ratio:.2f}x" if r.memory_ratio > 0 else "N/A"

            lines.append(
                f"| {r.name} | {size_kb:.1f} KB | {pyyaml_ms:.3f} | {pure_ms:.3f} | {speedup_str} | {mem_str} |"
            )

        lines.append("")

    # Benchmark descriptions
    lines.append("## Benchmark Descriptions\n")
    for r in results:
        if r.description:
            lines.append(f"- **{r.name}:** {r.description}")
    lines.append("")

    # Methodology
    lines.append("## Methodology\n")
    lines.append("### Timing")
    lines.append("- Each benchmark is run multiple times (configurable, default 10)")
    lines.append("- Garbage collection is forced before each measurement")
    lines.append("- Results show mean execution time\n")
    lines.append("### Memory")
    lines.append("- Memory is measured using Python's `tracemalloc`")
    lines.append("- Peak memory allocation during operation is recorded")
    lines.append("- Memory ratio < 1 means PyYAML-Pure uses less memory\n")
    lines.append("### Speedup Calculation")
    lines.append("- Speedup = PyYAML time / PyYAML-Pure time")
    lines.append("- Speedup > 1 means PyYAML-Pure is faster")
    lines.append("- Speedup < 1 means PyYAML is faster\n")

    # How to reproduce
    lines.append("## Reproducing Results\n")
    lines.append("```bash")
    lines.append("# Clone the repository")
    lines.append("git clone <repo-url>")
    lines.append("cd pyyaml-pure")
    lines.append("")
    lines.append("# Install dependencies")
    lines.append("pip install pyyaml  # Original PyYAML for comparison")
    lines.append("")
    lines.append("# Run benchmarks")
    lines.append("python benchmarks/benchmark.py --iterations 10 --output benchmarks/RESULTS.md")
    lines.append("```\n")

    output_path.write_text("\n".join(lines))
    print(f"\nMarkdown report saved to: {output_path}")


def save_json_results(results: list[BenchmarkResult], output_path: Path) -> None:
    """Save raw benchmark results as JSON for further analysis."""
    data = {
        "metadata": {
            "generated": datetime.now().isoformat(),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
        },
        "results": [
            {
                "name": r.name,
                "category": r.category,
                "description": r.description,
                "data_size": r.data_size,
                "pyyaml_times": r.pyyaml_times,
                "pure_times": r.pure_times,
                "pyyaml_mean": r.pyyaml_mean,
                "pure_mean": r.pure_mean,
                "pyyaml_stdev": r.pyyaml_stdev,
                "pure_stdev": r.pure_stdev,
                "speedup": r.speedup,
                "pyyaml_memory": r.pyyaml_memory,
                "pure_memory": r.pure_memory,
                "memory_ratio": r.memory_ratio,
            }
            for r in results
        ],
    }

    json_path = output_path.with_suffix(".json")
    json_path.write_text(json.dumps(data, indent=2))
    print(f"JSON results saved to: {json_path}")


# ============================================================================
# Entry Point
# ============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(description="PyYAML vs PyYAML-Pure Benchmark Suite")
    parser.add_argument(
        "--iterations", "-i", type=int, default=10, help="Number of iterations per benchmark (default: 10)"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="benchmarks/BENCHMARK_RESULTS.md",
        help="Output file path for markdown report",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("PyYAML vs PyYAML-Pure Benchmark Suite")
    print("=" * 60)
    print()

    results = run_all_benchmarks(iterations=args.iterations)

    print_results(results)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    generate_markdown_report(results, output_path)
    save_json_results(results, output_path)


if __name__ == "__main__":
    main()

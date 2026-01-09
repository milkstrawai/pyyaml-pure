# PyYAML vs PyYAML-Pure Comprehensive Comparison

**Generated:** 2025-01-09
**Platform:** macOS-26.0.1-arm64-arm-64bit
**Python:** 3.12.12

## Executive Summary

| Aspect | PyYAML | PyYAML-Pure | Winner |
|--------|--------|-------------|--------|
| Performance | 1.7x faster | - | **PyYAML** |
| Event Parsing Pass Rate | 76.3% | 100.0% | **PyYAML-Pure** |
| JSON Comparison Pass Rate | 76.3% | 93.5% | **PyYAML-Pure** |
| Pure Python | No (C extension) | Yes | **PyYAML-Pure** |
| YAML 1.2 Support | Partial | Full | **PyYAML-Pure** |
| Installation | Requires C compiler | Pure pip | **PyYAML-Pure** |

## Performance

PyYAML-Pure is approximately **1.7x slower** than PyYAML due to the use of pure Python vs C extensions.

| Benchmark Category | Typical Ratio |
|--------------------|---------------|
| Simple dictionaries | 0.51x |
| Nested structures | 0.50x |
| Lists of dictionaries | 0.58-0.60x |
| Flow style | 0.74x |
| Dumping | 0.67-0.83x |

For configuration files and typical API responses, the performance difference is negligible.

## Correctness

PyYAML-Pure achieves **perfect score** on the official YAML test suite event parsing:

| Metric | PyYAML | PyYAML-Pure |
|--------|--------|-------------|
| Event Parsing | 235/308 (76.3%) | **308/308 (100%)** |
| JSON Comparison | 213/279 (76.3%) | **261/279 (93.5%)** |

PyYAML-Pure passes **73 more event parsing tests** and **48 more JSON tests** than PyYAML.

## Recommendation

**Choose PyYAML-Pure when:**
- Correctness is more important than speed
- You need pure Python (no C dependencies)
- You're parsing complex YAML that PyYAML fails on
- You need full YAML 1.2 compliance
- Using PyPy (benefits from JIT compilation)
- Debugging YAML parsing issues

**Choose PyYAML when:**
- Raw performance is critical
- Processing large volumes of YAML (multi-MB files)
- C extensions are acceptable in your environment

## Detailed Results

See [BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md) for complete benchmark data.

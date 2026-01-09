# PyYAML vs PyYAML-Pure Benchmarks

This directory contains benchmarking scripts and results comparing PyYAML-Pure against the original PyYAML implementation.

## Quick Summary

| Metric | PyYAML | PyYAML-Pure | Notes |
|--------|--------|-------------|-------|
| **Performance** | 1.7x faster | Baseline | C extension vs pure Python |
| **Event Parsing Pass Rate** | 76.3% | **100.0%** | Perfect score |
| **JSON Comparison Pass Rate** | 76.3% | **93.5%** | +17.2% better |
| **Dependencies** | C compiler | None | Pure pip install |
| **YAML 1.2 Support** | Partial | Full | Better spec compliance |

## Files

| File | Description |
|------|-------------|
| `run_benchmark.py` | Main benchmark script |
| `compare_all.py` | Runs both benchmarks and test suite comparison |
| `benchmark.py` | Extended benchmark suite (optional) |
| `BENCHMARK_RESULTS.md` | Detailed benchmark results |
| `benchmark_results.json` | Raw benchmark data (JSON) |

## Running Benchmarks

### Quick Benchmark

```bash
# Run with default 5 iterations
python benchmarks/run_benchmark.py

# Run with custom iterations
python benchmarks/run_benchmark.py 10
```

### Comprehensive Comparison

```bash
# Run benchmarks + test suite comparison
python benchmarks/compare_all.py --iterations 10
```

### Requirements

```bash
# Install original PyYAML for comparison
pip install pyyaml
```

## Benchmark Categories

### Loading Benchmarks
- Simple dictionaries (100, 1000 keys)
- Nested structures (depth=5)
- Lists of dictionaries (100, 500 items)
- Multiline strings (literal blocks)
- Anchors and aliases
- Flow style collections
- Large lists (1000+ items)
- Real-world config files

### Dumping Benchmarks
- Simple dictionary serialization
- Nested dictionary serialization
- List of dictionaries serialization

## Interpreting Results

### Speedup Ratio
```
Speedup = PyYAML time / PyYAML-Pure time
```
- `Speedup > 1.0`: PyYAML-Pure is faster
- `Speedup < 1.0`: PyYAML is faster
- `Speedup = 0.58x`: PyYAML-Pure takes ~1.7x longer

### Why PyYAML-Pure is Slower

PyYAML uses **LibYAML** (C library) for parsing, which is significantly faster than any pure Python implementation. This is expected and intentional.

PyYAML-Pure prioritizes:
- **Correctness** over speed (100% event parsing pass rate)
- **Portability** (no C dependencies)
- **YAML 1.2 compliance**
- **Debuggability** (pure Python stack traces)

## When Speed Matters

For most use cases (config files, API responses), the performance difference is negligible:

| File Size | PyYAML | PyYAML-Pure | Real-World Impact |
|-----------|--------|-------------|-------------------|
| 1 KB | 0.5 ms | 0.9 ms | Negligible |
| 10 KB | 10 ms | 17 ms | Acceptable |
| 100 KB | 100 ms | 170 ms | Consider caching |
| 1 MB+ | 1+ sec | 1.7+ sec | Use PyYAML |

## Reproducibility

All benchmarks are designed to be reproducible:

1. **Isolated processes**: Each implementation runs in its own Python process
2. **Module isolation**: No import conflicts between implementations
3. **Garbage collection**: GC forced before each timing measurement
4. **Warmup runs**: Each benchmark has a warmup pass before timing
5. **Multiple iterations**: Results are averaged over multiple runs

## Contributing

To add new benchmarks:

1. Add generator code to `GENERATORS` dict in `run_benchmark.py`
2. Run benchmarks and verify correctness
3. Update documentation with new results

## See Also

- [BENCHMARK_RESULTS.md](BENCHMARK_RESULTS.md) - Detailed results
- [tests/test_implementation_comparison.py](../tests/test_implementation_comparison.py) - Test suite comparison

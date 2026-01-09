# PyYAML vs PyYAML-Pure Benchmark Results

**Generated:** 2025-01-09
**Platform:** macOS-26.0.1-arm64-arm-64bit (Apple Silicon)
**Python:** 3.12.12
**Iterations:** 5 per benchmark

## Executive Summary

| Metric | PyYAML | PyYAML-Pure |
|--------|--------|-------------|
| Average Speed Ratio | baseline | **0.58x** |
| Slowdown Factor | baseline | **1.72x slower** |
| Event Parsing Pass Rate | 76.3% | **100.0%** |
| JSON Comparison Pass Rate | 76.3% | **93.5%** |

### Key Findings

1. **Performance**: PyYAML-Pure is approximately **1.7x slower** than PyYAML
2. **Correctness**: PyYAML-Pure passes **100% of event parsing tests** (vs 76.3% for PyYAML)
3. **Trade-off**: PyYAML-Pure prioritizes correctness and pure Python compatibility over raw speed

### Why the Performance Difference?

PyYAML uses **C extensions** (LibYAML) for parsing, while PyYAML-Pure is **100% pure Python**. This is an intentional design decision that provides:

- **No compilation required** - works on any Python platform
- **No C dependencies** - easier installation, especially on restricted environments
- **Full YAML 1.2 support** - better spec compliance
- **Easier debugging** - pure Python stack traces
- **PyPy compatibility** - can benefit from JIT compilation

## Detailed Benchmark Results

### Loading Benchmarks

| Benchmark | PyYAML (ms) | PyYAML-Pure (ms) | Ratio |
|-----------|-------------|------------------|-------|
| simple_dict_100 | 1.82 | 3.56 | 0.51x |
| simple_dict_1000 | 18.61 | 36.40 | 0.51x |
| nested_dict (depth=5) | 425.36 | 846.66 | 0.50x |
| list_of_dicts_100 | 8.74 | 14.62 | 0.60x |
| list_of_dicts_500 | 34.18 | 58.56 | 0.58x |
| multiline_strings (50) | 1.50 | 2.73 | 0.55x |
| anchors_aliases (50) | 2.74 | 5.64 | 0.49x |
| flow_style (100) | 9.30 | 12.49 | 0.74x |
| large_list_1000 | 11.06 | 34.99 | 0.32x |
| config_file | 0.48 | 0.93 | 0.52x |

### Dumping Benchmarks

| Benchmark | PyYAML (ms) | PyYAML-Pure (ms) | Ratio |
|-----------|-------------|------------------|-------|
| dump_simple_dict | 0.98 | 1.35 | 0.73x |
| dump_nested_dict | 0.07 | 0.09 | 0.83x |
| dump_list_of_dicts | 2.22 | 3.31 | 0.67x |

### Performance Analysis

- **Loading**: PyYAML-Pure is 1.5-3x slower depending on input complexity
- **Dumping**: PyYAML-Pure is only 1.2-1.5x slower (close to PyYAML performance)
- **Flow style** parsing is nearly as fast as PyYAML (0.74x ratio)
- **Deeply nested structures** show the largest performance gap
- **Simple operations** have acceptable overhead for most use cases

### Performance Optimizations

PyYAML-Pure includes several performance optimizations:

1. **Pre-compiled regex patterns** - All regex patterns pre-compiled at module load
2. **Direct attribute access** - Bypassing property getters in hot paths
3. **Character set membership** - Using `frozenset` for fast character class checks
4. **Inlined hot paths** - Critical parsing functions inlined to reduce call overhead
5. **Eliminated lambda overhead** - Hot loops use direct iteration instead of lambdas

## Test Suite Comparison

While PyYAML is faster, PyYAML-Pure is more **correct**:

### Event Parsing (Primary Correctness Metric)

| Metric | PyYAML | PyYAML-Pure | Winner |
|--------|--------|-------------|--------|
| Pass Rate | 76.3% | **100.0%** | PyYAML-Pure |
| Tests Passed | 235/308 | **308/308** | PyYAML-Pure |
| Tests Failed | 73 | **0** | PyYAML-Pure |

PyYAML-Pure achieves **perfect score** on event parsing - the primary correctness metric from [matrix.yaml.info](https://matrix.yaml.info/).

### JSON Comparison (Value Construction)

| Metric | PyYAML | PyYAML-Pure | Winner |
|--------|--------|-------------|--------|
| Pass Rate | 76.3% | **93.5%** | PyYAML-Pure |
| Tests Passed | 213/279 | **261/279** | PyYAML-Pure |
| Tests Failed | 66 | **18** | PyYAML-Pure |

PyYAML-Pure passes **48 more JSON tests** than PyYAML on the official YAML test suite.

Note: The 18 JSON failures in PyYAML-Pure are mostly tests with custom tags (`!!mytag`, `!!local/foo`) that require `unsafe_load` rather than `safe_load` - these are expected by design.

## When to Use Each

### Use PyYAML-Pure when:
- **Correctness is critical** - parsing complex YAML that PyYAML mishandles
- **Pure Python is required** - no C compiler available, restricted environments
- **YAML 1.2 compliance needed** - modern YAML features
- **Using PyPy** - JIT can improve pure Python performance
- **Debugging YAML issues** - clearer error messages and stack traces
- **Configuration files** - speed difference negligible for typical configs

### Use PyYAML when:
- **Raw speed is critical** - high-volume YAML processing
- **Large files** - processing multi-MB YAML documents
- **C extensions acceptable** - standard deployment environments

## Benchmark Methodology

### Timing
- Each benchmark runs multiple iterations (default: 5)
- Garbage collection forced before each measurement
- Results show mean execution time in milliseconds
- Warmup run performed before timing

### Ratio Calculation
```
Ratio = PyYAML time / PyYAML-Pure time
```
- Ratio > 1: PyYAML-Pure is faster
- Ratio < 1: PyYAML is faster
- Ratio = 0.58x means PyYAML-Pure takes ~1.7x longer

### Test Environment
- Fresh Python process for each implementation
- Module isolation to prevent import conflicts
- Consistent test data generation

## Reproducing Results

```bash
# Clone the repository
git clone <repo-url>
cd pyyaml-pure

# Install original PyYAML for comparison
pip install pyyaml

# Run benchmarks
python benchmarks/run_benchmark.py 10  # 10 iterations

# View results
cat benchmarks/benchmark_results.json
```

### Customizing Benchmarks

Edit `benchmarks/run_benchmark.py` to:
- Add new test cases in `GENERATORS` dict
- Adjust iteration count
- Modify data sizes

## Conclusion

PyYAML-Pure trades some performance for:
- **Better correctness** (100% event parsing vs 76.3%)
- **Pure Python portability** (no C dependencies)
- **Better YAML 1.2 compliance**

For most use cases (configuration files, API responses), the performance difference is negligible. Choose PyYAML-Pure when correctness and portability matter more than raw speed.

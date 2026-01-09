# PyYAML-Pure Test Suite

This directory contains the test suite for PyYAML-Pure. The tests validate correctness against the official YAML test suite and ensure feature parity with PyYAML.

## Quick Start

```bash
# Run all tests
pytest tests/

# Run with verbose output
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=yaml --cov-report=html
```

## Test Files Overview

| File | Tests | Description |
|------|-------|-------------|
| `test_yaml_suite.py` | 824 | Official YAML test suite (src format) |
| `test_yaml_suite_canonical.py` | 808 | Official YAML test suite (data branch format) |
| `test_comments.py` | 28 | Comment preservation feature tests |
| `test_implementation_comparison.py` | 7 | PyYAML vs PyYAML-Pure comparison |
| `conftest.py` | - | Pytest fixtures and configuration |

**Total: ~1,667 tests**

## Test Descriptions

### test_yaml_suite.py

Runs tests from the official [YAML Test Suite](https://github.com/yaml/yaml-test-suite) using the `src/` format where each test is a single YAML file containing multiple test cases.

**Test Types:**
- **Event Parsing** (`test_yaml_suite_parsing`) - Validates that the parser produces correct event streams
- **JSON Comparison** (`test_yaml_suite_json`) - Validates that constructed Python values match expected JSON

```bash
# Run only event parsing tests
pytest tests/test_yaml_suite.py::test_yaml_suite_parsing -v

# Run only JSON comparison tests
pytest tests/test_yaml_suite.py::test_yaml_suite_json -v

# Run a specific test by ID
pytest tests/test_yaml_suite.py -k "2XXW" -v
```

### test_yaml_suite_canonical.py

Alternative test runner using the YAML test suite's `data` branch format, where each test case is a directory containing separate files:
- `in.yaml` - Input YAML
- `test.event` - Expected event stream
- `in.json` - Expected JSON output

```bash
pytest tests/test_yaml_suite_canonical.py -v
```

### test_comments.py

Tests for the comment preservation feature (`comments=True` parameter).

**Test Classes:**
- `TestCommentsParameter` - Tests `comments=True/False` parameter behavior
- `TestCommentPreservation` - Tests that comments survive round-trip
- `TestCommentedMapBehavior` - Tests that `CommentedMap` acts like a dict
- `TestCommentedSeqBehavior` - Tests that `CommentedSeq` acts like a list
- `TestRoundTripFunctions` - Tests legacy `round_trip_*` functions
- `TestEdgeCases` - Tests edge cases (empty docs, scalars, quoted strings)
- `TestCompatibility` - Tests compatibility between modes

```bash
# Run comment tests
pytest tests/test_comments.py -v

# Run a specific test class
pytest tests/test_comments.py::TestCommentPreservation -v
```

### test_implementation_comparison.py

Compares PyYAML-Pure against PyYAML on the same test suite to measure relative correctness.

```bash
# Run comparison tests
pytest tests/test_implementation_comparison.py -v

# Run standalone (generates detailed report)
python tests/test_implementation_comparison.py
```

## Running Specific Tests

```bash
# Run tests matching a pattern
pytest tests/ -k "comment" -v

# Run tests from a specific file
pytest tests/test_comments.py -v

# Run a specific test function
pytest tests/test_comments.py::TestCommentPreservation::test_header_comment_preserved -v

# Run failed tests only (after a previous run)
pytest tests/ --lf

# Run tests and stop on first failure
pytest tests/ -x
```

## Test Markers

Tests are marked with custom markers for filtering:

```bash
# Run slow tests
pytest tests/ -m slow

# Run YAML test suite tests
pytest tests/ -m yaml_suite

# Skip slow tests
pytest tests/ -m "not slow"
```

## Coverage Reports

```bash
# Generate HTML coverage report
pytest tests/ --cov=yaml --cov-report=html
open htmlcov/index.html

# Generate terminal coverage report
pytest tests/ --cov=yaml --cov-report=term-missing

# Generate XML coverage (for CI)
pytest tests/ --cov=yaml --cov-report=xml
```

## Test Requirements

The tests require:
- `pytest` - Test runner
- `pytest-cov` - Coverage reporting (optional)
- YAML test suite at `../yaml-test-suite/` (for suite tests)

Install test dependencies:
```bash
pip install pytest pytest-cov
```

## YAML Test Suite Setup

The YAML test suite tests require the official test suite to be available:

```bash
# Clone the test suite (from project root)
cd ..
git clone https://github.com/yaml/yaml-test-suite.git

# Or set environment variable
export YAML_TEST_SUITE=/path/to/yaml-test-suite
```

## Current Test Results

| Category | Pass Rate |
|----------|-----------|
| Event Parsing | **100%** (308/308) |
| JSON Comparison | **93.5%** (261/279) |
| Comment Preservation | **100%** (28/28) |

See [FAILED_TESTS.md](../FAILED_TESTS.md) for details on the remaining JSON comparison differences.

## Writing New Tests

### Adding a Comment Test

```python
# In test_comments.py
class TestCommentPreservation:
    def test_my_new_comment_feature(self):
        """Description of what this tests."""
        yaml_input = "# Comment\nkey: value"
        data = yaml.safe_load(yaml_input, comments=True)
        output = yaml.safe_dump(data, comments=True)
        assert "# Comment" in output
```

### Adding a General Test

```python
# In a new test file or existing one
import yaml

def test_my_feature():
    """Test description."""
    result = yaml.safe_load("key: value")
    assert result == {"key": "value"}
```

## Continuous Integration

For CI environments, use:

```bash
# Fast test run (skip slow tests)
pytest tests/ -m "not slow" --tb=short

# Full test run with coverage
pytest tests/ --cov=yaml --cov-report=xml --tb=short

# Parallel execution (requires pytest-xdist)
pytest tests/ -n auto
```

"""
Implementation Comparison Tests.

This module compares the pyyaml-pure implementation against the original PyYAML
using the official YAML test suite. It tests both:
1. Event parsing (test.event files) - the primary correctness metric
2. JSON output comparison (in.json files) - value construction

Usage:
    # Run comparison (standalone)
    python tests/test_implementation_comparison.py

    # Run via pytest
    pytest tests/test_implementation_comparison.py -v
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TestResult:
    """Result of a single test case."""

    test_id: str
    test_name: str
    passed: bool
    skipped: bool = False
    error_message: str = ""


@dataclass
class TestSuiteResult:
    """Results for an entire test suite run."""

    implementation: str
    test_type: str  # "events" or "json"
    results: list[TestResult] = field(default_factory=list)
    duration: float = 0.0

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed and not r.skipped)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed and not r.skipped)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.skipped)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def tested(self) -> int:
        return self.total - self.skipped

    @property
    def pass_rate(self) -> float:
        tested = self.tested
        if tested == 0:
            return 0.0
        return (self.passed / tested) * 100


def unescape_yaml(source: str) -> str:
    """Unescape special characters used in YAML test suite."""
    source = source.replace("␣", " ")
    source = source.replace("————»", "\t")
    source = source.replace("———»", "\t")
    source = source.replace("——»", "\t")
    source = source.replace("—»", "\t")
    source = source.replace("»", "\t")
    source = source.replace("⇔", "\uFEFF")
    source = source.replace("↵", "")
    source = source.replace("←", "\r")
    if source.endswith("∎\n"):
        source = source[:-2]
    elif source.endswith("∎"):
        source = source[:-1]
    return source


def get_test_cases() -> list[tuple[str, str, Path, bool]]:
    """Get all test cases from the YAML test suite data branch."""
    data_dir = Path(__file__).parent.parent.parent / "yaml-test-suite" / "data"
    if not data_dir.exists():
        return []

    cases = []
    for test_dir in sorted(data_dir.iterdir()):
        if not test_dir.is_dir():
            continue

        test_id = test_dir.name
        subdirs = [d for d in test_dir.iterdir() if d.is_dir() and d.name.isdigit()]

        if subdirs:
            for subdir in sorted(subdirs):
                case_path = subdir
                name_file = case_path / "==="
                name = name_file.read_text().strip() if name_file.exists() else test_id
                is_error = (case_path / "error").exists()
                cases.append((f"{test_id}/{subdir.name}", name, case_path, is_error))
        else:
            name_file = test_dir / "==="
            name = name_file.read_text().strip() if name_file.exists() else test_id
            is_error = (test_dir / "error").exists()
            cases.append((test_id, name, test_dir, is_error))

    return cases


# =============================================================================
# Event Testing (Primary correctness metric)
# =============================================================================

class EventsHandler:
    """Handler that formats events like the YAML test suite expects."""

    def __init__(self) -> None:
        self.events: list[str] = []

    def event_location(self, *args: Any) -> None:
        pass

    def start_stream(self, encoding: str) -> None:
        self.events.append("+STR\n")

    def end_stream(self) -> None:
        self.events.append("-STR\n")

    def start_document(
        self,
        version: tuple[int, int] | None,
        tag_directives: list[tuple[str, str]],
        implicit: bool,
    ) -> None:
        parts = ["+DOC"]
        if not implicit:
            parts.append("---")
        self.events.append(" ".join(parts) + "\n")

    def end_document(self, implicit: bool) -> None:
        parts = ["-DOC"]
        if not implicit:
            parts.append("...")
        self.events.append(" ".join(parts) + "\n")

    def start_mapping(
        self, anchor: str | None, tag: str | None, implicit: bool, style: int
    ) -> None:
        parts = ["+MAP"]
        if style == 2:  # flow style
            parts.append("{}")
        if anchor:
            parts.append(f"&{anchor}")
        if tag and not implicit:
            parts.append(f"<{tag}>")
        self.events.append(" ".join(parts) + "\n")

    def end_mapping(self) -> None:
        self.events.append("-MAP\n")

    def start_sequence(
        self, anchor: str | None, tag: str | None, implicit: bool, style: int
    ) -> None:
        parts = ["+SEQ"]
        if style == 2:  # flow style
            parts.append("[]")
        if anchor:
            parts.append(f"&{anchor}")
        if tag and not implicit:
            parts.append(f"<{tag}>")
        self.events.append(" ".join(parts) + "\n")

    def end_sequence(self) -> None:
        self.events.append("-SEQ\n")

    def scalar(
        self,
        value: str,
        anchor: str | None,
        tag: str | None,
        plain: bool,
        quoted: bool,
        style: int,
    ) -> None:
        parts = ["=VAL"]
        if anchor:
            parts.append(f"&{anchor}")
        if tag and not (plain or quoted):
            parts.append(f"<{tag}>")

        style_map = {1: ":", 2: "'", 3: '"', 4: "|", 5: ">"}
        indicator = style_map.get(style, ":")
        parts.append(indicator + self._escape_value(value))
        self.events.append(" ".join(parts) + "\n")

    def alias(self, anchor: str) -> None:
        self.events.append(f"=ALI *{anchor}\n")

    def _escape_value(self, value: str) -> str:
        result = []
        for ch in value:
            if ch == "\\":
                result.append("\\\\")
            elif ch == "\x00":
                result.append("\\0")
            elif ch == "\x07":
                result.append("\\a")
            elif ch == "\x08":
                result.append("\\b")
            elif ch == "\t":
                result.append("\\t")
            elif ch == "\n":
                result.append("\\n")
            elif ch == "\x0b":
                result.append("\\v")
            elif ch == "\x0c":
                result.append("\\f")
            elif ch == "\r":
                result.append("\\r")
            elif ch == "\x1b":
                result.append("\\e")
            elif ch == "\x85":
                result.append("\\N")
            elif ch == "\xa0":
                result.append("\\_")
            elif ch == "\u2028":
                result.append("\\L")
            elif ch == "\u2029":
                result.append("\\P")
            elif ord(ch) < 0x20 or (0x7F <= ord(ch) < 0xA0):
                result.append(f"\\x{ord(ch):02x}")
            else:
                result.append(ch)
        return "".join(result)

    def get_output(self) -> str:
        return "".join(self.events)


def test_events_pyyaml_pure(
    test_id: str, test_name: str, test_path: Path, is_error: bool
) -> TestResult:
    """Test event parsing for PyYAML-Pure."""
    yaml_file = test_path / "in.yaml"
    event_file = test_path / "test.event"

    if not yaml_file.exists():
        return TestResult(test_id, test_name, passed=False, skipped=True, error_message="No in.yaml")

    if not event_file.exists():
        return TestResult(test_id, test_name, passed=False, skipped=True, error_message="No test.event")

    yaml_input = unescape_yaml(yaml_file.read_text(encoding="utf-8"))

    # Import PyYAML-Pure parser
    package_dir = Path(__file__).parent.parent
    if str(package_dir) not in sys.path:
        sys.path.insert(0, str(package_dir))

    # Clear modules
    for mod in list(sys.modules.keys()):
        if mod == "yaml" or mod.startswith("yaml."):
            del sys.modules[mod]

    from yaml._parser import Parser

    handler = EventsHandler()
    parser = Parser(handler)

    if is_error:
        try:
            parser.parse(yaml_input)
            # Some error tests are about later stages
        except Exception:
            pass
        return TestResult(test_id, test_name, passed=True, skipped=True, error_message="Error test")

    try:
        parser.parse(yaml_input)
        actual_events = handler.get_output()
    except Exception as e:
        return TestResult(test_id, test_name, passed=False, error_message=f"Parse error: {e}")

    expected_events = event_file.read_text(encoding="utf-8")

    # Normalize for comparison
    expected_lines = [line.rstrip() for line in expected_events.strip().split("\n") if line.strip()]
    actual_lines = [line.rstrip() for line in actual_events.strip().split("\n") if line.strip()]

    if expected_lines == actual_lines:
        return TestResult(test_id, test_name, passed=True)
    else:
        diff_msg = f"Expected {len(expected_lines)} events, got {len(actual_lines)}"
        return TestResult(test_id, test_name, passed=False, error_message=diff_msg)


def test_events_pyyaml(
    test_id: str, test_name: str, test_path: Path, is_error: bool
) -> TestResult:
    """Test event parsing for original PyYAML using subprocess."""
    yaml_file = test_path / "in.yaml"
    event_file = test_path / "test.event"

    if not yaml_file.exists():
        return TestResult(test_id, test_name, passed=False, skipped=True, error_message="No in.yaml")

    if not event_file.exists():
        return TestResult(test_id, test_name, passed=False, skipped=True, error_message="No test.event")

    if is_error:
        return TestResult(test_id, test_name, passed=True, skipped=True, error_message="Error test")

    yaml_input = unescape_yaml(yaml_file.read_text(encoding="utf-8"))
    expected_events = event_file.read_text(encoding="utf-8")

    # Run PyYAML in subprocess to avoid import conflicts
    code = '''
import sys
import yaml

def escape_value(value):
    result = []
    for ch in value:
        if ch == "\\\\": result.append("\\\\\\\\")
        elif ch == "\\x00": result.append("\\\\0")
        elif ch == "\\x07": result.append("\\\\a")
        elif ch == "\\x08": result.append("\\\\b")
        elif ch == "\\t": result.append("\\\\t")
        elif ch == "\\n": result.append("\\\\n")
        elif ch == "\\x0b": result.append("\\\\v")
        elif ch == "\\x0c": result.append("\\\\f")
        elif ch == "\\r": result.append("\\\\r")
        elif ch == "\\x1b": result.append("\\\\e")
        elif ch == "\\x85": result.append("\\\\N")
        elif ch == "\\xa0": result.append("\\\\_")
        elif ch == "\\u2028": result.append("\\\\L")
        elif ch == "\\u2029": result.append("\\\\P")
        elif ord(ch) < 0x20 or (0x7F <= ord(ch) < 0xA0): result.append(f"\\\\x{ord(ch):02x}")
        else: result.append(ch)
    return "".join(result)

yaml_input = sys.stdin.read()
events = []
try:
    for event in yaml.parse(yaml_input):
        if isinstance(event, yaml.StreamStartEvent):
            events.append("+STR")
        elif isinstance(event, yaml.StreamEndEvent):
            events.append("-STR")
        elif isinstance(event, yaml.DocumentStartEvent):
            events.append("+DOC" + (" ---" if event.explicit else ""))
        elif isinstance(event, yaml.DocumentEndEvent):
            events.append("-DOC" + (" ..." if event.explicit else ""))
        elif isinstance(event, yaml.MappingStartEvent):
            parts = ["+MAP"]
            if event.flow_style: parts.append("{}")
            if event.anchor: parts.append(f"&{event.anchor}")
            if event.tag and event.implicit[0] == False: parts.append(f"<{event.tag}>")
            events.append(" ".join(parts))
        elif isinstance(event, yaml.MappingEndEvent):
            events.append("-MAP")
        elif isinstance(event, yaml.SequenceStartEvent):
            parts = ["+SEQ"]
            if event.flow_style: parts.append("[]")
            if event.anchor: parts.append(f"&{event.anchor}")
            if event.tag and event.implicit == False: parts.append(f"<{event.tag}>")
            events.append(" ".join(parts))
        elif isinstance(event, yaml.SequenceEndEvent):
            events.append("-SEQ")
        elif isinstance(event, yaml.ScalarEvent):
            parts = ["=VAL"]
            if event.anchor: parts.append(f"&{event.anchor}")
            if event.tag and event.implicit[0] == False and event.implicit[1] == False:
                parts.append(f"<{event.tag}>")
            style_map = {None: ":", "'": "'", '"': '"', "|": "|", ">": ">"}
            indicator = style_map.get(event.style, ":")
            parts.append(indicator + escape_value(event.value))
            events.append(" ".join(parts))
        elif isinstance(event, yaml.AliasEvent):
            events.append(f"=ALI *{event.anchor}")
    print("\\n".join(events))
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
'''

    result = subprocess.run(
        [sys.executable, "-c", code],
        input=yaml_input,
        capture_output=True,
        text=True,
        cwd="/",
    )

    if result.returncode != 0:
        return TestResult(test_id, test_name, passed=False, error_message=f"Parse error: {result.stderr[:100]}")

    actual_events = result.stdout

    expected_lines = [line.rstrip() for line in expected_events.strip().split("\n") if line.strip()]
    actual_lines = [line.rstrip() for line in actual_events.strip().split("\n") if line.strip()]

    if expected_lines == actual_lines:
        return TestResult(test_id, test_name, passed=True)
    else:
        diff_msg = f"Expected {len(expected_lines)} events, got {len(actual_lines)}"
        return TestResult(test_id, test_name, passed=False, error_message=diff_msg)


# =============================================================================
# JSON Testing (Value construction)
# =============================================================================

def parse_multi_json(json_text: str) -> list[Any]:
    """Parse JSON text that may contain multiple JSON values."""
    decoder = json.JSONDecoder()
    results = []
    idx = 0
    while idx < len(json_text):
        while idx < len(json_text) and json_text[idx] in " \t\n\r":
            idx += 1
        if idx >= len(json_text):
            break
        try:
            obj, end = decoder.raw_decode(json_text, idx)
            results.append(obj)
            idx = end
        except json.JSONDecodeError:
            break
    return results


def normalize_for_comparison(value: Any, expected: Any = None) -> Any:
    """Normalize values for comparison."""
    if isinstance(value, set):
        return {k: None for k in sorted(value, key=str)}
    elif isinstance(value, bytes):
        import base64
        return base64.b64encode(value).decode("ascii")
    elif isinstance(value, dict):
        return {k: normalize_for_comparison(v) for k, v in value.items()}
    elif isinstance(value, list):
        if value and all(isinstance(item, tuple) and len(item) == 2 for item in value):
            if isinstance(expected, list) and expected and all(isinstance(e, dict) and len(e) == 1 for e in expected):
                return [{k: normalize_for_comparison(v)} for k, v in value]
        return [normalize_for_comparison(v) for v in value]
    return value


def normalize_expected(value: Any) -> Any:
    """Normalize expected JSON values."""
    if isinstance(value, str):
        base64_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
        stripped = value.replace("\n", "")
        if "\n" in value and len(stripped) > 10 and all(c in base64_chars for c in stripped):
            return stripped
        return value
    elif isinstance(value, dict):
        return {k: normalize_expected(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [normalize_expected(v) for v in value]
    return value


def test_json_pyyaml_pure(
    test_id: str, test_name: str, test_path: Path, is_error: bool
) -> TestResult:
    """Test JSON output for PyYAML-Pure."""
    yaml_file = test_path / "in.yaml"
    json_file = test_path / "in.json"

    if not yaml_file.exists():
        return TestResult(test_id, test_name, passed=False, skipped=True, error_message="No in.yaml")
    if not json_file.exists():
        return TestResult(test_id, test_name, passed=False, skipped=True, error_message="No in.json")
    if is_error:
        return TestResult(test_id, test_name, passed=False, skipped=True, error_message="Error test")

    yaml_input = unescape_yaml(yaml_file.read_text(encoding="utf-8"))

    package_dir = Path(__file__).parent.parent
    if str(package_dir) not in sys.path:
        sys.path.insert(0, str(package_dir))

    for mod in list(sys.modules.keys()):
        if mod == "yaml" or mod.startswith("yaml."):
            del sys.modules[mod]

    import yaml as yaml_impl

    try:
        results = list(yaml_impl.safe_load_all(yaml_input))
        result = results[0] if len(results) == 1 else results
    except Exception as e:
        return TestResult(test_id, test_name, passed=False, error_message=f"Parse error: {e}")

    try:
        json_text = json_file.read_text(encoding="utf-8")
        json_values = parse_multi_json(json_text)
        expected = json_values[0] if len(json_values) == 1 else json_values
    except Exception as e:
        return TestResult(test_id, test_name, passed=False, skipped=True, error_message=f"JSON error: {e}")

    expected_normalized = normalize_expected(expected)
    result_normalized = normalize_for_comparison(result, expected_normalized)

    if result_normalized == expected_normalized:
        return TestResult(test_id, test_name, passed=True)
    else:
        return TestResult(test_id, test_name, passed=False, error_message="Mismatch")


def test_json_pyyaml(
    test_id: str, test_name: str, test_path: Path, is_error: bool
) -> TestResult:
    """Test JSON output for original PyYAML using subprocess."""
    yaml_file = test_path / "in.yaml"
    json_file = test_path / "in.json"

    if not yaml_file.exists():
        return TestResult(test_id, test_name, passed=False, skipped=True, error_message="No in.yaml")
    if not json_file.exists():
        return TestResult(test_id, test_name, passed=False, skipped=True, error_message="No in.json")
    if is_error:
        return TestResult(test_id, test_name, passed=False, skipped=True, error_message="Error test")

    yaml_input = unescape_yaml(yaml_file.read_text(encoding="utf-8"))

    code = '''
import sys
import json
import yaml
import base64

yaml_input = sys.stdin.read()
try:
    results = list(yaml.safe_load_all(yaml_input))
    result = results[0] if len(results) == 1 else results

    def convert(v):
        if isinstance(v, set):
            return {k: None for k in sorted(v, key=str)}
        elif isinstance(v, bytes):
            return base64.b64encode(v).decode("ascii")
        elif isinstance(v, dict):
            return {k: convert(val) for k, val in v.items()}
        elif isinstance(v, list):
            if v and all(isinstance(item, tuple) and len(item) == 2 for item in v):
                return [{k: convert(val)} for k, val in v]
            return [convert(val) for val in v]
        return v

    print(json.dumps(convert(result)))
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
'''

    result = subprocess.run(
        [sys.executable, "-c", code],
        input=yaml_input,
        capture_output=True,
        text=True,
        cwd="/",
    )

    if result.returncode != 0:
        return TestResult(test_id, test_name, passed=False, error_message=f"Parse error: {result.stderr[:100]}")

    try:
        actual = json.loads(result.stdout)
    except json.JSONDecodeError:
        return TestResult(test_id, test_name, passed=False, error_message="Invalid JSON output")

    try:
        json_text = json_file.read_text(encoding="utf-8")
        json_values = parse_multi_json(json_text)
        expected = json_values[0] if len(json_values) == 1 else json_values
    except Exception as e:
        return TestResult(test_id, test_name, passed=False, skipped=True, error_message=f"JSON error: {e}")

    expected_normalized = normalize_expected(expected)

    if actual == expected_normalized:
        return TestResult(test_id, test_name, passed=True)
    else:
        return TestResult(test_id, test_name, passed=False, error_message="Mismatch")


# =============================================================================
# Test Runners
# =============================================================================

def run_event_tests(implementation: str) -> TestSuiteResult:
    """Run event parsing tests for an implementation."""
    test_cases = get_test_cases()
    result = TestSuiteResult(implementation=implementation, test_type="events")

    test_func = test_events_pyyaml_pure if implementation == "PyYAML-Pure" else test_events_pyyaml

    start_time = time.time()
    for test_id, test_name, test_path, is_error in test_cases:
        test_result = test_func(test_id, test_name, test_path, is_error)
        result.results.append(test_result)
    result.duration = time.time() - start_time

    return result


def run_json_tests(implementation: str) -> TestSuiteResult:
    """Run JSON comparison tests for an implementation."""
    test_cases = get_test_cases()
    result = TestSuiteResult(implementation=implementation, test_type="json")

    test_func = test_json_pyyaml_pure if implementation == "PyYAML-Pure" else test_json_pyyaml

    start_time = time.time()
    for test_id, test_name, test_path, is_error in test_cases:
        test_result = test_func(test_id, test_name, test_path, is_error)
        result.results.append(test_result)
    result.duration = time.time() - start_time

    return result


def print_comparison_report(
    pyyaml_events: TestSuiteResult,
    pure_events: TestSuiteResult,
    pyyaml_json: TestSuiteResult,
    pure_json: TestSuiteResult,
) -> None:
    """Print a comprehensive comparison report."""
    print("\n" + "=" * 80)
    print("YAML IMPLEMENTATION COMPARISON REPORT")
    print("=" * 80)

    # Test suite info
    total_tests = pyyaml_events.total
    error_tests = pyyaml_events.skipped
    valid_tests = total_tests - error_tests

    print(f"\nYAML Test Suite: {total_tests} total tests ({valid_tests} valid, {error_tests} error/skipped)")
    print("Reference: https://matrix.yaml.info/")

    # Event parsing comparison (PRIMARY METRIC)
    print("\n" + "-" * 80)
    print("EVENT PARSING (Primary Correctness Metric)")
    print("-" * 80)
    print(f"\n{'Metric':<25} {'PyYAML':>15} {'PyYAML-Pure':>15} {'Difference':>15}")
    print("-" * 70)
    print(f"{'Tested':<25} {pyyaml_events.tested:>15} {pure_events.tested:>15} {'-':>15}")
    print(f"{'Passed':<25} {pyyaml_events.passed:>15} {pure_events.passed:>15} {pure_events.passed - pyyaml_events.passed:>+15}")
    print(f"{'Failed':<25} {pyyaml_events.failed:>15} {pure_events.failed:>15} {pure_events.failed - pyyaml_events.failed:>+15}")
    print(f"{'Pass Rate':<25} {pyyaml_events.pass_rate:>14.1f}% {pure_events.pass_rate:>14.1f}% {pure_events.pass_rate - pyyaml_events.pass_rate:>+14.1f}%")
    print(f"{'Duration (sec)':<25} {pyyaml_events.duration:>15.3f} {pure_events.duration:>15.3f} {pure_events.duration - pyyaml_events.duration:>+15.3f}")

    # JSON comparison
    json_tested_pyyaml = pyyaml_json.tested
    json_tested_pure = pure_json.tested

    print("\n" + "-" * 80)
    print("JSON COMPARISON (Value Construction)")
    print("-" * 80)
    print(f"\n{'Metric':<25} {'PyYAML':>15} {'PyYAML-Pure':>15} {'Difference':>15}")
    print("-" * 70)
    print(f"{'Tested':<25} {json_tested_pyyaml:>15} {json_tested_pure:>15} {'-':>15}")
    print(f"{'Passed':<25} {pyyaml_json.passed:>15} {pure_json.passed:>15} {pure_json.passed - pyyaml_json.passed:>+15}")
    print(f"{'Failed':<25} {pyyaml_json.failed:>15} {pure_json.failed:>15} {pure_json.failed - pyyaml_json.failed:>+15}")
    print(f"{'Pass Rate':<25} {pyyaml_json.pass_rate:>14.1f}% {pure_json.pass_rate:>14.1f}% {pure_json.pass_rate - pyyaml_json.pass_rate:>+14.1f}%")

    # Find event test differences
    pyyaml_event_results = {r.test_id: r for r in pyyaml_events.results}
    pure_event_results = {r.test_id: r for r in pure_events.results}

    pure_only_pass_events = []
    pyyaml_only_pass_events = []

    for test_id in pyyaml_event_results:
        pyyaml_r = pyyaml_event_results[test_id]
        pure_r = pure_event_results.get(test_id)
        if not pure_r or pyyaml_r.skipped or pure_r.skipped:
            continue
        if pure_r.passed and not pyyaml_r.passed:
            pure_only_pass_events.append(test_id)
        elif pyyaml_r.passed and not pure_r.passed:
            pyyaml_only_pass_events.append(test_id)

    if pure_only_pass_events:
        print(f"\n## Event Tests ONLY PyYAML-Pure Passes ({len(pure_only_pass_events)})")
        for tid in pure_only_pass_events[:10]:
            print(f"  - {tid}")
        if len(pure_only_pass_events) > 10:
            print(f"  ... and {len(pure_only_pass_events) - 10} more")

    if pyyaml_only_pass_events:
        print(f"\n## Event Tests ONLY PyYAML Passes ({len(pyyaml_only_pass_events)})")
        for tid in pyyaml_only_pass_events[:10]:
            print(f"  - {tid}")
        if len(pyyaml_only_pass_events) > 10:
            print(f"  ... and {len(pyyaml_only_pass_events) - 10} more")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"\nEvent Parsing (Primary):")
    print(f"  PyYAML:      {pyyaml_events.pass_rate:.1f}% ({pyyaml_events.passed}/{pyyaml_events.tested})")
    print(f"  PyYAML-Pure: {pure_events.pass_rate:.1f}% ({pure_events.passed}/{pure_events.tested})")

    print(f"\nJSON Comparison:")
    print(f"  PyYAML:      {pyyaml_json.pass_rate:.1f}% ({pyyaml_json.passed}/{pyyaml_json.tested})")
    print(f"  PyYAML-Pure: {pure_json.pass_rate:.1f}% ({pure_json.passed}/{pure_json.tested})")

    print("\n" + "=" * 80)


def run_comparison() -> tuple[TestSuiteResult, TestSuiteResult, TestSuiteResult, TestSuiteResult]:
    """Run full comparison between PyYAML and pyyaml-pure."""
    print("Running event parsing tests for PyYAML-Pure...")
    pure_events = run_event_tests("PyYAML-Pure")

    print("Running event parsing tests for PyYAML (this may take a while)...")
    pyyaml_events = run_event_tests("PyYAML")

    print("Running JSON comparison tests for PyYAML-Pure...")
    pure_json = run_json_tests("PyYAML-Pure")

    print("Running JSON comparison tests for PyYAML...")
    pyyaml_json = run_json_tests("PyYAML")

    return pyyaml_events, pure_events, pyyaml_json, pure_json


# Pytest integration
try:
    import pytest

    @pytest.fixture(scope="module")
    def comparison_results():
        return run_comparison()

    def test_pure_event_pass_rate(comparison_results):
        _, pure_events, _, _ = comparison_results
        assert pure_events.pass_rate >= 95.0, f"Event pass rate {pure_events.pass_rate:.1f}% below 95%"

    def test_pure_json_pass_rate(comparison_results):
        _, _, _, pure_json = comparison_results
        assert pure_json.pass_rate >= 90.0, f"JSON pass rate {pure_json.pass_rate:.1f}% below 90%"

    def test_comparison_summary(comparison_results):
        print_comparison_report(*comparison_results)

except ImportError:
    pass


if __name__ == "__main__":
    results = run_comparison()
    print_comparison_report(*results)

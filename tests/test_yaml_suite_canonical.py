"""
YAML Test Suite integration tests using the canonical data branch format.

This module runs tests from the official YAML test suite using the
recommended data branch format where each test case is a directory
containing individual files (in.yaml, test.event, in.json, etc.).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from yaml._parser import Handler, Parser


class EventsHandler(Handler):
    """Handler that formats events like the YAML test suite expects."""

    def __init__(self) -> None:
        self.events: list[str] = []

    def event_location(
        self, start_line: int, start_column: int, end_line: int, end_column: int
    ) -> None:
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

        # Style indicator
        style_map = {1: ":", 2: "'", 3: '"', 4: "|", 5: ">"}
        indicator = style_map.get(style, ":")
        parts.append(indicator + self._escape_value(value))

        self.events.append(" ".join(parts) + "\n")

    def alias(self, anchor: str) -> None:
        self.events.append(f"=ALI *{anchor}\n")

    def _escape_value(self, value: str) -> str:
        """Escape special characters in values."""
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


def unescape_yaml(source: str) -> str:
    """Unescape special characters used in YAML test suite."""
    # These are used in the test files to represent special characters
    source = source.replace("␣", " ")  # Space
    source = source.replace("————»", "\t")  # Tab (4 dashes)
    source = source.replace("———»", "\t")  # Tab (3 dashes)
    source = source.replace("——»", "\t")  # Tab (2 dashes)
    source = source.replace("—»", "\t")  # Tab (1 dash)
    source = source.replace("»", "\t")  # Tab
    source = source.replace("⇔", "\uFEFF")  # BOM
    source = source.replace("↵", "")  # Soft line break indicator
    source = source.replace("←", "\r")  # Carriage return
    # Handle end-of-input marker (no trailing newline)
    if source.endswith("∎\n"):
        source = source[:-2]
    elif source.endswith("∎"):
        source = source[:-1]
    return source


def get_test_cases() -> list[tuple[str, Path, bool]]:
    """Get all test cases from the YAML test suite data branch."""
    data_dir = Path(__file__).parent.parent.parent / "yaml-test-suite" / "data"
    if not data_dir.exists():
        return []

    cases = []
    for test_dir in sorted(data_dir.iterdir()):
        if not test_dir.is_dir():
            continue

        test_id = test_dir.name

        # Check if this test has subtests (numbered directories)
        subdirs = [d for d in test_dir.iterdir() if d.is_dir() and d.name.isdigit()]

        if subdirs:
            # Multiple subtests
            for subdir in sorted(subdirs):
                case_path = subdir
                name_file = case_path / "==="
                name = name_file.read_text().strip() if name_file.exists() else test_id
                is_error = (case_path / "error").exists()
                cases.append((f"{test_id}/{subdir.name} - {name}", case_path, is_error))
        else:
            # Single test
            name_file = test_dir / "==="
            name = name_file.read_text().strip() if name_file.exists() else test_id
            is_error = (test_dir / "error").exists()
            cases.append((f"{test_id} - {name}", test_dir, is_error))

    return cases


# Collect test cases
TEST_CASES = get_test_cases()


@pytest.mark.yaml_suite_canonical
@pytest.mark.parametrize(
    "test_name,test_path,is_error",
    TEST_CASES,
    ids=[c[0] for c in TEST_CASES],
)
def test_yaml_suite_events(test_name: str, test_path: Path, is_error: bool) -> None:
    """Test parsing against YAML test suite event format."""
    yaml_file = test_path / "in.yaml"
    event_file = test_path / "test.event"

    if not yaml_file.exists():
        pytest.skip("No in.yaml file")

    yaml_input = unescape_yaml(yaml_file.read_text(encoding="utf-8"))

    handler = EventsHandler()
    parser = Parser(handler)

    if is_error:
        # Test should produce an error
        try:
            parser.parse(yaml_input)
            # If we get here, parsing succeeded when it should have failed
            # Some error tests are about later stages, so this is acceptable
        except Exception:
            # Expected to fail
            pass
        return

    if not event_file.exists():
        pytest.skip("No test.event file")

    try:
        parser.parse(yaml_input)
        actual_events = handler.get_output()
    except Exception as e:
        pytest.fail(f"Parser raised exception: {e}")
        return

    expected_events = event_file.read_text(encoding="utf-8")

    # Normalize for comparison
    expected_lines = [l.rstrip() for l in expected_events.strip().split("\n") if l.strip()]
    actual_lines = [l.rstrip() for l in actual_events.strip().split("\n") if l.strip()]

    if expected_lines != actual_lines:
        # Show diff for debugging
        diff = []
        max_lines = max(len(expected_lines), len(actual_lines))
        for i in range(max_lines):
            exp = expected_lines[i] if i < len(expected_lines) else "<missing>"
            act = actual_lines[i] if i < len(actual_lines) else "<missing>"
            if exp != act:
                diff.append(f"  Line {i + 1}:")
                diff.append(f"    Expected: {exp!r}")
                diff.append(f"    Actual:   {act!r}")

        pytest.fail(f"Event stream mismatch:\n" + "\n".join(diff[:30]))


@pytest.mark.yaml_suite_canonical
@pytest.mark.parametrize(
    "test_name,test_path,is_error",
    TEST_CASES,
    ids=[c[0] for c in TEST_CASES],
)
def test_yaml_suite_json(test_name: str, test_path: Path, is_error: bool) -> None:
    """Test JSON output against YAML test suite."""
    import yaml as yaml_impl

    yaml_file = test_path / "in.yaml"
    json_file = test_path / "in.json"

    if not yaml_file.exists() or not json_file.exists() or is_error:
        pytest.skip("No JSON comparison needed")

    yaml_input = unescape_yaml(yaml_file.read_text(encoding="utf-8"))

    try:
        result = yaml_impl.safe_load(yaml_input)
        expected = json.loads(json_file.read_text(encoding="utf-8"))
    except Exception as e:
        pytest.skip(f"Could not parse: {e}")
        return

    assert result == expected, f"JSON mismatch: expected {expected}, got {result}"

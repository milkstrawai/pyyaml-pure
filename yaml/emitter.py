"""
YAML emitter - PyYAML compatible.

This module provides the Emitter class that converts events
to YAML output.
"""

from __future__ import annotations

import re
from typing import IO, TYPE_CHECKING, Any

from .error import EmitterError
from .events import (
    AliasEvent,
    DocumentEndEvent,
    DocumentStartEvent,
    Event,
    MappingEndEvent,
    MappingStartEvent,
    ScalarEvent,
    SequenceEndEvent,
    SequenceStartEvent,
    StreamEndEvent,
    StreamStartEvent,
)

if TYPE_CHECKING:
    pass


class Emitter:
    """
    Emitter class that converts events to YAML output.

    This class handles the formatting and serialization of
    YAML events into a character stream.
    """

    DEFAULT_TAG_PREFIXES = {
        "!": "!",
        "tag:yaml.org,2002:": "!!",
    }

    def __init__(
        self,
        stream: IO[str] | None = None,
        canonical: bool = False,
        indent: int | None = None,
        width: int | None = None,
        allow_unicode: bool = True,
        line_break: str | None = None,
    ) -> None:
        self.stream = stream
        self.canonical = canonical
        self.allow_unicode = allow_unicode
        self.best_indent = indent if indent and indent > 1 else 2
        self.best_width = width if width and width > self.best_indent * 2 else 80
        self.best_line_break = line_break or "\n"

        self.states: list[Any] = []
        self.state: Any = self.expect_stream_start
        self.events: list[Event] = []
        self.event: Event | None = None
        self.indents: list[int | None] = []
        self.indent: int | None = None
        self.flow_level: int = 0
        self.root_context: bool = False
        self.sequence_context: bool = False
        self.mapping_context: bool = False
        self.simple_key_context: bool = False

        self.line: int = 0
        self.column: int = 0
        self.whitespace: bool = True
        self.indentation: bool = True
        self.open_ended: bool = False

        self.tag_prefixes: dict[str, str] = {}
        self.prepared_anchor: str | None = None
        self.prepared_tag: str | None = None
        self.analysis: Any = None
        self.style: str | None = None

        self._output: list[str] = []

    def dispose(self) -> None:
        """Clean up resources."""
        self.states = []
        self.state = None

    def emit(self, event: Event) -> None:
        """Emit a single event."""
        self.events.append(event)
        while not self.need_more_events():
            self.event = self.events.pop(0)
            self.state()
            self.event = None

    def need_more_events(self) -> bool:
        """Check if more events are needed before emitting."""
        if not self.events:
            return True
        event = self.events[0]
        if isinstance(event, DocumentStartEvent):
            return self.need_events(1)
        elif isinstance(event, SequenceStartEvent):
            return self.need_events(2)
        elif isinstance(event, MappingStartEvent):
            return self.need_events(3)
        return False

    def need_events(self, count: int) -> bool:
        """Check if we have enough events."""
        level = 0
        for event in self.events[1:]:
            if isinstance(event, (DocumentStartEvent, SequenceStartEvent, MappingStartEvent)):
                level += 1
            elif isinstance(event, (DocumentEndEvent, SequenceEndEvent, MappingEndEvent)):
                level -= 1
            elif isinstance(event, StreamEndEvent):
                level = -1
            if level < 0:
                return False
        return len(self.events) < count + 1

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        """Increase the indentation level."""
        self.indents.append(self.indent)
        if self.indent is None:
            if flow:
                self.indent = self.best_indent
            else:
                self.indent = 0
        elif not indentless:
            self.indent += self.best_indent

    # State handlers

    def expect_stream_start(self) -> None:
        if isinstance(self.event, StreamStartEvent):
            self.write_stream_start()
            self.state = self.expect_first_document_start
        else:
            raise EmitterError(f"expected StreamStartEvent, but got {self.event}")

    def expect_nothing(self) -> None:
        raise EmitterError(f"expected nothing, but got {self.event}")

    def expect_first_document_start(self) -> None:
        return self.expect_document_start(first=True)

    def expect_document_start(self, first: bool = False) -> None:
        if isinstance(self.event, DocumentStartEvent):
            if (self.event.version or self.event.tags) and self.open_ended:
                self.write_indicator("...", need_whitespace=True)
                self.write_indent()

            if self.event.version:
                version_text = self.prepare_version(self.event.version)
                self.write_version_directive(version_text)

            self.tag_prefixes = self.DEFAULT_TAG_PREFIXES.copy()
            if self.event.tags:
                for handle, prefix in self.event.tags.items():
                    self.tag_prefixes[prefix] = handle
                    handle_text = self.prepare_tag_handle(handle)
                    prefix_text = self.prepare_tag_prefix(prefix)
                    self.write_tag_directive(handle_text, prefix_text)

            implicit = (
                first
                and not self.event.explicit
                and not self.canonical
                and not self.event.version
                and not self.event.tags
                and not self.check_empty_document()
            )
            if not implicit:
                self.write_indent()
                self.write_indicator("---", need_whitespace=True)
                if self.canonical:
                    self.write_indent()

            self.state = self.expect_document_root
        elif isinstance(self.event, StreamEndEvent):
            if self.open_ended:
                self.write_indicator("...", need_whitespace=True)
                self.write_indent()
            self.write_stream_end()
            self.state = self.expect_nothing
        else:
            raise EmitterError(f"expected DocumentStartEvent, but got {self.event}")

    def expect_document_end(self) -> None:
        if isinstance(self.event, DocumentEndEvent):
            self.write_indent()
            if self.event.explicit:
                self.write_indicator("...", need_whitespace=True)
                self.write_indent()
            self.flush_stream()
            self.state = self.expect_document_start
        else:
            raise EmitterError(f"expected DocumentEndEvent, but got {self.event}")

    def expect_document_root(self) -> None:
        self.states.append(self.expect_document_end)
        self.expect_node(root=True)

    def expect_node(
        self,
        root: bool = False,
        sequence: bool = False,
        mapping: bool = False,
        simple_key: bool = False,
    ) -> None:
        self.root_context = root
        self.sequence_context = sequence
        self.mapping_context = mapping
        self.simple_key_context = simple_key

        if isinstance(self.event, AliasEvent):
            self.expect_alias()
        elif isinstance(self.event, (ScalarEvent, SequenceStartEvent, MappingStartEvent)):
            self.process_anchor("&")
            self.process_tag()
            if isinstance(self.event, ScalarEvent):
                self.expect_scalar()
            elif isinstance(self.event, SequenceStartEvent):
                if self.flow_level or self.canonical or self.event.flow_style or self.check_empty_sequence():
                    self.expect_flow_sequence()
                else:
                    self.expect_block_sequence()
            elif isinstance(self.event, MappingStartEvent):
                if self.flow_level or self.canonical or self.event.flow_style or self.check_empty_mapping():
                    self.expect_flow_mapping()
                else:
                    self.expect_block_mapping()
        else:
            raise EmitterError(f"expected NodeEvent, but got {self.event}")

    def expect_alias(self) -> None:
        if not isinstance(self.event, AliasEvent) or self.event.anchor is None:
            raise EmitterError("expected AliasEvent with anchor")
        self.process_anchor("*")
        self.state = self.states.pop()

    def expect_scalar(self) -> None:
        self.increase_indent(flow=True)
        self.process_scalar()
        self.indent = self.indents.pop()
        self.state = self.states.pop()

    # Flow sequence

    def expect_flow_sequence(self) -> None:
        self.write_indicator("[", whitespace=True)
        self.flow_level += 1
        self.increase_indent(flow=True)
        self.state = self.expect_first_flow_sequence_item

    def expect_first_flow_sequence_item(self) -> None:
        if isinstance(self.event, SequenceEndEvent):
            self.indent = self.indents.pop()
            self.flow_level -= 1
            self.write_indicator("]", whitespace=False)
            self.state = self.states.pop()
        else:
            if self.canonical or self.column > self.best_width:
                self.write_indent()
            self.states.append(self.expect_flow_sequence_item)
            self.expect_node(sequence=True)

    def expect_flow_sequence_item(self) -> None:
        if isinstance(self.event, SequenceEndEvent):
            self.indent = self.indents.pop()
            self.flow_level -= 1
            if self.canonical:
                self.write_indicator(",", whitespace=False)
                self.write_indent()
            self.write_indicator("]", whitespace=False)
            self.state = self.states.pop()
        else:
            self.write_indicator(",", whitespace=False)
            if self.canonical or self.column > self.best_width:
                self.write_indent()
            self.states.append(self.expect_flow_sequence_item)
            self.expect_node(sequence=True)

    # Flow mapping

    def expect_flow_mapping(self) -> None:
        self.write_indicator("{", whitespace=True)
        self.flow_level += 1
        self.increase_indent(flow=True)
        self.state = self.expect_first_flow_mapping_key

    def expect_first_flow_mapping_key(self) -> None:
        if isinstance(self.event, MappingEndEvent):
            self.indent = self.indents.pop()
            self.flow_level -= 1
            self.write_indicator("}", whitespace=False)
            self.state = self.states.pop()
        else:
            if self.canonical or self.column > self.best_width:
                self.write_indent()
            if not self.canonical and self.check_simple_key():
                self.states.append(self.expect_flow_mapping_simple_value)
                self.expect_node(mapping=True, simple_key=True)
            else:
                self.write_indicator("?", whitespace=True)
                self.states.append(self.expect_flow_mapping_value)
                self.expect_node(mapping=True)

    def expect_flow_mapping_key(self) -> None:
        if isinstance(self.event, MappingEndEvent):
            self.indent = self.indents.pop()
            self.flow_level -= 1
            if self.canonical:
                self.write_indicator(",", whitespace=False)
                self.write_indent()
            self.write_indicator("}", whitespace=False)
            self.state = self.states.pop()
        else:
            self.write_indicator(",", whitespace=False)
            if self.canonical or self.column > self.best_width:
                self.write_indent()
            if not self.canonical and self.check_simple_key():
                self.states.append(self.expect_flow_mapping_simple_value)
                self.expect_node(mapping=True, simple_key=True)
            else:
                self.write_indicator("?", whitespace=True)
                self.states.append(self.expect_flow_mapping_value)
                self.expect_node(mapping=True)

    def expect_flow_mapping_simple_value(self) -> None:
        self.write_indicator(":", whitespace=False)
        self.states.append(self.expect_flow_mapping_key)
        self.expect_node(mapping=True)

    def expect_flow_mapping_value(self) -> None:
        if self.canonical or self.column > self.best_width:
            self.write_indent()
        self.write_indicator(":", whitespace=True)
        self.states.append(self.expect_flow_mapping_key)
        self.expect_node(mapping=True)

    # Block sequence

    def expect_block_sequence(self) -> None:
        indentless = self.mapping_context and not self.indentation
        self.increase_indent(flow=False, indentless=indentless)
        self.state = self.expect_first_block_sequence_item

    def expect_first_block_sequence_item(self) -> None:
        return self.expect_block_sequence_item(first=True)

    def expect_block_sequence_item(self, first: bool = False) -> None:
        if not first and isinstance(self.event, SequenceEndEvent):
            self.indent = self.indents.pop()
            self.state = self.states.pop()
        else:
            self.write_indent()
            self.write_indicator("-", need_whitespace=True, indentation=True)
            self.states.append(self.expect_block_sequence_item)
            self.expect_node(sequence=True)

    # Block mapping

    def expect_block_mapping(self) -> None:
        self.increase_indent(flow=False)
        self.state = self.expect_first_block_mapping_key

    def expect_first_block_mapping_key(self) -> None:
        return self.expect_block_mapping_key(first=True)

    def expect_block_mapping_key(self, first: bool = False) -> None:
        if not first and isinstance(self.event, MappingEndEvent):
            self.indent = self.indents.pop()
            self.state = self.states.pop()
        else:
            self.write_indent()
            if self.check_simple_key():
                self.states.append(self.expect_block_mapping_simple_value)
                self.expect_node(mapping=True, simple_key=True)
            else:
                self.write_indicator("?", need_whitespace=True, indentation=True)
                self.states.append(self.expect_block_mapping_value)
                self.expect_node(mapping=True)

    def expect_block_mapping_simple_value(self) -> None:
        self.write_indicator(":", whitespace=False)
        self.states.append(self.expect_block_mapping_key)
        self.expect_node(mapping=True)

    def expect_block_mapping_value(self) -> None:
        self.write_indent()
        self.write_indicator(":", need_whitespace=True, indentation=True)
        self.states.append(self.expect_block_mapping_key)
        self.expect_node(mapping=True)

    # Checkers

    def check_empty_sequence(self) -> bool:
        return (
            isinstance(self.event, SequenceStartEvent)
            and len(self.events) > 0
            and isinstance(self.events[0], SequenceEndEvent)
        )

    def check_empty_mapping(self) -> bool:
        return (
            isinstance(self.event, MappingStartEvent)
            and len(self.events) > 0
            and isinstance(self.events[0], MappingEndEvent)
        )

    def check_empty_document(self) -> bool:
        if not isinstance(self.event, DocumentStartEvent) or not self.events:
            return False
        event = self.events[0]
        return (
            isinstance(event, ScalarEvent)
            and event.anchor is None
            and event.tag is None
            and event.implicit
            and event.value == ""
        )

    def check_simple_key(self) -> bool:
        if isinstance(self.event, (AliasEvent, ScalarEvent)):
            return True
        if isinstance(self.event, (SequenceStartEvent, MappingStartEvent)):
            return self.event.flow_style or self.check_empty_sequence() or self.check_empty_mapping()
        return False

    # Processors

    def process_anchor(self, indicator: str) -> None:
        if not hasattr(self.event, "anchor") or self.event.anchor is None:
            self.prepared_anchor = None
            return

        anchor = self.event.anchor
        if self.prepared_anchor is None:
            self.prepared_anchor = self.prepare_anchor(anchor)
        if self.prepared_anchor:
            self.write_indicator(indicator + self.prepared_anchor, need_whitespace=True)
        self.prepared_anchor = None

    def process_tag(self) -> None:
        tag = getattr(self.event, "tag", None)
        if isinstance(self.event, ScalarEvent):
            if self.style is None:
                self.style = self.choose_scalar_style()
            if (not self.canonical or tag is None) and (
                (self.style == "" and self.event.implicit[0])
                or (self.style != "" and self.event.implicit[1])
            ):
                self.prepared_tag = None
                return
            if self.event.implicit[0] and tag is None:
                tag = "!"
                self.prepared_tag = None
        else:
            if (not self.canonical or tag is None) and getattr(self.event, "implicit", False):
                self.prepared_tag = None
                return

        if tag is None:
            raise EmitterError("tag is not specified")

        if self.prepared_tag is None:
            self.prepared_tag = self.prepare_tag(tag)
        if self.prepared_tag:
            self.write_indicator(self.prepared_tag, need_whitespace=True)
        self.prepared_tag = None

    def process_scalar(self) -> None:
        if self.analysis is None:
            self.analysis = self.analyze_scalar(self.event.value)
        if self.style is None:
            self.style = self.choose_scalar_style()
        split = not self.simple_key_context

        if self.style == '"':
            self.write_double_quoted(self.analysis.scalar, split)
        elif self.style == "'":
            self.write_single_quoted(self.analysis.scalar, split)
        elif self.style == ">":
            self.write_folded(self.analysis.scalar)
        elif self.style == "|":
            self.write_literal(self.analysis.scalar)
        else:
            self.write_plain(self.analysis.scalar, split)

        self.analysis = None
        self.style = None

    def choose_scalar_style(self) -> str | None:
        if self.analysis is None:
            self.analysis = self.analyze_scalar(self.event.value)

        if self.event.style == '"' or self.canonical:
            return '"'

        if not self.event.style and self.event.implicit[0]:
            if not (
                self.simple_key_context
                and (self.analysis.empty or self.analysis.multiline)
            ):
                if self.flow_level and self.analysis.allow_flow_plain:
                    return ""
                elif not self.flow_level and self.analysis.allow_block_plain:
                    return ""

        if self.event.style and self.event.style in "|>":
            if not self.flow_level and not self.simple_key_context and self.analysis.allow_block:
                return self.event.style

        if not self.event.style or self.event.style == "'":
            if self.analysis.allow_single_quoted and not (
                self.simple_key_context and self.analysis.multiline
            ):
                return "'"

        return '"'

    # Analyzers

    def analyze_scalar(self, scalar: str) -> Any:
        """Analyze a scalar to determine how it should be formatted."""

        class ScalarAnalysis:
            def __init__(self) -> None:
                self.scalar = scalar
                self.empty = len(scalar) == 0
                self.multiline = "\n" in scalar
                self.allow_flow_plain = True
                self.allow_block_plain = True
                self.allow_single_quoted = True
                self.allow_double_quoted = True
                self.allow_block = True

        analysis = ScalarAnalysis()

        # Simple checks
        if not scalar:
            analysis.allow_flow_plain = False
            analysis.allow_block_plain = False
            return analysis

        # Check for special characters
        if scalar[0] in "-?:,[]{}#&*!|>'\"%@`":
            analysis.allow_flow_plain = False
            analysis.allow_block_plain = False

        if scalar[0] in " \t":
            analysis.allow_flow_plain = False
            analysis.allow_block_plain = False

        if scalar[-1] in " \t":
            analysis.allow_flow_plain = False
            analysis.allow_block_plain = False

        return analysis

    # Preparers

    def prepare_version(self, version: tuple[int, int]) -> str:
        major, minor = version
        if major != 1:
            raise EmitterError(f"unsupported YAML version: {major}.{minor}")
        return f"{major}.{minor}"

    def prepare_tag_handle(self, handle: str) -> str:
        if not handle:
            raise EmitterError("tag handle must not be empty")
        if handle[0] != "!" or handle[-1] != "!":
            raise EmitterError(f"tag handle must start and end with '!': {handle}")
        for ch in handle[1:-1]:
            if not ("0" <= ch <= "9" or "A" <= ch <= "Z" or "a" <= ch <= "z" or ch in "-_"):
                raise EmitterError(f"invalid character in tag handle: {ch!r}")
        return handle

    def prepare_tag_prefix(self, prefix: str) -> str:
        if not prefix:
            raise EmitterError("tag prefix must not be empty")
        return prefix

    def prepare_tag(self, tag: str) -> str:
        if not tag:
            raise EmitterError("tag must not be empty")
        if tag == "!":
            return tag

        for prefix, handle in self.tag_prefixes.items():
            if tag.startswith(prefix) and (prefix == "!" or len(prefix) < len(tag)):
                suffix = tag[len(prefix) :]
                return f"{handle}{suffix}"

        return f"!<{tag}>"

    def prepare_anchor(self, anchor: str) -> str:
        if not anchor:
            raise EmitterError("anchor must not be empty")
        for ch in anchor:
            if not ("0" <= ch <= "9" or "A" <= ch <= "Z" or "a" <= ch <= "z" or ch in "-_"):
                raise EmitterError(f"invalid character in anchor: {ch!r}")
        return anchor

    # Writers

    def write_stream_start(self) -> None:
        pass

    def write_stream_end(self) -> None:
        self.flush_stream()

    def write_indicator(
        self,
        indicator: str,
        need_whitespace: bool = False,
        whitespace: bool = False,
        indentation: bool = False,
    ) -> None:
        if self.whitespace or not need_whitespace:
            data = indicator
        else:
            data = " " + indicator
        self.whitespace = whitespace
        self.indentation = self.indentation and indentation
        self.column += len(data)
        self.open_ended = False
        self._write(data)

    def write_indent(self) -> None:
        indent = self.indent or 0
        if not self.indentation or self.column > indent or (self.column == indent and not self.whitespace):
            self.write_line_break()
        if self.column < indent:
            self.whitespace = True
            data = " " * (indent - self.column)
            self.column = indent
            self._write(data)

    def write_line_break(self, data: str | None = None) -> None:
        if data is None:
            data = self.best_line_break
        self.whitespace = True
        self.indentation = True
        self.line += 1
        self.column = 0
        self._write(data)

    def write_version_directive(self, version_text: str) -> None:
        self._write(f"%YAML {version_text}")
        self.write_line_break()

    def write_tag_directive(self, handle_text: str, prefix_text: str) -> None:
        self._write(f"%TAG {handle_text} {prefix_text}")
        self.write_line_break()

    def write_plain(self, text: str, split: bool = True) -> None:
        if not text:
            return

        if not self.whitespace:
            self._write(" ")
            self.column += 1

        self.whitespace = False
        self.indentation = False

        spaces = False
        breaks = False
        start = end = 0

        while end <= len(text):
            ch = text[end] if end < len(text) else None
            if spaces:
                if ch != " ":
                    if start + 1 == end and self.column > self.best_width and split:
                        self.write_indent()
                        self.whitespace = False
                        self.indentation = False
                    else:
                        self._write(text[start:end])
                        self.column += end - start
                    start = end
            elif breaks:
                if ch not in "\n":
                    if text[start] == "\n":
                        self.write_line_break()
                    for _ in text[start:end]:
                        if _ == "\n":
                            self.write_line_break()
                        else:
                            self.write_line_break(_)
                    self.write_indent()
                    self.whitespace = False
                    self.indentation = False
                    start = end
            else:
                if ch is None or ch in " \n":
                    self._write(text[start:end])
                    self.column += end - start
                    start = end

            if ch is not None:
                spaces = ch == " "
                breaks = ch == "\n"
            end += 1

    def write_single_quoted(self, text: str, split: bool = True) -> None:
        self.write_indicator("'", whitespace=True)
        spaces = False
        breaks = False
        start = end = 0

        while end <= len(text):
            ch = text[end] if end < len(text) else None
            if spaces:
                if ch != " ":
                    if start + 1 == end and self.column > self.best_width and split and start != 0 and end != len(text):
                        self.write_indent()
                    else:
                        self._write(text[start:end])
                        self.column += end - start
                    start = end
            elif breaks:
                if ch not in "\n":
                    if text[start] == "\n":
                        self.write_line_break()
                    for _ in text[start:end]:
                        if _ == "\n":
                            self.write_line_break()
                        else:
                            self.write_line_break(_)
                    self.write_indent()
                    start = end
            else:
                if ch is None or ch in " '\n":
                    self._write(text[start:end])
                    self.column += end - start
                    if ch == "'":
                        self._write("''")
                        self.column += 2
                    start = end + 1

            if ch is not None:
                spaces = ch == " "
                breaks = ch == "\n"
            end += 1

        self.write_indicator("'", whitespace=False)

    ESCAPE_REPLACEMENTS = {
        "\0": "0",
        "\x07": "a",
        "\x08": "b",
        "\x09": "t",
        "\x0a": "n",
        "\x0b": "v",
        "\x0c": "f",
        "\x0d": "r",
        "\x1b": "e",
        '"': '"',
        "\\": "\\",
        "\x85": "N",
        "\xa0": "_",
        "\u2028": "L",
        "\u2029": "P",
    }

    def write_double_quoted(self, text: str, split: bool = True) -> None:
        self.write_indicator('"', whitespace=True)
        start = end = 0

        while end <= len(text):
            ch = None
            if end < len(text):
                ch = text[end]
            if ch is None or ch in '"\\\x85\u2028\u2029\ufeff' or not (
                "\x20" <= ch <= "\x7e"
                or (self.allow_unicode and ("\xa0" <= ch <= "\ud7ff" or "\ue000" <= ch <= "\ufffd"))
            ):
                if start < end:
                    self._write(text[start:end])
                    self.column += end - start
                if ch is not None:
                    if ch in self.ESCAPE_REPLACEMENTS:
                        self._write("\\" + self.ESCAPE_REPLACEMENTS[ch])
                        self.column += 2
                    elif ch <= "\xff":
                        self._write(f"\\x{ord(ch):02x}")
                        self.column += 4
                    elif ch <= "\uffff":
                        self._write(f"\\u{ord(ch):04x}")
                        self.column += 6
                    else:
                        self._write(f"\\U{ord(ch):08x}")
                        self.column += 10
                start = end + 1
            if 0 < end < len(text) - 1 and (ch == " " or start >= end) and self.column + (end - start) > self.best_width and split:
                self._write(text[start:end] + "\\")
                self.column += end - start + 1
                start = end
                self.write_indent()

            end += 1

        self.write_indicator('"', whitespace=False)

    def write_folded(self, text: str) -> None:
        hints = self.determine_block_hints(text)
        self.write_indicator(">" + hints, need_whitespace=True)
        if hints[-1:] == "+":
            self.open_ended = True
        self.write_line_break()
        leading_space = True
        spaces = False
        breaks = True
        start = end = 0

        while end <= len(text):
            ch = text[end] if end < len(text) else None
            if breaks:
                if ch is None or ch not in "\n":
                    if not leading_space and ch is not None and ch != " " and text[start] == "\n":
                        self.write_line_break()
                    leading_space = ch == " "
                    for _ in text[start:end]:
                        if _ == "\n":
                            self.write_line_break()
                        else:
                            self.write_line_break(_)
                    if ch is not None:
                        self.write_indent()
                    start = end
            elif spaces:
                if ch != " ":
                    if start + 1 == end and self.column > self.best_width:
                        self.write_indent()
                    else:
                        self._write(text[start:end])
                        self.column += end - start
                    start = end
            else:
                if ch is None or ch in " \n":
                    self._write(text[start:end])
                    self.column += end - start
                    if ch is None:
                        self.write_line_break()
                    start = end

            if ch is not None:
                breaks = ch == "\n"
                spaces = ch == " "
            end += 1

    def write_literal(self, text: str) -> None:
        hints = self.determine_block_hints(text)
        self.write_indicator("|" + hints, need_whitespace=True)
        if hints[-1:] == "+":
            self.open_ended = True
        self.write_line_break()
        breaks = True
        start = end = 0

        while end <= len(text):
            ch = text[end] if end < len(text) else None
            if breaks:
                if ch is None or ch not in "\n":
                    for _ in text[start:end]:
                        if _ == "\n":
                            self.write_line_break()
                        else:
                            self.write_line_break(_)
                    if ch is not None:
                        self.write_indent()
                    start = end
            else:
                if ch is None or ch == "\n":
                    self._write(text[start:end])
                    self.column += end - start
                    if ch is None:
                        self.write_line_break()
                    start = end
            if ch is not None:
                breaks = ch == "\n"
            end += 1

    def determine_block_hints(self, text: str) -> str:
        hints = ""
        if text:
            if text[0] in " \n":
                hints += str(self.best_indent)
            if text[-1] != "\n":
                hints += "-"
            elif len(text) == 1 or text[-2] == "\n":
                hints += "+"
        return hints

    def flush_stream(self) -> None:
        if self.stream:
            self.stream.write("".join(self._output))
            self._output = []

    def _write(self, data: str) -> None:
        if self.stream:
            self._output.append(data)
        else:
            self._output.append(data)

    def get_output(self) -> str:
        """Get the output as a string."""
        return "".join(self._output)

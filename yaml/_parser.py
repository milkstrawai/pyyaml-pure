"""
YAML 1.2 recursive descent parser.

This module implements a complete YAML 1.2 parser based on the grammar rules
from the YAML specification. It uses recursive descent with backtracking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING, Callable, TypeVar
from urllib.parse import unquote

from ._scanner import StringScanner
from ._source import Location, Source
from .error import Mark, SyntaxError as YAMLSyntaxError

if TYPE_CHECKING:
    from typing import Any

T = TypeVar("T")


class ScalarStyle(IntEnum):
    """Scalar presentation styles matching Psych/libyaml."""

    PLAIN = 1
    SINGLE_QUOTED = 2
    DOUBLE_QUOTED = 3
    LITERAL = 4
    FOLDED = 5


class CollectionStyle(IntEnum):
    """Collection styles."""

    BLOCK = 1
    FLOW = 2


# Pre-compiled regex patterns for performance
RE_NB_JSON = re.compile(r"[\u0009\u0020-\U0010FFFF]")
RE_NB_CHAR = re.compile(
    r"[\u0009\u000A\u000D\u0020-\u007E\u0085\u00A0-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]"
)
RE_B_BREAK = re.compile(r"\u000A|\u000D\u000A?")
RE_S_WHITE = re.compile(r"[\u0020\u0009]")
RE_S_WHITE_STAR = re.compile(r"[\u0020\u0009]*")
RE_NS_CHAR = re.compile(r"[\u0021-\u007E\u0085\u00A0-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]")
RE_NS_HEX_DIGIT = re.compile(r"[0-9A-Fa-f]")
RE_NS_DEC_DIGIT = re.compile(r"[0-9]")
RE_FLOW_INDICATOR = re.compile(r"[,\[\]{}]")
RE_C_INDICATOR = re.compile(r"[-?:,\[\]{}#&*!|>'\"%@`]")
RE_INDENT = re.compile(r" *")
RE_NS_WORD_CHAR = re.compile(r"[0-9A-Za-z\-]")
RE_NS_ANCHOR_CHAR = re.compile(r"[0-9A-Za-z\-_]")
RE_BARE_DOC_MARKER = re.compile(r"(?:---|\.\.\.)(?=\s|$)")
RE_DIRECTIVES_END = re.compile(r"---(?=\s|$)")
RE_DOCUMENT_END = re.compile(r"\.\.\.(?=\s|$)")
# For detecting block scalar indentation, only skip truly blank lines (spaces+newline)
# NOT lines with # (which is content in block scalars, not a comment)
RE_DETECT_INDENT = re.compile(r"((?:\ *\n)*)(\ *)")
RE_COMMENT_LINE = re.compile(r"\ *#.*\n")
RE_BLANK_LINE = re.compile(r"\ *\n")
RE_NS_PLAIN_SAFE_OUT = re.compile(r"[^\u0000-\u0020#]")
RE_NS_PLAIN_FIRST = re.compile(r"[^\u0000-\u0020\-?:,\[\]{}#&*!|>'\"%@`]")
RE_URI_CHAR = re.compile(r"[0-9A-Za-z\-#;/?:@&=+$,_.!~*'()\[\]]|%[0-9A-Fa-f]{2}")
RE_TAG_CHAR = re.compile(r"[0-9A-Za-z\-#;/?:@&=+$_.~*'()\[\]]|%[0-9A-Fa-f]{2}")
# Pre-compiled for hot path in _parse_nb_char
RE_B_CHAR_OR_BOM = re.compile(r"[\u000A\u000D\uFEFF]")

# Character sets for fast membership testing (avoiding regex in hot paths)
_S_WHITE_CHARS = frozenset(" \t")
_B_BREAK_CHARS = frozenset("\n\r")
_NS_CHAR_EXCLUDE = frozenset(" \t\n\r")
_FLOW_INDICATORS = frozenset(",[]{}")
_C_INDICATORS = frozenset("-?:,[]{}#&*!|>'\"%@`")


# Escape sequences for double-quoted strings
DOUBLE_QUOTED_ESCAPES = {
    "0": "\x00",
    "a": "\x07",
    "b": "\x08",
    "t": "\x09",
    "\t": "\x09",
    "n": "\x0a",
    "v": "\x0b",
    "f": "\x0c",
    "r": "\x0d",
    "e": "\x1b",
    " ": " ",
    '"': '"',
    "/": "/",
    "\\": "\\",
    "N": "\u0085",
    "_": "\u00a0",
    "L": "\u2028",
    "P": "\u2029",
}


# Context classes for error messages
@dataclass(slots=True)
class BlockMappingContext:
    pos: int
    indent: int

    def format(self, source: Source) -> str:
        indent_str = f" (indent={self.indent})" if self.indent != -1 else ""
        return f"block mapping at {source.point(self.pos)}{indent_str}"


@dataclass(slots=True)
class BlockSequenceContext:
    pos: int
    indent: int

    def format(self, source: Source) -> str:
        indent_str = f" (indent={self.indent})" if self.indent != -1 else ""
        return f"block sequence at {source.point(self.pos)}{indent_str}"


@dataclass(slots=True)
class FlowMappingContext:
    pos: int
    context: str

    def format(self, source: Source) -> str:
        return f"flow mapping at {source.point(self.pos)} (context={self.context})"


@dataclass(slots=True)
class FlowSequenceContext:
    pos: int
    context: str

    def format(self, source: Source) -> str:
        return f"flow sequence at {source.point(self.pos)} (context={self.context})"


@dataclass(slots=True)
class DoubleQuotedContext:
    pos: int

    def format(self, source: Source) -> str:
        return f"double quoted scalar at {source.point(self.pos)}"


ContextType = (
    BlockMappingContext
    | BlockSequenceContext
    | FlowMappingContext
    | FlowSequenceContext
    | DoubleQuotedContext
)


class Context:
    """Tracks parser context for error messages."""

    __slots__ = ("_contexts", "_deepest")

    def __init__(self) -> None:
        self._contexts: list[ContextType] = []
        self._deepest: list[ContextType] = []

    def push(self, ctx: ContextType) -> None:
        self._contexts.append(ctx)
        if len(self._contexts) > len(self._deepest):
            self._deepest = self._contexts.copy()

    def pop(self) -> None:
        self._contexts.pop()

    def syntax_error(
        self, source: Source, filename: str, pos: int, message: str
    ) -> YAMLSyntaxError:
        stack = self._deepest if not self._contexts else self._contexts
        if stack:
            pos = stack[-1].pos
            context_lines = "\n".join(f" {elem.format(source)}" for elem in stack)
            message = f"{message}\nwithin:\n{context_lines}"

        line = source.line(pos)
        column = source.column(pos)
        mark = Mark(filename, pos, line, column, None, None)
        return YAMLSyntaxError(problem=message, problem_mark=mark)


# Event dataclasses
@dataclass(slots=True)
class StreamStartEvent:
    location: Location

    def accept(self, handler: Handler) -> None:
        handler.event_location(*self.location.to_tuple())
        handler.start_stream("UTF-8")


@dataclass(slots=True)
class StreamEndEvent:
    location: Location

    def accept(self, handler: Handler) -> None:
        handler.event_location(*self.location.to_tuple())
        handler.end_stream()


@dataclass(slots=True)
class DocumentStartEvent:
    location: Location
    version: tuple[int, int] | None = None
    tag_directives: dict[str, str] = field(default_factory=dict)
    implicit: bool = True

    def accept(self, handler: Handler) -> None:
        handler.event_location(*self.location.to_tuple())
        handler.start_document(self.version, list(self.tag_directives.items()), self.implicit)


@dataclass(slots=True)
class DocumentEndEvent:
    location: Location
    implicit: bool = True

    def accept(self, handler: Handler) -> None:
        handler.event_location(*self.location.to_tuple())
        handler.end_document(self.implicit)


@dataclass(slots=True)
class MappingStartEvent:
    location: Location
    style: CollectionStyle
    anchor: str | None = None
    tag: str | None = None

    def accept(self, handler: Handler) -> None:
        handler.event_location(*self.location.to_tuple())
        # implicit=True means tag was auto-resolved; implicit=False means explicitly tagged
        handler.start_mapping(
            self.anchor, self.tag, self.tag is None, int(self.style)
        )


@dataclass(slots=True)
class MappingEndEvent:
    location: Location

    def accept(self, handler: Handler) -> None:
        handler.event_location(*self.location.trim().to_tuple())
        handler.end_mapping()


@dataclass(slots=True)
class SequenceStartEvent:
    location: Location
    style: CollectionStyle
    anchor: str | None = None
    tag: str | None = None

    def accept(self, handler: Handler) -> None:
        handler.event_location(*self.location.to_tuple())
        # implicit=True means tag was auto-resolved; implicit=False means explicitly tagged
        handler.start_sequence(
            self.anchor, self.tag, self.tag is None, int(self.style)
        )


@dataclass(slots=True)
class SequenceEndEvent:
    location: Location

    def accept(self, handler: Handler) -> None:
        handler.event_location(*self.location.trim().to_tuple())
        handler.end_sequence()


@dataclass(slots=True)
class ScalarEvent:
    location: Location
    source: str
    value: str
    style: ScalarStyle
    anchor: str | None = None
    tag: str | None = None

    def accept(self, handler: Handler) -> None:
        handler.event_location(*self.location.trim().to_tuple())
        # plain/quoted flags indicate implicit tag resolution (no explicit tag)
        # The non-specific tag "!" is still an explicit tag, so don't set these flags
        plain = not self.tag and self.style == ScalarStyle.PLAIN
        quoted = not self.tag and self.style != ScalarStyle.PLAIN
        handler.scalar(self.value, self.anchor, self.tag, plain, quoted, int(self.style))


@dataclass(slots=True)
class AliasEvent:
    location: Location
    name: str

    def accept(self, handler: Handler) -> None:
        handler.event_location(*self.location.to_tuple())
        handler.alias(self.name)


EventType = (
    StreamStartEvent
    | StreamEndEvent
    | DocumentStartEvent
    | DocumentEndEvent
    | MappingStartEvent
    | MappingEndEvent
    | SequenceStartEvent
    | SequenceEndEvent
    | ScalarEvent
    | AliasEvent
)


class Handler:
    """Base handler for parser events."""

    def event_location(
        self, start_line: int, start_column: int, end_line: int, end_column: int
    ) -> None:
        pass

    def start_stream(self, encoding: str) -> None:
        pass

    def end_stream(self) -> None:
        pass

    def start_document(
        self,
        version: tuple[int, int] | None,
        tag_directives: list[tuple[str, str]],
        implicit: bool,
    ) -> None:
        pass

    def end_document(self, implicit: bool) -> None:
        pass

    def start_mapping(
        self, anchor: str | None, tag: str | None, implicit: bool, style: int
    ) -> None:
        pass

    def end_mapping(self) -> None:
        pass

    def start_sequence(
        self, anchor: str | None, tag: str | None, implicit: bool, style: int
    ) -> None:
        pass

    def end_sequence(self) -> None:
        pass

    def scalar(
        self,
        value: str,
        anchor: str | None,
        tag: str | None,
        plain: bool,
        quoted: bool,
        style: int,
    ) -> None:
        pass

    def alias(self, anchor: str) -> None:
        pass

    def comment(self, comment: Any) -> None:
        pass


class Parser:
    """
    YAML 1.2 recursive descent parser.

    Implements the YAML 1.2 grammar using recursive descent with backtracking.
    Each parse_* method corresponds to a grammar production rule.
    """

    __slots__ = (
        "_scanner",
        "_filename",
        "_source",
        "_handler",
        "_events_cache",
        "_document_start_event",
        "_document_end_event",
        "_tag_directives",
        "_tag",
        "_anchor",
        "_in_bare_document",
        "_in_scalar",
        "_text_prefix",
        "_comments",
        "_context",
    )

    def __init__(self, handler: Handler) -> None:
        self._scanner: StringScanner | None = None
        self._filename: str = "<unknown>"
        self._source: Source | None = None
        self._handler = handler
        self._events_cache: list[list[EventType]] = []
        self._document_start_event: DocumentStartEvent | None = None
        self._document_end_event: DocumentEndEvent | None = None
        self._tag_directives: dict[str, str] = {}
        self._tag: str | None = None
        self._anchor: str | None = None
        self._in_bare_document = False
        self._in_scalar = False
        self._text_prefix = ""
        self._comments: dict[int, Any] | None = None
        self._context = Context()

    def parse(self, yaml: str, filename: str = "<unknown>", comments: bool = False) -> bool:
        """
        Parse a YAML string.

        Args:
            yaml: The YAML content to parse.
            filename: Filename for error messages.
            comments: Whether to preserve comments.

        Returns:
            True if parsing succeeded.

        Raises:
            SyntaxError: If the input is not valid YAML.
        """
        # Ensure trailing newline
        if yaml and not yaml.endswith("\n"):
            yaml = yaml + "\n"

        self._scanner = StringScanner(yaml)
        self._filename = filename
        self._source = Source(yaml)
        self._comments = {} if comments else None

        self._parse_l_yaml_stream()
        self._comments = None
        return True

    # -------------------------------------------------------------------------
    # Parsing helpers
    # -------------------------------------------------------------------------

    def _raise_syntax_error(self, message: str) -> None:
        """Raise a syntax error at the current position."""
        assert self._source is not None
        assert self._scanner is not None
        raise self._context.syntax_error(self._source, self._filename, self._scanner.pos, message)

    def _match(self, pattern: str | re.Pattern[str]) -> int | None:
        """
        Try to match pattern at current position.

        Handles bare document restrictions (--- and ... markers).
        Returns match length or None.
        """
        # Optimized: direct attribute access and minimal checks
        scanner = self._scanner

        if self._in_bare_document:
            pos = scanner._pos
            if pos >= scanner._len:
                return None
            if pos == 0 or scanner._string[pos - 1] == "\n":
                if scanner.check(RE_BARE_DOC_MARKER):
                    return None

        return scanner.skip(pattern)

    def _try(self, func: Callable[[], T]) -> T | bool:
        """
        Try to parse with backtracking.

        If func returns falsy, restore scanner position.
        """
        # Optimized: direct attribute access
        scanner = self._scanner
        pos_start = scanner._pos
        result = func()
        if not result:
            scanner._pos = pos_start
            return False
        return result

    def _plus(self, func: Callable[[], bool]) -> bool:
        """Match one or more (rule+)."""
        # Optimized: direct attribute access
        if not func():
            return False
        scanner = self._scanner
        pos_current = scanner._pos
        while func():
            new_pos = scanner._pos
            if new_pos == pos_current:
                break
            pos_current = new_pos
        return True

    def _star(self, func: Callable[[], bool]) -> bool:
        """Match zero or more (rule*)."""
        # Optimized: direct attribute access
        scanner = self._scanner
        pos_current = scanner._pos
        while func():
            new_pos = scanner._pos
            if new_pos == pos_current:
                break
            pos_current = new_pos
        return True

    def _peek(self, func: Callable[[], T]) -> T:
        """Look ahead without consuming."""
        assert self._scanner is not None
        pos_start = self._scanner.pos
        result = self._try(func)
        self._scanner.pos = pos_start
        return result

    def _start_of_line(self) -> bool:
        """Check if at start of line."""
        # Optimized: direct attribute access
        scanner = self._scanner
        pos = scanner._pos
        return pos == 0 or pos >= scanner._len or scanner._string[pos - 1] == "\n"

    def _at_document_boundary(self) -> bool:
        """Check if at a document boundary marker (--- or ...) at start of line."""
        assert self._scanner is not None
        if not self._start_of_line():
            return False
        # Check for --- or ... followed by whitespace/newline/eof
        return bool(self._scanner.check(RE_BARE_DOC_MARKER))

    def _from(self, pos: int) -> str:
        """Get string from pos to current position."""
        assert self._scanner is not None
        return self._scanner.string[pos : self._scanner.pos]

    def _detect_indent(self, n: int) -> int:
        """Auto-detect indentation level.

        Returns the additional indentation m beyond the base level n.
        For n=-1 (top level), returns the absolute column position.
        """
        assert self._scanner is not None
        pos = self._scanner.pos
        in_seq = pos > 0 and self._scanner.string[pos - 1] in "-?:"

        match = self._scanner.check(RE_DETECT_INDENT)
        if match is None:
            return 0

        pre = self._scanner[1] or ""
        m = len(self._scanner[2] or "")

        # Only add +1 when after seq/mapping indicator AND there are blank lines before content
        # For compact notation (content on same line), don't add +1
        if in_seq and pre:
            # After sequence/mapping indicator with newlines before content
            # The detected indent is correct, no adjustment needed
            pass
        elif n >= 0:
            # For nested content, compute relative to parent
            m -= n

        # For n == -1 (top level), use m as-is (actual detected column position)
        return max(0, m)

    def _count_spaces(self) -> int:
        """Count spaces at current position without consuming them.

        Used for compact notation where we need the raw space count.
        """
        assert self._scanner is not None
        match = self._scanner.check(RE_INDENT)
        return len(match) if match else 0

    # -------------------------------------------------------------------------
    # Event handling
    # -------------------------------------------------------------------------

    def _comments_flush(self) -> None:
        """Flush comments to the handler."""
        if self._comments:
            for comment in self._comments.values():
                self._handler.comment(comment)
            self._comments.clear()

    def _document_end_event_flush(self) -> None:
        """Flush document end event if pending."""
        if self._document_end_event:
            self._comments_flush()
            self._document_end_event.accept(self._handler)
            assert self._source is not None
            assert self._scanner is not None
            self._document_start_event = DocumentStartEvent(
                Location.point(self._source, self._scanner.pos)
            )
            self._tag_directives = self._document_start_event.tag_directives
            self._document_end_event = None

    def _events_cache_push(self) -> None:
        """Start a new event cache level."""
        self._events_cache.append([])

    def _events_cache_pop(self) -> list[EventType]:
        """Pop and return cached events."""
        return self._events_cache.pop()

    def _events_cache_flush(self) -> None:
        """Pop cache and flush events to next level."""
        for event in self._events_cache_pop():
            self._events_push(event)

    def _events_push(self, event: EventType) -> None:
        """Push an event to the handler or cache."""
        assert self._source is not None
        assert self._scanner is not None

        if not self._events_cache:
            if self._document_start_event:
                if isinstance(event, (MappingStartEvent, SequenceStartEvent, ScalarEvent)):
                    self._document_start_event.accept(self._handler)
                    self._document_start_event = None
                    self._document_end_event = DocumentEndEvent(
                        Location.point(self._source, self._scanner.pos)
                    )
            event.accept(self._handler)
        else:
            self._events_cache[-1].append(event)

    def _events_push_flush_properties(
        self,
        event: MappingStartEvent | SequenceStartEvent | ScalarEvent | StreamStartEvent | StreamEndEvent,
    ) -> None:
        """Push event and flush anchor/tag properties."""
        if self._anchor:
            if hasattr(event, "anchor"):
                event.anchor = self._anchor
            self._anchor = None
        if self._tag:
            if hasattr(event, "tag"):
                event.tag = self._tag
            self._tag = None
        self._events_push(event)

    # -------------------------------------------------------------------------
    # Context management
    # -------------------------------------------------------------------------

    def _within_block_mapping(self, pos: int, indent: int, func: Callable[[], T]) -> T:
        self._context.push(BlockMappingContext(pos, indent))
        try:
            return func()
        finally:
            self._context.pop()

    def _within_block_sequence(self, pos: int, indent: int, func: Callable[[], T]) -> T:
        self._context.push(BlockSequenceContext(pos, indent))
        try:
            return func()
        finally:
            self._context.pop()

    def _within_flow_mapping(self, pos: int, context: str, func: Callable[[], T]) -> T:
        self._context.push(FlowMappingContext(pos, context))
        try:
            return func()
        finally:
            self._context.pop()

    def _within_flow_sequence(self, pos: int, context: str, func: Callable[[], T]) -> T:
        self._context.push(FlowSequenceContext(pos, context))
        try:
            return func()
        finally:
            self._context.pop()

    def _within_double_quoted(self, pos: int, func: Callable[[], T]) -> T:
        self._context.push(DoubleQuotedContext(pos))
        try:
            return func()
        finally:
            self._context.pop()

    # -------------------------------------------------------------------------
    # Grammar rules
    # -------------------------------------------------------------------------

    # [002] nb-json
    def _parse_nb_json(self) -> bool:
        return bool(self._match(RE_NB_JSON))

    # [023] c-flow-indicator
    def _parse_c_flow_indicator(self) -> bool:
        return bool(self._match(RE_FLOW_INDICATOR))

    # [027] nb-char
    def _parse_nb_char(self) -> bool:
        # Optimized: direct attribute access and pre-compiled regex
        scanner = self._scanner
        pos_start = scanner._pos

        if self._match(RE_NB_CHAR):
            pos_end = scanner._pos
            scanner._pos = pos_start
            # Exclude b-char and BOM (use pre-compiled pattern)
            if self._match(RE_B_CHAR_OR_BOM):
                scanner._pos = pos_start
                return False
            self._scanner.pos = pos_end
            return True
        return False

    # [028] b-break - Optimized with direct char check
    def _parse_b_break(self) -> bool:
        scanner = self._scanner
        pos = scanner._pos
        if pos >= scanner._len:
            return False
        ch = scanner._string[pos]
        if ch == '\n':
            scanner._pos = pos + 1
            return True
        if ch == '\r':
            scanner._pos = pos + 1
            # Check for \r\n
            if scanner._pos < scanner._len and scanner._string[scanner._pos] == '\n':
                scanner._pos += 1
            return True
        return False

    # [029] b-as-line-feed
    _parse_b_as_line_feed = _parse_b_break

    # [030] b-non-content
    _parse_b_non_content = _parse_b_break

    # [033] s-white - Optimized with direct char check
    def _parse_s_white(self) -> bool:
        scanner = self._scanner
        pos = scanner._pos
        if pos < scanner._len and scanner._string[pos] in _S_WHITE_CHARS:
            scanner._pos = pos + 1
            if self._in_scalar:
                self._text_prefix = scanner._string[pos:pos + 1]
            return True
        return False

    # Effectively star { parse_s_white }
    def _parse_s_white_star(self) -> bool:
        self._match(RE_S_WHITE_STAR)
        return True

    # [034] ns-char - Use regex for correctness, keep parse state
    def _parse_ns_char(self) -> bool:
        scanner = self._scanner
        pos_start = scanner._pos

        if self._match(RE_NS_CHAR):
            if self._in_scalar:
                self._text_prefix = scanner._string[pos_start:scanner._pos]
            return True
        return False

    # [036] ns-hex-digit
    def _parse_ns_hex_digit(self) -> bool:
        return bool(self._match(RE_NS_HEX_DIGIT))

    # [039] ns-uri-char
    def _parse_ns_uri_char(self) -> bool:
        return bool(
            self._try(
                lambda: bool(self._match("%")) and self._parse_ns_hex_digit() and self._parse_ns_hex_digit()
            )
            or self._match(RE_URI_CHAR)
        )

    # [040] ns-tag-char
    def _parse_ns_tag_char(self) -> bool:
        assert self._scanner is not None
        pos_start = self._scanner.pos

        if self._parse_ns_uri_char():
            pos_end = self._scanner.pos
            self._scanner.pos = pos_start
            if self._match("!") or self._parse_c_flow_indicator():
                self._scanner.pos = pos_start
                return False
            self._scanner.pos = pos_end
            return True
        return False

    # [062] c-ns-esc-char - Escape sequence in double-quoted string
    def _parse_c_ns_esc_char(self) -> str | None:
        assert self._scanner is not None

        if not self._match("\\"):
            return None

        # Simple escapes
        ch = self._scanner.peek()
        if ch in DOUBLE_QUOTED_ESCAPES:
            self._scanner.pos += 1
            return DOUBLE_QUOTED_ESCAPES[ch]

        # Unicode escapes
        if ch == "x":
            self._scanner.pos += 1
            if hex_val := self._parse_hex_escape(2):
                return chr(int(hex_val, 16))
            return None
        elif ch == "u":
            self._scanner.pos += 1
            if hex_val := self._parse_hex_escape(4):
                return chr(int(hex_val, 16))
            return None
        elif ch == "U":
            self._scanner.pos += 1
            if hex_val := self._parse_hex_escape(8):
                return chr(int(hex_val, 16))
            return None

        return None

    def _parse_hex_escape(self, count: int) -> str | None:
        assert self._scanner is not None
        result = ""
        for _ in range(count):
            if self._parse_ns_hex_digit():
                result += self._scanner.string[self._scanner.pos - 1]
            else:
                return None
        return result

    # [063] s-indent(n)
    def _parse_s_indent(self, n: int) -> bool:
        if n < 0:
            # n/a case - indentation is not applicable (e.g., block keys)
            # This should prevent continuation, so return False
            return False
        if n == 0:
            return True  # 0 spaces required, always matches
        assert self._scanner is not None
        match = self._scanner.check(RE_INDENT)
        if match is not None and len(match) >= n:
            self._scanner.pos += n
            return True
        return False

    # [064] s-indent(<n)
    def _parse_s_indent_lt(self, n: int) -> bool:
        assert self._scanner is not None
        match = self._scanner.check(RE_INDENT)
        if match is not None and len(match) < n:
            self._scanner.pos += len(match)
            return True
        return False

    # [065] s-indent(<=n)
    def _parse_s_indent_le(self, n: int) -> bool:
        assert self._scanner is not None
        match = self._scanner.check(RE_INDENT)
        if match is not None and len(match) <= n:
            self._scanner.pos += len(match)
            return True
        return False

    # [066] s-separate-in-line - Optimized: inline whitespace scanning
    def _parse_s_separate_in_line(self) -> bool:
        scanner = self._scanner
        pos = scanner._pos
        string = scanner._string
        length = scanner._len

        # Fast path: check for at least one whitespace
        if pos < length and string[pos] in _S_WHITE_CHARS:
            pos += 1
            # Consume remaining whitespace
            while pos < length and string[pos] in _S_WHITE_CHARS:
                pos += 1
            scanner._pos = pos
            return True

        # Start of line check (inlined)
        return pos == 0 or pos >= length or string[pos - 1] == "\n"

    # [070] l-comment
    def _parse_l_comment(self) -> bool:
        return bool(
            self._try(
                lambda: self._parse_s_separate_in_line()
                and (self._parse_c_nb_comment_text() or True)
                and self._parse_b_comment()
            )
            or self._start_of_line()
            and self._parse_b_comment()
        )

    # [075] c-nb-comment-text
    def _parse_c_nb_comment_text(self) -> bool:
        assert self._scanner is not None
        if not self._match("#"):
            return False
        self._star(self._parse_nb_char)
        return True

    # [077] b-comment
    def _parse_b_comment(self) -> bool:
        return self._parse_b_non_content() or self._scanner.eos()

    # [078] s-b-comment
    def _parse_s_b_comment(self) -> bool:
        # YAML spec: ( s-separate-in-line ( c-nb-comment-text )? )? b-comment
        # The whole thing must backtrack if b-comment fails
        return bool(
            self._try(
                lambda: (
                    (self._parse_s_separate_in_line() and (self._parse_c_nb_comment_text() or True))
                    or True
                )
                and self._parse_b_comment()
            )
        )

    # [079] l-comment-star
    def _parse_l_comment_star(self) -> bool:
        self._star(self._parse_l_comment)
        return True

    # [080] s-l-comments
    def _parse_s_l_comments(self) -> bool:
        return (self._parse_s_b_comment() or self._start_of_line()) and self._parse_l_comment_star()

    # [081] s-separate(n,c)
    def _parse_s_separate(self, n: int, c: str) -> bool:
        if c in ("block-out", "block-in", "flow-out", "flow-in"):
            return self._parse_s_separate_lines(n)
        elif c == "block-key" or c == "flow-key":
            return self._parse_s_separate_in_line()
        return False

    # [082] s-separate-lines(n)
    def _parse_s_separate_lines(self, n: int) -> bool:
        return bool(
            self._try(lambda: self._parse_s_l_comments() and self._parse_s_flow_line_prefix(n))
            or self._parse_s_separate_in_line()
        )

    # [069] s-flow-line-prefix(n)
    def _parse_s_flow_line_prefix(self, n: int) -> bool:
        return self._parse_s_indent(n) and (self._parse_s_separate_in_line() or True)

    # [083] l-directive
    def _parse_l_directive(self) -> bool:
        assert self._scanner is not None
        if not self._match("%"):
            return False

        if self._parse_ns_yaml_directive():
            pass
        elif self._parse_ns_tag_directive():
            pass
        elif self._parse_ns_reserved_directive():
            pass
        else:
            self._raise_syntax_error("Unknown directive")

        return self._parse_s_l_comments()

    # [086] ns-yaml-directive
    def _parse_ns_yaml_directive(self) -> bool:
        assert self._scanner is not None
        if not self._match("YAML"):
            return False
        if not self._parse_s_separate_in_line():
            return False

        pos_start = self._scanner.pos
        if not self._plus(lambda: bool(self._match(RE_NS_DEC_DIGIT))):
            return False
        major = int(self._from(pos_start))

        if not self._match("."):
            return False

        pos_start = self._scanner.pos
        if not self._plus(lambda: bool(self._match(RE_NS_DEC_DIGIT))):
            return False
        minor = int(self._from(pos_start))

        if self._document_start_event:
            self._document_start_event.version = (major, minor)
            self._document_start_event.implicit = False

        return True

    # [088] ns-tag-directive
    def _parse_ns_tag_directive(self) -> bool:
        assert self._scanner is not None
        if not self._match("TAG"):
            return False
        if not self._parse_s_separate_in_line():
            return False

        pos_start = self._scanner.pos
        if not self._parse_c_tag_handle():
            return False
        handle = self._from(pos_start)

        if not self._parse_s_separate_in_line():
            return False

        pos_start = self._scanner.pos
        if not self._parse_ns_tag_prefix():
            return False
        prefix = self._from(pos_start)

        self._tag_directives[handle] = prefix
        if self._document_start_event:
            self._document_start_event.implicit = False

        return True

    # [089] c-tag-handle
    def _parse_c_tag_handle(self) -> bool:
        return bool(
            self._try(lambda: bool(self._match("!")) and self._plus(self._parse_ns_word_char) and bool(self._match("!")))
            or self._try(lambda: bool(self._match("!!")))
            or self._match("!")
        )

    def _parse_ns_word_char(self) -> bool:
        return bool(self._match(RE_NS_WORD_CHAR))

    # [093] ns-tag-prefix
    def _parse_ns_tag_prefix(self) -> bool:
        return self._parse_c_ns_local_tag_prefix() or self._parse_ns_global_tag_prefix()

    # [094] c-ns-local-tag-prefix
    def _parse_c_ns_local_tag_prefix(self) -> bool:
        if not self._match("!"):
            return False
        self._star(self._parse_ns_uri_char)
        return True

    # [095] ns-global-tag-prefix
    def _parse_ns_global_tag_prefix(self) -> bool:
        if not self._parse_ns_tag_char():
            return False
        self._star(self._parse_ns_uri_char)
        return True

    # [096] ns-reserved-directive
    def _parse_ns_reserved_directive(self) -> bool:
        assert self._scanner is not None
        if not self._plus(self._parse_ns_char):
            return False
        self._star(
            lambda: self._try(
                lambda: self._parse_s_separate_in_line() and self._plus(self._parse_ns_char)
            )
        )
        return True

    # [097] c-ns-tag-property
    def _parse_c_ns_tag_property(self) -> bool:
        assert self._scanner is not None
        pos_start = self._scanner.pos

        if self._parse_c_verbatim_tag():
            # Verbatim tag is !<...> - extract the content between !< and >
            tag_text = self._from(pos_start)
            self._tag = tag_text[2:-1]  # Strip !< and >
            return True
        if self._parse_c_ns_shorthand_tag():
            tag_text = self._from(pos_start)
            # Resolve shorthand tag and decode percent-encoded characters
            if tag_text.startswith("!!"):
                # Secondary tag handle !!suffix
                prefix = self._tag_directives.get("!!", "tag:yaml.org,2002:")
                suffix = unquote(tag_text[2:])
                self._tag = prefix + suffix
            elif tag_text.startswith("!") and tag_text != "!":
                # Check for named tag handle (!name!suffix)
                idx = tag_text.find("!", 1)
                if idx > 0:
                    # Named handle like !e!suffix
                    handle = tag_text[: idx + 1]
                    suffix = unquote(tag_text[idx + 1 :])
                    prefix = self._tag_directives.get(handle, handle)
                    self._tag = prefix + suffix
                else:
                    # Primary tag handle (!suffix)
                    suffix = unquote(tag_text[1:])  # Everything after the first !
                    prefix = self._tag_directives.get("!", "!")
                    if prefix == "!":
                        # No mapping for primary handle - keep as local tag
                        self._tag = tag_text
                    else:
                        self._tag = prefix + suffix
            else:
                self._tag = unquote(tag_text)
            return True
        if self._parse_c_non_specific_tag():
            self._tag = "!"
            return True

        return False

    # [098] c-verbatim-tag
    def _parse_c_verbatim_tag(self) -> bool:
        return bool(
            self._try(
                lambda: bool(self._match("!<"))
                and self._plus(self._parse_ns_uri_char)
                and bool(self._match(">"))
            )
        )

    # [099] c-ns-shorthand-tag
    def _parse_c_ns_shorthand_tag(self) -> bool:
        return bool(
            self._try(
                lambda: self._parse_c_tag_handle() and self._plus(self._parse_ns_tag_char)
            )
        )

    # [100] c-non-specific-tag
    def _parse_c_non_specific_tag(self) -> bool:
        return bool(self._match("!"))

    # [101] c-ns-anchor-property
    def _parse_c_ns_anchor_property(self) -> bool:
        assert self._scanner is not None
        if not self._match("&"):
            return False

        pos_start = self._scanner.pos
        if not self._parse_ns_anchor_name():
            return False

        self._anchor = self._from(pos_start)
        return True

    # [102] ns-anchor-char
    def _parse_ns_anchor_char(self) -> bool:
        assert self._scanner is not None
        pos_start = self._scanner.pos

        if self._parse_ns_char():
            pos_end = self._scanner.pos
            self._scanner.pos = pos_start
            if self._parse_c_flow_indicator():
                self._scanner.pos = pos_start
                return False
            self._scanner.pos = pos_end
            return True
        return False

    # [103] ns-anchor-name
    def _parse_ns_anchor_name(self) -> bool:
        return self._plus(self._parse_ns_anchor_char)

    # [104] c-ns-alias-node
    def _parse_c_ns_alias_node(self) -> bool:
        assert self._scanner is not None
        assert self._source is not None
        pos_start = self._scanner.pos

        if not self._match("*"):
            return False

        anchor_start = self._scanner.pos
        if not self._parse_ns_anchor_name():
            self._scanner.pos = pos_start
            return False

        anchor_name = self._from(anchor_start)
        self._events_push(
            AliasEvent(Location(self._source, pos_start, self._scanner.pos), anchor_name)
        )
        return True

    # [105] e-scalar
    def _parse_e_scalar(self) -> bool:
        assert self._source is not None
        assert self._scanner is not None
        self._events_push_flush_properties(
            ScalarEvent(
                Location.point(self._source, self._scanner.pos),
                "",
                "",
                ScalarStyle.PLAIN,
            )
        )
        return True

    # [106] e-node
    def _parse_e_node(self) -> bool:
        return self._parse_e_scalar()

    # [107] nb-double-char
    def _parse_nb_double_char(self) -> str | None:
        assert self._scanner is not None

        # Try escape sequence first
        if esc := self._parse_c_ns_esc_char():
            return esc

        # Regular character (not \ or ")
        pos_start = self._scanner.pos
        if self._parse_nb_json():
            ch = self._from(pos_start)
            if ch not in ("\\", '"'):
                return ch
            self._scanner.pos = pos_start

        return None

    # [108] ns-double-char
    def _parse_ns_double_char(self) -> str | None:
        assert self._scanner is not None
        pos_start = self._scanner.pos

        result = self._parse_nb_double_char()
        if result is not None:
            # Check it's not whitespace
            self._scanner.pos = pos_start
            if self._parse_s_white():
                self._scanner.pos = pos_start
                return None
            self._scanner.pos = pos_start + len(result.encode())
            return result
        return None

    # [109] c-double-quoted(n,c)
    def _parse_c_double_quoted(self, n: int, c: str) -> bool:
        assert self._scanner is not None
        assert self._source is not None
        pos_start = self._scanner.pos

        if not self._match('"'):
            return False

        def parse_inner() -> bool:
            value = self._parse_double_text(n, c)
            if value is None:
                return False

            if not self._match('"'):
                self._raise_syntax_error("Expected closing double quote")

            self._events_push_flush_properties(
                ScalarEvent(
                    Location(self._source, pos_start, self._scanner.pos),
                    self._from(pos_start),
                    value,
                    ScalarStyle.DOUBLE_QUOTED,
                )
            )
            return True

        return self._within_double_quoted(pos_start, parse_inner)

    # [110-116] Double-quoted text parsing
    def _parse_double_text(self, n: int, c: str) -> str | None:
        # Track parts with (char, is_escape) tuples to distinguish escaped vs literal whitespace
        parts: list[tuple[str, bool]] = []

        while True:
            # Check for end quote
            assert self._scanner is not None
            if self._scanner.check_char('"'):
                break

            # Try inline content - track whether it's from an escape sequence
            result = self._parse_nb_double_char_with_escape_flag()
            if result is not None:
                ch, is_escape = result
                parts.append((ch, is_escape))
                continue

            # Check for escaped line break: \ followed by newline [115] s-double-escaped
            # This folds WITHOUT inserting a space and WITHOUT stripping trailing whitespace
            if self._scanner.check_char("\\"):
                pos = self._scanner.pos
                self._scanner.pos += 1  # consume \
                self._parse_s_white_star()  # consume optional whitespace between content and \
                if self._parse_b_break():
                    # For escaped newlines, trailing whitespace is preserved (unlike flow folding)
                    # Consume empty lines and leading whitespace (s-flow-line-prefix)
                    self._parse_s_white_star()
                    while self._try(lambda: self._parse_b_break() and (self._parse_s_white_star() or True)):
                        pass
                    # NO space inserted for escaped line break
                    continue
                # Not an escaped line break - backtrack
                self._scanner.pos = pos

            # Try folded newline
            if self._parse_b_break():
                # Strip trailing LITERAL whitespace before the fold (flow folding rule)
                # Escaped whitespace (like \t) should be preserved
                while parts and parts[-1][0] in (" ", "\t") and not parts[-1][1]:
                    parts.pop()
                # Count blank lines
                blank_count = 0
                self._parse_s_white_star()
                while self._try(lambda: self._parse_b_break() and (self._parse_s_white_star() or True)):
                    blank_count += 1
                # 0 blank lines = fold with space, N blank lines = N newlines
                if blank_count > 0:
                    parts.append(("\n" * blank_count, False))
                else:
                    # Always add space for fold (including at start/end of string)
                    parts.append((" ", False))
                continue

            break

        return "".join(ch for ch, _ in parts)

    def _parse_nb_double_char_with_escape_flag(self) -> tuple[str, bool] | None:
        """Parse a double-quoted character and return (char, is_escape) tuple."""
        assert self._scanner is not None
        pos_start = self._scanner.pos

        # Try escape sequence first - wrap in position save/restore
        # because _parse_c_ns_esc_char consumes \ but may not find valid escape
        if esc := self._parse_c_ns_esc_char():
            return (esc, True)
        # Backtrack if escape parsing consumed something but returned None
        self._scanner.pos = pos_start

        # Regular character (not \ or ")
        if self._parse_nb_json():
            ch = self._from(pos_start)
            if ch not in ("\\", '"'):
                return (ch, False)
            self._scanner.pos = pos_start

        return None

    # [117] nb-single-char
    def _parse_nb_single_char(self) -> str | None:
        assert self._scanner is not None

        # Escaped single quote
        if self._match("''"):
            return "'"

        pos_start = self._scanner.pos
        if self._parse_nb_json():
            ch = self._from(pos_start)
            if ch != "'":
                return ch
            self._scanner.pos = pos_start

        return None

    # [120] c-single-quoted(n,c)
    def _parse_c_single_quoted(self, n: int, c: str) -> bool:
        assert self._scanner is not None
        assert self._source is not None
        pos_start = self._scanner.pos

        if not self._match("'"):
            return False

        parts: list[str] = []
        while True:
            if self._scanner.check_char("'") and not self._scanner.check("''"):
                break

            if ch := self._parse_nb_single_char():
                parts.append(ch)
                continue

            if self._parse_b_break():
                # Strip trailing whitespace before the fold (flow folding rule)
                while parts and parts[-1] in (" ", "\t"):
                    parts.pop()
                # Count blank lines (additional breaks after the first)
                blank_count = 0
                self._parse_s_white_star()
                while self._try(lambda: self._parse_b_break() and (self._parse_s_white_star() or True)):
                    blank_count += 1
                # 0 blank lines = fold with space, N blank lines = N newlines
                if blank_count > 0:
                    parts.append("\n" * blank_count)
                else:
                    # Always add space for fold (including at start/end of string)
                    parts.append(" ")
                continue

            break

        if not self._match("'"):
            self._raise_syntax_error("Expected closing single quote")

        value = "".join(parts)
        self._events_push_flush_properties(
            ScalarEvent(
                Location(self._source, pos_start, self._scanner.pos),
                self._from(pos_start),
                value,
                ScalarStyle.SINGLE_QUOTED,
            )
        )
        return True

    # [126-133] Plain scalars
    def _parse_ns_plain(self, n: int, c: str) -> bool:
        if c in ("flow-out", "flow-in", "block-key", "flow-key"):
            return self._parse_ns_plain_multi_line(n, c)
        else:
            return self._parse_ns_plain_one_line(c)

    def _parse_nb_ns_plain_in_line(self, c: str) -> bool:
        """Parse ( s-white* ns-plain-char(c) ) - whitespace followed by plain char."""
        # This is rule [131] from YAML 1.2 spec
        # Must be atomic: if plain-char fails, backtrack the whitespace too
        # Optimized: inline whitespace scanning and avoid lambda
        scanner = self._scanner
        pos_start = scanner._pos
        string = scanner._string
        length = scanner._len

        # Skip whitespace (s-white*)
        pos = pos_start
        while pos < length and string[pos] in _S_WHITE_CHARS:
            pos += 1
        scanner._pos = pos

        # Try ns-plain-char(c)
        if self._parse_ns_plain_char(c):
            return True

        # Backtrack
        scanner._pos = pos_start
        return False

    def _parse_ns_plain_one_line(self, c: str) -> bool:
        # Optimized: inline _star and avoid lambda
        scanner = self._scanner
        pos_start = scanner._pos

        if not self._parse_ns_plain_first(c):
            return False

        # Parse nb-ns-plain-in-line(c) = ( s-white* ns-plain-char(c) )*
        # Inlined _star loop
        pos_current = scanner._pos
        while self._parse_nb_ns_plain_in_line(c):
            new_pos = scanner._pos
            if new_pos == pos_current:
                break
            pos_current = new_pos

        value = scanner._string[pos_start : scanner._pos]
        self._events_push_flush_properties(
            ScalarEvent(
                Location(self._source, pos_start, scanner._pos),
                value,
                value,
                ScalarStyle.PLAIN,
            )
        )
        return True

    def _parse_ns_plain_multi_line(self, n: int, c: str) -> bool:
        # Optimized: inline _star and avoid lambda
        scanner = self._scanner
        pos_start = scanner._pos

        if not self._parse_ns_plain_first(c):
            return False

        lines: list[str] = []
        current_line = scanner._string[scanner._pos - 1 : scanner._pos]

        while True:
            line_start = scanner._pos - 1
            # Parse nb-ns-plain-in-line(c) = ( s-white* ns-plain-char(c) )*
            # Inlined _star loop
            pos_current = scanner._pos
            while self._parse_nb_ns_plain_in_line(c):
                new_pos = scanner._pos
                if new_pos == pos_current:
                    break
                pos_current = new_pos
            current_line = scanner._string[line_start : scanner._pos]

            # Inlined _try for next line parsing
            try_pos = scanner._pos
            if not self._parse_s_ns_plain_next_line(n, c):
                scanner._pos = try_pos
                break

            lines.append(current_line)
            current_line = ""

        lines.append(current_line.rstrip())

        # Get the raw value and normalize it according to plain scalar rules
        raw_value = scanner._string[pos_start : scanner._pos]

        # Plain scalar folding: adjacent non-blank lines fold with space, blank lines become newlines
        # One blank line = one newline separator between segments
        raw_lines = raw_value.split("\n")
        segments: list[str] = []
        current_folded: list[str] = []
        had_blank = False

        for line in raw_lines:
            stripped = line.strip()
            if stripped:
                # Finish current segment if we had blank lines
                if had_blank and current_folded:
                    segments.append(" ".join(current_folded))
                    current_folded = []
                    had_blank = False
                current_folded.append(stripped)
            else:
                # Blank line
                had_blank = True

        if current_folded:
            segments.append(" ".join(current_folded))

        value = "\n".join(segments)

        self._events_push_flush_properties(
            ScalarEvent(
                Location(self._source, pos_start, scanner._pos),
                scanner._string[pos_start : scanner._pos],
                value,
                ScalarStyle.PLAIN,
            )
        )
        return True

    def _parse_ns_plain_first(self, c: str) -> bool:
        assert self._scanner is not None

        # Document markers (--- or ...) at start of line are not allowed in plain scalars
        if self._at_document_boundary():
            return False

        # Can't start with indicator (with some exceptions)
        if self._scanner.check(RE_C_INDICATOR):
            # Check exceptions: - ? : followed by ns-plain-safe character
            # ns-plain-safe is essentially ns-char (excludes space, tab, newline, etc.)
            ch = self._scanner.peek()
            if ch in "-?:":
                next_ch = self._scanner.peek(2)[1:2] if len(self._scanner.peek(2)) > 1 else ""
                # Must be followed by ns-char (non-whitespace, non-break)
                if next_ch and RE_NS_CHAR.match(next_ch):
                    self._scanner.pos += 1
                    return True
            return False

        return self._parse_ns_char()

    def _parse_ns_plain_char(self, c: str) -> bool:
        # Optimized: direct attribute access and inlined checks
        scanner = self._scanner
        pos = scanner._pos
        if pos >= scanner._len:
            return False

        # Check for document boundary at start of line (inlined _at_document_boundary)
        if pos == 0 or scanner._string[pos - 1] == "\n":
            if scanner._string[pos:pos + 3] in ("---", "..."):
                # Must be followed by whitespace, newline, or EOF
                next_pos = pos + 3
                if next_pos >= scanner._len or scanner._string[next_pos] in " \t\n\r":
                    return False

        ch = scanner._string[pos]

        # : and # need special handling
        if ch == ":":
            # : followed by ns-plain-safe
            scanner._pos = pos + 1
            if self._parse_ns_plain_safe(c):
                return True
            scanner._pos = pos
            return False

        if ch == "#":
            # # preceded by ns-char is ok (not whitespace, not newline, not break chars)
            if pos > 0:
                prev = scanner._string[pos - 1]
                # Must be preceded by a valid ns-char (printable non-space)
                if prev not in _NS_CHAR_EXCLUDE and ord(prev) >= 0x21:
                    scanner._pos = pos + 1
                    return True
            return False

        return self._parse_ns_plain_safe(c)

    def _parse_ns_plain_safe(self, c: str) -> bool:
        # Optimized: direct attribute access and inlined flow indicator check
        scanner = self._scanner
        pos = scanner._pos
        if pos >= scanner._len:
            return False

        ch = scanner._string[pos]

        # Quick reject: whitespace and breaks are not ns-char
        if ch in _NS_CHAR_EXCLUDE:
            return False

        # ns-char check: printable chars excluding whitespace/breaks
        # Range 0x21-0x7E, 0x85, 0xA0-0xD7FF, 0xE000-0xFFFD, 0x10000-0x10FFFF
        char_ord = ord(ch)
        if not ((0x21 <= char_ord <= 0x7E) or char_ord == 0x85 or
                (0xA0 <= char_ord <= 0xD7FF) or (0xE000 <= char_ord <= 0xFFFD) or
                (0x10000 <= char_ord <= 0x10FFFF)):
            return False

        if c in ("flow-out", "block-key"):
            scanner._pos = pos + 1
            if self._in_scalar:
                self._text_prefix = ch
            return True
        else:  # flow-in, flow-key
            # Check for flow indicators: , [ ] { }
            if ch in _FLOW_INDICATORS:
                return False
            scanner._pos = pos + 1
            if self._in_scalar:
                self._text_prefix = ch
            return True

    def _parse_s_ns_plain_next_line(self, n: int, c: str) -> bool:
        return bool(
            self._try(
                lambda: self._parse_s_flow_folded(n)
                and self._parse_ns_plain_char(c)
            )
        )

    def _parse_s_flow_folded(self, n: int) -> bool:
        return bool(
            (self._parse_s_separate_in_line() or True)
            and self._parse_b_l_folded(n, "flow-in")
            and self._parse_s_flow_line_prefix(n)
        )

    def _parse_b_l_folded(self, n: int, c: str) -> bool:
        # Must use _try for b_l_trimmed since it can partially consume content
        return self._try(lambda: self._parse_b_l_trimmed(n, c)) or self._parse_b_as_space()

    def _parse_b_l_trimmed(self, n: int, c: str) -> bool:
        return bool(
            self._parse_b_non_content()
            and self._plus(lambda: self._parse_l_empty(n, c))
        )

    def _parse_b_as_space(self) -> bool:
        return self._parse_b_break()

    def _parse_l_empty(self, n: int, c: str) -> bool:
        # Must use _try since line prefix can consume content before b_as_line_feed fails
        return bool(
            self._try(
                lambda: (self._parse_s_line_prefix(n, c) or self._parse_s_indent_lt(n))
                and self._parse_b_as_line_feed()
            )
        )

    def _parse_s_line_prefix(self, n: int, c: str) -> bool:
        if c in ("block-out", "block-in"):
            return self._parse_s_block_line_prefix(n)
        else:
            return self._parse_s_flow_line_prefix(n)

    def _parse_s_block_line_prefix(self, n: int) -> bool:
        return self._parse_s_indent(n)

    # [137] c-l-literal(n) - Literal block scalar
    def _parse_c_l_literal(self, n: int) -> bool:
        assert self._scanner is not None
        assert self._source is not None
        pos_start = self._scanner.pos

        if not self._match("|"):
            return False

        # Parse block header
        chomping, indent_indicator = self._parse_c_b_block_header(n)
        if chomping is None:
            return False

        # Determine actual indent
        if indent_indicator:
            m = indent_indicator
        else:
            m = self._detect_indent(n)
            # For literal scalars after sequence/mapping entries (n >= 0),
            # content must be indented at least 1 more than the parent
            if m == 0 and n >= 0:
                m = 1

        actual_n = n + m if n >= 0 else m

        # Parse content
        lines: list[str] = []
        trailing_newlines = 0
        had_content = False  # Track if we've seen actual (non-whitespace) content
        while True:
            # Try to parse indented content line
            if self._parse_s_indent(actual_n):
                line_start = self._scanner.pos
                self._star(self._parse_nb_char)
                line_content = self._from(line_start)
                # Check if this line has actual content (non-space characters)
                # Note: tabs ARE content in YAML, only spaces are indentation
                # So we check for non-space, not non-whitespace
                has_non_space = any(c != ' ' for c in line_content)
                if has_non_space or had_content:
                    # Either: line has actual content, OR we've already seen content
                    # (space-only lines after content should be preserved)
                    # Add any blank lines that were accumulated BEFORE this line
                    for _ in range(trailing_newlines):
                        lines.append("")
                    trailing_newlines = 0
                    lines.append(line_content)
                    if has_non_space:
                        had_content = True
                    if not self._parse_b_break():
                        break
                else:
                    # Line has only whitespace AND we haven't seen content yet
                    # Treat as leading blank line (don't preserve the whitespace)
                    if self._parse_b_break():
                        trailing_newlines += 1
                    else:
                        # No break after whitespace - odd case, append as-is
                        for _ in range(trailing_newlines):
                            lines.append("")
                        trailing_newlines = 0
                        lines.append(line_content)
                        break
            # Check for blank line (less indentation or empty followed by break)
            elif self._try(lambda: (self._parse_s_indent_lt(actual_n) or True) and self._parse_b_break()):
                trailing_newlines += 1
            else:
                break

        # [177] l-trail-comments(n) - consume trailing comments with indent < actual_n
        # These are comments that appear after the block scalar but are less indented
        # than the content, so they don't belong to subsequent mapping entries
        if self._start_of_line():
            self._try(
                lambda: self._parse_s_indent_lt(actual_n)
                and self._parse_c_nb_comment_text()
                and self._parse_b_comment()
                and self._parse_l_comment_star()
            )

        # Apply chomping
        value = "\n".join(lines)
        if chomping == "keep":
            if lines:
                # Content with trailing newlines
                value += "\n"
                value += "\n" * trailing_newlines
            elif trailing_newlines > 0:
                # No content, but keep chomping preserves blank lines
                value = "\n" * trailing_newlines
        elif chomping == "strip":
            value = value.rstrip("\n")
        else:  # clip
            value = value.rstrip("\n") + "\n" if value else ""

        self._events_push_flush_properties(
            ScalarEvent(
                Location(self._source, pos_start, self._scanner.pos),
                self._from(pos_start),
                value,
                ScalarStyle.LITERAL,
            )
        )
        return True

    # [138] c-l-folded(n) - Folded block scalar
    def _parse_c_l_folded(self, n: int) -> bool:
        assert self._scanner is not None
        assert self._source is not None
        pos_start = self._scanner.pos

        if not self._match(">"):
            return False

        # Parse block header
        chomping, indent_indicator = self._parse_c_b_block_header(n)
        if chomping is None:
            return False

        # Determine actual indent
        if indent_indicator:
            m = indent_indicator
        else:
            m = self._detect_indent(n)
            # For folded scalars after sequence/mapping entries (n >= 0),
            # content must be indented at least 1 more than the parent
            if m == 0 and n >= 0:
                m = 1

        actual_n = n + m if n >= 0 else m

        # Parse content - handle blank lines and more-indented lines properly
        # In folded scalars:
        # - Adjacent normal-indented text lines are folded (joined with space)
        # - Blank lines become literal newlines (preserved)
        # - More-indented lines preserve their newlines (literal block)
        # - Blank lines around more-indented sections are preserved
        result_parts: list[str] = []  # Accumulate final result pieces
        current_folded_lines: list[str] = []  # Lines being folded together
        pending_blank_lines = 0
        in_more_indented = False

        while True:
            # Try to parse indented content line
            saved_pos = self._scanner.pos
            if self._parse_s_indent(actual_n):
                # Check if this line has more indentation
                extra_indent_start = self._scanner.pos
                self._star(self._parse_s_white)
                extra_indent = self._from(extra_indent_start)
                is_more_indented = len(extra_indent) > 0

                line_start = self._scanner.pos
                self._star(self._parse_nb_char)
                line = self._from(line_start)

                # If the line is empty (only had indentation), treat as blank line
                if not line and not extra_indent:
                    # Restore position and handle as blank line
                    self._scanner.pos = saved_pos
                    if self._try(lambda: (self._parse_s_indent_lt(actual_n) or self._parse_s_indent(actual_n)) and self._parse_b_break()):
                        pending_blank_lines += 1
                        continue
                    else:
                        break

                # Flush pending blank lines and handle transitions
                had_content = bool(current_folded_lines) or bool(result_parts)
                transitioning_to_more = is_more_indented and not in_more_indented
                transitioning_from_more = not is_more_indented and in_more_indented

                # Flush current folded lines before any transition or blank lines
                if pending_blank_lines > 0 or transitioning_to_more or transitioning_from_more:
                    if current_folded_lines:
                        result_parts.append(" ".join(current_folded_lines))
                        current_folded_lines = []

                # Handle blank lines
                if pending_blank_lines > 0:
                    # N blank lines normally produce N newlines.
                    # When transitioning to more-indented, there's an extra separator
                    # newline, so N blank lines produce N+1 newlines.
                    # When joining result_parts with \n, the join provides 1 newline
                    # between adjacent elements.
                    if had_content:
                        if transitioning_to_more or in_more_indented:
                            # Extra newline for more-indented separation
                            for _ in range(pending_blank_lines):
                                result_parts.append("")
                        else:
                            # Normal folding: N blank lines = N newlines = N-1 empty strings
                            for _ in range(pending_blank_lines - 1):
                                result_parts.append("")
                    else:
                        for _ in range(pending_blank_lines):
                            result_parts.append("")
                    pending_blank_lines = 0

                in_more_indented = is_more_indented

                if is_more_indented:
                    # More-indented: each line is its own segment (literal)
                    result_parts.append(extra_indent + line)
                else:
                    # Normal: accumulate for folding
                    current_folded_lines.append(line)

                if not self._parse_b_break():
                    break
            # Check for blank line (less indentation followed by break)
            elif self._try(lambda: (self._parse_s_indent_lt(actual_n) or True) and self._parse_b_break()):
                pending_blank_lines += 1
            else:
                break

        # [177] l-trail-comments(n) - consume trailing comments with indent < actual_n
        # These are comments that appear after the block scalar but are less indented
        # than the content, so they don't belong to subsequent mapping entries
        if self._start_of_line():
            self._try(
                lambda: self._parse_s_indent_lt(actual_n)
                and self._parse_c_nb_comment_text()
                and self._parse_b_comment()
                and self._parse_l_comment_star()
            )

        # Finish last folded segment
        if current_folded_lines:
            result_parts.append(" ".join(current_folded_lines))

        # Join with newlines
        value = "\n".join(result_parts)

        # Apply chomping
        if chomping == "keep":
            value += "\n"
        elif chomping != "strip" and value:
            value += "\n"

        self._events_push_flush_properties(
            ScalarEvent(
                Location(self._source, pos_start, self._scanner.pos),
                self._from(pos_start),
                value,
                ScalarStyle.FOLDED,
            )
        )
        return True

    # [162] c-b-block-header(m,t)
    def _parse_c_b_block_header(self, n: int) -> tuple[str | None, int | None]:
        assert self._scanner is not None

        indent_indicator: int | None = None
        chomping = "clip"

        # Optional indentation indicator and chomping indicator
        if self._scanner.check(RE_NS_DEC_DIGIT):
            ch = self._scanner.getch()
            indent_indicator = int(ch) if ch else None
            if self._scanner.check_char("+"):
                self._scanner.pos += 1
                chomping = "keep"
            elif self._scanner.check_char("-"):
                self._scanner.pos += 1
                chomping = "strip"
        elif self._scanner.check_char("+"):
            self._scanner.pos += 1
            chomping = "keep"
            if self._scanner.check(RE_NS_DEC_DIGIT):
                ch = self._scanner.getch()
                indent_indicator = int(ch) if ch else None
        elif self._scanner.check_char("-"):
            self._scanner.pos += 1
            chomping = "strip"
            if self._scanner.check(RE_NS_DEC_DIGIT):
                ch = self._scanner.getch()
                indent_indicator = int(ch) if ch else None

        if not self._parse_s_b_comment():
            return None, None

        return chomping, indent_indicator

    # [183] l-block-sequence(n)
    def _parse_l_block_sequence(self, n: int) -> bool:
        assert self._scanner is not None
        assert self._source is not None

        m = self._detect_indent(n)
        # For nested content (n >= 0), require additional indentation
        # For top-level (n == -1), m=0 is valid (content at column 0)
        if m == 0 and n >= 0:
            return False

        pos_start = self._scanner.pos
        # For top-level, actual_n is the absolute column (m)
        # For nested, actual_n is base + additional (n + m)
        actual_n = n + m if n >= 0 else m

        # Save collection-level properties before detecting first entry
        # The anchor/tag belong to the sequence, not to the first entry
        saved_anchor = self._anchor
        saved_tag = self._tag
        self._anchor = None
        self._tag = None

        # Cache events and try to parse first entry
        self._events_cache_push()
        first_entry = self._try(lambda: self._parse_s_indent(actual_n) and self._parse_c_l_block_seq_entry(actual_n))
        if not first_entry:
            self._events_cache_pop()
            # Restore properties since sequence detection failed
            self._anchor = saved_anchor
            self._tag = saved_tag
            return False

        # Get cached events from first entry
        first_entry_events = self._events_cache_pop()

        # Restore properties for the sequence start event
        self._anchor = saved_anchor
        self._tag = saved_tag

        def parse_seq() -> bool:
            self._events_push_flush_properties(
                SequenceStartEvent(
                    Location.point(self._source, pos_start), CollectionStyle.BLOCK
                )
            )

            # Push first entry's cached events
            for event in first_entry_events:
                self._events_push(event)

            # Parse remaining entries (stop at document boundaries)
            self._star(
                lambda: not self._at_document_boundary() and self._try(
                    lambda: self._parse_s_indent(actual_n) and self._parse_c_l_block_seq_entry(actual_n)
                )
            )

            self._events_push(SequenceEndEvent(Location.point(self._source, self._scanner.pos)))
            return True

        return self._within_block_sequence(pos_start, actual_n, parse_seq)

    # [184] c-l-block-seq-entry(n)
    def _parse_c_l_block_seq_entry(self, n: int) -> bool:
        assert self._scanner is not None

        if not self._match("-"):
            return False

        # Must be followed by non-ns-char
        if self._peek(self._parse_ns_char):
            self._scanner.pos -= 1
            return False

        return self._parse_s_l_block_indented(n, "block-in")

    # [185] s-l+block-indented(n,c)
    def _parse_s_l_block_indented(self, n: int, c: str) -> bool:
        # For compact notation (- - - x), we need the raw space count
        # not the relative indent, because we're on the same line
        m = self._count_spaces()

        # Cache events during speculative compact sequence/mapping parsing
        self._events_cache_push()
        compact_result = self._try(
            lambda: self._parse_s_indent(m)
            and (
                self._parse_ns_l_compact_sequence(n + 1 + m)
                or self._parse_ns_l_compact_mapping(n + 1 + m)
            )
        )
        if compact_result:
            self._events_cache_flush()
            return True
        else:
            self._events_cache_pop()

        return bool(
            self._parse_s_l_block_node(n, c)
            or (self._parse_e_node() and self._parse_s_l_comments())
        )

    # [186] ns-l-compact-sequence(n)
    def _parse_ns_l_compact_sequence(self, n: int) -> bool:
        assert self._scanner is not None
        assert self._source is not None
        pos_start = self._scanner.pos

        # Cache events during first entry parsing
        self._events_cache_push()
        if not self._parse_c_l_block_seq_entry(n):
            self._events_cache_pop()
            return False
        first_entry_events = self._events_cache_pop()

        def parse_rest() -> bool:
            self._events_push_flush_properties(
                SequenceStartEvent(
                    Location.point(self._source, pos_start), CollectionStyle.BLOCK
                )
            )

            # Push first entry's cached events
            for event in first_entry_events:
                self._events_push(event)

            self._star(
                lambda: self._try(
                    lambda: self._parse_s_indent(n) and self._parse_c_l_block_seq_entry(n)
                )
            )

            self._events_push(SequenceEndEvent(Location.point(self._source, self._scanner.pos)))
            return True

        return self._within_block_sequence(pos_start, n, parse_rest)

    # [187] l-block-mapping(n)
    def _parse_l_block_mapping(self, n: int) -> bool:
        assert self._scanner is not None
        assert self._source is not None

        m = self._detect_indent(n)
        # For nested content (n >= 0), require additional indentation
        # For top-level (n == -1), m=0 is valid (content at column 0)
        if m == 0 and n >= 0:
            return False

        pos_start = self._scanner.pos
        # For top-level, actual_n is the absolute column (m)
        # For nested, actual_n is base + additional (n + m)
        actual_n = n + m if n >= 0 else m

        # Save collection-level properties before detecting first entry
        # The anchor/tag belong to the mapping, not to the first entry
        saved_anchor = self._anchor
        saved_tag = self._tag
        self._anchor = None
        self._tag = None

        # Cache events and try to parse first entry
        self._events_cache_push()
        first_entry = self._try(lambda: self._parse_s_indent(actual_n) and self._parse_ns_l_block_map_entry(actual_n))
        if not first_entry:
            self._events_cache_pop()
            # Restore properties since mapping detection failed
            self._anchor = saved_anchor
            self._tag = saved_tag
            return False

        # Get cached events from first entry
        first_entry_events = self._events_cache_pop()

        # Restore properties for the mapping start event
        self._anchor = saved_anchor
        self._tag = saved_tag

        def parse_mapping() -> bool:
            self._events_push_flush_properties(
                MappingStartEvent(
                    Location.point(self._source, pos_start), CollectionStyle.BLOCK
                )
            )

            # Push first entry's cached events
            for event in first_entry_events:
                self._events_push(event)

            # Parse remaining entries (stop at document boundaries)
            self._star(
                lambda: not self._at_document_boundary() and self._try(
                    lambda: self._parse_s_indent(actual_n) and self._parse_ns_l_block_map_entry(actual_n)
                )
            )

            self._events_push(MappingEndEvent(Location.point(self._source, self._scanner.pos)))
            return True

        return self._within_block_mapping(pos_start, actual_n, parse_mapping)

    # [188] ns-l-block-map-entry(n)
    def _parse_ns_l_block_map_entry(self, n: int) -> bool:
        return self._parse_c_l_block_map_explicit_entry(n) or self._parse_ns_l_block_map_implicit_entry(n)

    # [189] c-l-block-map-explicit-entry(n)
    def _parse_c_l_block_map_explicit_entry(self, n: int) -> bool:
        if not self._parse_c_l_block_map_explicit_key(n):
            return False

        return self._parse_l_block_map_explicit_value(n) or self._parse_e_node()

    # [190] c-l-block-map-explicit-key(n)
    def _parse_c_l_block_map_explicit_key(self, n: int) -> bool:
        assert self._scanner is not None

        if not self._match("?"):
            return False

        # "?" must be followed by whitespace/newline for explicit key
        # Otherwise it's part of a plain scalar (e.g., "?foo" is a key, not "?" + "foo")
        if self._peek(self._parse_ns_char):
            self._scanner.pos -= 1
            return False

        return self._parse_s_l_block_indented(n, "block-out")

    # [191] l-block-map-explicit-value(n)
    def _parse_l_block_map_explicit_value(self, n: int) -> bool:
        assert self._scanner is not None

        if not self._try(lambda: self._parse_s_indent(n) and bool(self._match(":"))):
            return False

        return self._parse_s_l_block_indented(n, "block-out")

    # [192] ns-l-block-map-implicit-entry(n)
    def _parse_ns_l_block_map_implicit_entry(self, n: int) -> bool:
        # First try with actual key
        if self._parse_ns_s_block_map_implicit_key():
            return self._parse_c_l_block_map_implicit_value(n)

        # Try with empty key - but cache events in case we need to roll back
        self._events_cache_push()
        if not self._parse_e_node():
            self._events_cache_pop()
            return False

        # Try to parse the value part (requires ":")
        if self._parse_c_l_block_map_implicit_value(n):
            self._events_cache_flush()
            return True
        else:
            self._events_cache_pop()
            return False

    # [193] ns-s-block-map-implicit-key
    def _parse_ns_s_block_map_implicit_key(self) -> bool:
        return bool(
            self._try(lambda: self._parse_c_s_implicit_json_key("block-key"))
            or self._parse_ns_s_implicit_yaml_key("block-key")
        )

    # [194] c-l-block-map-implicit-value(n)
    def _parse_c_l_block_map_implicit_value(self, n: int) -> bool:
        assert self._scanner is not None

        if not self._match(":"):
            return False

        return bool(
            self._parse_s_l_block_node(n, "block-out")
            or (self._parse_e_node() and self._parse_s_l_comments())
        )

    # [195] ns-l-compact-mapping(n)
    def _parse_ns_l_compact_mapping(self, n: int) -> bool:
        assert self._scanner is not None
        assert self._source is not None
        pos_start = self._scanner.pos

        # Cache events during first entry parsing
        self._events_cache_push()
        if not self._parse_ns_l_block_map_entry(n):
            self._events_cache_pop()
            return False
        first_entry_events = self._events_cache_pop()

        def parse_rest() -> bool:
            self._events_push_flush_properties(
                MappingStartEvent(
                    Location.point(self._source, pos_start), CollectionStyle.BLOCK
                )
            )

            # Push first entry's cached events
            for event in first_entry_events:
                self._events_push(event)

            self._star(
                lambda: self._try(
                    lambda: self._parse_s_indent(n) and self._parse_ns_l_block_map_entry(n)
                )
            )

            self._events_push(MappingEndEvent(Location.point(self._source, self._scanner.pos)))
            return True

        return self._within_block_mapping(pos_start, n, parse_rest)

    # [196] s-l+block-node(n,c)
    def _parse_s_l_block_node(self, n: int, c: str) -> bool:
        return self._parse_s_l_block_in_block(n, c) or self._parse_s_l_flow_in_block(n)

    # [197] s-l+block-in-block(n,c)
    def _parse_s_l_block_in_block(self, n: int, c: str) -> bool:
        return self._parse_s_l_block_scalar(n, c) or self._parse_s_l_block_collection(n, c)

    # [198] s-l+block-scalar(n,c)
    def _parse_s_l_block_scalar(self, n: int, c: str) -> bool:
        # Save anchor/tag before trying, since properties parsing may set them
        saved_anchor = self._anchor
        saved_tag = self._tag

        result = self._try(
            lambda: self._parse_s_separate(n + 1, c)
            and (self._parse_c_ns_properties(n + 1, c) and self._parse_s_separate(n + 1, c) or True)
            and (self._parse_c_l_literal(n) or self._parse_c_l_folded(n))
        )

        if not result:
            # Restore anchor/tag since parsing failed
            self._anchor = saved_anchor
            self._tag = saved_tag

        return bool(result)

    # [199] s-l+block-collection(n,c)
    def _parse_s_l_block_collection(self, n: int, c: str) -> bool:
        # [199] s-l+block-collection(n,c)
        # Properties on the collection itself must be followed by s-l-comments (newline)
        # If properties are parsed but not followed by s-l-comments, they belong to the
        # first entry (key), not the collection - so backtrack
        #
        # Strategy: Try greedy property parsing first. If s-l-comments fails after
        # greedy properties, try conservative (same-line) property parsing.
        # This handles cases like:
        # - "!!map\n&a8 !!str key:" - greedy would grab !!map+&a8, but &a8 belongs to key
        # - "key: &anchor\n !!map\n  a: b" - properties can span lines for nested values

        def try_properties_greedy() -> bool:
            # Parse properties allowing multiline separator
            return self._parse_c_ns_properties(n + 1, c)

        def try_properties_conservative() -> bool:
            # Parse properties where tag and anchor must be on the same line
            return bool(
                self._try(
                    lambda: self._parse_c_ns_tag_property()
                    and (
                        self._try(
                            lambda: self._parse_s_separate_in_line()
                            and self._parse_c_ns_anchor_property()
                        )
                        or True
                    )
                )
                or (
                    self._parse_c_ns_anchor_property()
                    and (
                        self._try(
                            lambda: self._parse_s_separate_in_line()
                            and self._parse_c_ns_tag_property()
                        )
                        or True
                    )
                )
            )

        def try_properties_and_comments() -> bool:
            # Save state before trying
            saved_anchor = self._anchor
            saved_tag = self._tag
            saved_pos = self._scanner.pos

            # First try: separator + greedy properties + s-l-comments
            if (
                self._parse_s_separate(n + 1, c)
                and try_properties_greedy()
                and self._parse_s_l_comments()
            ):
                return True

            # Greedy failed, restore and try conservative
            self._anchor = saved_anchor
            self._tag = saved_tag
            self._scanner.pos = saved_pos

            # Second try: separator + conservative properties + s-l-comments
            if (
                self._parse_s_separate(n + 1, c)
                and try_properties_conservative()
                and self._parse_s_l_comments()
            ):
                return True

            # Both failed, restore state
            self._anchor = saved_anchor
            self._tag = saved_tag
            return False

        return bool(
            self._try(
                lambda: (
                    # Either: properties followed by s-l-comments
                    self._try(try_properties_and_comments)
                    # Or: just s-l-comments (no collection-level properties)
                    or self._parse_s_l_comments()
                )
                and (self._parse_l_block_sequence(self._seq_spaces(n, c)) or self._parse_l_block_mapping(n))
            )
        )

    def _seq_spaces(self, n: int, c: str) -> int:
        if c == "block-out":
            return n - 1
        return n

    # [200] s-l+flow-in-block(n)
    def _parse_s_l_flow_in_block(self, n: int) -> bool:
        # Cache events since ns_flow_node may emit events before s_l_comments fails
        self._events_cache_push()
        saved_anchor = self._anchor
        saved_tag = self._tag

        result = self._try(
            lambda: self._parse_s_separate(n + 1, "flow-out")
            and self._parse_ns_flow_node(n + 1, "flow-out")
            and self._parse_s_l_comments()
        )

        if result:
            self._events_cache_flush()
        else:
            self._events_cache_pop()
            self._anchor = saved_anchor
            self._tag = saved_tag

        return bool(result)

    # [137] c-flow-sequence(n,c)
    def _parse_c_flow_sequence(self, n: int, c: str) -> bool:
        assert self._scanner is not None
        assert self._source is not None
        pos_start = self._scanner.pos

        if not self._match("["):
            return False

        def parse_seq() -> bool:
            self._events_push_flush_properties(
                SequenceStartEvent(
                    Location.point(self._source, pos_start), CollectionStyle.FLOW
                )
            )

            self._parse_s_separate(n, c) or True
            if not self._scanner.check_char("]"):
                self._parse_ns_s_flow_seq_entries(n, self._in_flow(c))

            if not self._match("]"):
                self._raise_syntax_error("Expected ']'")

            self._events_push(SequenceEndEvent(Location(self._source, pos_start, self._scanner.pos)))
            return True

        return self._within_flow_sequence(pos_start, c, parse_seq)

    # [138] ns-s-flow-seq-entries(n,c)
    def _parse_ns_s_flow_seq_entries(self, n: int, c: str) -> bool:
        if not self._parse_ns_flow_seq_entry(n, c):
            return False

        self._parse_s_separate(n, c) or True

        while self._match(","):
            self._parse_s_separate(n, c) or True
            if self._scanner.check_char("]"):
                break
            if not self._parse_ns_flow_seq_entry(n, c):
                break
            self._parse_s_separate(n, c) or True

        return True

    # [139] ns-flow-seq-entry(n,c)
    def _parse_ns_flow_seq_entry(self, n: int, c: str) -> bool:
        # ns-flow-pair can consume input before failing, so wrap in _try
        return self._try(lambda: self._parse_ns_flow_pair(n, c)) or self._parse_ns_flow_node(n, c)

    # [140] c-flow-mapping(n,c)
    def _parse_c_flow_mapping(self, n: int, c: str) -> bool:
        assert self._scanner is not None
        assert self._source is not None
        pos_start = self._scanner.pos

        if not self._match("{"):
            return False

        def parse_mapping() -> bool:
            self._events_push_flush_properties(
                MappingStartEvent(
                    Location.point(self._source, pos_start), CollectionStyle.FLOW
                )
            )

            self._parse_s_separate(n, c) or True
            if not self._scanner.check_char("}"):
                self._parse_ns_s_flow_map_entries(n, self._in_flow(c))

            if not self._match("}"):
                self._raise_syntax_error("Expected '}'")

            self._events_push(MappingEndEvent(Location(self._source, pos_start, self._scanner.pos)))
            return True

        return self._within_flow_mapping(pos_start, c, parse_mapping)

    # [141] ns-s-flow-map-entries(n,c)
    def _parse_ns_s_flow_map_entries(self, n: int, c: str) -> bool:
        if not self._parse_ns_flow_map_entry(n, c):
            return False

        self._parse_s_separate(n, c) or True

        while self._match(","):
            self._parse_s_separate(n, c) or True
            if self._scanner.check_char("}"):
                break
            if not self._parse_ns_flow_map_entry(n, c):
                break
            self._parse_s_separate(n, c) or True

        return True

    # [142] ns-flow-map-entry(n,c)
    def _parse_ns_flow_map_entry(self, n: int, c: str) -> bool:
        return bool(
            self._try(
                lambda: bool(self._match("?"))
                and self._parse_s_separate(n, c)
                and self._parse_ns_flow_map_explicit_entry(n, c)
            )
            or self._parse_ns_flow_map_implicit_entry(n, c)
        )

    # [143] ns-flow-map-explicit-entry(n,c)
    def _parse_ns_flow_map_explicit_entry(self, n: int, c: str) -> bool:
        return self._parse_ns_flow_map_implicit_entry(n, c) or (
            self._parse_e_node() and self._parse_e_node()
        )

    # [144] ns-flow-map-implicit-entry(n,c)
    def _parse_ns_flow_map_implicit_entry(self, n: int, c: str) -> bool:
        # Each alternative must cache events separately so failed attempts
        # don't pollute successful ones
        assert self._scanner is not None
        pos = self._scanner.pos

        # Try yaml key entry
        self._events_cache_push()
        if self._parse_ns_flow_map_yaml_key_entry(n, c):
            self._events_cache_flush()
            return True
        self._events_cache_pop()
        self._scanner.pos = pos

        # Try empty key entry
        self._events_cache_push()
        if self._parse_c_ns_flow_map_empty_key_entry(n, c):
            self._events_cache_flush()
            return True
        self._events_cache_pop()
        self._scanner.pos = pos

        # Try json key entry
        self._events_cache_push()
        if self._parse_c_ns_flow_map_json_key_entry(n, c):
            self._events_cache_flush()
            return True
        self._events_cache_pop()
        self._scanner.pos = pos

        return False

    # [145] ns-flow-map-yaml-key-entry(n,c)
    def _parse_ns_flow_map_yaml_key_entry(self, n: int, c: str) -> bool:
        if not self._parse_ns_flow_yaml_node(n, c):
            return False

        return bool(
            self._try(
                lambda: (self._parse_s_separate(n, c) or True)
                and self._parse_c_ns_flow_map_separate_value(n, c)
            )
            or self._parse_e_node()
        )

    # [146] c-ns-flow-map-empty-key-entry(n,c)
    def _parse_c_ns_flow_map_empty_key_entry(self, n: int, c: str) -> bool:
        if not self._parse_e_node():
            return False

        return self._parse_c_ns_flow_map_separate_value(n, c)

    # [147] c-ns-flow-map-separate-value(n,c)
    def _parse_c_ns_flow_map_separate_value(self, n: int, c: str) -> bool:
        assert self._scanner is not None

        if not self._match(":"):
            return False

        # Must not be followed by ns-plain-safe
        if self._peek(lambda: self._parse_ns_plain_safe(c)):
            self._scanner.pos -= 1
            return False

        return bool(
            self._try(lambda: self._parse_s_separate(n, c) and self._parse_ns_flow_node(n, c))
            or self._parse_e_node()
        )

    # [148] c-ns-flow-map-json-key-entry(n,c)
    def _parse_c_ns_flow_map_json_key_entry(self, n: int, c: str) -> bool:
        if not self._parse_c_flow_json_node(n, c):
            return False

        return bool(
            self._try(
                lambda: (self._parse_s_separate(n, c) or True)
                and self._parse_c_ns_flow_map_adjacent_value(n, c)
            )
            or self._parse_e_node()
        )

    # [149] c-ns-flow-map-adjacent-value(n,c)
    def _parse_c_ns_flow_map_adjacent_value(self, n: int, c: str) -> bool:
        if not self._match(":"):
            return False

        return bool(
            self._try(
                lambda: (self._parse_s_separate(n, c) or True) and self._parse_ns_flow_node(n, c)
            )
            or self._parse_e_node()
        )

    # [150] ns-flow-pair(n,c)
    def _parse_ns_flow_pair(self, n: int, c: str) -> bool:
        assert self._source is not None
        assert self._scanner is not None
        pos_start = self._scanner.pos

        self._events_cache_push()

        result = bool(
            self._try(
                lambda: bool(self._match("?"))
                and self._parse_s_separate(n, c)
                and self._parse_ns_flow_map_explicit_entry(n, c)
            )
            or self._parse_ns_flow_pair_entry(n, c)
        )

        if result:
            # Wrap in single-pair mapping
            events = self._events_cache_pop()
            self._events_push(
                MappingStartEvent(Location.point(self._source, pos_start), CollectionStyle.FLOW)
            )
            for event in events:
                self._events_push(event)
            self._events_push(MappingEndEvent(Location.point(self._source, self._scanner.pos)))
        else:
            self._events_cache_pop()

        return result

    # [151] ns-flow-pair-entry(n,c)
    def _parse_ns_flow_pair_entry(self, n: int, c: str) -> bool:
        # Each alternative must cache events separately so failed attempts
        # don't pollute successful ones
        assert self._scanner is not None
        pos = self._scanner.pos

        # Try yaml key entry
        self._events_cache_push()
        if self._parse_ns_flow_pair_yaml_key_entry(n, c):
            self._events_cache_flush()
            return True
        self._events_cache_pop()
        self._scanner.pos = pos

        # Try empty key entry
        self._events_cache_push()
        if self._parse_c_ns_flow_map_empty_key_entry(n, c):
            self._events_cache_flush()
            return True
        self._events_cache_pop()
        self._scanner.pos = pos

        # Try json key entry
        self._events_cache_push()
        if self._parse_c_ns_flow_pair_json_key_entry(n, c):
            self._events_cache_flush()
            return True
        self._events_cache_pop()
        self._scanner.pos = pos

        return False

    # [152] ns-flow-pair-yaml-key-entry(n,c)
    def _parse_ns_flow_pair_yaml_key_entry(self, n: int, c: str) -> bool:
        if not self._parse_ns_s_implicit_yaml_key("flow-key"):
            return False

        return self._parse_c_ns_flow_map_separate_value(n, c)

    # [153] c-ns-flow-pair-json-key-entry(n,c)
    def _parse_c_ns_flow_pair_json_key_entry(self, n: int, c: str) -> bool:
        if not self._parse_c_s_implicit_json_key("flow-key"):
            return False

        return self._parse_c_ns_flow_map_adjacent_value(n, c)

    # [154] ns-s-implicit-yaml-key(c)
    def _parse_ns_s_implicit_yaml_key(self, c: str) -> bool:
        # Limit key length for implicit keys
        # In block-key context, flow content must be single-line.
        # If parsing fails with SyntaxError (e.g., multiline flow content),
        # we should return False to allow backtracking to other parse paths.
        assert self._scanner is not None
        pos = self._scanner.pos
        cached = [list(level) for level in self._events_cache]
        try:
            return bool(
                self._try(
                    lambda: self._parse_ns_flow_yaml_node(-1, c) and (self._parse_s_separate_in_line() or True)
                )
            )
        except YAMLSyntaxError:
            self._scanner.pos = pos
            self._events_cache = cached
            return False

    # [155] c-s-implicit-json-key(c)
    def _parse_c_s_implicit_json_key(self, c: str) -> bool:
        # In block-key context, flow content must be single-line.
        # If parsing fails with SyntaxError (e.g., multiline flow mapping),
        # we should return False to allow backtracking to other parse paths.
        assert self._scanner is not None
        pos = self._scanner.pos
        cached = [list(level) for level in self._events_cache]
        try:
            return bool(
                self._try(
                    lambda: self._parse_c_flow_json_node(-1, c) and (self._parse_s_separate_in_line() or True)
                )
            )
        except YAMLSyntaxError:
            self._scanner.pos = pos
            self._events_cache = cached
            return False

    # [156] ns-flow-yaml-content(n,c)
    def _parse_ns_flow_yaml_content(self, n: int, c: str) -> bool:
        return self._parse_ns_plain(n, c)

    # [157] c-flow-json-content(n,c)
    def _parse_c_flow_json_content(self, n: int, c: str) -> bool:
        return bool(
            self._parse_c_flow_sequence(n, c)
            or self._parse_c_flow_mapping(n, c)
            or self._parse_c_single_quoted(n, c)
            or self._parse_c_double_quoted(n, c)
        )

    # [158] ns-flow-content(n,c)
    def _parse_ns_flow_content(self, n: int, c: str) -> bool:
        return self._parse_ns_flow_yaml_content(n, c) or self._parse_c_flow_json_content(n, c)

    # [159] ns-flow-yaml-node(n,c)
    def _parse_ns_flow_yaml_node(self, n: int, c: str) -> bool:
        assert self._scanner is not None

        def properties_then_content() -> bool:
            if not self._parse_c_ns_properties(n, c):
                return False
            # Try whitespace + yaml content
            if self._parse_s_separate(n, c) and self._parse_ns_flow_yaml_content(n, c):
                return True
            # Only allow empty scalar if next char is not JSON content indicator
            # If it's JSON content ([ { ' "), let json-key-entry handle it
            next_char = self._scanner.peek()
            if next_char in ("[", "{", "'", '"'):
                return False
            return self._parse_e_scalar()

        return bool(
            self._parse_c_ns_alias_node()
            or self._parse_ns_flow_yaml_content(n, c)
            or self._try(properties_then_content)
        )

    # [160] c-flow-json-node(n,c)
    def _parse_c_flow_json_node(self, n: int, c: str) -> bool:
        return bool(
            self._try(
                lambda: (self._parse_c_ns_properties(n, c) and self._parse_s_separate(n, c) or True)
                and self._parse_c_flow_json_content(n, c)
            )
        )

    # [161] ns-flow-node(n,c)
    def _parse_ns_flow_node(self, n: int, c: str) -> bool:
        return bool(
            self._parse_c_ns_alias_node()
            or self._parse_ns_flow_content(n, c)
            or self._try(
                lambda: self._parse_c_ns_properties(n, c)
                and (
                    (self._parse_s_separate(n, c) and self._parse_ns_flow_content(n, c))
                    or self._parse_e_scalar()
                )
            )
        )

    def _in_flow(self, c: str) -> str:
        if c in ("flow-out", "flow-in"):
            return "flow-in"
        elif c in ("block-key", "flow-key"):
            return "flow-key"
        return c

    # [96] c-ns-properties(n,c)
    def _parse_c_ns_properties(self, n: int, c: str) -> bool:
        # YAML spec: properties are tag and/or anchor, with optional separator between them
        # The optional second property (sep + property) should be wrapped in _try
        # to restore position if it fails
        return bool(
            self._try(
                lambda: self._parse_c_ns_tag_property()
                and (self._try(lambda: self._parse_s_separate(n, c) and self._parse_c_ns_anchor_property()) or True)
            )
            or (
                self._parse_c_ns_anchor_property()
                and (self._try(lambda: self._parse_s_separate(n, c) and self._parse_c_ns_tag_property()) or True)
            )
        )

    # [201] l-document-prefix
    def _parse_l_document_prefix(self) -> bool:
        self._match("\uFEFF") or True  # BOM
        return self._parse_l_comment_star()

    # [202] c-directives-end
    # Note: Per YAML spec [205] c-forbidden, the --- marker must be followed by
    # whitespace, newline, or EOF to be a valid document marker
    def _parse_c_directives_end(self) -> bool:
        assert self._scanner is not None
        if self._scanner.check(RE_DIRECTIVES_END):
            self._scanner.pos += 3
            return True
        return False

    # [203] c-document-end
    # Note: Per YAML spec [205] c-forbidden, the ... marker must be followed by
    # whitespace, newline, or EOF to be a valid document end marker
    def _parse_c_document_end(self) -> bool:
        assert self._scanner is not None
        if self._scanner.check(RE_DOCUMENT_END):
            self._scanner.pos += 3
            return True
        return False

    # [204] l-document-suffix
    def _parse_l_document_suffix(self) -> bool:
        if self._parse_c_document_end():
            # Mark the document end as explicit (not implicit)
            if self._document_end_event:
                self._document_end_event.implicit = False
            return self._parse_s_l_comments()
        return False

    # [205] c-forbidden
    def _parse_c_forbidden(self) -> bool:
        return self._start_of_line() and (
            self._parse_c_directives_end() or self._parse_c_document_end()
        ) and (
            self._parse_b_char() or self._parse_s_white() or self._scanner.eos()
        )

    def _parse_b_char(self) -> bool:
        return self._parse_b_break()

    # [206] l-bare-document
    def _parse_l_bare_document(self) -> bool:
        self._in_bare_document = True
        try:
            return self._parse_s_l_block_node(-1, "block-in")
        finally:
            self._in_bare_document = False

    # [207] l-explicit-document
    def _parse_l_explicit_document(self) -> bool:
        if not self._parse_c_directives_end():
            return False

        if self._document_start_event:
            self._document_start_event.implicit = False

        return bool(
            self._parse_l_bare_document()
            or (self._parse_e_node() and self._parse_s_l_comments())
        )

    # [208] l-directive-document
    def _parse_l_directive_document(self) -> bool:
        if not self._plus(self._parse_l_directive):
            return False

        return self._parse_l_explicit_document()

    # [209] l-any-document
    def _parse_l_any_document(self) -> bool:
        return bool(
            self._parse_l_directive_document()
            or self._parse_l_explicit_document()
            or self._parse_l_bare_document()
        )

    # [211] l-yaml-stream - The top-level rule
    def _parse_l_yaml_stream(self) -> bool:
        assert self._source is not None
        assert self._scanner is not None

        self._events_push_flush_properties(
            StreamStartEvent(Location.point(self._source, self._scanner.pos))
        )

        self._star(self._parse_l_document_prefix)

        self._document_start_event = DocumentStartEvent(
            Location.point(self._source, self._scanner.pos)
        )
        self._tag_directives = self._document_start_event.tag_directives
        self._document_end_event = None

        self._parse_l_any_document()

        # Parse additional documents
        while True:
            pos_before = self._scanner.pos
            if self._try(
                lambda: self._parse_l_document_suffix()
                and self._star(self._parse_l_document_prefix)
                and (self._document_end_event_flush() or True)
                and (self._parse_l_any_document() or True)
            ):
                if self._scanner.pos > pos_before:  # Made progress
                    continue
            if self._try(
                lambda: self._star(self._parse_l_document_prefix)
                and (self._document_end_event_flush() or True)
                and self._parse_l_explicit_document()
            ):
                if self._scanner.pos > pos_before:  # Made progress
                    continue
            break

        # Consume any trailing comments/blank lines after the last document
        self._star(self._parse_l_comment)

        if not self._scanner.eos():
            self._raise_syntax_error("Parser finished before end of input")

        self._document_end_event_flush()
        self._events_push_flush_properties(
            StreamEndEvent(Location.point(self._source, self._scanner.pos))
        )
        return True

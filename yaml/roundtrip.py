"""
Round-trip YAML loading and dumping with comment preservation.

This module provides loaders and dumpers that preserve comments,
allowing YAML documents to be loaded, modified, and saved while
keeping comments intact.

Usage:
    from yaml import round_trip_load, round_trip_dump

    # Load preserving comments
    data = round_trip_load(yaml_string)

    # Modify data
    data['key'] = 'new_value'

    # Dump with comments preserved
    output = round_trip_dump(data)
"""

from __future__ import annotations

import re
from io import StringIO
from typing import IO, Any, Iterator

from ._comments import Comment, CommentedMap, CommentedSeq, CommentGroup
from .constructor import SafeConstructor
from .emitter import Emitter
from .events import (
    DocumentEndEvent,
    DocumentStartEvent,
    MappingEndEvent,
    MappingStartEvent,
    ScalarEvent,
    SequenceEndEvent,
    SequenceStartEvent,
    StreamEndEvent,
    StreamStartEvent,
)
from .nodes import MappingNode, Node, ScalarNode, SequenceNode
from .representer import SafeRepresenter
from .resolver import Resolver
from .serializer import Serializer


class CommentScanner:
    """
    Scans YAML source and extracts comments with their positions.

    Comments are associated with line numbers for later attachment
    to the appropriate nodes.
    """

    # Regex to match comment lines and inline comments
    COMMENT_LINE = re.compile(r"^(\s*)#\s*(.*?)$", re.MULTILINE)
    INLINE_COMMENT = re.compile(r"\s+#\s*(.*?)$")

    def __init__(self, source: str) -> None:
        self.source = source
        self.lines = source.split("\n")
        self.comments: dict[int, list[Comment]] = {}  # line -> comments before that line
        self.inline_comments: dict[int, Comment] = {}  # line -> inline comment on that line
        self._scan()

    def _scan(self) -> None:
        """Scan the source and extract all comments."""
        pending_comments: list[Comment] = []

        for line_no, line in enumerate(self.lines):
            stripped = line.strip()

            # Check for full-line comment
            if stripped.startswith("#"):
                comment_text = stripped[1:].lstrip()
                pending_comments.append(Comment(comment_text, len(line) - len(line.lstrip())))
            else:
                # Check for inline comment (not in quoted string)
                inline_match = self._find_inline_comment(line)
                if inline_match:
                    self.inline_comments[line_no] = Comment(
                        inline_match, line.rfind("#")
                    )

                # Attach pending comments to this line
                if pending_comments and stripped:
                    self.comments[line_no] = pending_comments
                    pending_comments = []

        # Handle trailing comments
        if pending_comments:
            self.comments[len(self.lines)] = pending_comments

    def _find_inline_comment(self, line: str) -> str | None:
        """Find inline comment, being careful about quoted strings."""
        in_single_quote = False
        in_double_quote = False
        i = 0

        while i < len(line):
            ch = line[i]

            # Handle escape sequences in double quotes
            if in_double_quote and ch == "\\" and i + 1 < len(line):
                i += 2
                continue

            if ch == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            elif ch == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
            elif ch == "#" and not in_single_quote and not in_double_quote:
                # Found a comment
                if i > 0 and line[i - 1] in " \t":
                    return line[i + 1 :].lstrip()

            i += 1

        return None

    def get_comments_before(self, line: int) -> list[Comment]:
        """Get comments that appear before the given line."""
        return self.comments.get(line, [])

    def get_inline_comment(self, line: int) -> Comment | None:
        """Get inline comment on the given line."""
        return self.inline_comments.get(line)


class RoundTripComposerHandler:
    """
    Handler that composes parser events into nodes with comment preservation.
    """

    def __init__(
        self, resolver: Resolver | None = None, comment_scanner: CommentScanner | None = None
    ) -> None:
        self._anchors: dict[str, Node] = {}
        self._root: Node | None = None
        self._documents: list[Node | None] = []
        self._stack: list[tuple[Node, list[Any]]] = []
        self._resolver = resolver
        self._comment_scanner = comment_scanner
        self._last_line: int = 0

    @property
    def documents(self) -> list[Node | None]:
        return self._documents

    def event_location(
        self, start_line: int, start_column: int, end_line: int, end_column: int
    ) -> None:
        self._last_line = start_line

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
        self._root = None
        self._stack = []
        self._anchors = {}

    def end_document(self, implicit: bool) -> None:
        self._documents.append(self._root)
        self._root = None

    def start_mapping(
        self, anchor: str | None, tag: str | None, implicit: bool, style: int
    ) -> None:
        node = MappingNode(
            tag=tag or "tag:yaml.org,2002:map",
            value=[],
            flow_style=style == 2,
            anchor=anchor,
        )

        # Attach comments
        if self._comment_scanner:
            comments = self._comment_scanner.get_comments_before(self._last_line)
            if comments:
                node.comment = [c.value for c in comments]

        if anchor:
            self._anchors[anchor] = node

        self._push_node(node)
        self._stack.append((node, []))

    def end_mapping(self) -> None:
        node, pairs = self._stack.pop()
        if isinstance(node, MappingNode):
            it = iter(pairs)
            node.value = list(zip(it, it))

    def start_sequence(
        self, anchor: str | None, tag: str | None, implicit: bool, style: int
    ) -> None:
        node = SequenceNode(
            tag=tag or "tag:yaml.org,2002:seq",
            value=[],
            flow_style=style == 2,
            anchor=anchor,
        )

        # Attach comments
        if self._comment_scanner:
            comments = self._comment_scanner.get_comments_before(self._last_line)
            if comments:
                node.comment = [c.value for c in comments]

        if anchor:
            self._anchors[anchor] = node

        self._push_node(node)
        self._stack.append((node, node.value))

    def end_sequence(self) -> None:
        node, _ = self._stack.pop()

    def scalar(
        self,
        value: str,
        anchor: str | None,
        tag: str | None,
        plain: bool,
        quoted: bool,
        style: int,
    ) -> None:
        style_map = {1: None, 2: "'", 3: '"', 4: "|", 5: ">"}

        if tag is None and self._resolver is not None:
            tag = self._resolver.resolve(ScalarNode, value, (plain, not quoted))
        if tag is None:
            tag = "tag:yaml.org,2002:str"

        node = ScalarNode(
            tag=tag,
            value=value,
            style=style_map.get(style),
            anchor=anchor,
        )

        # Attach comments
        if self._comment_scanner:
            # Before comments
            before_comments = self._comment_scanner.get_comments_before(self._last_line)
            inline_comment = self._comment_scanner.get_inline_comment(self._last_line)
            if before_comments or inline_comment:
                comments = [c.value for c in before_comments]
                if inline_comment:
                    comments.append(f"inline:{inline_comment.value}")
                node.comment = comments

        if anchor:
            self._anchors[anchor] = node

        self._push_node(node)

    def alias(self, anchor: str) -> None:
        if anchor not in self._anchors:
            from .error import ComposerError

            raise ComposerError(
                None, None, f"found undefined alias {anchor!r}", None
            )

        node = self._anchors[anchor]
        self._push_node(node)

    def _push_node(self, node: Node) -> None:
        if not self._stack:
            self._root = node
        else:
            parent, items = self._stack[-1]
            items.append(node)


class RoundTripConstructor(SafeConstructor):
    """
    Constructor that creates CommentedMap and CommentedSeq objects.

    Uses its own yaml_constructors to avoid affecting the base SafeConstructor.
    """

    # Create a copy of the parent's yaml_constructors so we don't modify the parent
    yaml_constructors = SafeConstructor.yaml_constructors.copy()

    def construct_yaml_map(self, node: Node) -> Any:
        data = CommentedMap()

        if not isinstance(node, MappingNode):
            from .error import ConstructorError

            raise ConstructorError(
                None, None, f"expected a mapping node, but found {node.id}", node.start_mark
            )

        # Note: We don't use node.comment for start_comments because
        # the comment is already attached to the first key's node.
        # This avoids duplicating the header comment.

        for idx, (key_node, value_node) in enumerate(node.value):
            key = self.construct_object(key_node, deep=True)
            if not isinstance(key, (str, int, float, bool, type(None))):
                key = str(key)

            value = self.construct_object(value_node, deep=True)
            data[key] = value

            # Attach comments to key
            if key_node.comment:
                group = CommentGroup()
                for c in key_node.comment:
                    if c.startswith("inline:"):
                        group.inline = Comment(c[7:])
                    else:
                        group.before.append(Comment(c))
                data.set_comment(key, group)

        return data

    def construct_yaml_seq(self, node: Node) -> Any:
        data = CommentedSeq()

        if not isinstance(node, SequenceNode):
            from .error import ConstructorError

            raise ConstructorError(
                None, None, f"expected a sequence node, but found {node.id}", node.start_mark
            )

        # Note: We don't use node.comment for start_comments because
        # the comment is already attached to the first item's node.

        for idx, item_node in enumerate(node.value):
            value = self.construct_object(item_node, deep=True)
            data.append(value)

            # Attach comments to index
            if item_node.comment:
                group = CommentGroup()
                for c in item_node.comment:
                    if c.startswith("inline:"):
                        group.inline = Comment(c[7:])
                    else:
                        group.before.append(Comment(c))
                data.set_comment(idx, group)

        return data


# Register constructors on RoundTripConstructor's own yaml_constructors
RoundTripConstructor.yaml_constructors["tag:yaml.org,2002:map"] = (
    RoundTripConstructor.construct_yaml_map
)
RoundTripConstructor.yaml_constructors["tag:yaml.org,2002:seq"] = (
    RoundTripConstructor.construct_yaml_seq
)


class RoundTripRepresenter(SafeRepresenter):
    """
    Representer that preserves comments from CommentedMap and CommentedSeq.
    """

    def represent_commented_map(self, data: CommentedMap) -> MappingNode:
        pairs = []
        for key, value in data.items():
            key_node = self.represent_data(key)
            value_node = self.represent_data(value)

            # Attach comments to key node
            comment_group = data.get_comment(key)
            if comment_group:
                comments = []
                for c in comment_group.before:
                    comments.append(c.value)
                if comment_group.inline:
                    comments.append(f"inline:{comment_group.inline.value}")
                if comments:
                    key_node.comment = comments

            pairs.append((key_node, value_node))

        node = MappingNode("tag:yaml.org,2002:map", pairs)

        # Note: We don't attach start_comments to the mapping node
        # because they're already attached to the first key's comments.

        return node

    def represent_commented_seq(self, data: CommentedSeq) -> SequenceNode:
        values = []
        for idx, item in enumerate(data):
            node = self.represent_data(item)

            # Attach comments to item node
            comment_group = data.get_comment(idx)
            if comment_group:
                comments = []
                for c in comment_group.before:
                    comments.append(c.value)
                if comment_group.inline:
                    comments.append(f"inline:{comment_group.inline.value}")
                if comments:
                    node.comment = comments

            values.append(node)

        node = SequenceNode("tag:yaml.org,2002:seq", values)

        # Note: We don't attach start_comments to the sequence node
        # because they're already attached to the first item's comments.

        return node


# Register representers
RoundTripRepresenter.add_representer(CommentedMap, RoundTripRepresenter.represent_commented_map)
RoundTripRepresenter.add_representer(CommentedSeq, RoundTripRepresenter.represent_commented_seq)


class RoundTripEmitter(Emitter):
    """
    Emitter that outputs comments from events.

    Comments are passed via a special 'comment' attribute on events.
    Comments are read directly from events when they are processed
    in the state machine.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._pending_inline_comment: str | None = None

    def _get_event_comments(self) -> tuple[list[str], str | None]:
        """Get comments from the current event."""
        before_comments: list[str] = []
        inline_comment: str | None = None

        if self.event and hasattr(self.event, "before_comments"):
            before_comments = self.event.before_comments or []
        if self.event and hasattr(self.event, "inline_comment"):
            inline_comment = self.event.inline_comment

        return before_comments, inline_comment

    def _write_before_comments(self, comments: list[str]) -> None:
        """Write before comments with proper indentation."""
        for text in comments:
            self._write_comment(text)

    def _write_comment(self, text: str) -> None:
        """Write a comment line with proper indentation."""
        # Write indent first
        indent = self.indent or 0
        if self.column > 0:
            self.write_line_break()
        if self.column < indent:
            self._write(" " * (indent - self.column))
            self.column = indent
        # Write comment
        self._write(f"# {text}")
        self.write_line_break()
        self.column = 0
        self.whitespace = True
        self.indentation = True

    def _write_inline_comment(self, text: str) -> None:
        """Write an inline comment at the end of the current line."""
        self._write(f"  # {text}")

    def expect_block_mapping_key(self, first: bool = False) -> None:
        """Override to write comments at the right time."""
        if not first and isinstance(self.event, MappingEndEvent):
            # Write inline comment for the last value if any
            if self._pending_inline_comment:
                self._write_inline_comment(self._pending_inline_comment)
                self._pending_inline_comment = None
            self.indent = self.indents.pop()
            self.state = self.states.pop()
        else:
            # Write inline comment for previous value first
            if not first and self._pending_inline_comment:
                self._write_inline_comment(self._pending_inline_comment)
                self._pending_inline_comment = None

            # Get comments from current event (the key scalar)
            before_comments, inline_comment = self._get_event_comments()

            # Write before comments for this key
            self._write_before_comments(before_comments)

            # Store inline comment to write after the value
            if inline_comment:
                self._pending_inline_comment = inline_comment

            # Now write indent and process key
            self.write_indent()
            if self.check_simple_key():
                self.states.append(self.expect_block_mapping_simple_value)
                self.expect_node(mapping=True, simple_key=True)
            else:
                self.write_indicator("?", need_whitespace=True, indentation=True)
                self.states.append(self.expect_block_mapping_value)
                self.expect_node(mapping=True)

    def expect_block_sequence_item(self, first: bool = False) -> None:
        """Override to write comments at the right time."""
        if not first and isinstance(self.event, SequenceEndEvent):
            # Write inline comment for the last item if any
            if self._pending_inline_comment:
                self._write_inline_comment(self._pending_inline_comment)
                self._pending_inline_comment = None
            self.indent = self.indents.pop()
            self.state = self.states.pop()
        else:
            # Write inline comment for previous item first
            if not first and self._pending_inline_comment:
                self._write_inline_comment(self._pending_inline_comment)
                self._pending_inline_comment = None

            # Get comments from current event (the item)
            before_comments, inline_comment = self._get_event_comments()

            # Write before comments for this item
            self._write_before_comments(before_comments)

            # Store inline comment to write after the item
            if inline_comment:
                self._pending_inline_comment = inline_comment

            # Now write indent and process item
            self.write_indent()
            self.write_indicator("-", need_whitespace=True, indentation=True)
            self.states.append(self.expect_block_sequence_item)
            self.expect_node(sequence=True)

    def expect_document_end(self) -> None:
        """Override to write any final pending inline comment."""
        if self._pending_inline_comment:
            self._write_inline_comment(self._pending_inline_comment)
            self._pending_inline_comment = None
        super().expect_document_end()


class RoundTripSerializer(Serializer):
    """
    Serializer that attaches comments to events.

    Comments from nodes are passed to the emitter via event attributes.
    """

    def serialize_node(
        self,
        node: Node,
        parent: Node | None,
        index: Any,
    ) -> None:
        """Serialize a node, attaching comments to events."""
        node_id = id(node)
        alias = self.anchors.get(node_id)

        if node_id in self.serialized_nodes:
            from .events import AliasEvent
            self.emit(AliasEvent(anchor=alias))
        else:
            self.serialized_nodes[node_id] = True
            self.descend_resolver(parent, index)

            # Extract comments from node
            before_comments: list[str] = []
            inline_comment: str | None = None

            if hasattr(node, "comment") and node.comment:
                for comment in node.comment:
                    if comment.startswith("inline:"):
                        inline_comment = comment[7:]
                    else:
                        before_comments.append(comment)

            if isinstance(node, ScalarNode):
                detected_tag = self.resolve(ScalarNode, node.value, (True, False))
                default_tag = self.resolve(ScalarNode, node.value, (False, True))
                implicit = (
                    (node.tag == detected_tag),
                    (node.tag == default_tag),
                )
                event = ScalarEvent(
                    anchor=alias,
                    tag=node.tag,
                    implicit=implicit,
                    value=node.value,
                    style=node.style,
                )
                # Attach comments to event
                event.before_comments = before_comments  # type: ignore
                event.inline_comment = inline_comment  # type: ignore
                self.emit(event)

            elif isinstance(node, SequenceNode):
                implicit = node.tag == self.resolve(SequenceNode, node.value, True)
                event = SequenceStartEvent(
                    anchor=alias,
                    tag=node.tag,
                    implicit=implicit,
                    flow_style=node.flow_style,
                )
                # Attach comments to event
                event.before_comments = before_comments  # type: ignore
                self.emit(event)

                for idx, item in enumerate(node.value):
                    self.serialize_node(item, node, idx)
                self.emit(SequenceEndEvent())

            elif isinstance(node, MappingNode):
                implicit = node.tag == self.resolve(MappingNode, node.value, True)
                event = MappingStartEvent(
                    anchor=alias,
                    tag=node.tag,
                    implicit=implicit,
                    flow_style=node.flow_style,
                )
                # Attach comments to event
                event.before_comments = before_comments  # type: ignore
                self.emit(event)

                for key, value in node.value:
                    self.serialize_node(key, node, None)
                    self.serialize_node(value, node, key)
                self.emit(MappingEndEvent())

            self.ascend_resolver()


class RoundTripLoader(RoundTripConstructor, Resolver):
    """
    Loader that preserves comments in CommentedMap and CommentedSeq.
    """

    def __init__(self, stream: str | bytes | IO[str] | IO[bytes]) -> None:
        RoundTripConstructor.__init__(self)
        Resolver.__init__(self)

        if hasattr(stream, "read"):
            stream = stream.read()
        if isinstance(stream, bytes):
            stream = stream.decode("utf-8")

        self._stream: str = stream
        self._comment_scanner = CommentScanner(stream)

        from ._parser import Parser

        self._handler = RoundTripComposerHandler(
            resolver=self, comment_scanner=self._comment_scanner
        )
        self._parser = Parser(self._handler)
        self._parsed = False
        self._documents: list[Node | None] = []
        self._document_index = 0

    def _parse(self) -> None:
        if not self._parsed:
            self._parser.parse(self._stream)
            self._documents = self._handler.documents
            self._parsed = True

    def check_data(self) -> bool:
        self._parse()
        return self._document_index < len(self._documents)

    def get_data(self) -> Any:
        if self.check_data():
            node = self._documents[self._document_index]
            self._document_index += 1
            return self.construct_document(node)
        return None

    def get_single_data(self) -> Any:
        self._parse()
        if self._documents:
            return self.construct_document(self._documents[0])
        return None

    def dispose(self) -> None:
        pass


class RoundTripDumper(RoundTripRepresenter, Resolver, RoundTripEmitter, RoundTripSerializer):
    """
    Dumper that preserves comments from CommentedMap and CommentedSeq.
    """

    def __init__(
        self,
        stream: IO[str] | None = None,
        default_style: str | None = None,
        default_flow_style: bool | None = False,
        canonical: bool | None = None,
        indent: int | None = None,
        width: int | None = None,
        allow_unicode: bool | None = None,
        line_break: str | None = None,
        encoding: str | None = None,
        explicit_start: bool | None = None,
        explicit_end: bool | None = None,
        version: tuple[int, int] | None = None,
        tags: dict[str, str] | None = None,
        sort_keys: bool = False,
    ) -> None:
        RoundTripRepresenter.__init__(
            self,
            default_style=default_style,
            default_flow_style=default_flow_style,
            sort_keys=sort_keys,
        )
        Resolver.__init__(self)

        if stream is None:
            stream = StringIO()
        self._output_stream = stream

        RoundTripEmitter.__init__(
            self,
            stream,
            canonical=canonical,
            indent=indent,
            width=width,
            allow_unicode=allow_unicode,
            line_break=line_break,
        )
        RoundTripSerializer.__init__(
            self,
            encoding=encoding,
            explicit_start=explicit_start,
            explicit_end=explicit_end,
            version=version,
            tags=tags,
        )

    def represent(self, data: Any) -> None:
        """Represent a Python object as YAML, then serialize and emit it."""
        self.open()
        node = self.represent_data(data)
        self.serialize(node)
        self.close()


def round_trip_load(
    stream: str | bytes | IO[str] | IO[bytes],
) -> Any:
    """
    Load YAML with comment preservation.

    Returns CommentedMap and CommentedSeq objects that preserve
    comments for round-trip editing.

    Args:
        stream: YAML string, bytes, or file-like object

    Returns:
        Python object (CommentedMap, CommentedSeq, or scalar)
    """
    loader = RoundTripLoader(stream)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def round_trip_load_all(
    stream: str | bytes | IO[str] | IO[bytes],
) -> Iterator[Any]:
    """
    Load all YAML documents with comment preservation.

    Args:
        stream: YAML string, bytes, or file-like object

    Yields:
        Python objects for each document
    """
    loader = RoundTripLoader(stream)
    try:
        while loader.check_data():
            yield loader.get_data()
    finally:
        loader.dispose()


def round_trip_dump(
    data: Any,
    stream: IO[str] | None = None,
    *,
    default_style: str | None = None,
    default_flow_style: bool | None = False,
    canonical: bool | None = None,
    indent: int | None = None,
    width: int | None = None,
    allow_unicode: bool | None = None,
    line_break: str | None = None,
    encoding: str | None = None,
    explicit_start: bool | None = None,
    explicit_end: bool | None = None,
    version: tuple[int, int] | None = None,
    tags: dict[str, str] | None = None,
    sort_keys: bool = False,
) -> str | None:
    """
    Dump Python object to YAML with comment preservation.

    If data is a CommentedMap or CommentedSeq, comments will be
    included in the output.

    Args:
        data: Python object to dump
        stream: Optional file-like object to write to
        **kwargs: Formatting options

    Returns:
        YAML string if stream is None, otherwise None
    """
    return_string = stream is None
    if return_string:
        stream = StringIO()

    dumper = RoundTripDumper(
        stream,
        default_style=default_style,
        default_flow_style=default_flow_style,
        canonical=canonical,
        indent=indent,
        width=width,
        allow_unicode=allow_unicode,
        line_break=line_break,
        encoding=encoding,
        explicit_start=explicit_start,
        explicit_end=explicit_end,
        version=version,
        tags=tags,
        sort_keys=sort_keys,
    )
    dumper.represent(data)

    if return_string:
        return stream.getvalue()
    return None


def round_trip_dump_all(
    documents: list[Any],
    stream: IO[str] | None = None,
    **kwargs: Any,
) -> str | None:
    """
    Dump multiple documents to YAML with comment preservation.

    Args:
        documents: List of Python objects to dump
        stream: Optional file-like object to write to
        **kwargs: Formatting options

    Returns:
        YAML string if stream is None, otherwise None
    """
    return_string = stream is None
    if return_string:
        stream = StringIO()

    for data in documents:
        dumper = RoundTripDumper(stream, explicit_start=True, **kwargs)
        dumper.represent(data)

    if return_string:
        return stream.getvalue()
    return None

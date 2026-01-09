"""
YAML loader classes - PyYAML compatible.

This module provides loader classes that combine parsing,
resolution, and construction to load YAML into Python objects.
"""

from __future__ import annotations

from typing import IO, TYPE_CHECKING, Any, Iterator

from ._parser import Handler, Parser
from .constructor import BaseConstructor, FullConstructor, SafeConstructor, UnsafeConstructor
from .nodes import MappingNode, Node, ScalarNode, SequenceNode
from .resolver import BaseResolver, Resolver

if TYPE_CHECKING:
    from .error import Mark


class ComposerHandler(Handler):
    """
    Handler that composes parser events into a node tree.

    This is used internally by loaders to build the AST.
    """

    def __init__(self, resolver: BaseResolver | None = None) -> None:
        self._anchors: dict[str, Node] = {}
        self._root: Node | None = None
        self._documents: list[Node | None] = []
        self._stack: list[tuple[Node, list[Any]]] = []
        self._current_key: Node | None = None
        self._last_mark: tuple[int, int, int, int] | None = None
        self._resolver = resolver

    @property
    def root(self) -> Node | None:
        return self._root

    @property
    def documents(self) -> list[Node | None]:
        return self._documents

    def _make_mark(self) -> Mark | None:
        if self._last_mark is None:
            return None
        from .error import Mark

        return Mark(
            "<unknown>",
            0,
            self._last_mark[0],
            self._last_mark[1],
            None,
            None,
        )

    def event_location(
        self, start_line: int, start_column: int, end_line: int, end_column: int
    ) -> None:
        self._last_mark = (start_line, start_column, end_line, end_column)

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
        # Reset for new document
        self._root = None
        self._stack = []
        self._anchors = {}

    def end_document(self, implicit: bool) -> None:
        # Save the completed document
        self._documents.append(self._root)
        self._root = None

    def start_mapping(
        self, anchor: str | None, tag: str | None, implicit: bool, style: int
    ) -> None:
        node = MappingNode(
            tag=tag or "tag:yaml.org,2002:map",
            value=[],
            start_mark=self._make_mark(),
            flow_style=style == 2,
            anchor=anchor,
        )

        if anchor:
            self._anchors[anchor] = node

        self._push_node(node)
        self._stack.append((node, []))

    def end_mapping(self) -> None:
        node, pairs = self._stack.pop()
        if isinstance(node, MappingNode):
            # Convert pairs list to proper format
            it = iter(pairs)
            node.value = list(zip(it, it))
        node.end_mark = self._make_mark()

    def start_sequence(
        self, anchor: str | None, tag: str | None, implicit: bool, style: int
    ) -> None:
        node = SequenceNode(
            tag=tag or "tag:yaml.org,2002:seq",
            value=[],
            start_mark=self._make_mark(),
            flow_style=style == 2,
            anchor=anchor,
        )

        if anchor:
            self._anchors[anchor] = node

        self._push_node(node)
        self._stack.append((node, node.value))

    def end_sequence(self) -> None:
        node, _ = self._stack.pop()
        node.end_mark = self._make_mark()

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

        # Resolve tag if not explicitly provided
        if tag is None and self._resolver is not None:
            tag = self._resolver.resolve(ScalarNode, value, (plain, not quoted))
        if tag is None:
            tag = "tag:yaml.org,2002:str"

        node = ScalarNode(
            tag=tag,
            value=value,
            start_mark=self._make_mark(),
            end_mark=self._make_mark(),
            style=style_map.get(style),
            anchor=anchor,
        )

        if anchor:
            self._anchors[anchor] = node

        self._push_node(node)

    def alias(self, anchor: str) -> None:
        if anchor not in self._anchors:
            from .error import ComposerError

            raise ComposerError(
                None,
                None,
                f"found undefined alias {anchor!r}",
                self._make_mark(),
            )

        node = self._anchors[anchor]
        self._push_node(node)

    def _push_node(self, node: Node) -> None:
        if not self._stack:
            self._root = node
        else:
            parent, items = self._stack[-1]
            items.append(node)


class BaseLoader(BaseConstructor, BaseResolver):
    """
    Base loader class.

    Combines parsing, composing, and construction.
    """

    def __init__(self, stream: str | bytes | IO[str] | IO[bytes]) -> None:
        BaseConstructor.__init__(self)
        BaseResolver.__init__(self)

        if hasattr(stream, "read"):
            stream = stream.read()
        if isinstance(stream, bytes):
            stream = stream.decode("utf-8")

        self._stream: str = stream
        self._handler = ComposerHandler(resolver=self)
        self._parser = Parser(self._handler)
        self._parsed = False
        self._documents: list[Node | None] = []
        self._document_index = 0

    def _parse(self) -> None:
        if not self._parsed:
            self._parser.parse(self._stream)
            # Documents are collected by the handler during parsing
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


class SafeLoader(BaseLoader, SafeConstructor, Resolver):
    """
    Safe loader that only allows basic Python types.

    This is the loader used by safe_load().
    """

    def __init__(self, stream: str | bytes | IO[str] | IO[bytes]) -> None:
        BaseLoader.__init__(self, stream)
        SafeConstructor.__init__(self)
        Resolver.__init__(self)


class FullLoader(BaseLoader, FullConstructor, Resolver):
    """
    Full loader that allows more types.

    This is the loader used by full_load().
    """

    def __init__(self, stream: str | bytes | IO[str] | IO[bytes]) -> None:
        BaseLoader.__init__(self, stream)
        FullConstructor.__init__(self)
        Resolver.__init__(self)


class UnsafeLoader(BaseLoader, UnsafeConstructor, Resolver):
    """
    Unsafe loader that allows arbitrary Python objects.

    This is the loader used by unsafe_load().
    """

    def __init__(self, stream: str | bytes | IO[str] | IO[bytes]) -> None:
        BaseLoader.__init__(self, stream)
        UnsafeConstructor.__init__(self)
        Resolver.__init__(self)


# Alias for compatibility
Loader = UnsafeLoader

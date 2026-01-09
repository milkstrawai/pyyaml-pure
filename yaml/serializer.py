"""
YAML serializer - PyYAML compatible.

This module provides the Serializer class that converts
node trees to event streams for the emitter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .error import SerializerError
from .events import (
    AliasEvent,
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

if TYPE_CHECKING:
    from .emitter import Emitter


class Serializer:
    """
    Serializer that converts node trees to event streams.

    This class is used by dumpers to serialize Python objects
    (converted to nodes) into YAML event streams.
    """

    ANCHOR_TEMPLATE = "id%03d"

    def __init__(
        self,
        encoding: str | None = None,
        explicit_start: bool | None = None,
        explicit_end: bool | None = None,
        version: tuple[int, int] | None = None,
        tags: dict[str, str] | None = None,
    ) -> None:
        self.use_encoding = encoding
        self.use_explicit_start = explicit_start
        self.use_explicit_end = explicit_end
        self.use_version = version
        self.use_tags = tags
        self.serialized_nodes: dict[int, bool] = {}
        self.anchors: dict[int, str | None] = {}
        self.last_anchor_id = 0
        self.closed: bool | None = None

    def open(self) -> None:
        """Start the stream."""
        if self.closed is None:
            self.emit(StreamStartEvent(encoding=self.use_encoding))
            self.closed = False
        elif self.closed:
            raise SerializerError("serializer is closed")
        else:
            raise SerializerError("serializer is already opened")

    def close(self) -> None:
        """End the stream."""
        if self.closed is None:
            raise SerializerError("serializer is not opened")
        elif not self.closed:
            self.emit(StreamEndEvent())
            self.closed = True

    def serialize(self, node: Node | None) -> None:
        """Serialize a node tree to events."""
        if self.closed is None:
            raise SerializerError("serializer is not opened")
        elif self.closed:
            raise SerializerError("serializer is closed")

        if node is not None:
            self.emit(
                DocumentStartEvent(
                    explicit=self.use_explicit_start,
                    version=self.use_version,
                    tags=self.use_tags,
                )
            )
            self.anchor_node(node)
            self.serialize_node(node, None, None)
            self.emit(DocumentEndEvent(explicit=self.use_explicit_end))

        self.serialized_nodes = {}
        self.anchors = {}
        self.last_anchor_id = 0

    def emit(self, event: Any) -> None:
        """Emit an event (to be overridden by subclass)."""
        raise NotImplementedError("Serializer.emit must be overridden")

    def anchor_node(self, node: Node) -> None:
        """Assign anchors to nodes that are referenced multiple times."""
        node_id = id(node)
        if node_id in self.anchors:
            if self.anchors[node_id] is None:
                self.anchors[node_id] = self.generate_anchor(node)
        else:
            self.anchors[node_id] = None
            if isinstance(node, SequenceNode):
                for item in node.value:
                    self.anchor_node(item)
            elif isinstance(node, MappingNode):
                for key, value in node.value:
                    self.anchor_node(key)
                    self.anchor_node(value)

    def generate_anchor(self, node: Node) -> str:
        """Generate a unique anchor name."""
        self.last_anchor_id += 1
        return self.ANCHOR_TEMPLATE % self.last_anchor_id

    def serialize_node(
        self,
        node: Node,
        parent: Node | None,
        index: Any,
    ) -> None:
        """Serialize a node to events."""
        node_id = id(node)
        alias = self.anchors.get(node_id)

        if node_id in self.serialized_nodes:
            self.emit(AliasEvent(anchor=alias))
        else:
            self.serialized_nodes[node_id] = True
            self.descend_resolver(parent, index)

            if isinstance(node, ScalarNode):
                detected_tag = self.resolve(ScalarNode, node.value, (True, False))
                default_tag = self.resolve(ScalarNode, node.value, (False, True))
                implicit = (
                    (node.tag == detected_tag),
                    (node.tag == default_tag),
                )
                self.emit(
                    ScalarEvent(
                        anchor=alias,
                        tag=node.tag,
                        implicit=implicit,
                        value=node.value,
                        style=node.style,
                    )
                )

            elif isinstance(node, SequenceNode):
                implicit = node.tag == self.resolve(SequenceNode, node.value, True)
                self.emit(
                    SequenceStartEvent(
                        anchor=alias,
                        tag=node.tag,
                        implicit=implicit,
                        flow_style=node.flow_style,
                    )
                )
                for idx, item in enumerate(node.value):
                    self.serialize_node(item, node, idx)
                self.emit(SequenceEndEvent())

            elif isinstance(node, MappingNode):
                implicit = node.tag == self.resolve(MappingNode, node.value, True)
                self.emit(
                    MappingStartEvent(
                        anchor=alias,
                        tag=node.tag,
                        implicit=implicit,
                        flow_style=node.flow_style,
                    )
                )
                for key, value in node.value:
                    self.serialize_node(key, node, None)
                    self.serialize_node(value, node, key)
                self.emit(MappingEndEvent())

            self.ascend_resolver()

    def descend_resolver(self, parent: Node | None, index: Any) -> None:
        """Descend into resolver context (to be overridden)."""
        pass

    def ascend_resolver(self) -> None:
        """Ascend from resolver context (to be overridden)."""
        pass

    def resolve(
        self,
        kind: type,
        value: Any,
        implicit: Any,
    ) -> str:
        """Resolve a tag (to be overridden)."""
        if kind == ScalarNode:
            return "tag:yaml.org,2002:str"
        elif kind == SequenceNode:
            return "tag:yaml.org,2002:seq"
        elif kind == MappingNode:
            return "tag:yaml.org,2002:map"
        return ""

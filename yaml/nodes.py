"""
YAML AST node classes - PyYAML compatible.

This module provides node classes that match PyYAML's nodes.py interface.
Nodes form the abstract syntax tree representation of YAML documents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .error import Mark


@dataclass
class Node:
    """
    Base class for all YAML nodes.

    Nodes represent the structure of YAML documents after parsing.
    Each node has a tag, value, and source location.
    """

    tag: str | None = None
    value: object = None
    start_mark: Mark | None = field(default=None, repr=False)
    end_mark: Mark | None = field(default=None, repr=False)

    # For comment preservation (optional feature)
    comment: list[str] | None = field(default=None, repr=False)

    # For anchor support
    anchor: str | None = field(default=None, repr=False)

    @property
    def id(self) -> str:
        """Return node type identifier."""
        return "node"


@dataclass
class ScalarNode(Node):
    """
    Node representing a scalar value.

    Scalars are the leaf nodes of the YAML tree, containing
    string, number, boolean, or null values.
    """

    value: str = ""
    style: str | None = None  # None (plain), '' (single), '"' (double), '|' (literal), '>' (folded)

    @property
    def id(self) -> str:
        return "scalar"


@dataclass
class CollectionNode(Node):
    """Base class for collection nodes."""

    flow_style: bool | None = None

    @property
    def id(self) -> str:
        return "collection"


@dataclass
class SequenceNode(CollectionNode):
    """
    Node representing a sequence (list/array).

    The value is a list of child nodes.
    """

    value: list[Node] = field(default_factory=list)

    @property
    def id(self) -> str:
        return "sequence"


@dataclass
class MappingNode(CollectionNode):
    """
    Node representing a mapping (dict/object).

    The value is a list of (key, value) node pairs.
    """

    value: list[tuple[Node, Node]] = field(default_factory=list)

    @property
    def id(self) -> str:
        return "mapping"

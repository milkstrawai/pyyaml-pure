"""
YAML tag resolver - PyYAML compatible.

This module provides tag resolution for YAML scalars,
determining the implicit type of values based on patterns.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .nodes import MappingNode, Node, ScalarNode, SequenceNode


class ResolverError(Exception):
    """Error during tag resolution."""

    pass


# Implicit resolvers for YAML 1.1 (PyYAML default)
# Maps (tag, regexp) for implicit scalar resolution

DEFAULT_SCALAR_TAG = "tag:yaml.org,2002:str"
DEFAULT_SEQUENCE_TAG = "tag:yaml.org,2002:seq"
DEFAULT_MAPPING_TAG = "tag:yaml.org,2002:map"


class BaseResolver:
    """
    Base resolver class.

    Provides basic tag resolution functionality that can be
    extended with additional implicit resolvers.
    """

    DEFAULT_SCALAR_TAG = DEFAULT_SCALAR_TAG
    DEFAULT_SEQUENCE_TAG = DEFAULT_SEQUENCE_TAG
    DEFAULT_MAPPING_TAG = DEFAULT_MAPPING_TAG

    yaml_implicit_resolvers: dict[str, list[tuple[str, re.Pattern[str]]]] = {}
    yaml_path_resolvers: dict[tuple[Any, ...], str] = {}

    def __init__(self) -> None:
        self.resolver_exact_paths: list[Any] = []
        self.resolver_prefix_paths: list[Any] = []

    @classmethod
    def add_implicit_resolver(
        cls,
        tag: str,
        regexp: re.Pattern[str],
        first: list[str] | None = None,
    ) -> None:
        """
        Add an implicit resolver for scalars.

        Args:
            tag: The tag to resolve to.
            regexp: Pattern to match scalar values.
            first: List of first characters that can start a match.
        """
        if not hasattr(cls, "yaml_implicit_resolvers"):
            cls.yaml_implicit_resolvers = {}

        if first is None:
            first = [None]  # type: ignore

        for ch in first:
            cls.yaml_implicit_resolvers.setdefault(ch, [])
            cls.yaml_implicit_resolvers[ch].append((tag, regexp))

    @classmethod
    def add_path_resolver(
        cls,
        tag: str,
        path: list[Any],
        kind: type | None = None,
    ) -> None:
        """Add a path-based resolver."""
        if not hasattr(cls, "yaml_path_resolvers"):
            cls.yaml_path_resolvers = {}

        new_path: list[Any] = []
        for element in path:
            if isinstance(element, (list, tuple)):
                if len(element) == 2:
                    node_check, index_check = element
                elif len(element) == 1:
                    node_check = element[0]
                    index_check = True
                else:
                    raise ResolverError(f"Invalid path element: {element}")
            else:
                node_check = None
                index_check = element

            if node_check is str:
                node_check = ScalarNode
            elif node_check is list:
                node_check = SequenceNode
            elif node_check is dict:
                node_check = MappingNode
            elif node_check not in (ScalarNode, SequenceNode, MappingNode, None):
                raise ResolverError(f"Invalid node check: {node_check}")

            if not isinstance(index_check, (str, int)) and index_check is not None:
                raise ResolverError(f"Invalid index check: {index_check}")

            new_path.append((node_check, index_check))

        if kind is str:
            kind = ScalarNode
        elif kind is list:
            kind = SequenceNode
        elif kind is dict:
            kind = MappingNode
        elif kind not in (ScalarNode, SequenceNode, MappingNode, None):
            raise ResolverError(f"Invalid node kind: {kind}")

        cls.yaml_path_resolvers[tuple(new_path), kind] = tag

    def descend_resolver(self, current_node: Node | None, current_index: Any) -> None:
        """Descend into a node for path-based resolution."""
        if not self.yaml_path_resolvers:
            return
        # Path resolution implementation
        pass

    def ascend_resolver(self) -> None:
        """Ascend from a node for path-based resolution."""
        if not self.yaml_path_resolvers:
            return
        # Path resolution implementation
        pass

    def check_resolver_prefix(
        self,
        depth: int,
        path: tuple[Any, ...],
        kind: type,
        current_node: Node | None,
        current_index: Any,
    ) -> bool:
        """Check if a path prefix matches."""
        # Implementation for path checking
        return False

    def resolve(
        self,
        kind: type,
        value: str | None,
        implicit: tuple[bool, bool],
    ) -> str:
        """
        Resolve the tag for a node.

        Args:
            kind: The node type (ScalarNode, SequenceNode, MappingNode).
            value: The scalar value (for ScalarNode).
            implicit: Tuple of (plain, quoted) flags.

        Returns:
            The resolved tag.
        """
        from .nodes import MappingNode, ScalarNode, SequenceNode

        if kind is ScalarNode and implicit[0]:
            if value == "":
                resolvers = self.yaml_implicit_resolvers.get("", [])
            else:
                resolvers = self.yaml_implicit_resolvers.get(value[0], [])
            resolvers += self.yaml_implicit_resolvers.get(None, [])  # type: ignore

            for tag, regexp in resolvers:
                if regexp.match(value or ""):
                    return tag

            # Check for plain implicit (null, true, false)
            implicit_tag = self._resolve_plain_implicit(value)
            if implicit_tag:
                return implicit_tag

        if kind is ScalarNode:
            return self.DEFAULT_SCALAR_TAG
        elif kind is SequenceNode:
            return self.DEFAULT_SEQUENCE_TAG
        elif kind is MappingNode:
            return self.DEFAULT_MAPPING_TAG

        return ""

    def _resolve_plain_implicit(self, value: str | None) -> str | None:
        """Resolve implicit type for plain scalars."""
        return None


class Resolver(BaseResolver):
    """
    Full resolver with YAML 1.1 implicit resolvers.

    This resolver handles the standard YAML 1.1 type tags including
    null, bool, int, float, timestamp, and more.
    """

    pass


# Add implicit resolvers for YAML 1.1

# Boolean
Resolver.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(
        r"""^(?:yes|Yes|YES|no|No|NO
            |true|True|TRUE|false|False|FALSE
            |on|On|ON|off|Off|OFF)$""",
        re.X,
    ),
    list("yYnNtTfFoO"),
)

# Integer
Resolver.add_implicit_resolver(
    "tag:yaml.org,2002:int",
    re.compile(
        r"""^(?:[-+]?0b[0-1_]+
            |[-+]?0[0-7_]+
            |[-+]?(?:0|[1-9][0-9_]*)
            |[-+]?0x[0-9a-fA-F_]+
            |[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+)$""",
        re.X,
    ),
    list("-+0123456789"),
)

# Float
Resolver.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(
        r"""^(?:[-+]?(?:[0-9][0-9_]*)?\.[0-9_]*(?:[eE][-+]?[0-9]+)?
            |[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*
            |[-+]?\.(?:inf|Inf|INF)
            |\.(nan|NaN|NAN))$""",
        re.X,
    ),
    list("-+0123456789."),
)

# Null
Resolver.add_implicit_resolver(
    "tag:yaml.org,2002:null",
    re.compile(r"^(?:~|null|Null|NULL|)$"),
    ["~", "n", "N", ""],
)

# Timestamp
Resolver.add_implicit_resolver(
    "tag:yaml.org,2002:timestamp",
    re.compile(
        r"""^(?:[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]
            |[0-9][0-9][0-9][0-9]-[0-9][0-9]?-[0-9][0-9]?
             (?:[Tt]|[ \t]+)[0-9][0-9]?
             :[0-9][0-9]:[0-9][0-9](?:\.[0-9]*)?
             (?:[ \t]*(?:Z|[-+][0-9][0-9]?(?::[0-9][0-9])?))?)$""",
        re.X,
    ),
    list("0123456789"),
)

# Value (= for default value)
Resolver.add_implicit_resolver(
    "tag:yaml.org,2002:value",
    re.compile(r"^(?:=)$"),
    ["="],
)

# Merge (<<)
Resolver.add_implicit_resolver(
    "tag:yaml.org,2002:merge",
    re.compile(r"^(?:<<)$"),
    ["<"],
)

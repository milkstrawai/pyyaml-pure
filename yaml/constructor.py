"""
YAML constructor - PyYAML compatible.

This module provides constructors that convert YAML nodes
to Python objects.
"""

from __future__ import annotations

import base64
import binascii
import datetime
import re
from typing import TYPE_CHECKING, Any, Callable

from .error import ConstructorError, Mark
from .nodes import MappingNode, Node, ScalarNode, SequenceNode

if TYPE_CHECKING:
    pass


class BaseConstructor:
    """
    Base constructor class.

    Provides basic construction functionality for converting
    YAML nodes to Python objects.
    """

    yaml_constructors: dict[str | None, Callable[..., Any]] = {}
    yaml_multi_constructors: dict[str, Callable[..., Any]] = {}

    def __init__(self) -> None:
        # Use id(node) as keys since Node objects are not hashable
        self.constructed_objects: dict[int, Any] = {}
        self.recursive_objects: dict[int, None] = {}
        self.state_generators: list[Any] = []
        self.deep_construct = False

    def check_data(self) -> bool:
        """Check if more data is available."""
        # Subclasses override to check for more documents
        return False

    def check_state_key(self, key: str) -> None:
        """Check if a state key is valid."""
        pass

    def get_data(self) -> Any:
        """Get the next constructed object."""
        # Subclasses override to get documents
        return None

    def get_single_data(self) -> Any:
        """Get a single document's data."""
        # Subclasses override
        return None

    def construct_document(self, node: Node | None) -> Any:
        """Construct a Python object from a document node."""
        if node is None:
            return None

        data = self.construct_object(node, deep=True)
        while self.state_generators:
            state_generators = self.state_generators
            self.state_generators = []
            for generator in state_generators:
                for _dummy in generator:
                    pass

        self.constructed_objects = {}
        self.recursive_objects = {}
        self.deep_construct = False
        return data

    def construct_object(self, node: Node, deep: bool = False) -> Any:
        """
        Construct a Python object from a node.

        Args:
            node: The node to construct.
            deep: Whether to construct nested objects.

        Returns:
            The constructed Python object.
        """
        node_id = id(node)
        if node_id in self.constructed_objects:
            return self.constructed_objects[node_id]

        if deep:
            old_deep = self.deep_construct
            self.deep_construct = True

        if node_id in self.recursive_objects:
            raise ConstructorError(
                None,
                None,
                "found unconstructable recursive node",
                node.start_mark,
            )

        self.recursive_objects[node_id] = None
        constructor: Callable[..., Any] | None = None
        tag_suffix = None

        if node.tag in self.yaml_constructors:
            constructor = self.yaml_constructors[node.tag]
        else:
            for tag_prefix in self.yaml_multi_constructors:
                if node.tag and node.tag.startswith(tag_prefix):
                    tag_suffix = node.tag[len(tag_prefix) :]
                    constructor = self.yaml_multi_constructors[tag_prefix]
                    break
            else:
                if None in self.yaml_constructors:
                    constructor = self.yaml_constructors[None]
                elif isinstance(node, ScalarNode):
                    constructor = self.__class__.construct_scalar
                elif isinstance(node, SequenceNode):
                    constructor = self.__class__.construct_sequence
                elif isinstance(node, MappingNode):
                    constructor = self.__class__.construct_mapping

        if constructor is None:
            raise ConstructorError(
                None,
                None,
                f"could not determine a constructor for the tag {node.tag!r}",
                node.start_mark,
            )

        if tag_suffix is None:
            data = constructor(self, node)
        else:
            data = constructor(self, tag_suffix, node)

        if isinstance(data, type(iter([]))):
            generator = data
            data = next(generator)
            if self.deep_construct:
                for _dummy in generator:
                    pass
            else:
                self.state_generators.append(generator)

        self.constructed_objects[node_id] = data
        del self.recursive_objects[node_id]

        if deep:
            self.deep_construct = old_deep

        return data

    def construct_scalar(self, node: Node) -> str:
        """Construct a scalar value."""
        if not isinstance(node, ScalarNode):
            raise ConstructorError(
                None,
                None,
                f"expected a scalar node, but found {node.id}",
                node.start_mark,
            )
        return node.value

    def construct_sequence(self, node: Node, deep: bool = False) -> list[Any]:
        """Construct a sequence (list)."""
        if not isinstance(node, SequenceNode):
            raise ConstructorError(
                None,
                None,
                f"expected a sequence node, but found {node.id}",
                node.start_mark,
            )
        return [self.construct_object(child, deep=deep) for child in node.value]

    def construct_mapping(self, node: Node, deep: bool = False) -> dict[Any, Any]:
        """Construct a mapping (dict)."""
        if not isinstance(node, MappingNode):
            raise ConstructorError(
                None,
                None,
                f"expected a mapping node, but found {node.id}",
                node.start_mark,
            )

        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, (str, int, float, bool, type(None), tuple)):
                if isinstance(key, list):
                    key = tuple(key)
            value = self.construct_object(value_node, deep=deep)
            mapping[key] = value

        return mapping

    def construct_pairs(self, node: Node, deep: bool = False) -> list[tuple[Any, Any]]:
        """Construct a list of key-value pairs."""
        if not isinstance(node, MappingNode):
            raise ConstructorError(
                None,
                None,
                f"expected a mapping node, but found {node.id}",
                node.start_mark,
            )
        pairs: list[tuple[Any, Any]] = []
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            value = self.construct_object(value_node, deep=deep)
            pairs.append((key, value))
        return pairs

    @classmethod
    def add_constructor(cls, tag: str | None, constructor: Callable[..., Any]) -> None:
        """Add a constructor for a specific tag."""
        if not hasattr(cls, "yaml_constructors") or cls.yaml_constructors is BaseConstructor.yaml_constructors:
            cls.yaml_constructors = cls.yaml_constructors.copy()
        cls.yaml_constructors[tag] = constructor

    @classmethod
    def add_multi_constructor(cls, tag_prefix: str, multi_constructor: Callable[..., Any]) -> None:
        """Add a multi-constructor for a tag prefix."""
        if not hasattr(cls, "yaml_multi_constructors") or cls.yaml_multi_constructors is BaseConstructor.yaml_multi_constructors:
            cls.yaml_multi_constructors = cls.yaml_multi_constructors.copy()
        cls.yaml_multi_constructors[tag_prefix] = multi_constructor


class SafeConstructor(BaseConstructor):
    """
    Safe constructor that only allows basic Python types.

    This is the default constructor for safe_load().
    """

    def construct_scalar(self, node: Node) -> Any:
        if isinstance(node, MappingNode):
            for key_node, value_node in node.value:
                if key_node.tag == "tag:yaml.org,2002:value":
                    return self.construct_scalar(value_node)
        return super().construct_scalar(node)

    def flatten_mapping(self, node: MappingNode) -> None:
        """Flatten merge keys in a mapping."""
        merge: list[tuple[Node, Node]] = []
        index = 0

        while index < len(node.value):
            key_node, value_node = node.value[index]

            if key_node.tag == "tag:yaml.org,2002:merge":
                del node.value[index]
                if isinstance(value_node, MappingNode):
                    self.flatten_mapping(value_node)
                    merge.extend(value_node.value)
                elif isinstance(value_node, SequenceNode):
                    submerge: list[tuple[Node, Node]] = []
                    for subnode in value_node.value:
                        if not isinstance(subnode, MappingNode):
                            raise ConstructorError(
                                "while constructing a mapping",
                                node.start_mark,
                                f"expected a mapping for merging, but found {subnode.id}",
                                subnode.start_mark,
                            )
                        self.flatten_mapping(subnode)
                        submerge.append(subnode.value)
                    submerge.reverse()
                    for value in submerge:
                        merge.extend(value)
                else:
                    raise ConstructorError(
                        "while constructing a mapping",
                        node.start_mark,
                        f"expected a mapping or list of mappings for merging, but found {value_node.id}",
                        value_node.start_mark,
                    )
            elif key_node.tag == "tag:yaml.org,2002:value":
                key_node.tag = "tag:yaml.org,2002:str"
                index += 1
            else:
                index += 1

        if merge:
            node.value = merge + node.value

    def construct_mapping(self, node: Node, deep: bool = False) -> dict[Any, Any]:
        if isinstance(node, MappingNode):
            self.flatten_mapping(node)
        return super().construct_mapping(node, deep=deep)

    def construct_yaml_null(self, node: Node) -> None:
        self.construct_scalar(node)
        return None

    def construct_yaml_bool(self, node: Node) -> bool:
        value = self.construct_scalar(node)
        return value.lower() in ("yes", "true", "on", "1")

    def construct_yaml_int(self, node: Node) -> int:
        value = self.construct_scalar(node)
        value = value.replace("_", "")

        sign = 1
        if value[0] == "-":
            sign = -1
            value = value[1:]
        elif value[0] == "+":
            value = value[1:]

        if value == "0":
            return 0
        elif value.startswith("0b"):
            return sign * int(value[2:], 2)
        elif value.startswith("0x"):
            return sign * int(value[2:], 16)
        elif value.startswith("0o"):
            return sign * int(value[2:], 8)
        elif value[0] == "0":
            return sign * int(value, 8)
        elif ":" in value:
            digits = [int(part) for part in value.split(":")]
            digits.reverse()
            base = 1
            result = 0
            for digit in digits:
                result += digit * base
                base *= 60
            return sign * result
        else:
            return sign * int(value)

    def construct_yaml_float(self, node: Node) -> float:
        value = self.construct_scalar(node)
        value = value.replace("_", "").lower()

        sign = 1
        if value[0] == "-":
            sign = -1
            value = value[1:]
        elif value[0] == "+":
            value = value[1:]

        if value == ".inf":
            return sign * float("inf")
        elif value == ".nan":
            return float("nan")
        elif ":" in value:
            digits = [float(part) for part in value.split(":")]
            digits.reverse()
            base = 1
            result = 0.0
            for digit in digits:
                result += digit * base
                base *= 60
            return sign * result
        else:
            return sign * float(value)

    def construct_yaml_binary(self, node: Node) -> bytes:
        try:
            value = self.construct_scalar(node)
            return base64.b64decode(value.encode("ascii"))
        except (ValueError, binascii.Error) as exc:
            raise ConstructorError(
                None,
                None,
                f"failed to decode base64 data: {exc}",
                node.start_mark,
            ) from exc

    timestamp_regexp = re.compile(
        r"""^(?P<year>[0-9][0-9][0-9][0-9])
            -(?P<month>[0-9][0-9]?)
            -(?P<day>[0-9][0-9]?)
            (?:(?:[Tt]|[ \t]+)
            (?P<hour>[0-9][0-9]?)
            :(?P<minute>[0-9][0-9])
            :(?P<second>[0-9][0-9])
            (?:\.(?P<fraction>[0-9]*))?
            (?:[ \t]*(?P<tz>Z|(?P<tz_sign>[-+])(?P<tz_hour>[0-9][0-9]?)
            (?::(?P<tz_minute>[0-9][0-9]))?))?)?$""",
        re.X,
    )

    def construct_yaml_timestamp(self, node: Node) -> datetime.datetime | datetime.date:
        value = self.construct_scalar(node)
        match = self.timestamp_regexp.match(value)
        if match is None:
            raise ConstructorError(
                None,
                None,
                f"could not parse timestamp: {value!r}",
                node.start_mark,
            )

        values = match.groupdict()
        year = int(values["year"])
        month = int(values["month"])
        day = int(values["day"])

        if values["hour"] is None:
            return datetime.date(year, month, day)

        hour = int(values["hour"])
        minute = int(values["minute"])
        second = int(values["second"])
        fraction = 0
        if values["fraction"]:
            fraction = int(values["fraction"][:6].ljust(6, "0"))

        delta = None
        if values["tz_sign"]:
            tz_hour = int(values["tz_hour"])
            tz_minute = int(values["tz_minute"] or 0)
            delta = datetime.timedelta(hours=tz_hour, minutes=tz_minute)
            if values["tz_sign"] == "-":
                delta = -delta
        elif values["tz"] == "Z":
            delta = datetime.timedelta(0)

        dt = datetime.datetime(year, month, day, hour, minute, second, fraction)
        if delta is not None:
            dt -= delta

        return dt

    def construct_yaml_omap(self, node: Node) -> list[tuple[Any, Any]]:
        # !!omap is a sequence of single-key mappings
        if not isinstance(node, SequenceNode):
            raise ConstructorError(
                None,
                None,
                f"expected a sequence node for omap, but found {node.id}",
                node.start_mark,
            )
        omap: list[tuple[Any, Any]] = []
        for subnode in node.value:
            if not isinstance(subnode, MappingNode):
                raise ConstructorError(
                    None,
                    None,
                    f"expected a mapping for omap entry, but found {subnode.id}",
                    subnode.start_mark,
                )
            if len(subnode.value) != 1:
                raise ConstructorError(
                    None,
                    None,
                    "expected a single-key mapping for omap entry",
                    subnode.start_mark,
                )
            key_node, value_node = subnode.value[0]
            key = self.construct_object(key_node, deep=True)
            value = self.construct_object(value_node, deep=True)
            omap.append((key, value))
        return omap

    def construct_yaml_pairs(self, node: Node) -> list[tuple[Any, Any]]:
        # !!pairs is a sequence of single-key mappings (like !!omap but allows duplicates)
        if not isinstance(node, SequenceNode):
            raise ConstructorError(
                None,
                None,
                f"expected a sequence node for pairs, but found {node.id}",
                node.start_mark,
            )
        pairs: list[tuple[Any, Any]] = []
        for subnode in node.value:
            if not isinstance(subnode, MappingNode):
                raise ConstructorError(
                    None,
                    None,
                    f"expected a mapping for pairs entry, but found {subnode.id}",
                    subnode.start_mark,
                )
            if len(subnode.value) != 1:
                raise ConstructorError(
                    None,
                    None,
                    "expected a single-key mapping for pairs entry",
                    subnode.start_mark,
                )
            key_node, value_node = subnode.value[0]
            key = self.construct_object(key_node, deep=True)
            value = self.construct_object(value_node, deep=True)
            pairs.append((key, value))
        return pairs

    def construct_yaml_set(self, node: Node) -> set[Any]:
        data = self.construct_mapping(node)
        return set(data.keys())

    def construct_yaml_str(self, node: Node) -> str:
        return self.construct_scalar(node)

    def construct_yaml_seq(self, node: Node) -> list[Any]:
        return self.construct_sequence(node, deep=True)

    def construct_yaml_map(self, node: Node) -> dict[Any, Any]:
        return self.construct_mapping(node, deep=True)

    def construct_undefined(self, node: Node) -> None:
        raise ConstructorError(
            None,
            None,
            f"could not determine a constructor for the tag {node.tag!r}",
            node.start_mark,
        )


SafeConstructor.add_constructor("tag:yaml.org,2002:null", SafeConstructor.construct_yaml_null)
SafeConstructor.add_constructor("tag:yaml.org,2002:bool", SafeConstructor.construct_yaml_bool)
SafeConstructor.add_constructor("tag:yaml.org,2002:int", SafeConstructor.construct_yaml_int)
SafeConstructor.add_constructor("tag:yaml.org,2002:float", SafeConstructor.construct_yaml_float)
SafeConstructor.add_constructor("tag:yaml.org,2002:binary", SafeConstructor.construct_yaml_binary)
SafeConstructor.add_constructor("tag:yaml.org,2002:timestamp", SafeConstructor.construct_yaml_timestamp)
SafeConstructor.add_constructor("tag:yaml.org,2002:omap", SafeConstructor.construct_yaml_omap)
SafeConstructor.add_constructor("tag:yaml.org,2002:pairs", SafeConstructor.construct_yaml_pairs)
SafeConstructor.add_constructor("tag:yaml.org,2002:set", SafeConstructor.construct_yaml_set)
SafeConstructor.add_constructor("tag:yaml.org,2002:str", SafeConstructor.construct_yaml_str)
SafeConstructor.add_constructor("tag:yaml.org,2002:seq", SafeConstructor.construct_yaml_seq)
SafeConstructor.add_constructor("tag:yaml.org,2002:map", SafeConstructor.construct_yaml_map)
SafeConstructor.add_constructor(None, SafeConstructor.construct_undefined)


class FullConstructor(SafeConstructor):
    """
    Full constructor that allows more types.

    This is the constructor for full_load().
    """

    pass


class UnsafeConstructor(FullConstructor):
    """
    Unsafe constructor that allows arbitrary Python objects.

    This is the constructor for unsafe_load().
    """

    pass


# Alias for compatibility
Constructor = UnsafeConstructor

"""
YAML representer - PyYAML compatible.

This module provides representers that convert Python objects
to YAML nodes.
"""

from __future__ import annotations

import datetime
import base64
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Callable

from .error import RepresenterError
from .nodes import MappingNode, Node, ScalarNode, SequenceNode

if TYPE_CHECKING:
    pass


class BaseRepresenter:
    """
    Base representer class.

    Provides basic representation functionality for converting
    Python objects to YAML nodes.
    """

    yaml_representers: dict[type, Callable[..., Node]] = {}
    yaml_multi_representers: dict[type, Callable[..., Node]] = {}

    default_style: str | None = None
    default_flow_style: bool | None = False

    def __init__(
        self,
        default_style: str | None = None,
        default_flow_style: bool | None = False,
        sort_keys: bool = True,
    ) -> None:
        self.default_style = default_style
        self.default_flow_style = default_flow_style
        self.sort_keys = sort_keys
        self.represented_objects: dict[int, Node] = {}
        self.object_keeper: list[Any] = []
        self.alias_key: int | None = None

    def represent(self, data: Any) -> Node:
        """Represent a Python object as a node."""
        node = self.represent_data(data)
        self.represented_objects = {}
        self.object_keeper = []
        self.alias_key = None
        return node

    def represent_data(self, data: Any) -> Node:
        """Represent data as a node, handling aliases."""
        if self.ignore_aliases(data):
            self.alias_key = None
        else:
            self.alias_key = id(data)

        if self.alias_key is not None:
            if self.alias_key in self.represented_objects:
                node = self.represented_objects[self.alias_key]
                return node
            self.object_keeper.append(data)

        data_types = type(data).__mro__
        if data_types[0] in self.yaml_representers:
            node = self.yaml_representers[data_types[0]](self, data)
        else:
            for data_type in data_types:
                if data_type in self.yaml_multi_representers:
                    node = self.yaml_multi_representers[data_type](self, data)
                    break
            else:
                if None in self.yaml_multi_representers:
                    node = self.yaml_multi_representers[None](self, data)
                elif None in self.yaml_representers:
                    node = self.yaml_representers[None](self, data)
                else:
                    node = ScalarNode(tag=None, value=str(data))

        if self.alias_key is not None:
            self.represented_objects[self.alias_key] = node

        return node

    def ignore_aliases(self, data: Any) -> bool:
        """Check if aliases should be ignored for this data."""
        return data is None or isinstance(data, (str, bytes, bool, int, float))

    def represent_scalar(
        self,
        tag: str,
        value: str,
        style: str | None = None,
    ) -> ScalarNode:
        """Represent a scalar value."""
        if style is None:
            style = self.default_style
        node = ScalarNode(tag=tag, value=value, style=style)
        if self.alias_key is not None:
            self.represented_objects[self.alias_key] = node
        return node

    def represent_sequence(
        self,
        tag: str,
        sequence: Any,
        flow_style: bool | None = None,
    ) -> SequenceNode:
        """Represent a sequence."""
        value: list[Node] = []
        node = SequenceNode(tag=tag, value=value, flow_style=flow_style)
        if self.alias_key is not None:
            self.represented_objects[self.alias_key] = node

        best_style = True
        for item in sequence:
            node_item = self.represent_data(item)
            if not (isinstance(node_item, ScalarNode) and node_item.style is None):
                best_style = False
            value.append(node_item)

        if flow_style is None:
            if self.default_flow_style is not None:
                node.flow_style = self.default_flow_style
            else:
                node.flow_style = best_style

        return node

    def represent_mapping(
        self,
        tag: str,
        mapping: Any,
        flow_style: bool | None = None,
    ) -> MappingNode:
        """Represent a mapping."""
        value: list[tuple[Node, Node]] = []
        node = MappingNode(tag=tag, value=value, flow_style=flow_style)
        if self.alias_key is not None:
            self.represented_objects[self.alias_key] = node

        best_style = True
        if hasattr(mapping, "items"):
            mapping_items = list(mapping.items())
            if self.sort_keys:
                try:
                    mapping_items.sort(key=lambda x: x[0])
                except TypeError:
                    pass
        else:
            mapping_items = mapping

        for item_key, item_value in mapping_items:
            node_key = self.represent_data(item_key)
            node_value = self.represent_data(item_value)
            if not (isinstance(node_key, ScalarNode) and node_key.style is None):
                best_style = False
            if not (isinstance(node_value, ScalarNode) and node_value.style is None):
                best_style = False
            value.append((node_key, node_value))

        if flow_style is None:
            if self.default_flow_style is not None:
                node.flow_style = self.default_flow_style
            else:
                node.flow_style = best_style

        return node

    @classmethod
    def add_representer(cls, data_type: type, representer: Callable[..., Node]) -> None:
        """Add a representer for a specific type."""
        if not hasattr(cls, "yaml_representers") or cls.yaml_representers is BaseRepresenter.yaml_representers:
            cls.yaml_representers = cls.yaml_representers.copy()
        cls.yaml_representers[data_type] = representer

    @classmethod
    def add_multi_representer(cls, data_type: type, representer: Callable[..., Node]) -> None:
        """Add a multi-representer for a type and its subclasses."""
        if not hasattr(cls, "yaml_multi_representers") or cls.yaml_multi_representers is BaseRepresenter.yaml_multi_representers:
            cls.yaml_multi_representers = cls.yaml_multi_representers.copy()
        cls.yaml_multi_representers[data_type] = representer


class SafeRepresenter(BaseRepresenter):
    """
    Safe representer for basic Python types.
    """

    def represent_none(self, data: None) -> ScalarNode:
        return self.represent_scalar("tag:yaml.org,2002:null", "null")

    def represent_str(self, data: str) -> ScalarNode:
        return self.represent_scalar("tag:yaml.org,2002:str", data)

    def represent_bytes(self, data: bytes) -> ScalarNode:
        data_str = base64.b64encode(data).decode("ascii")
        return self.represent_scalar("tag:yaml.org,2002:binary", data_str, style="|")

    def represent_bool(self, data: bool) -> ScalarNode:
        value = "true" if data else "false"
        return self.represent_scalar("tag:yaml.org,2002:bool", value)

    def represent_int(self, data: int) -> ScalarNode:
        return self.represent_scalar("tag:yaml.org,2002:int", str(data))

    def represent_float(self, data: float) -> ScalarNode:
        if data != data:  # NaN
            value = ".nan"
        elif data == float("inf"):
            value = ".inf"
        elif data == float("-inf"):
            value = "-.inf"
        else:
            value = repr(data).lower()
            if "." not in value and "e" not in value:
                value += ".0"
        return self.represent_scalar("tag:yaml.org,2002:float", value)

    def represent_list(self, data: list[Any]) -> SequenceNode:
        return self.represent_sequence("tag:yaml.org,2002:seq", data)

    def represent_dict(self, data: dict[Any, Any]) -> MappingNode:
        return self.represent_mapping("tag:yaml.org,2002:map", data)

    def represent_set(self, data: set[Any]) -> MappingNode:
        value: dict[Any, None] = {}
        for key in data:
            value[key] = None
        return self.represent_mapping("tag:yaml.org,2002:set", value)

    def represent_date(self, data: datetime.date) -> ScalarNode:
        value = data.isoformat()
        return self.represent_scalar("tag:yaml.org,2002:timestamp", value)

    def represent_datetime(self, data: datetime.datetime) -> ScalarNode:
        value = data.isoformat(" ")
        return self.represent_scalar("tag:yaml.org,2002:timestamp", value)

    def represent_tuple(self, data: tuple[Any, ...]) -> SequenceNode:
        return self.represent_sequence("tag:yaml.org,2002:seq", data)

    def represent_ordered_dict(self, data: OrderedDict[Any, Any]) -> SequenceNode:
        pairs: list[dict[Any, Any]] = []
        for key, value in data.items():
            pairs.append({key: value})
        return self.represent_sequence("tag:yaml.org,2002:omap", pairs)

    def represent_undefined(self, data: Any) -> Node:
        raise RepresenterError(f"cannot represent an object: {data!r}")


SafeRepresenter.add_representer(type(None), SafeRepresenter.represent_none)
SafeRepresenter.add_representer(str, SafeRepresenter.represent_str)
SafeRepresenter.add_representer(bytes, SafeRepresenter.represent_bytes)
SafeRepresenter.add_representer(bool, SafeRepresenter.represent_bool)
SafeRepresenter.add_representer(int, SafeRepresenter.represent_int)
SafeRepresenter.add_representer(float, SafeRepresenter.represent_float)
SafeRepresenter.add_representer(list, SafeRepresenter.represent_list)
SafeRepresenter.add_representer(dict, SafeRepresenter.represent_dict)
SafeRepresenter.add_representer(set, SafeRepresenter.represent_set)
SafeRepresenter.add_representer(frozenset, SafeRepresenter.represent_set)
SafeRepresenter.add_representer(datetime.date, SafeRepresenter.represent_date)
SafeRepresenter.add_representer(datetime.datetime, SafeRepresenter.represent_datetime)
SafeRepresenter.add_representer(tuple, SafeRepresenter.represent_tuple)
SafeRepresenter.add_representer(OrderedDict, SafeRepresenter.represent_ordered_dict)
SafeRepresenter.add_representer(None, SafeRepresenter.represent_undefined)


class Representer(SafeRepresenter):
    """
    Full representer that can represent more Python types.
    """

    pass

"""
YAML event classes - PyYAML compatible.

This module provides event classes that match PyYAML's events.py interface.
Events are produced by the parser and consumed by the composer/emitter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .error import Mark


@dataclass
class Event:
    """Base class for all YAML events."""

    start_mark: Mark | None = field(default=None, repr=False)
    end_mark: Mark | None = field(default=None, repr=False)


# Stream events


@dataclass
class StreamStartEvent(Event):
    """Event indicating the start of a YAML stream."""

    encoding: str | None = None


@dataclass
class StreamEndEvent(Event):
    """Event indicating the end of a YAML stream."""

    pass


# Document events


@dataclass
class DocumentStartEvent(Event):
    """Event for document start."""

    explicit: bool = False
    version: tuple[int, int] | None = None
    tags: dict[str, str] | None = None


@dataclass
class DocumentEndEvent(Event):
    """Event for document end."""

    explicit: bool = False


# Alias event


@dataclass
class AliasEvent(Event):
    """Event for alias (*anchor)."""

    anchor: str | None = None


# Node events


@dataclass
class NodeEvent(Event):
    """Base class for node events."""

    anchor: str | None = None


@dataclass
class CollectionStartEvent(NodeEvent):
    """Base class for collection start events."""

    tag: str | None = None
    implicit: bool = False
    flow_style: bool | None = None


@dataclass
class CollectionEndEvent(Event):
    """Base class for collection end events."""

    pass


# Scalar event


@dataclass
class ScalarEvent(NodeEvent):
    """Event for scalar values."""

    tag: str | None = None
    implicit: tuple[bool, bool] = (False, False)  # (plain, quoted)
    value: str = ""
    style: str | None = None  # None, '', '"', '|', '>'


# Sequence events


@dataclass
class SequenceStartEvent(CollectionStartEvent):
    """Event for sequence start."""

    pass


@dataclass
class SequenceEndEvent(CollectionEndEvent):
    """Event for sequence end."""

    pass


# Mapping events


@dataclass
class MappingStartEvent(CollectionStartEvent):
    """Event for mapping start."""

    pass


@dataclass
class MappingEndEvent(CollectionEndEvent):
    """Event for mapping end."""

    pass

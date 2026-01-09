"""
YAML token classes - PyYAML compatible.

This module provides token classes that match PyYAML's tokens.py interface.
Tokens are produced by the scanner and consumed by the parser.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .error import Mark


@dataclass
class Token:
    """Base class for all YAML tokens."""

    start_mark: Mark | None = field(default=None, repr=False)
    end_mark: Mark | None = field(default=None, repr=False)

    @property
    def id(self) -> str:
        """Return token identifier for error messages."""
        return f"<{self.__class__.__name__}>"


# Stream tokens


@dataclass
class StreamStartToken(Token):
    """Token indicating the start of a YAML stream."""

    encoding: str | None = None

    @property
    def id(self) -> str:
        return "<stream start>"


@dataclass
class StreamEndToken(Token):
    """Token indicating the end of a YAML stream."""

    @property
    def id(self) -> str:
        return "<stream end>"


# Directive tokens


@dataclass
class DirectiveToken(Token):
    """Token for YAML directives (%YAML, %TAG)."""

    name: str | None = None
    value: tuple[int, int] | tuple[str, str] | None = None

    @property
    def id(self) -> str:
        return "<directive>"


# Document tokens


@dataclass
class DocumentStartToken(Token):
    """Token for document start marker (---)."""

    @property
    def id(self) -> str:
        return "<document start>"


@dataclass
class DocumentEndToken(Token):
    """Token for document end marker (...)."""

    @property
    def id(self) -> str:
        return "<document end>"


# Block structure tokens


@dataclass
class BlockSequenceStartToken(Token):
    """Token indicating the start of a block sequence."""

    @property
    def id(self) -> str:
        return "<block sequence start>"


@dataclass
class BlockMappingStartToken(Token):
    """Token indicating the start of a block mapping."""

    @property
    def id(self) -> str:
        return "<block mapping start>"


@dataclass
class BlockEndToken(Token):
    """Token indicating the end of a block structure."""

    @property
    def id(self) -> str:
        return "<block end>"


# Flow structure tokens


@dataclass
class FlowSequenceStartToken(Token):
    """Token for flow sequence start ([)."""

    @property
    def id(self) -> str:
        return "["


@dataclass
class FlowSequenceEndToken(Token):
    """Token for flow sequence end (])."""

    @property
    def id(self) -> str:
        return "]"


@dataclass
class FlowMappingStartToken(Token):
    """Token for flow mapping start ({)."""

    @property
    def id(self) -> str:
        return "{"


@dataclass
class FlowMappingEndToken(Token):
    """Token for flow mapping end (})."""

    @property
    def id(self) -> str:
        return "}"


# Entry tokens


@dataclass
class BlockEntryToken(Token):
    """Token for block sequence entry (-)."""

    @property
    def id(self) -> str:
        return "-"


@dataclass
class FlowEntryToken(Token):
    """Token for flow entry separator (,)."""

    @property
    def id(self) -> str:
        return ","


# Key/Value tokens


@dataclass
class KeyToken(Token):
    """Token for explicit key indicator (?)."""

    @property
    def id(self) -> str:
        return "?"


@dataclass
class ValueToken(Token):
    """Token for value indicator (:)."""

    @property
    def id(self) -> str:
        return ":"


# Alias and anchor tokens


@dataclass
class AliasToken(Token):
    """Token for alias (*anchor)."""

    value: str | None = None

    @property
    def id(self) -> str:
        return "<alias>"


@dataclass
class AnchorToken(Token):
    """Token for anchor (&anchor)."""

    value: str | None = None

    @property
    def id(self) -> str:
        return "<anchor>"


# Tag token


@dataclass
class TagToken(Token):
    """Token for tag (!tag or !!type)."""

    value: tuple[str | None, str] | None = None

    @property
    def id(self) -> str:
        return "<tag>"


# Scalar token


@dataclass
class ScalarToken(Token):
    """Token for scalar values."""

    value: str = ""
    plain: bool = True
    style: str | None = None  # None, '', '"', '|', '>'

    @property
    def id(self) -> str:
        return "<scalar>"

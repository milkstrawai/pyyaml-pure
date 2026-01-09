"""
YAML dumper classes - PyYAML compatible.

This module provides dumper classes that combine representation,
serialization, and emission to dump Python objects to YAML.
"""

from __future__ import annotations

from typing import IO, Any

from .emitter import Emitter
from .representer import BaseRepresenter, Representer, SafeRepresenter
from .resolver import BaseResolver, Resolver
from .serializer import Serializer


class BaseDumper(Emitter, Serializer, BaseRepresenter, BaseResolver):
    """
    Base dumper class.

    Combines emission, serialization, representation, and resolution.
    """

    def __init__(
        self,
        stream: IO[str] | None = None,
        default_style: str | None = None,
        default_flow_style: bool | None = False,
        canonical: bool = False,
        indent: int | None = None,
        width: int | None = None,
        allow_unicode: bool = True,
        line_break: str | None = None,
        encoding: str | None = None,
        explicit_start: bool | None = None,
        explicit_end: bool | None = None,
        version: tuple[int, int] | None = None,
        tags: dict[str, str] | None = None,
        sort_keys: bool = True,
    ) -> None:
        Emitter.__init__(
            self,
            stream=stream,
            canonical=canonical,
            indent=indent,
            width=width,
            allow_unicode=allow_unicode,
            line_break=line_break,
        )
        Serializer.__init__(
            self,
            encoding=encoding,
            explicit_start=explicit_start,
            explicit_end=explicit_end,
            version=version,
            tags=tags,
        )
        BaseRepresenter.__init__(
            self,
            default_style=default_style,
            default_flow_style=default_flow_style,
            sort_keys=sort_keys,
        )
        BaseResolver.__init__(self)

    def emit(self, event: Any) -> None:
        """Emit an event through the emitter."""
        return Emitter.emit(self, event)

    def descend_resolver(self, parent: Any, index: Any) -> None:
        """Descend into resolver context."""
        return BaseResolver.descend_resolver(self, parent, index)

    def ascend_resolver(self) -> None:
        """Ascend from resolver context."""
        return BaseResolver.ascend_resolver(self)

    def resolve(self, kind: type, value: Any, implicit: Any) -> str:
        """Resolve a tag."""
        return BaseResolver.resolve(self, kind, value, implicit)


class SafeDumper(Emitter, Serializer, SafeRepresenter, Resolver):
    """
    Safe dumper that only produces basic Python types.

    This is the dumper used by safe_dump().
    """

    def __init__(
        self,
        stream: IO[str] | None = None,
        default_style: str | None = None,
        default_flow_style: bool | None = False,
        canonical: bool = False,
        indent: int | None = None,
        width: int | None = None,
        allow_unicode: bool = True,
        line_break: str | None = None,
        encoding: str | None = None,
        explicit_start: bool | None = None,
        explicit_end: bool | None = None,
        version: tuple[int, int] | None = None,
        tags: dict[str, str] | None = None,
        sort_keys: bool = True,
    ) -> None:
        Emitter.__init__(
            self,
            stream=stream,
            canonical=canonical,
            indent=indent,
            width=width,
            allow_unicode=allow_unicode,
            line_break=line_break,
        )
        Serializer.__init__(
            self,
            encoding=encoding,
            explicit_start=explicit_start,
            explicit_end=explicit_end,
            version=version,
            tags=tags,
        )
        SafeRepresenter.__init__(
            self,
            default_style=default_style,
            default_flow_style=default_flow_style,
            sort_keys=sort_keys,
        )
        Resolver.__init__(self)

    def emit(self, event: Any) -> None:
        """Emit an event through the emitter."""
        return Emitter.emit(self, event)

    def descend_resolver(self, parent: Any, index: Any) -> None:
        """Descend into resolver context."""
        return Resolver.descend_resolver(self, parent, index)

    def ascend_resolver(self) -> None:
        """Ascend from resolver context."""
        return Resolver.ascend_resolver(self)

    def resolve(self, kind: type, value: Any, implicit: Any) -> str:
        """Resolve a tag."""
        return Resolver.resolve(self, kind, value, implicit)


class Dumper(Emitter, Serializer, Representer, Resolver):
    """
    Full dumper that can represent all Python types.

    This is the dumper used by dump().
    """

    def __init__(
        self,
        stream: IO[str] | None = None,
        default_style: str | None = None,
        default_flow_style: bool | None = False,
        canonical: bool = False,
        indent: int | None = None,
        width: int | None = None,
        allow_unicode: bool = True,
        line_break: str | None = None,
        encoding: str | None = None,
        explicit_start: bool | None = None,
        explicit_end: bool | None = None,
        version: tuple[int, int] | None = None,
        tags: dict[str, str] | None = None,
        sort_keys: bool = True,
    ) -> None:
        Emitter.__init__(
            self,
            stream=stream,
            canonical=canonical,
            indent=indent,
            width=width,
            allow_unicode=allow_unicode,
            line_break=line_break,
        )
        Serializer.__init__(
            self,
            encoding=encoding,
            explicit_start=explicit_start,
            explicit_end=explicit_end,
            version=version,
            tags=tags,
        )
        Representer.__init__(
            self,
            default_style=default_style,
            default_flow_style=default_flow_style,
            sort_keys=sort_keys,
        )
        Resolver.__init__(self)

    def emit(self, event: Any) -> None:
        """Emit an event through the emitter."""
        return Emitter.emit(self, event)

    def descend_resolver(self, parent: Any, index: Any) -> None:
        """Descend into resolver context."""
        return Resolver.descend_resolver(self, parent, index)

    def ascend_resolver(self) -> None:
        """Ascend from resolver context."""
        return Resolver.ascend_resolver(self)

    def resolve(self, kind: type, value: Any, implicit: Any) -> str:
        """Resolve a tag."""
        return Resolver.resolve(self, kind, value, implicit)

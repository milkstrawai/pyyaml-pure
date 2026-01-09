"""
pyyaml-pure - A pure Python YAML 1.2 parser and emitter.

This package provides a drop-in replacement for PyYAML with full YAML 1.2
compliance and optional comment preservation.

Usage:
    import yaml

    data = yaml.safe_load("key: value")
    output = yaml.safe_dump(data)
"""

from __future__ import annotations

from io import StringIO
from typing import IO, Any, Iterator, Type

from .constructor import (
    BaseConstructor,
    FullConstructor,
    SafeConstructor,
    UnsafeConstructor,
)
from .dumper import BaseDumper, Dumper, SafeDumper
from .emitter import Emitter
from .error import (
    ComposerError,
    ConstructorError,
    EmitterError,
    Mark,
    MarkedYAMLError,
    ParserError,
    ReaderError,
    RepresenterError,
    ScannerError,
    SerializerError,
    YAMLError,
)
from .events import (
    AliasEvent,
    DocumentEndEvent,
    DocumentStartEvent,
    Event,
    MappingEndEvent,
    MappingStartEvent,
    ScalarEvent,
    SequenceEndEvent,
    SequenceStartEvent,
    StreamEndEvent,
    StreamStartEvent,
)
from .loader import BaseLoader, FullLoader, Loader, SafeLoader, UnsafeLoader
from .nodes import MappingNode, Node, ScalarNode, SequenceNode
from .reader import Reader
from .representer import BaseRepresenter, Representer, SafeRepresenter
from .resolver import BaseResolver, Resolver
from .scanner import Scanner, scan
from .serializer import Serializer
from .roundtrip import (
    CommentedMap,
    CommentedSeq,
    RoundTripLoader,
    RoundTripDumper,
    round_trip_load,
    round_trip_load_all,
    round_trip_dump,
    round_trip_dump_all,
)
from ._comments import Comment, CommentGroup
from .tokens import (
    AliasToken,
    AnchorToken,
    BlockEndToken,
    BlockEntryToken,
    BlockMappingStartToken,
    BlockSequenceStartToken,
    DirectiveToken,
    DocumentEndToken,
    DocumentStartToken,
    FlowEntryToken,
    FlowMappingEndToken,
    FlowMappingStartToken,
    FlowSequenceEndToken,
    FlowSequenceStartToken,
    KeyToken,
    ScalarToken,
    StreamEndToken,
    StreamStartToken,
    TagToken,
    Token,
    ValueToken,
)

__version__ = "0.1.0"

__all__ = [
    # Version
    "__version__",
    # Loading functions
    "safe_load",
    "safe_load_all",
    "full_load",
    "full_load_all",
    "unsafe_load",
    "unsafe_load_all",
    "load",
    "load_all",
    # Dumping functions
    "safe_dump",
    "safe_dump_all",
    "dump",
    "dump_all",
    # Round-trip functions (comment preservation)
    "round_trip_load",
    "round_trip_load_all",
    "round_trip_dump",
    "round_trip_dump_all",
    # Comment classes
    "Comment",
    "CommentGroup",
    "CommentedMap",
    "CommentedSeq",
    "RoundTripLoader",
    "RoundTripDumper",
    # Low-level functions
    "scan",
    "parse",
    "compose",
    "compose_all",
    "emit",
    "serialize",
    "serialize_all",
    # Classes - Loaders
    "BaseLoader",
    "SafeLoader",
    "FullLoader",
    "UnsafeLoader",
    "Loader",
    # Classes - Dumpers
    "BaseDumper",
    "SafeDumper",
    "Dumper",
    # Classes - Constructors
    "BaseConstructor",
    "SafeConstructor",
    "FullConstructor",
    "UnsafeConstructor",
    # Classes - Representers
    "BaseRepresenter",
    "SafeRepresenter",
    "Representer",
    # Classes - Resolvers
    "BaseResolver",
    "Resolver",
    # Classes - Other
    "Reader",
    "Scanner",
    "Emitter",
    "Serializer",
    # Node classes
    "Node",
    "ScalarNode",
    "SequenceNode",
    "MappingNode",
    # Event classes
    "Event",
    "StreamStartEvent",
    "StreamEndEvent",
    "DocumentStartEvent",
    "DocumentEndEvent",
    "MappingStartEvent",
    "MappingEndEvent",
    "SequenceStartEvent",
    "SequenceEndEvent",
    "ScalarEvent",
    "AliasEvent",
    # Token classes
    "Token",
    "StreamStartToken",
    "StreamEndToken",
    "DirectiveToken",
    "DocumentStartToken",
    "DocumentEndToken",
    "BlockSequenceStartToken",
    "BlockMappingStartToken",
    "BlockEndToken",
    "FlowSequenceStartToken",
    "FlowSequenceEndToken",
    "FlowMappingStartToken",
    "FlowMappingEndToken",
    "KeyToken",
    "ValueToken",
    "BlockEntryToken",
    "FlowEntryToken",
    "AliasToken",
    "AnchorToken",
    "TagToken",
    "ScalarToken",
    # Errors
    "YAMLError",
    "MarkedYAMLError",
    "ReaderError",
    "ScannerError",
    "ParserError",
    "ComposerError",
    "ConstructorError",
    "EmitterError",
    "SerializerError",
    "RepresenterError",
    # Other
    "Mark",
    # Custom representer/constructor registration
    "add_representer",
    "add_safe_representer",
    "add_constructor",
    "add_safe_constructor",
    "add_multi_constructor",
    "add_safe_multi_constructor",
    "add_implicit_resolver",
]


# =============================================================================
# Loading Functions
# =============================================================================


def safe_load(
    stream: str | bytes | IO[str] | IO[bytes],
    *,
    comments: bool = False,
) -> Any:
    """
    Parse the first YAML document in a stream and produce the corresponding
    Python object. Only basic Python types are produced.

    Args:
        stream: A string, bytes, or file-like object containing YAML.
        comments: If True, preserve comments (returns CommentedMap/CommentedSeq).

    Returns:
        The parsed Python object.
    """
    if comments:
        loader = RoundTripLoader(stream)
    else:
        loader = SafeLoader(stream)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def safe_load_all(
    stream: str | bytes | IO[str] | IO[bytes],
    *,
    comments: bool = False,
) -> Iterator[Any]:
    """
    Parse all YAML documents in a stream and produce corresponding Python objects.
    Only basic Python types are produced.

    Args:
        stream: A string, bytes, or file-like object containing YAML.
        comments: If True, preserve comments (returns CommentedMap/CommentedSeq).

    Yields:
        Parsed Python objects for each document.
    """
    if comments:
        loader = RoundTripLoader(stream)
    else:
        loader = SafeLoader(stream)
    try:
        while loader.check_data():
            yield loader.get_data()
    finally:
        loader.dispose()


def full_load(stream: str | bytes | IO[str] | IO[bytes]) -> Any:
    """
    Parse the first YAML document in a stream and produce the corresponding
    Python object. Allows more Python types than safe_load.

    Args:
        stream: A string, bytes, or file-like object containing YAML.

    Returns:
        The parsed Python object.
    """
    loader = FullLoader(stream)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def full_load_all(stream: str | bytes | IO[str] | IO[bytes]) -> Iterator[Any]:
    """
    Parse all YAML documents in a stream and produce corresponding Python objects.
    Allows more Python types than safe_load_all.

    Args:
        stream: A string, bytes, or file-like object containing YAML.

    Yields:
        Parsed Python objects for each document.
    """
    loader = FullLoader(stream)
    try:
        while loader.check_data():
            yield loader.get_data()
    finally:
        loader.dispose()


def unsafe_load(stream: str | bytes | IO[str] | IO[bytes]) -> Any:
    """
    Parse the first YAML document in a stream and produce the corresponding
    Python object. Can construct arbitrary Python objects - UNSAFE!

    Args:
        stream: A string, bytes, or file-like object containing YAML.

    Returns:
        The parsed Python object.

    Warning:
        This function can construct arbitrary Python objects. Do not use with
        untrusted input!
    """
    loader = UnsafeLoader(stream)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def unsafe_load_all(stream: str | bytes | IO[str] | IO[bytes]) -> Iterator[Any]:
    """
    Parse all YAML documents in a stream and produce corresponding Python objects.
    Can construct arbitrary Python objects - UNSAFE!

    Args:
        stream: A string, bytes, or file-like object containing YAML.

    Yields:
        Parsed Python objects for each document.

    Warning:
        This function can construct arbitrary Python objects. Do not use with
        untrusted input!
    """
    loader = UnsafeLoader(stream)
    try:
        while loader.check_data():
            yield loader.get_data()
    finally:
        loader.dispose()


def load(
    stream: str | bytes | IO[str] | IO[bytes],
    Loader: Type[BaseLoader] = FullLoader,
) -> Any:
    """
    Parse the first YAML document in a stream and produce the corresponding
    Python object.

    Args:
        stream: A string, bytes, or file-like object containing YAML.
        Loader: The loader class to use. Defaults to FullLoader.

    Returns:
        The parsed Python object.
    """
    loader = Loader(stream)
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def load_all(
    stream: str | bytes | IO[str] | IO[bytes],
    Loader: Type[BaseLoader] = FullLoader,
) -> Iterator[Any]:
    """
    Parse all YAML documents in a stream and produce corresponding Python objects.

    Args:
        stream: A string, bytes, or file-like object containing YAML.
        Loader: The loader class to use. Defaults to FullLoader.

    Yields:
        Parsed Python objects for each document.
    """
    loader = Loader(stream)
    try:
        while loader.check_data():
            yield loader.get_data()
    finally:
        loader.dispose()


# =============================================================================
# Dumping Functions
# =============================================================================


def safe_dump(
    data: Any,
    stream: IO[str] | None = None,
    *,
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
    comments: bool = False,
) -> str | None:
    """
    Serialize a Python object into a YAML stream using only basic types.

    Args:
        data: The Python object to serialize.
        stream: Optional file-like object to write to. If None, returns a string.
        comments: If True, preserve comments from CommentedMap/CommentedSeq.
        **kwargs: Additional formatting options.

    Returns:
        YAML string if stream is None, otherwise None.
    """
    if comments:
        return round_trip_dump(
            data,
            stream=stream,
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
    return dump_all(
        [data],
        stream=stream,
        Dumper=SafeDumper,
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


def safe_dump_all(
    documents: Any,
    stream: IO[str] | None = None,
    *,
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
    comments: bool = False,
) -> str | None:
    """
    Serialize a sequence of Python objects into a YAML stream using only basic types.

    Args:
        documents: Iterable of Python objects to serialize.
        stream: Optional file-like object to write to. If None, returns a string.
        comments: If True, preserve comments from CommentedMap/CommentedSeq.
        **kwargs: Additional formatting options.

    Returns:
        YAML string if stream is None, otherwise None.
    """
    if comments:
        return round_trip_dump_all(
            documents,
            stream=stream,
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
    return dump_all(
        documents,
        stream=stream,
        Dumper=SafeDumper,
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


def dump(
    data: Any,
    stream: IO[str] | None = None,
    Dumper: Type[BaseDumper] = Dumper,
    *,
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
) -> str | None:
    """
    Serialize a Python object into a YAML stream.

    Args:
        data: The Python object to serialize.
        stream: Optional file-like object to write to. If None, returns a string.
        Dumper: The dumper class to use. Defaults to Dumper.
        **kwargs: Additional formatting options.

    Returns:
        YAML string if stream is None, otherwise None.
    """
    return dump_all(
        [data],
        stream=stream,
        Dumper=Dumper,
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


def dump_all(
    documents: Any,
    stream: IO[str] | None = None,
    Dumper: Type[BaseDumper] = Dumper,
    *,
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
) -> str | None:
    """
    Serialize a sequence of Python objects into a YAML stream.

    Args:
        documents: Iterable of Python objects to serialize.
        stream: Optional file-like object to write to. If None, returns a string.
        Dumper: The dumper class to use. Defaults to Dumper.
        **kwargs: Additional formatting options.

    Returns:
        YAML string if stream is None, otherwise None.
    """
    getvalue = None
    if stream is None:
        stream = StringIO()
        getvalue = stream.getvalue

    dumper = Dumper(
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
    try:
        dumper.open()
        for data in documents:
            dumper.serialize(dumper.represent(data))
        dumper.close()
    finally:
        dumper.dispose()

    if getvalue:
        return getvalue()
    return None


# =============================================================================
# Low-level Functions
# =============================================================================


def parse(
    stream: str | bytes | IO[str] | IO[bytes],
    Loader: Type[BaseLoader] = SafeLoader,
) -> Iterator[Event]:
    """
    Parse a YAML stream and produce parsing events.

    Args:
        stream: A string, bytes, or file-like object containing YAML.
        Loader: The loader class to use.

    Yields:
        Event objects.
    """
    from ._parser import Handler, Parser

    class EventCollector(Handler):
        def __init__(self) -> None:
            self.events: list[Event] = []

        def event_location(
            self, start_line: int, start_column: int, end_line: int, end_column: int
        ) -> None:
            pass

        def start_stream(self, encoding: str) -> None:
            self.events.append(StreamStartEvent(encoding=encoding))

        def end_stream(self) -> None:
            self.events.append(StreamEndEvent())

        def start_document(
            self,
            version: tuple[int, int] | None,
            tag_directives: list[tuple[str, str]],
            implicit: bool,
        ) -> None:
            tags = dict(tag_directives) if tag_directives else None
            self.events.append(
                DocumentStartEvent(explicit=not implicit, version=version, tags=tags)
            )

        def end_document(self, implicit: bool) -> None:
            self.events.append(DocumentEndEvent(explicit=not implicit))

        def start_mapping(
            self, anchor: str | None, tag: str | None, implicit: bool, style: int
        ) -> None:
            self.events.append(
                MappingStartEvent(
                    anchor=anchor,
                    tag=tag,
                    implicit=implicit,
                    flow_style=style == 2,
                )
            )

        def end_mapping(self) -> None:
            self.events.append(MappingEndEvent())

        def start_sequence(
            self, anchor: str | None, tag: str | None, implicit: bool, style: int
        ) -> None:
            self.events.append(
                SequenceStartEvent(
                    anchor=anchor,
                    tag=tag,
                    implicit=implicit,
                    flow_style=style == 2,
                )
            )

        def end_sequence(self) -> None:
            self.events.append(SequenceEndEvent())

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
            self.events.append(
                ScalarEvent(
                    anchor=anchor,
                    tag=tag,
                    implicit=(plain, quoted),
                    value=value,
                    style=style_map.get(style),
                )
            )

        def alias(self, anchor: str) -> None:
            self.events.append(AliasEvent(anchor=anchor))

    if hasattr(stream, "read"):
        stream = stream.read()
    if isinstance(stream, bytes):
        stream = stream.decode("utf-8")

    handler = EventCollector()
    parser = Parser(handler)
    parser.parse(stream)

    for event in handler.events:
        yield event


def compose(
    stream: str | bytes | IO[str] | IO[bytes],
    Loader: Type[BaseLoader] = SafeLoader,
) -> Node | None:
    """
    Parse the first YAML document in a stream and produce the corresponding
    representation tree.

    Args:
        stream: A string, bytes, or file-like object containing YAML.
        Loader: The loader class to use.

    Returns:
        The root Node, or None if the stream is empty.
    """
    loader = Loader(stream)
    try:
        loader._parse()
        if loader._documents:
            return loader._documents[0]
        return None
    finally:
        loader.dispose()


def compose_all(
    stream: str | bytes | IO[str] | IO[bytes],
    Loader: Type[BaseLoader] = SafeLoader,
) -> Iterator[Node]:
    """
    Parse all YAML documents in a stream and produce corresponding
    representation trees.

    Args:
        stream: A string, bytes, or file-like object containing YAML.
        Loader: The loader class to use.

    Yields:
        Node objects for each document.
    """
    loader = Loader(stream)
    try:
        loader._parse()
        for doc in loader._documents:
            if doc is not None:
                yield doc
    finally:
        loader.dispose()


def emit(
    events: Iterator[Event],
    stream: IO[str] | None = None,
    Dumper: Type[BaseDumper] = Dumper,
    canonical: bool = False,
    indent: int | None = None,
    width: int | None = None,
    allow_unicode: bool = True,
    line_break: str | None = None,
) -> str | None:
    """
    Emit YAML parsing events into a stream.

    Args:
        events: Iterator of Event objects.
        stream: Optional file-like object to write to.
        **kwargs: Emitter options.

    Returns:
        YAML string if stream is None, otherwise None.
    """
    getvalue = None
    if stream is None:
        stream = StringIO()
        getvalue = stream.getvalue

    emitter = Emitter(
        stream,
        canonical=canonical,
        indent=indent,
        width=width,
        allow_unicode=allow_unicode,
        line_break=line_break,
    )
    try:
        for event in events:
            emitter.emit(event)
    finally:
        emitter.dispose()

    if getvalue:
        return getvalue()
    return None


def serialize(
    node: Node,
    stream: IO[str] | None = None,
    Dumper: Type[BaseDumper] = Dumper,
    *,
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
) -> str | None:
    """
    Serialize a representation tree into a YAML stream.

    Args:
        node: The root Node to serialize.
        stream: Optional file-like object to write to.
        **kwargs: Serializer options.

    Returns:
        YAML string if stream is None, otherwise None.
    """
    return serialize_all(
        [node],
        stream=stream,
        Dumper=Dumper,
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
    )


def serialize_all(
    nodes: Any,
    stream: IO[str] | None = None,
    Dumper: Type[BaseDumper] = Dumper,
    *,
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
) -> str | None:
    """
    Serialize a sequence of representation trees into a YAML stream.

    Args:
        nodes: Iterable of Node objects.
        stream: Optional file-like object to write to.
        **kwargs: Serializer options.

    Returns:
        YAML string if stream is None, otherwise None.
    """
    getvalue = None
    if stream is None:
        stream = StringIO()
        getvalue = stream.getvalue

    dumper = Dumper(
        stream,
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
    )
    try:
        dumper.open()
        for node in nodes:
            dumper.serialize(node)
        dumper.close()
    finally:
        dumper.dispose()

    if getvalue:
        return getvalue()
    return None


# =============================================================================
# Custom Representer/Constructor Registration
# =============================================================================


def add_representer(data_type: type, representer: Any, Dumper: Type[BaseDumper] = Dumper) -> None:
    """
    Add a representer for the given type to the Dumper.

    Args:
        data_type: The Python type to represent.
        representer: A callable that takes (dumper, data) and returns a Node.
        Dumper: The Dumper class to add the representer to.
    """
    Dumper.add_representer(data_type, representer)


def add_safe_representer(data_type: type, representer: Any) -> None:
    """
    Add a representer for the given type to SafeDumper.

    Args:
        data_type: The Python type to represent.
        representer: A callable that takes (dumper, data) and returns a Node.
    """
    SafeDumper.add_representer(data_type, representer)


def add_constructor(
    tag: str, constructor: Any, Loader: Type[BaseLoader] = FullLoader
) -> None:
    """
    Add a constructor for the given tag to the Loader.

    Args:
        tag: The YAML tag to construct.
        constructor: A callable that takes (loader, node) and returns a Python object.
        Loader: The Loader class to add the constructor to.
    """
    Loader.add_constructor(tag, constructor)


def add_safe_constructor(tag: str, constructor: Any) -> None:
    """
    Add a constructor for the given tag to SafeLoader.

    Args:
        tag: The YAML tag to construct.
        constructor: A callable that takes (loader, node) and returns a Python object.
    """
    SafeLoader.add_constructor(tag, constructor)


def add_multi_constructor(
    tag_prefix: str, multi_constructor: Any, Loader: Type[BaseLoader] = FullLoader
) -> None:
    """
    Add a multi-constructor for tags with the given prefix to the Loader.

    Args:
        tag_prefix: The tag prefix to match.
        multi_constructor: A callable that takes (loader, tag, node) and returns a Python object.
        Loader: The Loader class to add the multi-constructor to.
    """
    Loader.add_multi_constructor(tag_prefix, multi_constructor)


def add_safe_multi_constructor(tag_prefix: str, multi_constructor: Any) -> None:
    """
    Add a multi-constructor for tags with the given prefix to SafeLoader.

    Args:
        tag_prefix: The tag prefix to match.
        multi_constructor: A callable that takes (loader, tag, node) and returns a Python object.
    """
    SafeLoader.add_multi_constructor(tag_prefix, multi_constructor)


def add_implicit_resolver(
    tag: str,
    regexp: Any,
    first: list[str] | None = None,
    Loader: Type[BaseLoader] = FullLoader,
    Dumper: Type[BaseDumper] = Dumper,
) -> None:
    """
    Add an implicit resolver for the given tag.

    Args:
        tag: The YAML tag to resolve.
        regexp: A compiled regular expression to match scalar values.
        first: Optional list of first characters that can start this value.
        Loader: The Loader class to add the resolver to.
        Dumper: The Dumper class to add the resolver to.
    """
    Loader.add_implicit_resolver(tag, regexp, first)
    Dumper.add_implicit_resolver(tag, regexp, first)

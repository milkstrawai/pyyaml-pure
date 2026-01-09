"""
YAML error classes - PyYAML compatible.

This module provides exception classes that match PyYAML's error.py interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any


@dataclass(slots=True)
class Mark:
    """
    Represents a position in the YAML input stream.

    This class is used to provide detailed error messages with line and column
    information.
    """

    name: str
    index: int
    line: int
    column: int
    buffer: str | None = None
    pointer: int | None = None

    def get_snippet(self, indent: int = 4, max_length: int = 75) -> str | None:
        """Get a snippet of the input around this mark for error messages."""
        if self.buffer is None:
            return None

        head = ""
        start = self.pointer or 0
        while start > 0 and self.buffer[start - 1] not in "\0\r\n\x85\u2028\u2029":
            start -= 1
            if self.pointer - start > max_length // 2 - 1:
                head = " ... "
                start += 5
                break

        tail = ""
        end = self.pointer or 0
        while end < len(self.buffer) and self.buffer[end] not in "\0\r\n\x85\u2028\u2029":
            end += 1
            if end - start > max_length:
                tail = " ... "
                end -= 5
                break

        snippet = self.buffer[start:end]
        return (
            " " * indent
            + head
            + snippet
            + tail
            + "\n"
            + " " * (indent + (self.pointer or 0) - start + len(head))
            + "^"
        )

    def __str__(self) -> str:
        snippet = self.get_snippet()
        where = f'  in "{self.name}", line {self.line + 1}, column {self.column + 1}'
        if snippet is not None:
            where += ":\n" + snippet
        return where


class YAMLError(Exception):
    """Base exception for all YAML errors."""

    pass


class MarkedYAMLError(YAMLError):
    """
    YAML error with position information.

    This exception includes marks that point to the problematic location
    in the YAML input.
    """

    def __init__(
        self,
        context: str | None = None,
        context_mark: Mark | None = None,
        problem: str | None = None,
        problem_mark: Mark | None = None,
        note: str | None = None,
    ) -> None:
        super().__init__()
        self.context = context
        self.context_mark = context_mark
        self.problem = problem
        self.problem_mark = problem_mark
        self.note = note

    def __str__(self) -> str:
        lines: list[str] = []
        if self.context is not None:
            lines.append(self.context)
        if self.context_mark is not None and (
            self.problem is None
            or self.problem_mark is None
            or self.context_mark.name != self.problem_mark.name
            or self.context_mark.line != self.problem_mark.line
            or self.context_mark.column != self.problem_mark.column
        ):
            lines.append(str(self.context_mark))
        if self.problem is not None:
            lines.append(self.problem)
        if self.problem_mark is not None:
            lines.append(str(self.problem_mark))
        if self.note is not None:
            lines.append(self.note)
        return "\n".join(lines)


class ReaderError(YAMLError):
    """Error while reading the YAML stream."""

    def __init__(
        self,
        name: str,
        position: int,
        character: int | str,
        encoding: str,
        reason: str,
    ) -> None:
        super().__init__()
        self.name = name
        self.position = position
        self.character = character
        self.encoding = encoding
        self.reason = reason

    def __str__(self) -> str:
        if isinstance(self.character, bytes):
            return (
                f"'{self.encoding}' codec can't decode byte #x{ord(self.character):02x}: "
                f"{self.reason}\n  in \"{self.name}\", position {self.position}"
            )
        else:
            return (
                f"unacceptable character #x{self.character:04x}: {self.reason}\n"
                f'  in "{self.name}", position {self.position}'
            )


class ScannerError(MarkedYAMLError):
    """Error while scanning YAML tokens."""

    pass


class ParserError(MarkedYAMLError):
    """Error while parsing YAML."""

    pass


class ComposerError(MarkedYAMLError):
    """Error while composing YAML nodes."""

    pass


class ConstructorError(MarkedYAMLError):
    """Error while constructing Python objects from YAML."""

    pass


class EmitterError(YAMLError):
    """Error while emitting YAML."""

    pass


class SerializerError(YAMLError):
    """Error while serializing nodes to events."""

    pass


class RepresenterError(YAMLError):
    """Error while representing Python objects as nodes."""

    pass


class SyntaxError(MarkedYAMLError):
    """Syntax error during YAML parsing."""

    pass

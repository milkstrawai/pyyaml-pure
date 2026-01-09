"""
Source and Location classes for tracking positions in YAML input.

These classes provide line/column information from byte offsets for
error messages and location tracking.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    pass

# Regex patterns for detecting trimmable lines
_COMMENT_LINE_RE = re.compile(r"^ *#.*\n$")
_BLANK_LINE_RE = re.compile(r"^ *\n$")


class Source:
    """
    Wraps the input string and provides line/column lookup from byte offsets.

    This class is used for error messages and location tracking in the parser.
    It precomputes line offsets for efficient binary search lookups.
    """

    __slots__ = ("_line_offsets", "_trimmable_lines")

    def __init__(self, string: str) -> None:
        """
        Initialize the source with the input string.

        Args:
            string: The YAML input string.
        """
        self._line_offsets: list[int] = []
        self._trimmable_lines: list[Literal["comment", "blank"] | bool] = []

        offset = 0
        # Split keeping line endings to accurately track byte offsets
        for line in string.splitlines(keepends=True):
            self._line_offsets.append(offset)

            # Determine if line is trimmable (comment or blank)
            if _COMMENT_LINE_RE.match(line):
                self._trimmable_lines.append("comment")
            elif _BLANK_LINE_RE.match(line):
                self._trimmable_lines.append("blank")
            else:
                self._trimmable_lines.append(False)

            offset += len(line)

        # Add final offset for end of string
        self._line_offsets.append(offset)
        self._trimmable_lines.append(True)  # End is always trimmable

    def line(self, offset: int) -> int:
        """
        Return 0-based line number for given byte offset.

        Uses binary search for O(log n) lookup.

        Args:
            offset: Byte offset in the source string.

        Returns:
            0-based line number.
        """
        # Find first line offset greater than our offset
        index = bisect.bisect_right(self._line_offsets, offset)
        if index == 0:
            return 0
        return index - 1

    def column(self, offset: int) -> int:
        """
        Return 0-based column for given byte offset.

        Args:
            offset: Byte offset in the source string.

        Returns:
            0-based column number.
        """
        line = self.line(offset)
        return offset - self._line_offsets[line]

    def point(self, offset: int) -> str:
        """
        Return human-readable position string.

        Args:
            offset: Byte offset in the source string.

        Returns:
            String like "line 1 column 5".
        """
        return f"line {self.line(offset) + 1} column {self.column(offset)}"

    def trim(self, offset: int) -> int:
        """
        Trim trailing whitespace and comments from offset.

        Moves the offset backwards past trailing blank lines and comment lines.

        Args:
            offset: Byte offset to trim from.

        Returns:
            New offset with trailing trimmable content removed.
        """
        line = self.line(offset)
        while line != 0 and offset == self._line_offsets[line] and self._trimmable_lines[line - 1]:
            offset = self._line_offsets[line - 1]
            line = self.line(offset)
        return offset

    def trim_comments(self, offset: int) -> int:
        """
        Trim trailing comments from offset.

        Only trims comment lines, not blank lines.

        Args:
            offset: Byte offset to trim from.

        Returns:
            New offset with trailing comments removed.
        """
        line = self.line(offset)
        while (
            line != 0
            and offset == self._line_offsets[line]
            and self._trimmable_lines[line - 1] == "comment"
        ):
            offset = self._line_offsets[line - 1]
            line = self.line(offset)
        return offset


@dataclass(slots=True)
class Location:
    """
    Represents a range of bytes in the input string.

    Used to track the location of parsed elements for error messages
    and AST nodes.
    """

    source: Source
    pos_start: int
    pos_end: int

    @classmethod
    def point(cls, source: Source, pos: int) -> Location:
        """
        Create a zero-width location at a single position.

        Args:
            source: The source object.
            pos: The position.

        Returns:
            A new Location with start == end.
        """
        return cls(source, pos, pos)

    @property
    def start_line(self) -> int:
        """Return 0-based start line number."""
        return self.source.line(self.pos_start)

    @property
    def start_column(self) -> int:
        """Return 0-based start column number."""
        return self.source.column(self.pos_start)

    @property
    def end_line(self) -> int:
        """Return 0-based end line number."""
        return self.source.line(self.pos_end)

    @property
    def end_column(self) -> int:
        """Return 0-based end column number."""
        return self.source.column(self.pos_end)

    def to_tuple(self) -> tuple[int, int, int, int]:
        """
        Return location as a tuple.

        Returns:
            Tuple of (start_line, start_column, end_line, end_column).
        """
        return (self.start_line, self.start_column, self.end_line, self.end_column)

    def join(self, other: Location) -> None:
        """
        Extend this location to include another.

        Modifies this location in place to extend to the end of the other.

        Args:
            other: The location to extend to.
        """
        self.pos_end = other.pos_end

    def trim(self) -> Location:
        """
        Return new location with trailing whitespace/comments trimmed.

        Returns:
            A new Location with trimmed end position.
        """
        return Location(self.source, self.pos_start, self.source.trim(self.pos_end))

    def trim_comments(self) -> Location:
        """
        Return new location with trailing comments trimmed.

        Returns:
            A new Location with trailing comments removed.
        """
        return Location(self.source, self.pos_start, self.source.trim_comments(self.pos_end))

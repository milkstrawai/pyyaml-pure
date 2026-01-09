"""
StringScanner - A Python equivalent of Ruby's StringScanner for lexical scanning.

This module provides position tracking, regex matching, and backtracking support
for the YAML parser.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Pattern, Match

if TYPE_CHECKING:
    pass


class StringScanner:
    """
    A scanner for lexical analysis with position tracking and backtracking.

    This class is modeled after Ruby's StringScanner and provides efficient
    string scanning with regex pattern matching and position management.
    """

    __slots__ = ("_string", "_pos", "_match", "_len")

    def __init__(self, string: str) -> None:
        """
        Initialize the scanner with the input string.

        Args:
            string: The string to scan.
        """
        self._string = string
        self._pos = 0
        self._match: Match[str] | None = None
        self._len = len(string)

    @property
    def string(self) -> str:
        """Return the underlying string."""
        return self._string

    @property
    def pos(self) -> int:
        """Return current scan position."""
        return self._pos

    @pos.setter
    def pos(self, value: int) -> None:
        """Set the scan position."""
        self._pos = value

    def eos(self) -> bool:
        """Return True if at end of string."""
        return self._pos >= self._len

    def peek(self, length: int = 1) -> str:
        """
        Look ahead without advancing position.

        Args:
            length: Number of characters to peek.

        Returns:
            The substring at current position.
        """
        return self._string[self._pos : self._pos + length]

    def check_char(self, char: str) -> bool:
        """
        Check if the current character matches without advancing.

        Args:
            char: Single character to check.

        Returns:
            True if matches.
        """
        return self._pos < self._len and self._string[self._pos] == char

    def skip_char(self, char: str) -> bool:
        """
        Skip a single character if it matches.

        Args:
            char: Single character to match.

        Returns:
            True if matched and skipped.
        """
        if self._pos < self._len and self._string[self._pos] == char:
            self._pos += 1
            self._match = None
            return True
        return False

    def skip_literal(self, literal: str) -> int | None:
        """
        Skip a literal string if it matches at current position.

        This is a fast path for matching literal strings without regex.

        Args:
            literal: The exact string to match.

        Returns:
            Length of match or None if no match.
        """
        if self._string.startswith(literal, self._pos):
            length = len(literal)
            self._pos += length
            self._match = None
            return length
        return None

    def skip(self, pattern: str | Pattern[str]) -> int | None:
        """
        Scan forward for pattern, updating position if matched.

        Args:
            pattern: Literal string or compiled regex pattern.

        Returns:
            Length matched or None if no match.
        """
        if isinstance(pattern, str):
            return self.skip_literal(pattern)

        # Optimized: inline the regex match for speed
        pos = self._pos
        match = pattern.match(self._string, pos)
        if match:
            end = match.end()
            self._match = match
            self._pos = end
            return end - pos
        self._match = None
        return None

    def scan(self, pattern: str | Pattern[str]) -> str | None:
        """
        Scan forward for pattern and return matched string.

        Args:
            pattern: Literal string or compiled regex pattern.

        Returns:
            Matched string or None if no match.
        """
        if isinstance(pattern, str):
            if self._string.startswith(pattern, self._pos):
                self._pos += len(pattern)
                self._match = None
                return pattern
            return None

        match = pattern.match(self._string, self._pos)
        if match:
            self._match = match
            self._pos = match.end()
            return match.group(0)
        self._match = None
        return None

    def check(self, pattern: str | Pattern[str]) -> str | None:
        """
        Look ahead for pattern without advancing position.

        Args:
            pattern: Literal string or compiled regex pattern.

        Returns:
            Matched string or None if no match.
        """
        if isinstance(pattern, str):
            if self._string.startswith(pattern, self._pos):
                return pattern
            return None

        match = pattern.match(self._string, self._pos)
        if match:
            self._match = match
            return match.group(0)
        self._match = None
        return None

    def check_until(self, pattern: Pattern[str]) -> str | None:
        """
        Search forward for pattern without advancing position.

        Args:
            pattern: Compiled regex pattern to search for.

        Returns:
            String from current position to end of match, or None.
        """
        match = pattern.search(self._string, self._pos)
        if match:
            self._match = match
            return self._string[self._pos : match.end()]
        self._match = None
        return None

    def skip_until(self, pattern: Pattern[str]) -> int | None:
        """
        Advance position to the end of the pattern match.

        Args:
            pattern: Compiled regex pattern to search for.

        Returns:
            Number of characters skipped or None if not found.
        """
        match = pattern.search(self._string, self._pos)
        if match:
            self._match = match
            length = match.end() - self._pos
            self._pos = match.end()
            return length
        self._match = None
        return None

    def scan_until(self, pattern: Pattern[str]) -> str | None:
        """
        Scan forward to pattern and return matched string.

        Args:
            pattern: Compiled regex pattern to search for.

        Returns:
            String from current position to end of match, or None.
        """
        match = pattern.search(self._string, self._pos)
        if match:
            self._match = match
            result = self._string[self._pos : match.end()]
            self._pos = match.end()
            return result
        self._match = None
        return None

    def getch(self) -> str | None:
        """
        Get and advance past a single character.

        Returns:
            The character at current position or None if at end.
        """
        if self._pos >= self._len:
            return None
        char = self._string[self._pos]
        self._pos += 1
        self._match = None
        return char

    def __getitem__(self, index: int) -> str | None:
        """
        Return the nth capture group from the last match.

        Args:
            index: Capture group index (0 for full match).

        Returns:
            The captured string or None.
        """
        if self._match is None:
            return None
        try:
            return self._match.group(index)
        except IndexError:
            return None

    @property
    def matched(self) -> str | None:
        """Return the entire matched string from the last operation."""
        if self._match is None:
            return None
        return self._match.group(0)

    @property
    def rest(self) -> str:
        """Return the rest of the string from current position."""
        return self._string[self._pos :]

    @property
    def rest_size(self) -> int:
        """Return the length of the rest of the string."""
        return self._len - self._pos

    def reset(self) -> None:
        """Reset the scanner to the beginning."""
        self._pos = 0
        self._match = None

    def terminate(self) -> None:
        """Move the scanner to the end of the string."""
        self._pos = self._len
        self._match = None

    def unscan(self) -> None:
        """
        Revert the scanner to before the last match.

        This only works if there was a previous match.
        """
        if self._match is not None:
            self._pos = self._match.start()
            self._match = None

    def beginning_of_line(self) -> bool:
        """Check if scanner is at the beginning of a line."""
        return self._pos == 0 or (self._pos > 0 and self._string[self._pos - 1] == "\n")

    def __repr__(self) -> str:
        rest = self._string[self._pos :]
        if len(rest) > 20:
            rest = rest[:20] + "..."
        return f"StringScanner(pos={self._pos}, rest={rest!r})"

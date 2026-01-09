"""
YAML stream reader - PyYAML compatible.

This module provides the Reader class that handles reading YAML input
from various sources (strings, files, streams) with encoding detection.
"""

from __future__ import annotations

import codecs
import re
from typing import IO, TYPE_CHECKING

from .error import Mark, ReaderError

if TYPE_CHECKING:
    pass

# Regular expression to detect non-printable characters
# YAML allows: TAB, LF, CR, and printable Unicode characters
NON_PRINTABLE_RE = re.compile(
    "[^\x09\x0A\x0D\x20-\x7E\x85\xA0-\uD7FF\uE000-\uFFFD"
    "\U00010000-\U0010FFFF]"
)


class Reader:
    """
    Reader handles reading input from various sources.

    It detects the encoding of the input stream and provides
    access to the decoded characters with position tracking.
    """

    def __init__(self, stream: str | bytes | IO[str] | IO[bytes]) -> None:
        """
        Initialize the reader with an input stream.

        Args:
            stream: String, bytes, or file-like object to read from.
        """
        self.name: str = "<unknown>"
        self.stream: IO[str] | None = None
        self.stream_pointer: int = 0
        self.eof: bool = False
        self.buffer: str = ""
        self.pointer: int = 0
        self.raw_buffer: bytes | None = None
        self.raw_decode: codecs.IncrementalDecoder | None = None
        self.encoding: str | None = None
        self.index: int = 0
        self.line: int = 0
        self.column: int = 0

        if isinstance(stream, str):
            self.name = "<unicode string>"
            self.check_printable(stream)
            self.buffer = stream + "\0"
        elif isinstance(stream, bytes):
            self.name = "<byte string>"
            self.raw_buffer = stream
            self.determine_encoding()
        else:
            self.stream = stream
            self.name = getattr(stream, "name", "<stream>")
            if hasattr(stream, "mode") and "b" not in stream.mode:
                # Text mode stream
                self.encoding = "utf-8"
                self.raw_decode = None
            else:
                # Binary mode stream - read initial chunk
                self.raw_buffer = b""
                self.determine_encoding()

    def check_printable(self, data: str) -> None:
        """
        Check for non-printable characters in the input.

        Args:
            data: String to check.

        Raises:
            ReaderError: If non-printable characters are found.
        """
        match = NON_PRINTABLE_RE.search(data)
        if match:
            character = match.group()
            position = self.index + (len(self.buffer) - len(data)) + match.start()
            raise ReaderError(
                self.name,
                position,
                ord(character),
                "unicode",
                "special characters are not allowed",
            )

    def peek(self, index: int = 0) -> str:
        """
        Look ahead at characters without consuming them.

        Args:
            index: Number of characters to look ahead.

        Returns:
            The character at the given offset.
        """
        pointer = self.pointer + index
        while pointer >= len(self.buffer):
            if not self.update(1):
                return "\0"
        return self.buffer[pointer]

    def prefix(self, length: int = 1) -> str:
        """
        Return a substring from current position.

        Args:
            length: Length of substring.

        Returns:
            Substring of given length.
        """
        while self.pointer + length >= len(self.buffer):
            if not self.update(length):
                break
        return self.buffer[self.pointer : self.pointer + length]

    def forward(self, length: int = 1) -> None:
        """
        Advance the read position.

        Args:
            length: Number of characters to advance.
        """
        while self.pointer + length + 1 >= len(self.buffer):
            if not self.update(length + 1):
                break
        for _ in range(length):
            ch = self.buffer[self.pointer]
            self.pointer += 1
            self.index += 1
            if ch in "\n\x85\u2028\u2029" or (
                ch == "\r" and self.buffer[self.pointer] != "\n"
            ):
                self.line += 1
                self.column = 0
            elif ch != "\uFEFF":
                self.column += 1

    def get_mark(self) -> Mark:
        """
        Get the current position as a Mark.

        Returns:
            Mark object representing current position.
        """
        if self.stream is None:
            return Mark(
                self.name,
                self.index,
                self.line,
                self.column,
                self.buffer,
                self.pointer,
            )
        return Mark(self.name, self.index, self.line, self.column, None, None)

    def determine_encoding(self) -> None:
        """Detect the encoding of the input stream."""
        while not self.eof and (
            self.raw_buffer is None or len(self.raw_buffer) < 4
        ):
            self.update_raw()

        if self.raw_buffer is None:
            self.raw_buffer = b""

        # Check for BOM
        if self.raw_buffer.startswith(codecs.BOM_UTF32_LE):
            self.encoding = "utf-32-le"
            self.raw_buffer = self.raw_buffer[4:]
        elif self.raw_buffer.startswith(codecs.BOM_UTF32_BE):
            self.encoding = "utf-32-be"
            self.raw_buffer = self.raw_buffer[4:]
        elif self.raw_buffer.startswith(codecs.BOM_UTF16_LE):
            self.encoding = "utf-16-le"
            self.raw_buffer = self.raw_buffer[2:]
        elif self.raw_buffer.startswith(codecs.BOM_UTF16_BE):
            self.encoding = "utf-16-be"
            self.raw_buffer = self.raw_buffer[2:]
        elif self.raw_buffer.startswith(codecs.BOM_UTF8):
            self.encoding = "utf-8"
            self.raw_buffer = self.raw_buffer[3:]
        else:
            # Detect encoding from null bytes pattern
            if self.raw_buffer.startswith(b"\x00\x00\x00"):
                self.encoding = "utf-32-be"
            elif self.raw_buffer.startswith(b"\x00\x00"):
                self.encoding = "utf-16-be"
            elif len(self.raw_buffer) >= 4 and self.raw_buffer[1:4] == b"\x00\x00\x00":
                self.encoding = "utf-32-le"
            elif len(self.raw_buffer) >= 2 and self.raw_buffer[1:2] == b"\x00":
                self.encoding = "utf-16-le"
            else:
                self.encoding = "utf-8"

        self.raw_decode = codecs.getincrementaldecoder(self.encoding)("strict")
        self.update(1)

    def update_raw(self, size: int = 4096) -> None:
        """Read more raw bytes from the stream."""
        if self.stream is not None:
            data = self.stream.read(size)
            if isinstance(data, str):
                # Text mode stream
                self.check_printable(data)
                self.buffer += data
                if len(data) < size:
                    self.eof = True
            else:
                # Binary mode stream
                if self.raw_buffer is None:
                    self.raw_buffer = data
                else:
                    self.raw_buffer += data
                if len(data) < size:
                    self.eof = True

    def update(self, length: int = 1) -> bool:
        """
        Update the buffer with more decoded characters.

        Args:
            length: Minimum number of characters needed.

        Returns:
            True if more characters are available.
        """
        if self.raw_buffer is None:
            return not self.eof

        # Remove processed characters from buffer
        if self.pointer > 0 and self.pointer > len(self.buffer) // 2:
            self.buffer = self.buffer[self.pointer :]
            self.pointer = 0

        # Decode more if needed
        while len(self.buffer) < length:
            if not self.eof:
                self.update_raw()

            if self.raw_decode is None:
                break

            try:
                data = self.raw_decode.decode(self.raw_buffer or b"", self.eof)
                self.check_printable(data)
                self.buffer += data
                self.raw_buffer = b""
            except UnicodeDecodeError as exc:
                assert self.encoding is not None
                raise ReaderError(
                    self.name,
                    self.index,
                    exc.object[exc.start],
                    self.encoding,
                    exc.reason,
                ) from exc

            if self.eof:
                self.buffer += "\0"
                self.raw_buffer = None
                self.raw_decode = None
                break

        return len(self.buffer) >= length

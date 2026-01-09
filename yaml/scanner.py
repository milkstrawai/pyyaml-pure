"""
YAML scanner - PyYAML compatible wrapper.

This module provides the Scanner class that wraps our internal
parser to provide PyYAML-compatible tokenization.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterator

from .error import Mark
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

if TYPE_CHECKING:
    pass


class Scanner:
    """
    Scanner class that provides PyYAML-compatible tokenization.

    This wraps the internal parser to emit tokens instead of events.
    """

    def __init__(self) -> None:
        self.tokens: list[Token] = []
        self.tokens_taken: int = 0
        self.done: bool = False

    def check_token(self, *choices: type) -> bool:
        """Check if the next token is one of the given types."""
        while self.need_more_tokens():
            self.fetch_more_tokens()

        if self.tokens:
            if not choices:
                return True
            for choice in choices:
                if isinstance(self.tokens[0], choice):
                    return True

        return False

    def peek_token(self) -> Token | None:
        """Peek at the next token without consuming it."""
        while self.need_more_tokens():
            self.fetch_more_tokens()

        if self.tokens:
            return self.tokens[0]
        return None

    def get_token(self) -> Token | None:
        """Get and consume the next token."""
        while self.need_more_tokens():
            self.fetch_more_tokens()

        if self.tokens:
            self.tokens_taken += 1
            return self.tokens.pop(0)
        return None

    def need_more_tokens(self) -> bool:
        """Check if more tokens need to be fetched."""
        if self.done:
            return False
        if not self.tokens:
            return True
        return False

    def fetch_more_tokens(self) -> None:
        """Fetch more tokens from the input."""
        # This is a placeholder - the actual implementation
        # would use the parser to generate tokens
        self.done = True


def scan(stream: str, Loader: type | None = None) -> Iterator[Token]:
    """
    Scan a YAML stream and yield tokens.

    Args:
        stream: YAML input string.
        Loader: Optional loader class (unused, for compatibility).

    Yields:
        Token objects.
    """
    # This is a simplified implementation
    # A full implementation would use the parser
    yield StreamStartToken()
    yield StreamEndToken()

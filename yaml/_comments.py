"""
Comment preservation support for YAML parsing and emitting.

This module provides classes for tracking and preserving comments
during YAML round-trip processing.
"""

from __future__ import annotations

from typing import Any, Iterator


class Comment:
    """
    Represents a YAML comment.

    Attributes:
        value: The comment text (without the # prefix)
        column: The column where the comment starts (for formatting)
    """

    __slots__ = ("value", "column")

    def __init__(self, value: str, column: int = 0) -> None:
        self.value = value
        self.column = column

    def __repr__(self) -> str:
        return f"Comment({self.value!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Comment):
            return self.value == other.value
        return False


class CommentGroup:
    """
    Groups of comments associated with a value.

    Comments can appear in several positions:
    - before: Comments on lines before the key/value
    - inline: Comment on the same line after the value
    - after: Comments on lines after the value (before next item)
    """

    __slots__ = ("before", "inline", "after")

    def __init__(self) -> None:
        self.before: list[Comment] = []
        self.inline: Comment | None = None
        self.after: list[Comment] = []

    def __bool__(self) -> bool:
        return bool(self.before or self.inline or self.after)

    def __repr__(self) -> str:
        parts = []
        if self.before:
            parts.append(f"before={self.before}")
        if self.inline:
            parts.append(f"inline={self.inline}")
        if self.after:
            parts.append(f"after={self.after}")
        return f"CommentGroup({', '.join(parts)})"


class CommentedValue:
    """
    Wrapper for a scalar value with associated comments.

    This is used internally during construction to carry comments
    through the loading process.
    """

    __slots__ = ("value", "comments")

    def __init__(self, value: Any, comments: CommentGroup | None = None) -> None:
        self.value = value
        self.comments = comments or CommentGroup()


class CommentedMap(dict):
    """
    A dict subclass that preserves comments.

    Comments are stored separately and associated with keys.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Comments for each key (before key, inline after value)
        self._key_comments: dict[Any, CommentGroup] = {}
        # Comments at the start of the mapping (before first key)
        self._start_comments: list[Comment] = []
        # Comments at the end of the mapping (after last value)
        self._end_comments: list[Comment] = []

    def set_comment(self, key: Any, comments: CommentGroup) -> None:
        """Set comments for a key."""
        self._key_comments[key] = comments

    def get_comment(self, key: Any) -> CommentGroup | None:
        """Get comments for a key."""
        return self._key_comments.get(key)

    def set_start_comments(self, comments: list[Comment]) -> None:
        """Set comments before the first key."""
        self._start_comments = comments

    def set_end_comments(self, comments: list[Comment]) -> None:
        """Set comments after the last value."""
        self._end_comments = comments

    @property
    def start_comments(self) -> list[Comment]:
        return self._start_comments

    @property
    def end_comments(self) -> list[Comment]:
        return self._end_comments

    def copy(self) -> "CommentedMap":
        """Create a copy preserving comments."""
        new = CommentedMap(super().copy())
        new._key_comments = self._key_comments.copy()
        new._start_comments = self._start_comments.copy()
        new._end_comments = self._end_comments.copy()
        return new

    def __repr__(self) -> str:
        return f"CommentedMap({super().__repr__()})"


class CommentedSeq(list):
    """
    A list subclass that preserves comments.

    Comments are stored separately and associated with indices.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Comments for each index (before item, inline after item)
        self._item_comments: dict[int, CommentGroup] = {}
        # Comments at the start of the sequence (before first item)
        self._start_comments: list[Comment] = []
        # Comments at the end of the sequence (after last item)
        self._end_comments: list[Comment] = []

    def set_comment(self, index: int, comments: CommentGroup) -> None:
        """Set comments for an index."""
        self._item_comments[index] = comments

    def get_comment(self, index: int) -> CommentGroup | None:
        """Get comments for an index."""
        return self._item_comments.get(index)

    def set_start_comments(self, comments: list[Comment]) -> None:
        """Set comments before the first item."""
        self._start_comments = comments

    def set_end_comments(self, comments: list[Comment]) -> None:
        """Set comments after the last item."""
        self._end_comments = comments

    @property
    def start_comments(self) -> list[Comment]:
        return self._start_comments

    @property
    def end_comments(self) -> list[Comment]:
        return self._end_comments

    def copy(self) -> "CommentedSeq":
        """Create a copy preserving comments."""
        new = CommentedSeq(super().copy())
        new._item_comments = self._item_comments.copy()
        new._start_comments = self._start_comments.copy()
        new._end_comments = self._end_comments.copy()
        return new

    def __repr__(self) -> str:
        return f"CommentedSeq({super().__repr__()})"


def extract_comments_from_token(token_comment: str | None) -> list[Comment]:
    """Extract Comment objects from a token's comment string."""
    if not token_comment:
        return []

    comments = []
    for line in token_comment.split("\n"):
        line = line.strip()
        if line.startswith("#"):
            # Remove the # and leading space
            text = line[1:].lstrip()
            comments.append(Comment(text))
        elif line:
            comments.append(Comment(line))

    return comments

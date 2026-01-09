"""
Tests for comment preservation functionality.

Tests the `comments=True` parameter for safe_load/safe_dump
and the round-trip comment preservation.
"""

import pytest
import yaml
from yaml import CommentedMap, CommentedSeq


class TestCommentsParameter:
    """Test the comments=True parameter on load/dump functions."""

    def test_safe_load_without_comments_returns_dict(self):
        """safe_load without comments=True should return regular dict."""
        data = yaml.safe_load("key: value")
        assert type(data) is dict
        assert data == {"key": "value"}

    def test_safe_load_with_comments_returns_commented_map(self):
        """safe_load with comments=True should return CommentedMap."""
        data = yaml.safe_load("key: value", comments=True)
        assert isinstance(data, CommentedMap)
        assert data == {"key": "value"}

    def test_safe_load_all_without_comments_returns_dicts(self):
        """safe_load_all without comments=True should return regular dicts."""
        docs = list(yaml.safe_load_all("---\na: 1\n---\nb: 2"))
        assert all(type(d) is dict for d in docs)

    def test_safe_load_all_with_comments_returns_commented_maps(self):
        """safe_load_all with comments=True should return CommentedMaps."""
        docs = list(yaml.safe_load_all("---\na: 1\n---\nb: 2", comments=True))
        assert all(isinstance(d, CommentedMap) for d in docs)

    def test_safe_dump_without_comments_discards_comments(self):
        """safe_dump without comments=True should discard comments."""
        yaml_input = "# Header\nkey: value  # inline"
        data = yaml.safe_load(yaml_input, comments=True)
        output = yaml.safe_dump(data)
        assert "# Header" not in output
        assert "# inline" not in output

    def test_safe_dump_with_comments_preserves_comments(self):
        """safe_dump with comments=True should preserve comments."""
        yaml_input = "# Header\nkey: value  # inline"
        data = yaml.safe_load(yaml_input, comments=True)
        output = yaml.safe_dump(data, comments=True)
        assert "# Header" in output
        assert "# inline" in output


class TestCommentPreservation:
    """Test that comments are correctly preserved through round-trip."""

    def test_header_comment_preserved(self):
        """Comments at the start of a mapping should be preserved."""
        yaml_input = "# Header comment\nname: value"
        data = yaml.safe_load(yaml_input, comments=True)
        output = yaml.safe_dump(data, comments=True)
        assert "# Header comment" in output

    def test_inline_comment_preserved(self):
        """Inline comments after values should be preserved."""
        yaml_input = "name: John  # user name"
        data = yaml.safe_load(yaml_input, comments=True)
        output = yaml.safe_dump(data, comments=True)
        assert "# user name" in output

    def test_before_key_comment_preserved(self):
        """Comments before a key should be preserved."""
        yaml_input = "first: 1\n# Comment before second\nsecond: 2"
        data = yaml.safe_load(yaml_input, comments=True)
        output = yaml.safe_dump(data, comments=True)
        assert "# Comment before second" in output

    def test_multiple_comments_preserved(self):
        """Multiple comments in a document should all be preserved."""
        yaml_input = """# Header
name: John  # the name
# Before age
age: 30  # years old
"""
        data = yaml.safe_load(yaml_input, comments=True)
        output = yaml.safe_dump(data, comments=True)
        assert "# Header" in output
        assert "# the name" in output
        assert "# Before age" in output
        assert "# years old" in output

    def test_nested_structure_comments_preserved(self):
        """Comments in nested structures should be preserved."""
        yaml_input = """# Config
database:
  # Host setting
  host: localhost
  port: 5432  # default port
"""
        data = yaml.safe_load(yaml_input, comments=True)
        output = yaml.safe_dump(data, comments=True)
        assert "# Config" in output
        assert "# Host setting" in output
        assert "# default port" in output


class TestCommentedMapBehavior:
    """Test that CommentedMap behaves like a regular dict."""

    def test_commented_map_is_dict_subclass(self):
        """CommentedMap should be a dict subclass."""
        data = yaml.safe_load("key: value", comments=True)
        assert isinstance(data, dict)

    def test_commented_map_supports_dict_operations(self):
        """CommentedMap should support standard dict operations."""
        data = yaml.safe_load("a: 1\nb: 2", comments=True)

        # Get
        assert data["a"] == 1

        # Set
        data["c"] = 3
        assert data["c"] == 3

        # Delete
        del data["a"]
        assert "a" not in data

        # Keys/values/items
        assert list(data.keys()) == ["b", "c"]
        assert list(data.values()) == [2, 3]

        # Len
        assert len(data) == 2

    def test_modification_preserves_comments(self):
        """Modifying values should preserve comments on the key."""
        yaml_input = "name: John  # user name"
        data = yaml.safe_load(yaml_input, comments=True)
        data["name"] = "Jane"
        output = yaml.safe_dump(data, comments=True)
        assert "Jane" in output
        assert "# user name" in output

    def test_adding_new_key_has_no_comment(self):
        """Adding a new key should work without comments."""
        yaml_input = "# Header\nname: John"
        data = yaml.safe_load(yaml_input, comments=True)
        data["age"] = 30
        output = yaml.safe_dump(data, comments=True)
        assert "age: 30" in output


class TestCommentedSeqBehavior:
    """Test that CommentedSeq behaves like a regular list."""

    def test_commented_seq_is_list_subclass(self):
        """CommentedSeq should be a list subclass."""
        data = yaml.safe_load("items:\n- a\n- b", comments=True)
        assert isinstance(data["items"], list)

    def test_sequence_comments_preserved(self):
        """Comments in sequences should be preserved."""
        yaml_input = """items:
# First item
- apple
- banana  # yellow fruit
"""
        data = yaml.safe_load(yaml_input, comments=True)
        output = yaml.safe_dump(data, comments=True)
        assert "# First item" in output
        assert "# yellow fruit" in output


class TestRoundTripFunctions:
    """Test the legacy round_trip_* functions still work."""

    def test_round_trip_load_returns_commented_map(self):
        """round_trip_load should return CommentedMap."""
        data = yaml.round_trip_load("key: value")
        assert isinstance(data, CommentedMap)

    def test_round_trip_dump_preserves_comments(self):
        """round_trip_dump should preserve comments."""
        yaml_input = "# Header\nkey: value"
        data = yaml.round_trip_load(yaml_input)
        output = yaml.round_trip_dump(data)
        assert "# Header" in output

    def test_round_trip_load_all(self):
        """round_trip_load_all should work."""
        docs = list(yaml.round_trip_load_all("---\na: 1\n---\nb: 2"))
        assert len(docs) == 2
        assert all(isinstance(d, CommentedMap) for d in docs)


class TestEdgeCases:
    """Test edge cases in comment preservation."""

    def test_empty_document(self):
        """Empty document should work."""
        data = yaml.safe_load("", comments=True)
        assert data is None

    def test_scalar_only(self):
        """Scalar-only document should work."""
        data = yaml.safe_load("hello", comments=True)
        assert data == "hello"

    def test_comment_in_quoted_string_not_extracted(self):
        """Comments inside quoted strings should not be extracted."""
        yaml_input = 'message: "Hello # not a comment"'
        data = yaml.safe_load(yaml_input, comments=True)
        assert data["message"] == "Hello # not a comment"

    def test_multiple_inline_comments_on_different_lines(self):
        """Each line can have its own inline comment."""
        yaml_input = """a: 1  # comment a
b: 2  # comment b
c: 3  # comment c
"""
        data = yaml.safe_load(yaml_input, comments=True)
        output = yaml.safe_dump(data, comments=True)
        assert "# comment a" in output
        assert "# comment b" in output
        assert "# comment c" in output

    def test_comment_only_document(self):
        """Document with only comments should work."""
        yaml_input = "# Just a comment\n"
        data = yaml.safe_load(yaml_input, comments=True)
        assert data is None


class TestCompatibility:
    """Test compatibility between regular and commented modes."""

    def test_commented_map_equals_dict(self):
        """CommentedMap should equal equivalent dict."""
        data1 = yaml.safe_load("a: 1\nb: 2")
        data2 = yaml.safe_load("a: 1\nb: 2", comments=True)
        assert data1 == data2

    def test_dump_commented_map_without_comments_flag(self):
        """Dumping CommentedMap without comments=True should work."""
        data = yaml.safe_load("# Header\na: 1", comments=True)
        output = yaml.safe_dump(data)
        # Should work, just without comments
        assert "a: 1" in output
        assert "# Header" not in output

    def test_dump_regular_dict_with_comments_flag(self):
        """Dumping regular dict with comments=True should work."""
        data = {"a": 1, "b": 2}
        output = yaml.safe_dump(data, comments=True)
        assert "a: 1" in output
        assert "b: 2" in output

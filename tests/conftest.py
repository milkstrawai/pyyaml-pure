"""
Pytest configuration and fixtures for YAML tests.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest."""
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "yaml_suite: marks tests from YAML test suite")


@pytest.fixture
def yaml_test_suite_path() -> Path:
    """Get path to YAML test suite."""
    # Look for yaml-test-suite in parent directory
    base = Path(__file__).parent.parent.parent
    suite_path = base / "yaml-test-suite" / "src"
    if suite_path.exists():
        return suite_path
    # Try alternative location
    alt_path = Path(os.environ.get("YAML_TEST_SUITE", "")) / "src"
    if alt_path.exists():
        return alt_path
    pytest.skip("YAML test suite not found")
    return Path()  # Never reached


@pytest.fixture
def simple_yaml() -> str:
    """Simple YAML document for basic tests."""
    return """
name: John
age: 30
active: true
"""


@pytest.fixture
def nested_yaml() -> str:
    """Nested YAML document for structure tests."""
    return """
person:
  name: John
  address:
    city: New York
    zip: "10001"
  hobbies:
    - reading
    - gaming
"""


@pytest.fixture
def multi_doc_yaml() -> str:
    """Multi-document YAML for document tests."""
    return """---
first: document
---
second: document
---
third: document
"""

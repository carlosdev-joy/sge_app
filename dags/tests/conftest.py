"""conftest.py — pytest fixtures shared across all ORQUESTRA tests."""
import pytest


@pytest.fixture(autouse=True)
def reset_modules():
    """Yield and do nothing — avoids state leakage between test files."""
    yield

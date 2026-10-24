from typing import Any

import pytest

from tests.support.samples import load_sample


@pytest.fixture
def sample_study() -> Any:
    """Factory fixture: sample_study("multi_phase") -> the recorded study JSON."""
    return load_sample

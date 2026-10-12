"""Fixtures for the Heizkurve tests."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/heizkurve in every test."""
    yield

"""
Tests for the analytics router helper (to_float) and endpoint logic.
"""

from decimal import Decimal
from routers.analytics import to_float


# ── to_float helper ──────────────────────────────────────────────────────


class TestToFloat:
    def test_decimal(self):
        assert to_float(Decimal("3.14")) == 3.14

    def test_int(self):
        assert to_float(42) == 42.0

    def test_float_passthrough(self):
        assert to_float(1.5) == 1.5

    def test_string_numeric(self):
        assert to_float("7.7") == 7.7

    def test_none_returns_zero(self):
        assert to_float(None) == 0.0

    def test_non_numeric_string_returns_zero(self):
        assert to_float("not a number") == 0.0

    def test_empty_string_returns_zero(self):
        assert to_float("") == 0.0

    def test_negative_decimal(self):
        assert to_float(Decimal("-0.005")) == pytest.approx(-0.005)


# Need pytest for approx
import pytest

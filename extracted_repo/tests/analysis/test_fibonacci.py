# tests/test_fibonacci.py
import pytest
from app.analysis.fibonacci import fib_levels, fib_extensions

def test_fib_levels_up():
    out = fib_levels(100, 200)
    levels = out["levels"]
    # retracement 0.618 ของ 100→200 ควรใกล้ 138.2
    assert abs(levels["0.618"] - 138.2) < 1.0

def test_fib_levels_down():
    out = fib_levels(200, 100)
    levels = out["levels"]
    # retracement 0.5 ของ 200→100 ควรใกล้ 150
    assert abs(levels["0.5"] - 150.0) < 1.0

def test_fib_extensions():
    out = fib_extensions(100, 200)
    levels = out["levels"]
    # extension 1.618 ของ 100→200 ควรใกล้ 261.8
    assert abs(levels["1.618"] - 261.8) < 2.0

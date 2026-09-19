import pytest

from src.tools import calculations as calc


def test_cagr_doubling_twice():
    assert abs(calc.cagr(100, 400, 2) - 1.0) < 1e-9


def test_yoy_growth():
    assert calc.yoy_growth(100, 150) == 0.5
    assert calc.yoy_growth(100, 50) == -0.5


def test_growth_zero_base_raises():
    with pytest.raises(ValueError):
        calc.yoy_growth(0, 100)


def test_cagr_requires_positive():
    with pytest.raises(ValueError):
        calc.cagr(-1, 100, 2)
    with pytest.raises(ValueError):
        calc.cagr(100, 200, 0)


def test_margin_and_ratio():
    assert calc.margin(25, 100) == 0.25
    with pytest.raises(ValueError):
        calc.ratio(1, 0)


def test_npv_known_value():
    assert abs(calc.npv(0.1, [-100, 50, 50, 50]) - 24.3426) < 1e-3


def test_irr_known_value():
    assert abs(calc.irr([-100, 50, 50, 50]) - 0.2332) < 2e-3


def test_irr_without_sign_change_raises():
    with pytest.raises(ValueError):
        calc.irr([100, 50, 50])


def test_project_length_and_value():
    p = calc.project(100, 0.1, 3)
    assert len(p) == 3
    assert abs(p[-1] - 133.1) < 1e-6

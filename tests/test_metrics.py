"""Tests for S5 statistics."""

import math

import pytest

from logsub.eval.metrics import betainc, clopper_pearson


def test_betainc_uniform_is_identity():
    # I_x(1,1) == x
    for x in (0.0, 0.1, 0.5, 0.9, 1.0):
        assert math.isclose(betainc(1, 1, x), x, abs_tol=1e-9)


def test_betainc_symmetry():
    # I_x(a,b) == 1 - I_{1-x}(b,a)
    assert math.isclose(betainc(2, 5, 0.3), 1 - betainc(5, 2, 0.7), abs_tol=1e-9)


def test_clopper_pearson_edges():
    r0 = clopper_pearson(0, 20)
    assert r0.lo == 0.0 and r0.hi < 1.0 and r0.point == 0.0
    rn = clopper_pearson(20, 20)
    assert rn.hi == 1.0 and rn.lo > 0.0 and rn.point == 1.0


def test_clopper_pearson_known_value():
    # 0/10 -> upper bound is 1 - (alpha/2)^(1/n) ~ 0.3085 for 95% CI
    r = clopper_pearson(0, 10)
    assert math.isclose(r.hi, 1 - (0.025) ** (1 / 10), rel_tol=1e-3)


def test_clopper_pearson_contains_point():
    r = clopper_pearson(5, 100)
    assert r.lo < r.point < r.hi
    # wider interval for fewer samples
    wide = clopper_pearson(1, 20)
    narrow = clopper_pearson(50, 1000)
    assert (wide.hi - wide.lo) > (narrow.hi - narrow.lo)


def test_overlap_logic():
    a = clopper_pearson(10, 100)   # ~0.10
    b = clopper_pearson(12, 100)   # ~0.12, overlaps a
    c = clopper_pearson(60, 100)   # ~0.60, disjoint from a
    assert a.overlaps(b)
    assert not a.overlaps(c)


def test_invalid_counts():
    with pytest.raises(ValueError):
        clopper_pearson(11, 10)

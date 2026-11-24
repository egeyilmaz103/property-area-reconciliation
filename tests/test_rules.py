import math
import pytest
from area_reconcile import rules as r


@pytest.mark.parametrize("x,exp", [(137.5, 138), (137.49, 137), (100.0, 100), (0.5, 1)])
def test_round_half_up(x, exp):
    assert r.round_half_up(x) == exp


def test_common_share_and_gross():
    assert r.equal_common_share(120, 8) == 15
    assert r.gross_area(90, 15) == 105
    with pytest.raises(ValueError):
        r.equal_common_share(10, 0)


@pytest.mark.parametrize("declared", [None, float("nan"), 0, -5])
def test_no_declaration(declared):
    assert r.decide_final_area(declared, 105.4) == (105, r.NO_DECLARATION)


def test_declared_above():
    assert r.decide_final_area(120.5, 105.0) == (121, r.DECLARED_ABOVE)
    assert r.decide_final_area(105.0, 105.0) == (105, r.DECLARED_ABOVE)


def test_within_tolerance_boundary():
    assert r.decide_final_area(95.0, 105.0) == (95, r.DECLARED_WITHIN_TOL)   # gap exactly 10
    assert r.decide_final_area(94.9, 105.0)[1] == r.DECLARED_TOO_LOW         # gap 10.1


def test_too_low_uses_computed():
    assert r.decide_final_area(80.0, 105.4) == (105, r.DECLARED_TOO_LOW)

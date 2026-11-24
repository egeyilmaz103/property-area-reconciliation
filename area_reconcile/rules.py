"""Pure business rules for unit-area reconciliation.

Kept free of I/O and pandas so each rule is easy to read, test and reuse.
"""
from __future__ import annotations

import math

# A declared area that is lower than the computed gross area is still accepted
# when the shortfall is at most this many square metres.
TOLERANCE_M2 = 10.0

# Decision codes returned by :func:`decide_final_area`.
NO_DECLARATION = "COMPUTED_NO_DECLARATION"
DECLARED_ABOVE = "DECLARED_ABOVE_COMPUTED"
DECLARED_WITHIN_TOL = "DECLARED_WITHIN_TOLERANCE"
DECLARED_TOO_LOW = "COMPUTED_DECLARED_TOO_LOW"


def round_half_up(value: float) -> int:
    """Round to the nearest integer, with .5 rounding up (137.5 -> 138)."""
    return int(math.floor(value + 0.5))


def equal_common_share(common_area_m2: float, n_units: int) -> float:
    """Common-area share per unit: the building's common area split equally."""
    if n_units <= 0:
        raise ValueError("A building needs at least one independent unit.")
    return common_area_m2 / n_units


def gross_area(net_m2: float, common_share_m2: float) -> float:
    """Gross unit area = net area from the plan + equal share of common areas."""
    return net_m2 + common_share_m2


def _is_missing(declared) -> bool:
    return declared is None or (isinstance(declared, float) and math.isnan(declared)) or declared <= 0


def decide_final_area(declared, computed_gross: float, tol: float = TOLERANCE_M2):
    """Decide which area goes into the system for one unit.

    Rules, applied in order:
      1. No usable declaration            -> computed gross area.
      2. Declared >= computed gross       -> declared area (never under-report a declaration).
      3. Declared < computed, gap <= tol  -> declared area (within tolerance).
      4. Declared < computed, gap  > tol  -> computed gross area.

    Returns ``(final_area_m2 as int, decision_code)``.
    """
    if _is_missing(declared):
        return round_half_up(computed_gross), NO_DECLARATION
    if declared >= computed_gross:
        return round_half_up(declared), DECLARED_ABOVE
    if computed_gross - declared <= tol:
        return round_half_up(declared), DECLARED_WITHIN_TOL
    return round_half_up(computed_gross), DECLARED_TOO_LOW

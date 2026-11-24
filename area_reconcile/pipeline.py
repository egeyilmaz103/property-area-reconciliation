"""Reconciliation pipeline: plans + deeds + declarations -> final unit areas and issue list."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import rules

PERMIT_TOLERANCE_PCT = 1.0   # flag a building whose final total is >1% below the permit gross area


@dataclass
class Results:
    units: pd.DataFrame
    issues: pd.DataFrame
    buildings: pd.DataFrame


def load(data_dir: str | Path) -> dict[str, pd.DataFrame]:
    d = Path(data_dir)
    return {n: pd.read_csv(d / f"{n}.csv") for n in ("buildings", "deeds", "plans", "declarations")}


def compute_gross(buildings: pd.DataFrame, deeds: pd.DataFrame, plans: pd.DataFrame) -> pd.DataFrame:
    """Attach net/gross areas to every deed unit (equal common-area share per unit)."""
    df = deeds.merge(plans, on=["building_id", "unit_no"], how="left", validate="1:1")
    df = df.merge(buildings[["building_id", "common_area_m2", "n_units"]], on="building_id", how="left")
    if df["net_m2"].isna().any():
        missing = df.loc[df["net_m2"].isna(), ["building_id", "unit_no"]].to_dict("records")
        raise ValueError(f"Units without a plan area: {missing[:5]}")
    df["common_share_m2"] = df.apply(lambda r: rules.equal_common_share(r.common_area_m2, int(r.n_units)), axis=1)
    df["gross_m2"] = df["net_m2"] + df["common_share_m2"]
    return df.drop(columns=["common_area_m2", "n_units"])


def match_declarations(units: pd.DataFrame, declarations: pd.DataFrame):
    """Link each declaration to a deed unit.

    Pass 1: same unit number AND same person            -> confirmed.
    Pass 2: person owns a still-unmatched unit          -> matched by owner
            (covers unit number 0 or a mistyped number).
    Pass 3: same unit number but a different person     -> matched by unit number (owner mismatch).
    Pass 4: nothing fits                                 -> orphan declaration.
    Returns (matches, issues): matches maps (building_id, unit_no) -> declaration row.
    """
    matches: dict[tuple, pd.Series] = {}
    issues: list[dict] = []

    for building_id, decls in declarations.groupby("building_id"):
        bu = units[units.building_id == building_id].set_index("unit_no")
        pending = list(decls.sort_values("declaration_id").itertuples(index=False))

        # Pass 1
        rest = []
        for d in pending:
            key_unit = d.declared_unit_no
            if key_unit in bu.index and (building_id, key_unit) not in matches and bu.loc[key_unit, "owner_id"] == d.declarant_id:
                matches[(building_id, key_unit)] = ("direct", d)
            else:
                rest.append(d)

        # Pass 2
        rest2 = []
        for d in rest:
            free = [u for u in bu.index if (building_id, u) not in matches and bu.loc[u, "owner_id"] == d.declarant_id]
            if free:
                target = min(free, key=lambda u: abs(d.declared_m2 - bu.loc[u, "gross_m2"]))
                matches[(building_id, target)] = ("owner", d)
                kind = "UNIT_NO_ZERO" if d.declared_unit_no == 0 else "UNIT_NO_MISMATCH"
                issues.append({"building_id": building_id, "unit_no": target, "issue": kind,
                               "detail": f"Declaration {d.declaration_id} carries unit no {d.declared_unit_no}; "
                                         f"matched to deed unit {target} through the owner."})
            else:
                rest2.append(d)

        # Pass 3 and 4
        for d in rest2:
            u = d.declared_unit_no
            if u in bu.index and (building_id, u) not in matches:
                matches[(building_id, u)] = ("unit_no", d)
                issues.append({"building_id": building_id, "unit_no": u, "issue": "OWNER_MISMATCH",
                               "detail": f"Declarant {d.declarant_id} differs from deed owner {bu.loc[u, 'owner_id']}; verify."})
            else:
                issues.append({"building_id": building_id, "unit_no": d.declared_unit_no, "issue": "ORPHAN_DECLARATION",
                               "detail": f"Declaration {d.declaration_id} could not be tied to any deed unit."})
    return matches, issues


def run(data_dir: str | Path, tol: float = rules.TOLERANCE_M2,
        permit_tol_pct: float = PERMIT_TOLERANCE_PCT) -> Results:
    t = load(data_dir)
    units = compute_gross(t["buildings"], t["deeds"], t["plans"])
    matches, issues = match_declarations(units, t["declarations"])

    declared, decisions, finals, methods = [], [], [], []
    for r in units.itertuples(index=False):
        m = matches.get((r.building_id, r.unit_no))
        dec = m[1].declared_m2 if m else None
        final, code = rules.decide_final_area(dec, r.gross_m2, tol)
        declared.append(dec); decisions.append(code); finals.append(final); methods.append(m[0] if m else "none")
        if m is None:
            issues.append({"building_id": r.building_id, "unit_no": r.unit_no, "issue": "NO_DECLARATION",
                           "detail": "No declaration found for this deed unit; computed gross area used."})
        elif dec is not None and abs(dec - r.gross_m2) > tol:
            direction = "below" if dec < r.gross_m2 else "above"
            issues.append({"building_id": r.building_id, "unit_no": r.unit_no, "issue": "AREA_GAP",
                           "detail": f"Declared {dec:.1f} m2 is {abs(dec - r.gross_m2):.1f} m2 {direction} computed gross {r.gross_m2:.1f} m2."})
    units = units.assign(declared_m2=declared, final_m2=finals, decision=decisions, match_method=methods)

    # Building class outliers (a declaration whose class differs from the building's most common class).
    for building_id, g in t["declarations"].groupby("building_id"):
        if len(g) > 1:
            mode = g["building_class"].mode().iloc[0]
            for d in g[g.building_class != mode].itertuples(index=False):
                issues.append({"building_id": building_id, "unit_no": d.declared_unit_no, "issue": "CLASS_OUTLIER",
                               "detail": f"Declaration {d.declaration_id} lists class {d.building_class}; most declarations list class {mode}."})

    # Building-level permit check.
    b = t["buildings"].copy()
    agg = units.groupby("building_id").agg(sum_net_m2=("net_m2", "sum"), sum_gross_m2=("gross_m2", "sum"),
                                           sum_final_m2=("final_m2", "sum"),
                                           n_declared=("declared_m2", lambda s: s.notna().sum()))
    b = b.merge(agg, on="building_id")
    b["shortfall_vs_permit_m2"] = (b["permit_gross_m2"] - b["sum_final_m2"]).clip(lower=0).round(1)
    for r in b.itertuples(index=False):
        if r.shortfall_vs_permit_m2 > r.permit_gross_m2 * permit_tol_pct / 100:
            issues.append({"building_id": r.building_id, "unit_no": None, "issue": "SUM_BELOW_PERMIT",
                           "detail": f"Final total {r.sum_final_m2} m2 is {r.shortfall_vs_permit_m2} m2 below permit gross {r.permit_gross_m2} m2; check plan and permit."})

    issues_df = pd.DataFrame(issues, columns=["building_id", "unit_no", "issue", "detail"]).sort_values(
        ["building_id", "issue", "unit_no"], na_position="last").reset_index(drop=True)
    count = issues_df.groupby("building_id").size()
    b["n_issues"] = b["building_id"].map(count).fillna(0).astype(int)
    units = units.merge(
        issues_df.dropna(subset=["unit_no"]).assign(unit_no=lambda x: x.unit_no.astype(int))
        .groupby(["building_id", "unit_no"])["issue"].agg(", ".join).rename("flags").reset_index(),
        on=["building_id", "unit_no"], how="left")
    units["flags"] = units["flags"].fillna("")
    return Results(units=units, issues=issues_df, buildings=b)

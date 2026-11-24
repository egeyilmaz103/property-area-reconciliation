"""Outputs: bulk-upload Excel, per-building feedback text and a summary chart."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .pipeline import Results

ISSUE_LABELS = {
    "AREA_GAP": "Declared area differs from computed", "NO_DECLARATION": "No declaration",
    "UNIT_NO_MISMATCH": "Wrong unit no on declaration", "UNIT_NO_ZERO": "Unit no left as 0",
    "OWNER_MISMATCH": "Declarant differs from owner", "ORPHAN_DECLARATION": "Orphan declaration",
    "CLASS_OUTLIER": "Building class outlier", "SUM_BELOW_PERMIT": "Total below permit",
}


def write_excel(res: Results, path: Path) -> None:
    cols = ["building_id", "unit_no", "floor", "unit_type", "owner_id", "net_m2", "common_share_m2",
            "gross_m2", "declared_m2", "final_m2", "decision", "match_method", "flags"]
    units = res.units[cols].round(1)
    summary = res.buildings.round(1)
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        units[["building_id", "unit_no", "final_m2"]].rename(columns={"final_m2": "area_m2"}).to_excel(
            xw, "bulk_upload", index=False)
        units.to_excel(xw, "units_detail", index=False)
        summary.to_excel(xw, "buildings", index=False)
        res.issues.to_excel(xw, "issues", index=False)
        for ws in xw.book.worksheets:
            ws.freeze_panes = "A2"
            for col in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in col[:200])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 70)


def write_feedback(res: Results, path: Path) -> None:
    lines = ["# Per-building feedback\n"]
    for b in res.buildings.sort_values("building_id").itertuples(index=False):
        iss = res.issues[res.issues.building_id == b.building_id]
        lines.append(f"## {b.building_id} ({b.n_units} units, permit {b.permit_gross_m2} m2, final total {b.sum_final_m2} m2)")
        if iss.empty:
            lines.append("No issues found.\n")
            continue
        for kind, g in iss.groupby("issue"):
            lines.append(f"- **{ISSUE_LABELS.get(kind, kind)}** ({len(g)}): " + "; ".join(
                (f"unit {int(r.unit_no)}: " if pd.notna(r.unit_no) else "") + r.detail for r in g.itertuples()))
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_chart(res: Results, path: Path) -> None:
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.2), constrained_layout=True)
    counts = res.issues["issue"].map(lambda k: ISSUE_LABELS.get(k, k)).value_counts().sort_values()
    a1.barh(counts.index, counts.values, color="#2a6f97")
    a1.set_title("Issues found by type"); a1.set_xlabel("Count")
    for i, v in enumerate(counts.values):
        a1.text(v, i, f" {v}", va="center", fontsize=9)
    dec = res.units["decision"].value_counts().sort_values()
    a2.barh(dec.index, dec.values, color="#6a994e")
    a2.set_title("How each unit's final area was decided"); a2.set_xlabel("Units")
    for i, v in enumerate(dec.values):
        a2.text(v, i, f" {v}", va="center", fontsize=9)
    for a in (a1, a2):
        a.spines[["top", "right"]].set_visible(False)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def write_all(res: Results, out_dir: str | Path) -> None:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    write_excel(res, out / "units_final.xlsx")
    write_feedback(res, out / "feedback.md")
    write_chart(res, out / "summary.png")

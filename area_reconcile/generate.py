"""Synthetic data generator.

Produces four CSV tables that mimic the shape of a municipal property inventory:
buildings (permit data), deeds, architectural-plan areas and tax declarations.
No real person, address or record is used: owners are pseudonymous IDs and every
number is drawn from a seeded random generator.

Realistic problems are injected on purpose (missing declarations, unit-number
typos, owner mismatches, wrong areas, a permit larger than the plan sum) so the
reconciliation pipeline has something to find.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def generate(n_buildings: int = 60, seed: int = 42) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    buildings, deeds, plans, decls = [], [], [], []
    person_counter = 0
    decl_id = 0

    def new_person() -> str:
        nonlocal person_counter
        person_counter += 1
        return f"P{person_counter:05d}"

    for b in range(1, n_buildings + 1):
        building_id = f"B{b:03d}"
        floors = int(rng.integers(3, 9))
        per_floor = int(rng.integers(1, 4))
        n_units = max(4, min(24, floors * per_floor))

        unit_rows = []
        for u in range(1, n_units + 1):
            floor = 0 if u <= max(1, per_floor - 1) and rng.random() < 0.7 else min(floors, 1 + (u - 1) // per_floor)
            unit_type = "commercial" if floor == 0 else "residential"
            net = round(float(rng.uniform(40, 110) if unit_type == "commercial" else rng.uniform(65, 140)), 1)
            unit_rows.append((u, floor, unit_type, net))

        sum_net = sum(r[3] for r in unit_rows)
        common = round(sum_net * float(rng.uniform(0.10, 0.18)), 1)
        plan_gross = sum_net + common
        # In ~25% of buildings the permit shows a somewhat larger gross area than the plan sum.
        permit_gross = round(plan_gross * (1 + (float(rng.uniform(0.012, 0.03)) if rng.random() < 0.25 else 0.0)), 1)

        buildings.append({
            "building_id": building_id,
            "permit_year": int(rng.integers(1975, 2023)),
            "permit_gross_m2": permit_gross,
            "common_area_m2": common,
            "n_units": n_units,
        })

        owners: list[str] = []
        for (u, floor, unit_type, net) in unit_rows:
            owner = owners[int(rng.integers(0, len(owners)))] if owners and rng.random() < 0.08 else new_person()
            owners.append(owner)
            deeds.append({
                "building_id": building_id, "unit_no": u, "floor": floor, "unit_type": unit_type,
                "owner_id": owner, "land_share_num": int(round(net)), "land_share_den": int(round(sum_net)),
            })
            plans.append({"building_id": building_id, "unit_no": u, "net_m2": net})

        base_class = int(rng.integers(1, 6))
        share = common / n_units
        for (u, floor, unit_type, net), owner in zip(unit_rows, owners):
            if rng.random() > 0.92:           # no declaration filed
                continue
            true_gross = net + share
            if rng.random() < 0.07:           # clearly wrong declared area
                declared = true_gross * float(rng.choice([rng.uniform(0.70, 0.88), rng.uniform(1.10, 1.25)]))
            else:
                declared = true_gross + float(rng.normal(0, 2.5))
            declared_no = u
            r = rng.random()
            if r < 0.03:
                declared_no = 0               # unit number left as 0
            elif r < 0.07:
                declared_no = int(rng.choice([x for x in range(1, n_units + 1) if x != u]))   # wrong unit number
            declarant = owner if rng.random() < 0.93 else new_person()
            klass = base_class if rng.random() > 0.03 else int(np.clip(base_class + rng.choice([-1, 1]), 1, 5))
            decl_id += 1
            decls.append({
                "declaration_id": f"D{decl_id:05d}", "building_id": building_id,
                "declared_unit_no": declared_no, "declarant_id": declarant,
                "declared_m2": round(float(declared), 1), "building_class": klass,
            })

    decl_df = pd.DataFrame(decls).sample(frac=1.0, random_state=seed).reset_index(drop=True)
    return {
        "buildings": pd.DataFrame(buildings),
        "deeds": pd.DataFrame(deeds),
        "plans": pd.DataFrame(plans),
        "declarations": decl_df,
    }


def write(out_dir: str | Path, n_buildings: int = 60, seed: int = 42) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, df in generate(n_buildings, seed).items():
        df.to_csv(out / f"{name}.csv", index=False)

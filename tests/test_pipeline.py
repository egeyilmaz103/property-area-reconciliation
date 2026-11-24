import pandas as pd
from area_reconcile import generate, pipeline


def _tables(tmp_path):
    generate.write(tmp_path, n_buildings=12, seed=7)
    return tmp_path


def test_deterministic(tmp_path):
    a = generate.generate(10, 1)["declarations"]
    b = generate.generate(10, 1)["declarations"]
    pd.testing.assert_frame_equal(a, b)


def test_one_row_per_deed_unit(tmp_path):
    d = _tables(tmp_path)
    res = pipeline.run(d)
    deeds = pd.read_csv(d / "deeds.csv")
    assert len(res.units) == len(deeds)
    assert not res.units.duplicated(["building_id", "unit_no"]).any()
    assert (res.units["final_m2"] > 0).all()


def test_declaration_used_once(tmp_path):
    d = _tables(tmp_path)
    res = pipeline.run(d)
    assert res.units["declared_m2"].notna().sum() <= len(pd.read_csv(d / "declarations.csv"))


def test_owner_match_fixes_zero_unit_no():
    units = pd.DataFrame({"building_id": ["B1"] * 2, "unit_no": [1, 2], "owner_id": ["A", "B"], "gross_m2": [100.0, 90.0]})
    decl = pd.DataFrame({"declaration_id": ["D1"], "building_id": ["B1"], "declared_unit_no": [0],
                         "declarant_id": ["B"], "declared_m2": [91.0], "building_class": [3]})
    m, issues = pipeline.match_declarations(units, decl)
    assert ("B1", 2) in m and issues[0]["issue"] == "UNIT_NO_ZERO"


def test_orphan_declaration():
    units = pd.DataFrame({"building_id": ["B1"], "unit_no": [1], "owner_id": ["A"], "gross_m2": [100.0]})
    decl = pd.DataFrame({"declaration_id": ["D1"], "building_id": ["B1"], "declared_unit_no": [9],
                         "declarant_id": ["Z"], "declared_m2": [50.0], "building_class": [3]})
    m, issues = pipeline.match_declarations(units, decl)
    assert not m and issues[0]["issue"] == "ORPHAN_DECLARATION"

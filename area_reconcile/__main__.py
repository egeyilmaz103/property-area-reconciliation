"""CLI: python -m area_reconcile generate|run"""
import argparse

from . import generate, pipeline, report


def main() -> None:
    p = argparse.ArgumentParser(prog="area_reconcile")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="create synthetic CSV data")
    g.add_argument("--out", default="data/synthetic"); g.add_argument("--buildings", type=int, default=60)
    g.add_argument("--seed", type=int, default=42)
    r = sub.add_parser("run", help="reconcile and write outputs")
    r.add_argument("--data", default="data/synthetic"); r.add_argument("--out", default="outputs")
    r.add_argument("--tolerance", type=float, default=10.0)
    a = p.parse_args()
    if a.cmd == "generate":
        generate.write(a.out, a.buildings, a.seed)
        print(f"Wrote synthetic data to {a.out}")
    else:
        res = pipeline.run(a.data, tol=a.tolerance)
        report.write_all(res, a.out)
        u = res.units
        print(f"Buildings: {len(res.buildings)} | Units: {len(u)} | Issues: {len(res.issues)}")
        print(u["decision"].value_counts().to_string())
        print(res.issues["issue"].value_counts().to_string())


main()

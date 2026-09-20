"""gec-eval: score predictions, run a system over HTTP, or stress-test it. Independent of model code."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .io import load_dataset, load_predictions, write_jsonl
from .report import evaluate
from .stress import run_stress
from .sut import HttpSUT, collect_predictions


def _dump(obj: dict, out: str | None) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    if out:
        Path(out).write_text(text, encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(text)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gec-eval")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score", help="score an existing predictions.jsonl")
    s.add_argument("--dataset", required=True)
    s.add_argument("--predictions", required=True)
    s.add_argument("--system", default="unnamed")
    s.add_argument("--out")
    r = sub.add_parser("run", help="call a running API for every example, then score")
    r.add_argument("--dataset", required=True)
    r.add_argument("--api", default="http://localhost:8000")
    r.add_argument("--pipeline", default="o2", choices=["o2", "o3"])
    r.add_argument("--mode", default="reference")
    r.add_argument("--predictions-out")
    r.add_argument("--out")
    t = sub.add_parser("stress", help="perturbation/invariant stress test against a running API")
    t.add_argument("--dataset", required=True)
    t.add_argument("--api", default="http://localhost:8000")
    t.add_argument("--pipeline", default="o2", choices=["o2", "o3"])
    t.add_argument("--mode", default="reference")
    t.add_argument("--out")
    a = ap.parse_args(argv)

    meta, exs = load_dataset(a.dataset)
    if a.cmd == "score":
        _dump(evaluate(meta, exs, load_predictions(a.predictions), system=a.system, dataset_path=a.dataset,
                       preds_path=a.predictions), a.out)
    elif a.cmd == "run":
        sut = HttpSUT(a.api, a.pipeline, a.mode)
        preds = collect_predictions(sut, exs, lambda i, n: print(f"\r{i}/{n}", end="", file=sys.stderr))
        pp = a.predictions_out or "predictions.jsonl"
        write_jsonl(pp, preds)
        _dump(evaluate(meta, exs, preds, system=sut.name, dataset_path=a.dataset, preds_path=pp), a.out)
    else:
        _dump(run_stress(HttpSUT(a.api, a.pipeline, a.mode), exs), a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

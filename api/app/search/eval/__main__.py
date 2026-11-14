"""Measure product search against the scenario sets (docs/plans/30-product-search.md §6.2).

    uv run python -m app.search.eval [--set core --set noisy ...] [--save-baseline]
        [--misses N] [--show-expected]

Runs against the catalogue in DATABASE_URL (a laptop database with the full product file).
Prints the metrics per set, the misses, and what changed since the saved baseline.
"""

import argparse
import asyncio
import json
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass
from functools import partial

from sqlalchemy import text

from app.db import get_engine
from app.search import search as search_module
from app.search import search_products
from app.search.eval.scenarios import SCENARIO_DIR, Scenario, load_all

SETS = ("core", "noisy", "recipes", "negative", "categories", "specific", "vague")
BASELINE = SCENARIO_DIR / "baseline.json"
TOP = 20


@dataclass
class Outcome:
    scenario: Scenario
    ids: list[str]
    ms: float

    def _relevant(self) -> frozenset[str]:
        e = self.scenario.expected
        return e.get("typical", frozenset()) | e.get("acceptable", frozenset())

    def _first_rank(self, ids: frozenset[str]) -> int | None:
        return next((i for i, pid in enumerate(self.ids, 1) if pid in ids), None)

    def checks(self) -> dict[str, bool]:
        """Every check that applies to this scenario: name -> passed."""
        e = self.scenario.expected
        out: dict[str, bool] = {}
        relevant = self._relevant()
        if relevant:
            out["top20"] = self._first_rank(relevant) is not None
            out["top5"] = (self._first_rank(relevant) or 99) <= 5
        if e.get("typical"):
            out["rank1_typical"] = bool(self.ids) and self.ids[0] in e["typical"]
        if "wrong_kind" in e:
            out["clean5"] = not (set(self.ids[:5]) & e["wrong_kind"])
        return out

    def reciprocal_rank(self) -> float | None:
        relevant = self.scenario.expected.get("typical") or self._relevant()
        if not relevant:
            return None
        rank = self._first_rank(relevant)
        return 1 / rank if rank else 0.0

    def passed(self) -> bool:
        return all(self.checks().values())


def _rate(group: list[Outcome], check: str) -> str:
    vals = [c[check] for o in group if check in (c := o.checks())]
    return f"{100 * sum(vals) / len(vals):.0f}%" if vals else "-"


async def run(sets: list[str], save: bool, misses: int, show_expected: bool) -> None:
    engine = get_engine()
    async with engine.connect() as conn:
        scenarios = await load_all(conn, sets)
        empty = [s for s in scenarios if any(not v for v in s.expected.values())]
        if empty:
            print(f"! {len(empty)} scenarios have an expectation that matches no product:")
            for s in empty[:20]:
                print(f"    {s.id}: {[g for g, v in s.expected.items() if not v]}")
        outcomes = []
        for s in scenarios:
            start = time.perf_counter()
            hits = await search_products(conn, s.q, claims=s.claims, category=s.category, limit=TOP)
            await conn.rollback()  # end the transaction that set the trigram threshold
            outcomes.append(
                Outcome(s, [h.product_id for h in hits], (time.perf_counter() - start) * 1000)
            )
        names = dict((await conn.execute(text("SELECT id, name_fi FROM products"))).all())
    await engine.dispose()

    by_set: dict[str, list[Outcome]] = defaultdict(list)
    for o in outcomes:
        by_set[o.scenario.set].append(o)

    columns = ("pass", "top20", "top5", "rank1", "clean5")
    print(f"\n{'set':<10}{'n':>6}" + "".join(f"{c:>8}" for c in columns) + "    MRR  p50ms  p95ms")
    for name in sets:
        group = by_set.get(name, [])
        if not group:
            continue
        rate = partial(_rate, group)
        rrs = [r for o in group if (r := o.reciprocal_rank()) is not None]
        times = sorted(o.ms for o in group)
        p95 = times[min(len(times) - 1, int(0.95 * len(times)))]
        passed = sum(o.passed() for o in group)
        print(
            f"{name:<10}{len(group):>6}{100 * passed / len(group):>7.0f}%{rate('top20'):>8}"
            f"{rate('top5'):>8}{rate('rank1_typical'):>8}{rate('clean5'):>8}"
            f"{statistics.fmean(rrs) if rrs else 0:>7.2f}"
            f"{statistics.median(times):>7.0f}{p95:>7.0f}"
        )

    for name in sets:
        failed = [o for o in by_set.get(name, []) if not o.passed()]
        if not failed or misses == 0:
            continue
        print(f"\nMisses in {name} ({len(failed)}):")
        for o in failed[:misses]:
            bad = [k for k, v in o.checks().items() if not v]
            claims = f" [{','.join(o.scenario.claims)}]" if o.scenario.claims else ""
            print(f'  {o.scenario.id}: "{o.scenario.q}"{claims} fails {", ".join(bad)}')
            e = o.scenario.expected
            for pid in o.ids[:5]:
                grade = next(
                    (g for g in ("typical", "acceptable", "wrong_kind") if pid in e.get(g, ())), ""
                )
                print(f"      {pid} {names.get(pid, '?')[:60]:<60} {grade}")
            if show_expected and e.get("typical"):
                sample = ", ".join(
                    f"{p} {names.get(p, '?')[:40]}" for p in sorted(e["typical"])[:3]
                )
                print(f"      expected e.g. {sample}")

    current = {o.scenario.id: o.passed() for o in outcomes}
    if BASELINE.exists():
        old = json.loads(BASELINE.read_text())
        fixed = sorted(k for k, v in current.items() if v and old.get(k) is False)
        broke = sorted(k for k, v in current.items() if not v and old.get(k) is True)
        print(f"\nSince baseline: {len(fixed)} fixed, {len(broke)} broken")
        for k in broke[:30]:
            print(f"  broken: {k}")
        for k in fixed[:15]:
            print(f"  fixed:  {k}")
        core_ids = {o.scenario.id for o in by_set.get("core", [])}
        core_broke = [k for k in broke if k in core_ids]
        if core_broke:
            print(f"! core regressions: {core_broke}")
    if save:
        merged = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
        merged.update(current)
        BASELINE.write_text(json.dumps(dict(sorted(merged.items())), indent=0) + "\n")
        print(f"Baseline saved: {BASELINE}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", action="append", choices=SETS, dest="sets")
    parser.add_argument("--save-baseline", action="store_true")
    parser.add_argument("--misses", type=int, default=15, help="misses to list per set")
    parser.add_argument("--show-expected", action="store_true")
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="try another weight without editing the code, e.g. W_FTS=0.25",
    )
    args = parser.parse_args()
    for item in args.param:
        name, value = item.split("=", 1)
        if not hasattr(search_module, name):
            parser.error(f"unknown parameter {name}")
        setattr(search_module, name, type(getattr(search_module, name))(value))
        print(f"{name} = {value}")
    asyncio.run(run(args.sets or list(SETS), args.save_baseline, args.misses, args.show_expected))


if __name__ == "__main__":
    main()

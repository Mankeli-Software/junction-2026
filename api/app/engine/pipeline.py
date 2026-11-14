"""decide(): validate, resolve, filter, rank, price and explain (technical-plan.md §4).

Pure: everything comes in through EngineInput, so the same input gives the same output.
"""

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from app.schemas import (
    Alternative,
    AskedLine,
    Clarification,
    Decision,
    DeliverySummary,
    EngineInput,
    EngineOutput,
    Flag,
    GroupSubtotal,
    LineRequest,
    Localized,
    ProductRecord,
    QuoteLine,
    ReasonCode,
    Rejection,
    RequestedUnit,
    RuleSet,
    StockStatus,
    TextKey,
    Trace,
    TraceRemoval,
)

from . import text, units
from .filters import Candidate, Context, Removal, check

# Order of the filter steps (§4.2), so the trace lists removals in pipeline order.
STEP_ORDER = [
    ReasonCode.DIET_CLAIM_MISSING,
    ReasonCode.ALLERGEN_CONFLICT,
    ReasonCode.OFFER_UNAVAILABLE,
    ReasonCode.UNAVAILABLE,
    ReasonCode.DELIVERY_DATE_UNREACHABLE,
    ReasonCode.PAST_CLOSING_TIME,
    ReasonCode.UNIT_UNKNOWN,
    ReasonCode.UNIT_CONVERSION_UNKNOWN,
    ReasonCode.PARTIAL_STOCK,
    ReasonCode.PRICE_NOT_VALID,
]
AMBIGUITY_WINDOW = 5  # top search results looked at for "spans categories"
MAX_OPTIONS = 3
MAX_ALTERNATIVES = 2


@dataclass
class LineResult:
    line: QuoteLine | None = None
    flags: list[Flag] = field(default_factory=list)
    clarification: Clarification | None = None
    rejection: Rejection | None = None


def decide(data: EngineInput) -> EngineOutput:
    rules = data.rules
    products = {p.product_id: p for p in data.products}
    ctx_offers = {o.product_id: o for o in data.offers}

    if len({line.line_id for line in data.lines}) != len(data.lines):
        results = [_reject(line, ReasonCode.INPUT_INVALID, {}, rules) for line in data.lines]
    else:
        results = []
        for line in data.lines:
            ctx = Context(line, data.kitchen.exclusions, ctx_offers, rules, data.business_now)
            results.append(_line(line, data, products, ctx))
    return _order(results, data)


# --- One line ---------------------------------------------------------------------------


def _line(
    line: LineRequest, data: EngineInput, products: dict[str, ProductRecord], ctx: Context
) -> LineResult:
    rules = data.rules
    if not _valid(line, data):
        return _reject(line, ReasonCode.INPUT_INVALID, {}, rules)

    # Resolve: a named product, "my usual", or the search results for this line.
    named = False
    if line.product_id is not None:
        if line.product_id not in products:
            return _reject(line, ReasonCode.PRODUCT_NOT_FOUND, {"product": line.product_id}, rules)
        ids, named = [line.product_id], True
    elif line.usual:
        usual = _usual(line, data)
        if not usual:
            return _clarify(line, ReasonCode.USUAL_NOT_FOUND, {"product": line.text or ""}, rules)
        if len(usual) > 1:
            options = [a for pid in usual if (a := _option(pid, products, ctx)) is not None]
            return _clarify(
                line, ReasonCode.AMBIGUOUS_MATCH, {"product": line.text or ""}, rules, options
            )
        ids, named = usual, True
    else:
        ids = [pid for pid in data.candidates.get(line.line_id, []) if pid in products]
        if not ids:
            return _clarify(line, ReasonCode.NO_MATCH, {"product": _asked(line)}, rules)

    survivors, removals = _filter([products[pid] for pid in ids], ctx)

    if not survivors:
        if all(r.code == ReasonCode.OFFER_UNAVAILABLE for _, r in removals):
            first = removals[0][1]
            return _clarify(line, first.code, first.fields, rules)
        first = removals[0][1]  # the best search hit's reason is the most relevant one
        return _reject(line, first.code, first.fields, rules)

    if not named and line.category is None:
        window = survivors[:AMBIGUITY_WINDOW]
        categories = sorted({c.product.category for c in window})
        if len(categories) > 1:
            best = [
                _rank([c for c in window if c.product.category == cat], data)[0]
                for cat in categories
            ]
            options = [_alternative(c) for c in _rank(best, data)[:MAX_OPTIONS]]
            return _clarify(
                line, ReasonCode.AMBIGUOUS_MATCH, {"product": _asked(line)}, rules, options
            )

    ranked = _rank(survivors, data)
    return _priced(line, ranked, _trace(len(ids), removals, len(survivors), rules), rules)


def _valid(line: LineRequest, data: EngineInput) -> bool:
    if not (line.product_id or line.usual or line.text or line.category):
        return False
    if line.unit == RequestedUnit.package and not line.package_word:
        return False
    return line.needed_by >= data.business_now.date()


def _usual(line: LineRequest, data: EngineInput) -> list[str]:
    words = (line.text or "").lower().split()
    return sorted(
        {
            item.product_id
            for item in data.history.usual_items
            if all(w in f"{item.name.fi} {item.name.en}".lower() for w in words)
        }
    )


def _filter(
    products: list[ProductRecord], ctx: Context
) -> tuple[list[Candidate], list[tuple[Candidate, Removal]]]:
    survivors, removals = [], []
    for product in products:
        candidate = Candidate(product)
        removal = check(candidate, ctx)
        if removal is None:
            survivors.append(candidate)
        else:
            removals.append((candidate, removal))
    return survivors, removals


def _rank(candidates: list[Candidate], data: EngineInput) -> list[Candidate]:
    """Lowest total, then verified stock, then products ordered before, then product id."""
    ordered_before = {h.product_id for h in data.history.recent_lines}
    return sorted(
        candidates,
        key=lambda c: (
            c.total_cents,
            c.stock != StockStatus.verified,
            c.product.product_id not in ordered_before,
            c.product.product_id,
        ),
    )


def _trace(
    found: int, removals: list[tuple[Candidate, Removal]], left: int, rules: RuleSet
) -> Trace:
    counts = Counter(r.code for _, r in removals)
    return Trace(
        found=found,
        removed=[
            TraceRemoval(reason_code=code, count=counts[code], text=text.short(rules, code))
            for code in STEP_ORDER
            if counts[code]
        ],
        left=left,
        ranking_rule=text.text(rules, TextKey.RANKING_RULE),
    )


def _priced(line: LineRequest, ranked: list[Candidate], trace: Trace, rules: RuleSet) -> LineResult:
    chosen = ranked[0]
    product, amount = chosen.product, chosen.amount
    assert amount is not None
    reasons: list[str] = []
    explain = [text.text(rules, TextKey.CHOSEN_CHEAPEST, date=text.day(line.needed_by))]
    flags: list[Flag] = []

    if amount.size is not None and amount.in_asked_unit > line.quantity:
        reasons.append(ReasonCode.ROUNDED_UP)
        explain.append(
            text.message(
                rules,
                ReasonCode.ROUNDED_UP,
                product=product.name,
                quantity=text.number(Decimal(amount.sales_units)),
                unit=text.unit_name(rules, chosen.sales_unit, plural=True),
            )
        )
    if chosen.stock == StockStatus.unverified:
        reasons.append(ReasonCode.AVAILABILITY_UNVERIFIED)
        flags.append(_flag(ReasonCode.AVAILABILITY_UNVERIFIED, line, product, rules))

    measure = units.base_measure(product, chosen.sales_unit)
    quote_line = QuoteLine(
        line_id=line.line_id,
        group=line.group,
        asked=AskedLine(
            text=line.text,
            quantity=line.quantity,
            unit=line.unit,
            package_word=line.package_word,
            needed_by=line.needed_by,
        ),
        product_id=product.product_id,
        name=product.name,
        image_url=product.image_url,
        sales_unit=chosen.sales_unit,
        sales_unit_label=text.unit_name(rules, chosen.sales_unit),
        quantity_sales_units=amount.sales_units,
        quantity_in_asked_unit=amount.in_asked_unit,
        unit_price_gross=chosen.unit_price,
        price_per_base_unit=(chosen.unit_price / measure[0]).quantize(Decimal("0.0001"))
        if measure
        else None,
        base_unit=measure[1] if measure else None,
        line_total_cents=chosen.total_cents,
        delivery_date=line.needed_by,
        stock_status=chosen.stock,
        origin=product.origin,
        reason_codes=reasons,
        reason_text=text.join(*explain),
        trace=trace,
        alternatives=[_alternative(c) for c in ranked[1 : 1 + MAX_ALTERNATIVES]],
    )
    return LineResult(line=quote_line, flags=flags)


def _flag(code: ReasonCode, line: LineRequest, product: ProductRecord, rules: RuleSet) -> Flag:
    return Flag(
        flag_key=f"{code.value}:{line.line_id}",
        code=code,
        line_ids=[line.line_id],
        kind="acknowledge",
        text=text.message(rules, code, product=product.name),
    )


def _alternative(c: Candidate) -> Alternative:
    assert c.amount is not None
    return Alternative(
        product_id=c.product.product_id,
        label=c.product.name,
        quantity_sales_units=c.amount.sales_units,
        line_total_cents=c.total_cents,
    )


def _option(
    product_id: str, products: dict[str, ProductRecord], ctx: Context
) -> Alternative | None:
    if product_id not in products:
        return None
    candidate = Candidate(products[product_id])
    return _alternative(candidate) if check(candidate, ctx) is None else None


def _asked(line: LineRequest) -> str:
    return line.text or line.category or ""


def _clarify(
    line: LineRequest,
    code: ReasonCode,
    fields: dict[str, text.Field],
    rules: RuleSet,
    options: list[Alternative] | None = None,
) -> LineResult:
    question = text.message(rules, code, **fields)
    return LineResult(
        clarification=Clarification(line_id=line.line_id, question=question, options=options or [])
    )


def _reject(
    line: LineRequest, code: ReasonCode, fields: dict[str, text.Field], rules: RuleSet
) -> LineResult:
    return LineResult(
        rejection=Rejection(
            line_id=line.line_id,
            reason_code=code,
            text=text.message(rules, code, **fields),
            next_step=text.next_step(rules, code, **fields),
        )
    )


# --- The whole order --------------------------------------------------------------------


def _order(results: list[LineResult], data: EngineInput) -> EngineOutput:
    rules = data.rules
    lines = [r.line for r in results if r.line is not None]
    flags = [f for r in results for f in r.flags]
    rejections = [r.rejection for r in results if r.rejection is not None]
    clarification = next((r.clarification for r in results if r.clarification), None)
    total = sum(line.line_total_cents for line in lines)
    dates = sorted({line.delivery_date for line in lines})

    if clarification is not None:
        decision, speak = Decision.needs_clarification, clarification.question
    elif lines:
        decision = Decision.ready
        parts = [
            text.text(
                rules,
                TextKey.SUMMARY_READY,
                count=len(lines),
                total=text.euros(total),
                dates=_dates(dates),
            )
        ]
        parts += [text.join(r.text, r.next_step) for r in rejections]
        if flags:
            parts.append(text.text(rules, TextKey.SUMMARY_NOTES, notes=len(flags)))
        speak = text.join(*parts)
    else:
        decision = Decision.rejected
        speak = text.join(
            text.text(rules, TextKey.SUMMARY_REJECTED),
            *[text.join(r.text, r.next_step) for r in rejections],
        )

    groups: dict[str, list[QuoteLine]] = {}
    for line in lines:
        if line.group is not None:
            groups.setdefault(line.group, []).append(line)

    return EngineOutput(
        decision=decision,
        lines=lines,
        groups=[
            GroupSubtotal(
                group=name,
                line_ids=[line.line_id for line in members],
                subtotal_cents=sum(line.line_total_cents for line in members),
            )
            for name, members in groups.items()
        ],
        flags=flags,
        clarification=clarification,
        rejections=rejections,
        not_ordered=[],
        total_cents=total,
        delivery=DeliverySummary(earliest=dates[0], latest=dates[-1]) if dates else None,
        speak=speak,
        rules_ref=rules.ref,
    )


def _dates(dates: list) -> Localized:
    days = [text.day(d) for d in dates]
    if len(days) == 1:
        return days[0]
    return Localized(
        fi=", ".join(d.fi for d in days[:-1]) + " ja " + days[-1].fi,
        en=", ".join(d.en for d in days[:-1]) + " and " + days[-1].en,
    )

"""decide(): validate, resolve, filter, rank, price and explain (technical-plan.md §4).

Pure: everything comes in through EngineInput, so the same input gives the same output.
"""

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
    RankedCandidate,
    ReasonCode,
    Rejection,
    RemovedProduct,
    RequestedUnit,
    RuleSet,
    StockStatus,
    TextKey,
    Trace,
    TraceRemoval,
)

from . import substitute, text
from .filters import Candidate, Context, Removal, allergens_unknown, check

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
    ReasonCode.PACKAGING_AMBIGUOUS,
    ReasonCode.PARTIAL_STOCK,
    ReasonCode.PRICE_NOT_VALID,
]
AMBIGUITY_WINDOW = 5  # top search results looked at for "spans categories"
MAX_OPTIONS = 3
MAX_ALTERNATIVES = 2
SPOKEN_LINES = 3  # lines named in the spoken summary; the rest are counted
# A line whose best candidate fails on these goes back to the buyer as a question.
ASK_BUYER = {ReasonCode.UNIT_CONVERSION_UNKNOWN, ReasonCode.PACKAGING_AMBIGUOUS}
# Removals because the product doesn't suit the kitchen, not because of price or stock.
KITCHEN = {ReasonCode.DIET_CLAIM_MISSING, ReasonCode.ALLERGEN_CONFLICT}


@dataclass
class LineResult:
    line: QuoteLine | None = None
    flags: list[Flag] = field(default_factory=list)
    allergens_unknown: bool = False  # goes into the order's ALLERGEN_NO_LISTING notice
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
    given = [pid for pid in data.candidates.get(line.line_id, []) if pid in products]
    sub_ids = set(data.substitutes.get(line.line_id, []))
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
        ids = [pid for pid in given if pid not in sub_ids]
    subs = [pid for pid in given if pid in sub_ids and pid not in ids]
    if not ids and not subs:
        return _clarify(line, ReasonCode.NO_MATCH, {"product": _asked(line)}, rules)

    checked = _check([products[pid] for pid in ids], ctx)
    survivors = [c for c, r in checked if r is None]
    removals = [(c, r) for c, r in checked if r is not None]

    # The best candidate that suits the kitchen couldn't be priced: ask to try again
    # rather than quote a worse one or reject the line (§4.2).
    first_safe = next(((c, r) for c, r in checked if r is None or r.code not in KITCHEN), None)
    if first_safe is not None and first_safe[1] is not None:
        if first_safe[1].code == ReasonCode.OFFER_UNAVAILABLE:
            return _clarify(line, ReasonCode.OFFER_UNAVAILABLE, first_safe[1].fields, rules)

    if not survivors:
        first = removals[0][1]  # the best search hit's reason is the most relevant one
        if first.code in ASK_BUYER:
            return _clarify(line, first.code, first.fields, rules)
        if subs:
            return _substitute(line, data, products, ctx, checked, subs)
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
    trace = _trace(len(ids), removals, ranked, rules)
    result = _priced(line, ranked, trace, rules)
    result.allergens_unknown = allergens_unknown(ranked[0].product, ctx.exclusions, rules)
    return result


def _substitute(
    line: LineRequest,
    data: EngineInput,
    products: dict[str, ProductRecord],
    ctx: Context,
    checked: list[tuple[Candidate, Removal | None]],
    subs: list[str],
) -> LineResult:
    """The line can't be filled from its own candidates: run the substitution ladder."""
    rules = data.rules
    original, why = checked[0]
    assert why is not None
    curated = {s for c, _ in checked for s in c.product.substitutions}
    sub_checked = _check([products[pid] for pid in subs], ctx)
    steps = [
        substitute.Step(c, substitute.step_of(original.product, c.product, curated), i)
        for i, (c, r) in enumerate(sub_checked)
        if r is None
    ]
    removals = [(c, r) for c, r in [*checked, *sub_checked] if r is not None]
    lead = text.message(rules, why.code, **why.fields)
    if not steps:
        fields: dict[str, text.Field] = {"product": original.product.name}
        return LineResult(
            rejection=Rejection(
                line_id=line.line_id,
                reason_code=ReasonCode.CALLBACK_REQUESTED,
                text=text.join(lead, text.message(rules, ReasonCode.CALLBACK_REQUESTED, **fields)),
                next_step=text.next_step(rules, ReasonCode.CALLBACK_REQUESTED, **fields),
            )
        )

    ordered_before = {h.product_id for h in data.history.recent_lines}
    choice = substitute.choose(original, substitute.rank(steps, ordered_before), ctx.offers, rules)
    ranked = [choice.chosen.candidate] + [
        s.candidate for s in choice.ranked if s is not choice.chosen
    ]
    if choice.code in substitute.AUTOMATIC.values():
        trace = _trace(len(checked) + len(sub_checked), removals, ranked, rules)
        result = _priced(line, ranked, trace, rules, (choice.code, original.product, lead))
        result.allergens_unknown = allergens_unknown(ranked[0].product, ctx.exclusions, rules)
        return result

    chosen = choice.chosen.candidate
    question = text.message(
        rules,
        choice.code,
        substitute=chosen.product.name,
        total=text.euros(chosen.total_cents),
        percent=choice.percent if choice.percent is not None else "",
    )
    options = [_alternative(c) for c in ranked[:MAX_OPTIONS]]
    return LineResult(
        clarification=Clarification(
            line_id=line.line_id, question=text.join(lead, question), options=options
        )
    )


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


def _check(products: list[ProductRecord], ctx: Context) -> list[tuple[Candidate, Removal | None]]:
    """Every candidate with the reason it was removed, or None if it passed, in input order."""
    checked = []
    for product in products:
        candidate = Candidate(product)
        checked.append((candidate, check(candidate, ctx)))
    return checked


def _rank(candidates: list[Candidate], data: EngineInput) -> list[Candidate]:
    """Waste first: candidates within the round-up limits, then the least surplus. Then the
    lowest total, verified stock, products ordered before, Finnish origin and product id."""
    ordered_before = {h.product_id for h in data.history.recent_lines}
    return sorted(
        candidates,
        key=lambda c: (
            not c.within_limits,
            Decimal(0) if c.within_limits else c.surplus,
            c.total_cents,
            c.stock != StockStatus.verified,
            c.product.product_id not in ordered_before,
            c.product.origin != "FI",
            c.product.product_id,
        ),
    )


def _trace(
    found: int,
    removals: list[tuple[Candidate, Removal]],
    ranked: list[Candidate],
    rules: RuleSet,
) -> Trace:
    """`ranked[0]` is the chosen candidate."""
    removed: dict[ReasonCode, list[Candidate]] = {}
    for candidate, removal in removals:
        removed.setdefault(removal.code, []).append(candidate)
    return Trace(
        found=found,
        removed=[
            TraceRemoval(
                reason_code=code,
                count=len(removed[code]),
                text=text.short(rules, code),
                products=[
                    RemovedProduct(product_id=c.product.product_id, name=c.product.name)
                    for c in removed[code]
                ],
            )
            for code in STEP_ORDER
            if code in removed
        ],
        left=len(ranked),
        ranking_rule=text.text(rules, TextKey.RANKING_RULE),
        ranked=[
            RankedCandidate(
                rank=i + 1,
                product_id=c.product.product_id,
                name=c.product.name,
                price_per_base_unit=_per_base(c)[0],
                stock_status=c.stock,
                chosen=i == 0,
            )
            for i, c in enumerate(ranked)
        ],
    )


def _per_base(c: Candidate) -> tuple[Decimal | None, str | None]:
    """Price per litre or kilo, to four decimals, and its unit label."""
    found = substitute.price_per_base(c)
    if found is None:
        return None, None
    return found[0].quantize(Decimal("0.0001")), found[1]


def _priced(
    line: LineRequest,
    ranked: list[Candidate],
    trace: Trace,
    rules: RuleSet,
    swap: tuple[ReasonCode, ProductRecord, Localized] | None = None,
) -> LineResult:
    """Price `ranked[0]`. `swap` is set when it replaces a product automatically: the
    SUBSTITUTED_* code, the replaced product and why it was replaced."""
    chosen = ranked[0]
    product, amount = chosen.product, chosen.amount
    assert amount is not None
    reasons: list[str] = []
    flags: list[Flag] = []
    if swap is None:
        explain = [text.text(rules, TextKey.CHOSEN_CHEAPEST, date=text.day(line.needed_by))]
    else:
        code, replaced, why = swap
        reasons.append(code)
        flags.append(_flag(code, line, replaced, rules, substitute=product.name))
        explain = [why, text.message(rules, code, product=replaced.name, substitute=product.name)]

    if chosen.surplus > 0:
        reasons.append(ReasonCode.ROUNDED_UP)
        rounded = {
            "quantity": text.number(Decimal(amount.sales_units)),
            "unit": text.unit_name(rules, chosen.sales_unit, plural=amount.sales_units != 1),
        }
        explain.append(text.message(rules, ReasonCode.ROUNDED_UP, product=product.name, **rounded))
        if not chosen.within_limits:  # more waste than the limits allow: the buyer must see it
            flags.append(_flag(ReasonCode.ROUNDED_UP, line, product, rules, **rounded))
    if amount.from_name:
        reasons.append(ReasonCode.PACK_SIZE_FROM_NAME)
        flags.append(_flag(ReasonCode.PACK_SIZE_FROM_NAME, line, product, rules))
    if chosen.stock == StockStatus.unverified:
        reasons.append(ReasonCode.AVAILABILITY_UNVERIFIED)
        flags.append(_flag(ReasonCode.AVAILABILITY_UNVERIFIED, line, product, rules))

    per_base, base_unit = _per_base(chosen)
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
        price_per_base_unit=per_base,
        base_unit=base_unit,
        line_total_cents=chosen.total_cents,
        delivery_date=line.needed_by,
        stock_status=chosen.stock,
        origin=product.origin,
        reason_codes=reasons,
        reason_text=text.join(*explain),
        trace=trace,
        alternatives=[
            _alternative(c)
            for c in ranked[1:]
            if c.within_limits or not chosen.within_limits  # no waste-heavy alternatives
        ][:MAX_ALTERNATIVES],
    )
    return LineResult(line=quote_line, flags=flags)


def _flag(
    code: ReasonCode,
    line: LineRequest,
    product: ProductRecord,
    rules: RuleSet,
    **fields: text.Field,
) -> Flag:
    return Flag(
        flag_key=f"{code.value}:{line.line_id}",
        code=code,
        line_ids=[line.line_id],
        kind="acknowledge",
        text=text.message(rules, code, product=product.name, **fields),
    )


def _no_listing_flag(lines: list[QuoteLine], data: EngineInput) -> Flag:
    """One notice per order for every product whose allergens can't be checked (vision §10)."""
    labels = [data.rules.kitchen[e].label for e in sorted(data.kitchen.exclusions)]
    return Flag(
        flag_key=ReasonCode.ALLERGEN_NO_LISTING.value,
        code=ReasonCode.ALLERGEN_NO_LISTING,
        line_ids=[line.line_id for line in lines],
        kind="acknowledge",
        text=text.message(
            data.rules,
            ReasonCode.ALLERGEN_NO_LISTING,
            products=_listed(*(line.name for line in lines)),
            choice=_listed(*labels),
        ),
    )


def _listed(*items: Localized) -> Localized:
    return Localized(fi=", ".join(i.fi for i in items), en=", ".join(i.en for i in items))


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
    unknown = [r.line for r in results if r.line is not None and r.allergens_unknown]
    if unknown:
        flags.append(_no_listing_flag(unknown, data))
    rejections = [r.rejection for r in results if r.rejection is not None]
    clarification = next((r.clarification for r in results if r.clarification), None)
    total = sum(line.line_total_cents for line in lines)
    dates = sorted({line.delivery_date for line in lines})

    if clarification is not None:
        decision, speak = Decision.needs_clarification, clarification.question
    elif lines:
        decision = Decision.ready
        parts = [text.text(rules, TextKey.SUMMARY_READY)]
        parts += [_spoken_line(line, rules) for line in lines[:SPOKEN_LINES]]
        if len(lines) == 1 and lines[0].alternatives:
            alternative = lines[0].alternatives[0]
            parts.append(
                text.text(
                    rules,
                    TextKey.SUMMARY_ALTERNATIVE,
                    product=alternative.label,
                    total=text.euros(alternative.line_total_cents),
                )
            )
        if len(lines) > SPOKEN_LINES:
            parts.append(text.text(rules, TextKey.SUMMARY_MORE, count=len(lines) - SPOKEN_LINES))
        parts.append(
            text.text(rules, TextKey.SUMMARY_TOTAL, dates=_dates(dates), total=text.euros(total))
        )
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


def _spoken_line(line: QuoteLine, rules: RuleSet) -> Localized:
    """The top pick for one line (vision §5): product, amount and line total."""
    return text.text(
        rules,
        TextKey.SUMMARY_LINE,
        product=line.name,
        quantity=text.number(Decimal(line.quantity_sales_units)),
        unit=text.unit_name(rules, line.sales_unit, plural=line.quantity_sales_units != 1),
        total=text.euros(line.line_total_cents),
    )


def _dates(dates: list) -> Localized:
    days = [text.day(d) for d in dates]
    if len(days) == 1:
        return days[0]
    return Localized(
        fi=", ".join(d.fi for d in days[:-1]) + " ja " + days[-1].fi,
        en=", ".join(d.en for d in days[:-1]) + " and " + days[-1].en,
    )

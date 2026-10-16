"""The Submitted Deck's metrics (ADR 0026 s1, as amended by ADR 0028).

    deck_metrics(Deck, FormatInputs) -> DeckMetrics

Pure: every card fact and statistic comes in through `FormatInputs`. Basic
lands are not in `FormatInputs.cards`; the deck counts them by colour.
"""

from typing import Any

from ..schemas.deck import Deck, DeckFiring, DeckMetrics, NotableOmission
from . import fitness as fx
from .draft import FormatInputs
from .mana import effective_lands, shortfalls

# How many firings a deck reports, largest first. The summary names a few;
# the total already prices the rest.
TOP_FIRINGS = 5


def deck_metrics(deck: Deck, inputs: FormatInputs) -> DeckMetrics:
    cards = [inputs.cards[oid] for oid in deck.main]
    spells = [c for c in cards if fx.LAND_TAG not in c["tags"]]
    curve = _curve(spells)
    synergy, firings = _synergy(cards, inputs)
    short = shortfalls(cards, deck.basics, inputs.mana_sources)
    worst = max(short, key=lambda sf: sf.short, default=None)
    if worst is not None and worst.short == 0:
        worst = None  # only a shortfall is a fact worth naming
    average_mv = sum(c["cmc"] for c in spells) / len(spells) if spells else 0.0
    lands = effective_lands(cards, deck.basics, inputs.mana_sources)
    target = inputs.land_target.lands_for(average_mv)
    return DeckMetrics(
        card_quality=_card_quality(spells, inputs.stats),
        curve=curve,
        curve_distance=sum(
            abs(curve[mv] - inputs.cfg.target_curve[mv]) for mv in curve
        ),
        synergy=synergy,
        synergy_firings=firings,
        creatures=sum(1 for c in cards if fx.CREATURE_TAG in c["tags"]),
        removal=sum(1 for c in cards if fx.REMOVAL_TAG in c["tags"]),
        mana_shortfall=worst.short if worst else 0.0,
        mana_short_spell=worst.oracle_id if worst else None,
        mana_short_colors=worst.colors if worst else None,
        mana_required=worst.required if worst else None,
        mana_available=worst.available if worst else None,
        spells_short=sum(1 for sf in short if sf.short > 0),
        average_mana_value=average_mv,
        effective_lands=lands,
        land_target=target,
        land_distance=inputs.land_target.distance(lands, target),
        notable_omission=_notable_omission(spells, deck, inputs),
    )


def _card_quality(spells: list[dict[str, Any]], stats: fx.Stats) -> float:
    """Mean GIH WR of the nonland cards, against the format average."""
    if not spells:
        return 0.0
    mean = sum(stats.gih_wr(c["oracle_id"]) for c in spells) / len(spells)
    return mean - stats.format_avg_wr


def _curve(spells: list[dict[str, Any]]) -> dict[int, int]:
    """Nonland cards per mana value, bucketed as the curve term buckets them."""
    curve = dict.fromkeys(range(1, 7), 0)
    for card in spells:
        curve[fx.mv_bucket(card["cmc"])] += 1
    return curve


def _synergy(
    cards: list[dict[str, Any]], inputs: FormatInputs
) -> tuple[float, list[DeckFiring]]:
    """Each nonland card's synergy with the rest of the deck, through `fitness.synergy`.

    Without a baseline, so each firing pays its absolute value (ADR 0006),
    and each card's total is capped as at a pick. A firing is counted from
    both ends, exactly as `fitness.synergy` reads an edge.
    """
    total = 0.0
    firings: list[DeckFiring] = []
    for i, card in enumerate(cards):
        if fx.LAND_TAG in card["tags"]:
            continue
        rest = cards[:i] + cards[i + 1 :]  # another copy of itself still counts
        result = fx.synergy(card, rest, inputs.edges, inputs.cfg)
        total += result.total
        firings += [
            DeckFiring(
                oracle_id=card["oracle_id"],
                tag_on_card=fr.tag_on_card,
                complementary_tag=fr.complementary_tag,
                count=fr.pool_count,
                pp=fr.pp,
                contributing=list(fr.contributing_oracle_ids),
            )
            for fr in result.top_firings
        ]
    firings.sort(key=lambda f: -f.pp)
    return total, firings[:TOP_FIRINGS]


def _notable_omission(
    spells: list[dict[str, Any]], deck: Deck, inputs: FormatInputs
) -> NotableOmission | None:
    """At most one: the best playable sideboard card, if far better than the weakest.

    ADR 0026 s1. "Playable" means castable in the colours the deck's spells
    already use; "better" is GIH WR, the same card quality the deck is
    graded on; "far" is the fitness function's `mistake_gap`, the gap at
    which a pick is a mistake. Lands are left out on both sides.
    """
    if not spells:
        return None
    colours = "".join(c for c in "WUBRG" if any(c in s["colors"] for s in spells))
    gih = inputs.stats.gih_wr
    weakest = min(spells, key=lambda c: gih(c["oracle_id"]))
    candidates = [
        inputs.cards[oid]
        for oid in deck.sideboard
        if fx.LAND_TAG not in inputs.cards[oid]["tags"]
        and fx.playable_in(inputs.cards[oid], colours)
    ]
    best = max(candidates, key=lambda c: gih(c["oracle_id"]), default=None)
    if best is None:
        return None
    gap = gih(best["oracle_id"]) - gih(weakest["oracle_id"])
    if gap <= inputs.cfg.mistake_gap:
        return None
    return NotableOmission(
        oracle_id=best["oracle_id"],
        gih_wr=gih(best["oracle_id"]),
        instead_of=weakest["oracle_id"],
        instead_of_gih_wr=gih(weakest["oracle_id"]),
        gap=gap,
    )

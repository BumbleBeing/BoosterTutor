"""The Draft Summary's brief: the whole draft and its Reviewed Deck, as text (ADR 0030 s2).

Pure: a `DraftAnalysis`, the `Deck` with its `DeckMetrics` and
`DeckRatings`, the `CardFacts` for the draft's cards and the format's
`FormatInputs` in; a `SummaryBrief` out.

Unlike a Pick Note's brief, this one is written with hindsight: every
pick, what wheeled, and the deck the drafter built. It is still only
facts. Every number is display text from `format.py`, and the summary may
state no number this text does not, which the eval checks by string
match. No Pick Note prose goes in: notes are written when a pick is first
opened (ADR 0024 s3), so which ones exist depends on what the user
clicked, and the summary must not.

The format's own statistics are not here: they are the Format Primer,
cached block 2 of the call (`primer.py`).
"""

import uuid
from collections import Counter

from pydantic import BaseModel

from ..analysis import fitness as fx
from ..analysis.draft import FormatInputs
from ..schemas.deck import Deck, DeckFiring, DeckMetrics, DeckRatings, MetricRating
from ..schemas.draft_analysis import CardScore, DraftAnalysis, PickAnalysis
from ..schemas.draft_log import PACKS
from . import format as fmt
from .card_facts import CardFacts
from .pick import comparison, name_line

COLOUR_NAMES = {"W": "white", "U": "blue", "B": "black", "R": "red", "G": "green"}
CAVEAT = (
    "Grades are relative to 17Lands players, who play better than average: "
    "a C is an average 17Lands deck. A percentile is the share of the "
    "format's 40-card decks on 17Lands that this deck is at least as good as."
)
# How many of the deck's tag-pair firings the brief names, largest first.
FIRINGS_NAMED = 3


class SummaryBrief(BaseModel):
    text: str
    # Every (pack, pick) in the draft: a Key Pick must be one of them.
    picks: list[tuple[int, int]]


def summary_brief(
    analysis: DraftAnalysis,
    deck: Deck,
    metrics: DeckMetrics,
    ratings: DeckRatings,
    cards: dict[uuid.UUID, CardFacts],
    inputs: FormatInputs,
) -> SummaryBrief:
    named = (
        {c.oracle_id for p in analysis.picks for c in p.cards}
        | set(deck.main)
        | set(deck.sideboard)
    )
    missing = named - cards.keys()
    if missing:
        raise LookupError(f"{len(missing)} card(s) in this draft have no card facts")

    lines = _header(analysis, inputs.cfg)
    lines += _picks(analysis, cards)
    lines += _noted(analysis, cards)
    lines += _wheels(analysis, cards, inputs.stats.format_avg_wr)
    lines += _deck(deck, cards, inputs)
    lines += _ratings(metrics, ratings, cards, inputs)
    return SummaryBrief(
        text="\n".join(lines) + "\n",
        picks=[(p.pack_number, p.pick_number) for p in analysis.picks],
    )


# --------------------------------------------------------------------------
# The draft
# --------------------------------------------------------------------------


def _header(analysis: DraftAnalysis, cfg: fx.FitnessConfig) -> list[str]:
    return [
        (
            f"{analysis.set_code.upper()} {analysis.event_type}: a finished draft "
            f"of {PACKS * analysis.pack_size} picks, {PACKS} packs of "
            f"{analysis.pack_size}, and the deck built from it."
        ),
        (
            f"Bands, by fitness below the pack's best card: solid within "
            f"{fmt.pp(cfg.solid_gap)}, questionable within "
            f"{fmt.pp(cfg.mistake_gap)}, mistake beyond {fmt.pp(cfg.mistake_gap)}. "
            "Indifferent: every card in the pack was solid."
        ),
        *(
            []
            if analysis.has_taxonomy
            else ["This set has no tags yet, so synergy and removal are not scored."]
        ),
    ]


def _label(pick: PickAnalysis) -> str:
    return f"P{pick.pack_number}p{pick.pick_number}"


def _picks(analysis: DraftAnalysis, cards: dict[uuid.UUID, CardFacts]) -> list[str]:
    lines = [
        "",
        "## The picks",
        (
            "One line each: the pick, the card taken, its verdict, and its gap to "
            "the pack's best card. P2p7 is pack 2, pick 7."
        ),
    ]
    for pick in analysis.picks:
        if pick.gap is None:
            gap = "a basic land, never scored"
        elif pick.gap == 0:
            gap = "the best card"
        else:
            gap = f"{fmt.pp(pick.gap)} below the best"
        lines.append(
            f"- {_label(pick)} {cards[pick.picked].name} · {pick.verdict} · {gap}"
        )
    tally = Counter(p.verdict for p in analysis.picks)
    lines.append(
        "Verdicts: "
        + ", ".join(
            f"{tally[v]} {v}"
            for v in ("solid", "questionable", "mistake", "indifferent")
        )
        + "."
    )
    last = analysis.picks[-1].pool.predicted_archetype
    lines.append(f"Leading pair before the last pick: {last or 'none'}.")
    return lines


def _noted(analysis: DraftAnalysis, cards: dict[uuid.UUID, CardFacts]) -> list[str]:
    noted = [p for p in analysis.picks if p.noted]
    lines = ["", "## The Noted Picks"]
    if not noted:
        return [*lines, "None: no pick was questionable, a mistake or narrow."]
    lines.append(
        "Critical: questionable or a mistake. Narrow: the pack's only solid "
        "card, taken while close alternatives tempted."
    )
    for pick in noted:
        by_id = {c.oracle_id: c for c in pick.cards}
        taken = by_id[pick.picked]
        kind = "narrow" if pick.narrow else "critical"
        lines += ["", f"### {_label(pick)} ({kind}, {pick.verdict})"]
        lines.append(f"Card taken: {_scored(taken, cards)}")
        if kind == "critical" and pick.best is not None:
            best = by_id[pick.best]
            lines.append(f"Best card: {_scored(best, cards)}")
            if pick.gap is not None:
                lines.append(f"Gap: {fmt.pp(pick.gap)} below the best card.")
                lines += comparison("best card minus card taken", best, taken)
        else:
            for runner_up in [c for c in pick.cards if c.scored][1:3]:
                assert taken.total is not None and runner_up.total is not None
                lines.append(
                    f"Runner-up: {_scored(runner_up, cards)}, "
                    f"{fmt.pp(taken.total - runner_up.total)} below the card taken"
                )
    return lines


def _scored(card: CardScore, cards: dict[uuid.UUID, CardFacts]) -> str:
    line = name_line(cards[card.oracle_id])
    if card.total is None or card.gih_wr is None:
        return f"{line} · not scored (basic land)"
    return (
        f"{line} · fitness {fmt.score(card.total)} · GIH WR {fmt.win_rate(card.gih_wr)}"
    )


def _wheels(
    analysis: DraftAnalysis, cards: dict[uuid.UUID, CardFacts], format_avg: float
) -> list[str]:
    taken = {(p.pack_number, p.pick_number): p.picked for p in analysis.picks}
    lines = [
        "",
        "## What wheeled",
        (
            "A pack comes back after passing the seven other drafters. A good "
            f"card has a GIH WR at or above the format average of "
            f"{fmt.win_rate(format_avg)}; a good card wheeling says its color "
            "may be open."
        ),
    ]
    for pack in analysis.wheels:
        lines += [
            "",
            f"### Pack {pack.pack_number}",
            "By color, across the pack's laps:",
        ]
        for signal in pack.colors:
            lines.append(
                f"- {signal.color}: {signal.good_cards_wheeled} good card(s) of "
                f"{signal.cards_wheeled} wheeled; the table took "
                f"{signal.cards_taken_by_table}"
            )
        # Basics have win rates too, but one wheeling signals nothing.
        good = [
            (lap, card)
            for lap in pack.laps
            for card in lap.wheeled
            if card.above_average
            and not cards[card.oracle_id].type_line.startswith("Basic Land")
        ]
        if not good:
            lines.append("No good card wheeled.")
            continue
        lines.append("Good cards that wheeled:")
        for lap, card in good:
            assert card.gih_wr is not None
            line = (
                f"- from pick {lap.first_pick} to pick {lap.returned_at}: "
                f"{cards[card.oracle_id].name} · GIH WR {fmt.win_rate(card.gih_wr)}"
            )
            if card.alsa is not None:
                line += f" · usually last seen at pick {fmt.count(card.alsa)}"
            pick = taken[(pack.pack_number, lap.returned_at)]
            line += (
                " · the drafter took it"
                if pick == card.oracle_id
                else f" · the drafter took {cards[pick].name}"
            )
            lines.append(line)
    return lines


# --------------------------------------------------------------------------
# The deck
# --------------------------------------------------------------------------


def _deck(
    deck: Deck, cards: dict[uuid.UUID, CardFacts], inputs: FormatInputs
) -> list[str]:
    spells = [oid for oid in deck.main if fx.LAND_TAG not in inputs.cards[oid]["tags"]]
    lands = [oid for oid in deck.main if fx.LAND_TAG in inputs.cards[oid]["tags"]]
    colours = Counter(c for oid in spells for c in inputs.cards[oid]["colors"])
    copies = Counter(spells)
    order = sorted(copies, key=lambda oid: (inputs.cards[oid]["cmc"], cards[oid].name))

    lines = [
        "",
        "## The Reviewed Deck",
        "Colors of its spells (cards of each color; a gold card counts for each): "
        + ", ".join(f"{c} {colours[c]}" for c in "WUBRG" if colours[c]),
        f"Spells ({len(spells)}), by mana value:",
    ]
    for oid in order:
        facts = cards[oid]
        name = f"{facts.name} {facts.mana_cost}" if facts.mana_cost else facts.name
        if copies[oid] > 1:
            name += f" ×{copies[oid]}"
        lines.append(
            f"- {name} · {facts.type_line} · "
            f"GIH WR {fmt.win_rate(inputs.stats.gih_wr(oid))}"
        )
    land_names = sorted(cards[oid].name for oid in lands)
    basics = [
        f"{name} ×{deck.basics[colour]}"
        for name, colour in (
            ("Plains", "W"),
            ("Island", "U"),
            ("Swamp", "B"),
            ("Mountain", "R"),
            ("Forest", "G"),
        )
        if deck.basics.get(colour)
    ]
    count = len(lands) + sum(deck.basics.values())
    lines.append(f"Lands ({count}): " + "; ".join([*land_names, *basics]))
    lines.append(f"Sideboard: {len(deck.sideboard)} cards.")
    return lines


def _ratings(
    metrics: DeckMetrics,
    ratings: DeckRatings,
    cards: dict[uuid.UUID, CardFacts],
    inputs: FormatInputs,
) -> list[str]:
    by_metric = {m.metric: m for m in ratings.metrics}
    if ratings.rated:
        assert ratings.grade is not None and ratings.percentile is not None
        assert ratings.predicted_win_rate is not None
        lines = [
            "",
            "## Deck Ratings",
            CAVEAT,
            (
                f"Overall: grade {ratings.grade} ({fmt.percentile(ratings.percentile)})"
                f", a predicted win rate of {fmt.win_rate(ratings.predicted_win_rate)}."
            ),
        ]
    else:
        lines = [
            "",
            "## Deck Ratings",
            (
                f"Deck Ratings: {ratings.message}. This format has no fitted ratings, "
                "so the metrics below have no grades."
            ),
        ]

    def graded(name: str) -> str:
        rating: MetricRating = by_metric[name]
        if rating.grade is None or rating.percentile is None:
            return ""
        return f" · grade {rating.grade} ({fmt.percentile(rating.percentile)})"

    cfg = inputs.cfg
    curve = ", ".join(
        f"{'6+' if mv == 6 else mv}: {n}" for mv, n in sorted(metrics.curve.items())
    )
    target = ", ".join(
        f"{'6+' if mv == 6 else mv}: {n}" for mv, n in sorted(cfg.target_curve.items())
    )
    lines += [
        (
            f"- Card quality: the spells' mean GIH WR is "
            f"{fmt.signed_pp(metrics.card_quality)} against the format average of "
            f"{fmt.win_rate(inputs.stats.format_avg_wr)}" + graded("card_quality")
        ),
        (
            f"- Curve: spells by mana value {curve}, against the format's target "
            f"{target}; {metrics.curve_distance} card(s) off the target in all"
            + graded("curve_distance")
        ),
        (
            f"- Synergy: {fmt.signed_pp(metrics.synergy)} from tag pairs among the "
            "deck's own cards" + graded("synergy")
        ),
        *[
            f"  {cards[f.oracle_id].name}: its {_tag(f.tag_on_card)} finds "
            f"{f.count} {_tag(f.complementary_tag)} card(s) in the deck, "
            f"{fmt.signed_pp(f.pp)}"
            for f in _distinct(metrics.synergy_firings)[:FIRINGS_NAMED]
        ],
        f"- Creatures: {metrics.creatures}" + graded("creatures"),
        f"- Removal: {metrics.removal}" + graded("removal"),
        f"- Mana: {_mana(metrics, cards)}" + graded("mana_shortfall"),
        (
            f"- Lands: {fmt.count(metrics.effective_lands)} effective lands (lands, "
            f"plus part of a land for each Fixer) against a target of "
            f"{metrics.land_target}, for spells averaging "
            f"{fmt.mana_value(metrics.average_mana_value)} mana value; "
            f"{fmt.count(metrics.land_distance)} off, being short weighing double"
            + graded("land_distance")
        ),
    ]
    omission = metrics.notable_omission
    if omission is not None:
        lines.append(
            f"Notable omission: {cards[omission.oracle_id].name} (GIH WR "
            f"{fmt.win_rate(omission.gih_wr)}) is in the sideboard while "
            f"{cards[omission.instead_of].name} (GIH WR "
            f"{fmt.win_rate(omission.instead_of_gih_wr)}) is in the deck, "
            f"{fmt.pp(omission.gap)} apart."
        )
    return lines


def _distinct(firings: list[DeckFiring]) -> list[DeckFiring]:
    """One firing per card and tag pair: two copies of a card fire alike."""
    seen: set[tuple[uuid.UUID, str, str]] = set()
    out = []
    for f in firings:
        key = (f.oracle_id, f.tag_on_card, f.complementary_tag)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def _mana(metrics: DeckMetrics, cards: dict[uuid.UUID, CardFacts]) -> str:
    if metrics.mana_short_spell is None:
        return "every spell has the sources it needs (Karsten's 40-card table)"
    assert metrics.mana_short_colors is not None
    assert metrics.mana_available is not None
    colours = " or ".join(COLOUR_NAMES[c] for c in metrics.mana_short_colors)
    return (
        f"the largest shortfall, by Karsten's 40-card table: "
        f"{cards[metrics.mana_short_spell].name} needs {metrics.mana_required} "
        f"{colours} sources; the deck has {fmt.count(metrics.mana_available)}, "
        f"{fmt.count(metrics.mana_shortfall)} short. {metrics.spells_short} "
        "spell(s) are short of sources"
    )


def _tag(tag: str) -> str:
    """`_removal_` and `creature_sac_outlet` as words."""
    return tag.strip("_").replace("_", " ")

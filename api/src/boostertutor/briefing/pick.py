"""One Noted Pick's brief: everything a Pick Note may say, as text (ADR 0024 s5).

Pure: a `DraftAnalysis`, the `CardFacts` for its cards, and the format's
`FitnessConfig` in; a `PickBrief` out. Three rules shape it.

- Every number is display text from `format.py`, and any comparison Claude
  might want to make (the gap, where it comes from) is computed here, so
  the note never has to do arithmetic and the eval can check it by string
  match.
- Oracle text only for the cards the note is about: the card taken and the
  best card, and for a Narrow Pick the two runners-up. Every other card is
  one line: name, cost, rarity, type line and its scores.
- Only what was true at the pick: this pick's pack, scores and pool. It
  never reads another pick or the wheels, so a live note in a practice
  draft and a Draft Review's note on the same pick read the same brief.
"""

import uuid
from collections import Counter
from typing import Literal

from pydantic import BaseModel

from ..analysis.fitness import FitnessConfig
from ..schemas.draft_analysis import CardScore, DraftAnalysis, PickAnalysis
from ..schemas.draft_log import PACKS
from . import format as fmt
from .card_facts import CardFacts

NoteKind = Literal["critical", "narrow"]

# The parts of a fitness score, as the brief names them. `role` has been
# removal scarcity alone since ADR 0018, so the brief calls it that.
PARTS = (
    ("gih_wr", "GIH WR"),
    ("color_fit", "colour fit"),
    ("curve", "curve"),
    ("role", "removal"),
    ("synergy", "synergy"),
)

KIND_LINES: dict[NoteKind, str] = {
    "critical": "critical: explain what this pick cost",
    "narrow": "narrow: the one right answer among close alternatives, and the "
    "drafter found it",
}


class PickBrief(BaseModel):
    pack_number: int
    pick_number: int
    kind: NoteKind
    text: str


def pick_brief(
    analysis: DraftAnalysis,
    cards: dict[uuid.UUID, CardFacts],
    cfg: FitnessConfig,
    *,
    pack_number: int,
    pick_number: int,
) -> PickBrief:
    """The brief for one Noted Pick. A pick that is not noted has none."""
    pick = next(
        (
            p
            for p in analysis.picks
            if (p.pack_number, p.pick_number) == (pack_number, pick_number)
        ),
        None,
    )
    if pick is None:
        raise ValueError(f"the draft has no P{pack_number}p{pick_number}")
    if not pick.noted:
        raise ValueError(f"P{pack_number}p{pick_number} is not a Noted Pick")
    named = {c.oracle_id for c in pick.cards} | set(_pool_before(analysis, pick))
    missing = named - cards.keys()
    if missing:
        raise LookupError(f"{len(missing)} card(s) in this pick have no card facts")

    kind: NoteKind = "narrow" if pick.narrow else "critical"
    lines = _header(analysis, pick, kind, cfg)
    lines += _cards(pick, kind, cards)
    lines += _pool(pick, cards, analysis)
    return PickBrief(
        pack_number=pack_number,
        pick_number=pick_number,
        kind=kind,
        text="\n".join(lines) + "\n",
    )


# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------


def _header(
    analysis: DraftAnalysis, pick: PickAnalysis, kind: NoteKind, cfg: FitnessConfig
) -> list[str]:
    overall = (pick.pack_number - 1) * analysis.pack_size + pick.pick_number
    lines = [
        (
            f"{analysis.set_code.upper()} {analysis.event_type}. "
            f"Pack {pick.pack_number}, pick {pick.pick_number} "
            f"(pick {overall} of {PACKS * analysis.pack_size})."
        ),
        f"Verdict: {pick.verdict}",
        f"Note: {KIND_LINES[kind]}",
        (
            f"Bands, by fitness below the pack's best card: solid within "
            f"{fmt.pp(cfg.solid_gap)}, questionable within "
            f"{fmt.pp(cfg.mistake_gap)}, mistake beyond {fmt.pp(cfg.mistake_gap)}."
        ),
    ]
    if not analysis.has_taxonomy:
        lines.append("This set has no tags yet, so synergy and removal are not scored.")
    return lines


def _cards(
    pick: PickAnalysis, kind: NoteKind, cards: dict[uuid.UUID, CardFacts]
) -> list[str]:
    by_id = {c.oracle_id: c for c in pick.cards}
    taken = by_id[pick.picked]
    best = by_id[pick.best] if pick.best is not None else None
    detailed = [taken.oracle_id]

    lines = ["", *_detail("Card taken", taken, cards)]
    if kind == "critical" and best is not None and best.oracle_id != taken.oracle_id:
        detailed.append(best.oracle_id)
        lines += ["", *_detail("Best card", best, cards)]
        if pick.gap is not None:
            lines += [
                "",
                f"Gap: the card taken scored {fmt.pp(pick.gap)} below the best card.",
                *_comparison("best card minus card taken", best, taken),
            ]
    if kind == "narrow":
        # The cards are sorted best first, and the card taken is the best.
        for runner_up in [c for c in pick.cards if c.scored][1:3]:
            detailed.append(runner_up.oracle_id)
            lines += ["", *_detail("Runner-up", runner_up, cards)]
            assert taken.total is not None and runner_up.total is not None
            lines += [
                f"  {fmt.pp(taken.total - runner_up.total)} below the card taken.",
                *_comparison("card taken minus this runner-up", taken, runner_up),
            ]

    others = [c for c in pick.cards if c.oracle_id not in detailed]
    if others:
        lines += ["", "Other cards in the pack, best first:"]
        lines += [f"- {_one_line(c, best, cards)}" for c in others]
    return lines


def _pool(
    pick: PickAnalysis, cards: dict[uuid.UUID, CardFacts], analysis: DraftAnalysis
) -> list[str]:
    pool = pick.pool
    if pool.size == 0:
        return ["", "Pool before this pick: empty, this is the first pick."]
    # The pool's cards are the picks before this one, read from this
    # analysis. Every earlier pick is in it, because picks are in order.
    earlier = _pool_before(analysis, pick)
    copies = Counter(earlier)
    names = [
        cards[oid].name if copies[oid] == 1 else f"{cards[oid].name} ×{copies[oid]}"
        for oid in dict.fromkeys(earlier)
    ]
    colours = ", ".join(f"{c} {n}" for c, n in pool.colors.items())
    curve = ", ".join(
        f"{'6+' if mv == 6 else mv}: {n}" for mv, n in sorted(pool.curve.items()) if mv
    )
    return [
        "",
        f"Pool before this pick: {pool.size} cards, in pick order:",
        # Semicolons, because card names have commas: "Bofur, Reliable Guardian".
        f"  {'; '.join(names)}",
        f"  Colours (cards of each colour, lands left out): {colours}",
        f"  Curve (non-land cards by mana value): {curve}",
        f"  Creatures {pool.creatures}, removal {pool.removal}",
        f"  Leading pair: {pool.predicted_archetype or 'none yet'}",
    ]


def _pool_before(analysis: DraftAnalysis, pick: PickAnalysis) -> list[uuid.UUID]:
    """The cards taken before this pick, in pick order."""
    return [
        p.picked
        for p in analysis.picks
        if (p.pack_number, p.pick_number) < (pick.pack_number, pick.pick_number)
    ]


# --------------------------------------------------------------------------
# One card
# --------------------------------------------------------------------------


def _name_line(facts: CardFacts) -> str:
    """ "Lakeshore Apothecary {1}{U} · common · Creature — Human Cleric"."""
    name = f"{facts.name} {facts.mana_cost}" if facts.mana_cost else facts.name
    return f"{name} · {facts.rarity} · {facts.type_line}"


def _detail(
    label: str, card: CardScore, cards: dict[uuid.UUID, CardFacts]
) -> list[str]:
    facts = cards[card.oracle_id]
    lines = [f"{label}: {_name_line(facts)}"]
    if facts.oracle_text:
        lines += [f"  Text: {line}" for line in facts.oracle_text.splitlines()]
    if not card.scored:
        lines.append(
            "  Basic land, never scored: basics are free when building, so "
            "taking one is always a mistake."
        )
        return lines
    assert card.total is not None and card.gih_wr is not None
    lines.append(
        f"  fitness {fmt.score(card.total)} ({card.fitness_class}) = "
        f"GIH WR {fmt.win_rate(card.gih_wr)} over {fmt.games(card.games)}"
        + "".join(
            f", {label} {fmt.signed_pp(getattr(card, part))}"
            for part, label in PARTS[1:]
        )
    )
    if card.insufficient_data:
        lines.append("  Thin sample: treat this card's win rate with caution.")
    for firing in card.firings:
        contributing = Counter(firing.contributing)
        sources = ", ".join(
            cards[oid].name if n == 1 else f"{cards[oid].name} ×{n}"
            for oid, n in contributing.items()
        )
        lines.append(
            f"  Synergy: its {_tag(firing.tag_on_card)} finds "
            f"{firing.pool_count} {_tag(firing.complementary_tag)} card(s) in the "
            f"pool, against {fmt.count(firing.expected_count)} usually found by "
            f"now: {fmt.signed_pp(firing.pp)}. From: {sources}."
        )
    return lines


def _comparison(label: str, higher: CardScore, lower: CardScore) -> list[str]:
    """Where a gap between two scored cards comes from, part by part."""
    diffs = [
        (name, (getattr(higher, part) or 0.0) - (getattr(lower, part) or 0.0))
        for part, name in PARTS
    ]
    largest = max(diffs, key=lambda d: d[1])
    return [
        f"  Where it comes from ({label}): "
        + ", ".join(f"{name} {fmt.signed_pp(d)}" for name, d in diffs)
        + ".",
        f"  Largest part: {largest[0]}.",
    ]


def _one_line(
    card: CardScore, best: CardScore | None, cards: dict[uuid.UUID, CardFacts]
) -> str:
    line = _name_line(cards[card.oracle_id])
    if not card.scored:
        return f"{line} · not scored (basic land)"
    assert card.total is not None and card.gih_wr is not None
    line += (
        f" · fitness {fmt.score(card.total)} · GIH WR {fmt.win_rate(card.gih_wr)}"
        f" · {card.fitness_class}"
    )
    if best is not None and best.total is not None:
        line += f" · {fmt.pp(best.total - card.total)} below the best"
    if card.insufficient_data:
        line += " · thin sample"
    return line


def _tag(tag: str) -> str:
    """`_removal_` and `creature_sac_outlet` as words."""
    return tag.strip("_").replace("_", " ")


def noted_pick_briefs(
    analysis: DraftAnalysis, cards: dict[uuid.UUID, CardFacts], cfg: FitnessConfig
) -> list[PickBrief]:
    """A brief for every Noted Pick in the draft, in pick order."""
    return [
        pick_brief(
            analysis, cards, cfg, pack_number=p.pack_number, pick_number=p.pick_number
        )
        for p in analysis.picks
        if p.noted
    ]

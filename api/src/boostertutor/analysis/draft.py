"""Score every pick of a draft (development plan 3.3, ADRs 0003-0018).

    analyze_draft(DraftLog, FormatInputs) -> DraftAnalysis

Pure: the database reads happen in `boostertutor.format_inputs`, which
builds a `FormatInputs`. This module turns the fitness function's per-pack
scoring into a whole draft: the pool grows pick by pick, every distinct card
in each pack is scored against the pool before the pick, and the card taken
gets its verdict.

Ported from DraftDouble's `ingest/draft_link.py` (`build_draft_view`), minus
everything about display: names, images and layout belong to the API and
the frontend (Phase 5), not to the analysis.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

from ..schemas import DraftLog
from ..schemas.draft_analysis import (
    CardScore,
    DraftAnalysis,
    PickAnalysis,
    PoolState,
    SynergyFiring,
)
from . import fitness as fx
from .wheel import wheel_analysis

# (oracle_id, pack_number, enabler, payoff, tag_on_card) -> E[n_eff], ADR 0017.
Baseline = dict[tuple[uuid.UUID, int, str, str, str], float]

PP_DECIMALS = 3


def fitness_card(
    oracle_id: uuid.UUID,
    *,
    type_line: str,
    mana_cost: str | None,
    cmc: float,
    colors: str,
    color_identity: str,
    tags: list[str],
) -> dict[str, Any]:
    """The slice of a card the fitness function reads.

    Two tags are derived from the type line rather than authored: `creature`
    and `land`. The curve and colour terms read `land` (a land is not a
    one-drop, and is playable in any pair its colour identity touches,
    ADR 0012 s6). `_removal_` is authored by hand and is the only thing that
    counts as removal; there is no oracle-text heuristic.
    """
    all_tags = list(tags)
    if "Creature" in type_line and fx.CREATURE_TAG not in all_tags:
        all_tags.append(fx.CREATURE_TAG)
    if "Land" in type_line and fx.LAND_TAG not in all_tags:
        all_tags.append(fx.LAND_TAG)
    card: dict[str, Any] = {
        "oracle_id": oracle_id,
        "colors": colors,
        "color_identity": color_identity,
        "cmc": cmc,
        "tags": all_tags,
        "type_line": type_line,
    }
    # Hybrid cards are playable as either colour; a land takes its options
    # from its colour identity. After the tags, since this reads `land`.
    card["color_options"] = fx.playable_colors({**card, "mana_cost": mana_cost})
    return card


def is_basic_land(card: dict[str, Any]) -> bool:
    """Plains, Island, Swamp, Mountain, Forest. Never scored (DraftDouble #28).

    A basic's "in hand" win rate only says which colours win, and basics are
    free when building, so taking one is always a mistake.
    """
    return "Basic Land" in str(card["type_line"])


@dataclass(frozen=True)
class FormatInputs:
    """Everything the analysis reads about one format, loaded in one go.

    `cards` holds a `fitness_card` dict for every card the set's packs can
    hold. `edges` are the authored `tag_pairs` (enabler, payoff, coefficient,
    decay), and `baseline` the synergy expectations built from the measured
    histogram for those edges' current decays.
    """

    set_code: str
    event_type: str
    stats_snapshot: Any  # dt.date; Any so tests can pass a plain string
    cards: dict[uuid.UUID, dict[str, Any]]
    stats: fx.Stats
    edges: list[dict[str, Any]] = field(default_factory=list)
    baseline: Baseline = field(default_factory=dict)
    # ALSA per card: not a scoring input (ADR 0018), but a fact the wheel
    # analysis reports ("usually gone by pick 3").
    alsa: dict[uuid.UUID, float] = field(default_factory=dict)
    cfg: fx.FitnessConfig = field(default_factory=fx.FitnessConfig)


def synergy_expectations(
    rows: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> Baseline:
    """Turn the stored histogram into E[n_eff] per (card, pack, edge, end).

        E[n_eff] = sum(observations x n_eff(n, decay)) / sum(observations)

    The decay comes from the edge as it is *now*, which is why the table
    stores counts rather than expectations: re-tuning a decay changes the
    expectation without invalidating the measurement (ADR 0017). The
    denominator counts every appearance of the card, n = 0 included.
    A row for an edge deleted since the measurement is skipped.
    """
    decay = {(e["enabler"], e["payoff"]): e["decay"] for e in edges}
    weighted: dict[tuple[uuid.UUID, int, str, str, str], float] = {}
    totals: dict[tuple[uuid.UUID, int, str, str, str], int] = {}
    for row in rows:
        edge = (row["enabler"], row["payoff"])
        if edge not in decay:
            continue
        key = (
            row["oracle_id"],
            row["pack_number"],
            row["enabler"],
            row["payoff"],
            row["tag_on_card"],
        )
        obs = row["observations"]
        n_eff = fx.effective_count(row["complement_count"], decay[edge])
        weighted[key] = weighted.get(key, 0.0) + obs * n_eff
        totals[key] = totals.get(key, 0) + obs
    return {k: weighted[k] / totals[k] for k in weighted if totals[k]}


def analyze_draft(log: DraftLog, inputs: FormatInputs) -> DraftAnalysis:
    """Every pick's scores, classes and verdict, and the pool before it."""
    if (log.set_code, log.event_type) != (inputs.set_code, inputs.event_type):
        raise ValueError(
            f"a {log.set_code}/{log.event_type} draft can't be analysed with "
            f"{inputs.set_code}/{inputs.event_type} data"
        )
    missing = {
        oid for pick in log.picks for oid in pick.pack_cards if oid not in inputs.cards
    }
    if missing:
        raise ValueError(f"{len(missing)} card(s) in the draft have no card data")

    cfg = inputs.cfg
    pool: list[dict[str, Any]] = []  # every card taken so far
    picks: list[PickAnalysis] = []
    for pick in log.picks:
        # The fitness terms never count a basic land in the pool: a Swamp is
        # not a one-drop. `pool` keeps it for the pool summary.
        fitness_pool = [c for c in pool if not is_basic_land(c)]
        t = (pick.pack_number - 1) * log.pack_size + pick.pick_number

        # Two copies of a common are one choice, so each card is scored once.
        distinct = list(dict.fromkeys(pick.pack_cards))
        scorable = [
            inputs.cards[oid]
            for oid in distinct
            if not is_basic_land(inputs.cards[oid])
        ]
        scored = (
            fx.score_pack(
                scorable,
                fitness_pool,
                t=t,
                pack_no=pick.pack_number,
                stats=inputs.stats,
                edges=inputs.edges,
                cfg=cfg,
                baseline=inputs.baseline,
            )
            if scorable
            else []
        )
        classes = fx.classify_pack(scored, cfg) if scored else {}
        by_id = {cf.oracle_id: cf for cf in scored}
        best = max(scored, key=lambda cf: cf.total) if scored else None
        taken = by_id.get(pick.picked)

        cards = [_card_score(oid, by_id.get(oid), classes.get(oid)) for oid in distinct]
        cards.sort(key=lambda c: (c.total is None, -(c.total or 0.0)))
        verdict = fx.verdict(scored, pick.picked, cfg, pack_size=len(distinct))
        narrow = fx.is_narrow_pick(scored, pick.picked, cfg, pack_size=len(distinct))
        picks.append(
            PickAnalysis(
                pack_number=pick.pack_number,
                pick_number=pick.pick_number,
                picked=pick.picked,
                verdict=verdict,
                best=best.oracle_id if best else None,
                gap=_pp(best.total - taken.total) if best and taken else None,
                commitment=_pp(fx.commitment(t, cfg)),
                narrow=narrow,
                noted=fx.is_noted(verdict, narrow=narrow),
                pool=_pool_state(pool),
                cards=cards,
            )
        )
        pool.append(inputs.cards[pick.picked])

    return DraftAnalysis(
        set_code=log.set_code,
        event_type=log.event_type,
        stats_snapshot=inputs.stats_snapshot,
        has_taxonomy=bool(inputs.edges),
        pack_size=log.pack_size,
        picks=picks,
        wheels=wheel_analysis(
            log,
            inputs.cards,
            gih_wr={oid: wr for oid, (wr, _) in inputs.stats.overall.items()},
            alsa=inputs.alsa,
            format_avg_wr=inputs.stats.format_avg_wr,
        ),
    )


def _pp(value: float) -> float:
    # `+ 0.0` turns -0.0 (a zero tax, negated) into a plain 0.0.
    return round(value, PP_DECIMALS) + 0.0


def _card_score(
    oracle_id: uuid.UUID, cf: fx.CardFitness | None, fitness_class: str | None
) -> CardScore:
    if cf is None:  # a basic land
        return CardScore(oracle_id=oracle_id, scored=False)
    return CardScore(
        oracle_id=oracle_id,
        scored=True,
        total=_pp(cf.total),
        gih_wr=_pp(cf.base_unconditioned),
        color_fit=_pp(cf.color_fit),
        curve=_pp(cf.curve),
        role=_pp(cf.role),
        synergy=_pp(cf.synergy),
        games=cf.n_games,
        insufficient_data=cf.insufficient_data,
        fitness_class=fitness_class,
        firings=[
            SynergyFiring(
                tag_on_card=fr.tag_on_card,
                complementary_tag=fr.complementary_tag,
                pool_count=fr.pool_count,
                effective_count=_pp(fr.effective_count),
                expected_count=_pp(fr.expected_count),
                coefficient=fr.coefficient,
                pp=_pp(fr.pp),
                contributing=list(fr.contributing_oracle_ids),
            )
            for fr in cf.top_firings
        ],
    )


def _pool_state(pool: list[dict[str, Any]]) -> PoolState:
    spells = [c for c in pool if fx.LAND_TAG not in c["tags"]]
    curve = dict.fromkeys(range(7), 0)
    for card in spells:
        curve[int(min(max(card["cmc"], 0), 6))] += 1
    return PoolState(
        size=len(pool),
        colors=fx.colored_counts(pool),
        curve=curve,
        creatures=sum(1 for c in pool if fx.CREATURE_TAG in c["tags"]),
        removal=sum(1 for c in pool if fx.REMOVAL_TAG in c["tags"]),
        predicted_archetype=fx.predicted_archetype(pool),
    )

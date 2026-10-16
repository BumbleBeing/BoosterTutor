"""The Format Primer: what every Draft Summary is told about the format (ADR 0030 s3).

Pure: `PrimerFacts` in, text out. The facts are loaded by
`boostertutor.format_primer` from `archetype_stats` and `card_draft_stats`.

The primer is cached block 2 of the Draft Summary call, so it must be the
same bytes for every draft of the format: everything is sorted here, and
nothing about a draft, a user or the time goes in. It changes only when a
new Stats Snapshot is ingested. There is no measured statistic for a
format's speed, so the primer says nothing about it rather than guess.
"""

import datetime as dt

from pydantic import BaseModel

from . import format as fmt

COLOURS = "WUBRG"


class ArchetypeRate(BaseModel):
    archetype: str  # a colour pair, sorted WUBRG: "BR", "WU"
    win_rate: float  # in percent
    games: int


class CommonRate(BaseModel):
    name: str
    gih_wr: float
    games: int


class PrimerFacts(BaseModel):
    set_code: str
    event_type: str
    stats_snapshot: dt.date
    format_avg_wr: float
    archetypes: list[ArchetypeRate]
    # Colour letter -> its best mono-coloured commons, best first.
    top_commons: dict[str, list[CommonRate]]


def format_primer(facts: PrimerFacts) -> str:
    pairs = sorted(facts.archetypes, key=lambda a: (-a.win_rate, a.archetype))
    lines = [
        (
            f"Format primer: {facts.set_code.upper()} {facts.event_type}, "
            f"17Lands statistics of {facts.stats_snapshot.isoformat()}."
        ),
        f"The format's average GIH WR: {fmt.win_rate(facts.format_avg_wr)}.",
        "",
        "Color pairs by deck win rate, best first:",
        *[
            f"- {a.archetype} {fmt.win_rate(a.win_rate)} over {fmt.games(a.games)}"
            for a in pairs
        ],
        "",
        "The best commons of each color, by GIH WR:",
    ]
    for colour in COLOURS:
        commons = sorted(
            facts.top_commons.get(colour, []), key=lambda c: (-c.gih_wr, c.name)
        )
        if commons:
            lines.append(
                f"- {colour}: "
                + "; ".join(f"{c.name} {fmt.win_rate(c.gih_wr)}" for c in commons)
            )
    return "\n".join(lines) + "\n"

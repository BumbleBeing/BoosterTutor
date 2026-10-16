"""The Format Primer: cached block 2 of every Draft Summary (ADR 0030 s3)."""

import datetime as dt

from boostertutor.briefing.primer import (
    ArchetypeRate,
    CommonRate,
    PrimerFacts,
    format_primer,
)


def facts(**changes: object) -> PrimerFacts:
    base = PrimerFacts(
        set_code="hob",
        event_type="PremierDraft",
        stats_snapshot=dt.date(2026, 10, 1),
        format_avg_wr=56.3,
        archetypes=[
            ArchetypeRate(archetype="WG", win_rate=49.735, games=1323),
            ArchetypeRate(archetype="BR", win_rate=57.578, games=85459),
        ],
        top_commons={
            "R": [CommonRate(name="Pinecone Strike", gih_wr=58.04, games=40211)],
            "B": [
                CommonRate(name="Reverent Howl", gih_wr=57.2, games=30120),
                CommonRate(name="Crude Bent Blade", gih_wr=56.95, games=29000),
            ],
        },
    )
    return base.model_copy(update=changes)


def test_the_primer_states_each_pair_best_first_with_its_games() -> None:
    text = format_primer(facts())
    assert "HOB PremierDraft" in text
    assert "average GIH WR: 56.3%" in text
    br, wg = text.index("BR 57.6% over 85,459 games"), text.index("WG 49.7%")
    assert br < wg


def test_the_primer_lists_each_colour_s_best_commons_in_wubrg_order() -> None:
    text = format_primer(facts())
    assert "B: Reverent Howl 57.2%; Crude Bent Blade 57.0%" in text
    assert text.index("- B: ") < text.index("- R: ")


def test_the_primer_is_the_same_text_however_its_facts_were_ordered() -> None:
    """Cached block 2 must be byte-identical across drafts (ADR 0024 s6)."""
    shuffled = facts(archetypes=list(reversed(facts().archetypes)))
    assert format_primer(shuffled) == format_primer(facts())

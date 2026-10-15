"""Save a format's analysis inputs, trimmed to one draft's cards, as a test fixture.

    uv run python scripts/snapshot_format_inputs.py

Writes `tests/fixtures/format_inputs/hob.PremierDraft.json` from the
database: every input `analyze_draft` reads (cards, win rates, tag pairs,
synergy expectations, format settings), for just the cards in the saved
17Lands draft. The golden-file test then runs with no database at all.

Re-run it deliberately, when the inputs should change (a new stats
snapshot, a re-tagged set, a new baseline), and regenerate the golden file
with it: `UPDATE_GOLDEN=1 uv run pytest tests/test_draft_analysis.py`.
The diff of the two files is then exactly what moved.
"""

import dataclasses
import json
from pathlib import Path

from boostertutor.db import SessionLocal
from boostertutor.drafts import name_index
from boostertutor.format_inputs import load_format_inputs
from boostertutor.parsing import seventeen_lands

API = Path(__file__).resolve().parents[1]

FIXTURES = API / "tests" / "fixtures"


def main() -> None:
    draft = json.loads((FIXTURES / "seventeen_lands_draft" / "draft.json").read_text())
    metadata = json.loads(
        (FIXTURES / "seventeen_lands_draft" / "event_metadata.json").read_text()
    )
    with SessionLocal() as session:
        names = name_index(session, seventeen_lands.draft_set_code(metadata))
        log = seventeen_lands.parse_draft(draft, metadata, names)
        inputs = load_format_inputs(session, log.set_code, log.event_type)

    keep = {oid for pick in log.picks for oid in pick.pack_cards}
    snapshot = {
        "set_code": inputs.set_code,
        "event_type": inputs.event_type,
        "stats_snapshot": inputs.stats_snapshot.isoformat(),
        "format_avg_wr": inputs.stats.format_avg_wr,
        # name_key -> oracle id, so the test can parse the draft without a database.
        "names": {k: str(v) for k, v in sorted(names.items()) if v in keep},
        "cards": {
            str(oid): {**card, "oracle_id": str(oid)}
            for oid, card in sorted(inputs.cards.items())
            if oid in keep
        },
        "overall": {
            str(oid): list(rate)
            for oid, rate in sorted(inputs.stats.overall.items())
            if oid in keep
        },
        "alsa": {
            str(oid): value for oid, value in sorted(inputs.alsa.items()) if oid in keep
        },
        "edges": sorted(inputs.edges, key=lambda e: (e["enabler"], e["payoff"])),
        "baseline": sorted(
            [str(oid), pack, enabler, payoff, on_card, expected]
            for (
                oid,
                pack,
                enabler,
                payoff,
                on_card,
            ), expected in inputs.baseline.items()
            if oid in keep
        ),
        "cfg": dataclasses.asdict(inputs.cfg),
    }
    out = FIXTURES / "format_inputs" / f"{log.set_code}.{log.event_type}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=1, sort_keys=True) + "\n")
    print(f"wrote {out.relative_to(API)}: {len(snapshot['cards'])} cards")


if __name__ == "__main__":
    main()

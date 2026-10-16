"""Save what the deck metrics, Deck Ratings and Format Primer read, as a test fixture.

    uv run python scripts/snapshot_deck_inputs.py [SET] [EVENT_TYPE]

Writes `tests/fixtures/format_inputs/<set>.<event>.deck.json` from the
database: the set's Fixers (`mana_sources`), its land targets, its fitted
Deck Ratings model, its `PrimerFacts`, and the mana cost of every card in
the older snapshot. It sits beside the file written by
`snapshot_format_inputs.py`, which predates Phase 4b and holds none of
these (its cards have no `mana_cost`, which the mana metric reads), so the
Draft Summary's tests and eval run with no database.

Re-run it deliberately, when a new Stats Snapshot is ingested, the Fixers
are re-authored or Deck Ratings are refitted.
"""

import dataclasses
import json
import sys
import uuid
from pathlib import Path

from boostertutor.db import SessionLocal
from boostertutor.format_inputs import load_deck_rating_model, load_format_inputs
from boostertutor.format_primer import load_primer_facts

API = Path(__file__).resolve().parents[1]
FIXTURES = API / "tests" / "fixtures"


def main() -> None:
    set_code = sys.argv[1] if len(sys.argv) > 1 else "hob"
    event_type = sys.argv[2] if len(sys.argv) > 2 else "PremierDraft"
    with SessionLocal() as session:
        inputs = load_format_inputs(session, set_code, event_type)
        model = load_deck_rating_model(session, set_code, event_type)
        primer = load_primer_facts(session, set_code, event_type)
    if model is None:
        raise SystemExit(f"{set_code} {event_type} has no fitted Deck Ratings")

    older = json.loads(
        (FIXTURES / "format_inputs" / f"{set_code}.{event_type}.json").read_text()
    )
    snapshot = {
        "set_code": set_code,
        "event_type": event_type,
        "mana_sources": {
            str(oid): dataclasses.asdict(source)
            for oid, source in sorted(inputs.mana_sources.items())
        },
        "mana_costs": {
            oid: inputs.cards[uuid.UUID(oid)]["mana_cost"]
            for oid in sorted(older["cards"])
        },
        "land_target": dataclasses.asdict(inputs.land_target),
        "deck_rating_model": dataclasses.asdict(model),
        "primer": primer.model_dump(mode="json"),
    }
    out = FIXTURES / "format_inputs" / f"{set_code}.{event_type}.deck.json"
    out.write_text(json.dumps(snapshot, indent=1, sort_keys=True) + "\n")
    print(
        f"wrote {out.relative_to(API)}: {len(snapshot['mana_sources'])} mana "
        f"sources, a model fitted on {model.decks:,} decks"
    )


if __name__ == "__main__":
    main()

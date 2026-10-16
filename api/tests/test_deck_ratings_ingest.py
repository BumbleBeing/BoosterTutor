"""Reading the game dump's 40-card decks (ingest/deck_ratings.py)."""

import uuid

from boostertutor.ingest.deck_ratings import decks_from_game_rows
from boostertutor.parsing.names import name_key

ORC, ELF = uuid.uuid4(), uuid.uuid4()
NAMES = {name_key("Orc"): ORC, name_key("Elf"): ELF}
HEADER = [
    "draft_id", "build_index", "won",
    "deck_Orc", "sideboard_Orc", "deck_Elf", "sideboard_Elf", "deck_Mystery",
    "deck_Swamp", "deck_Forest", "sideboard_Forest",
]  # fmt: skip


def row(draft: str, build: str, won: str, orc: int, elf: int, swamps: int, *,
        mystery: int = 0, benched_elves: int = 0) -> list[str]:  # fmt: skip
    return [draft, build, won, str(orc), "0", str(elf), str(benched_elves),
            str(mystery), str(swamps), "6", "3"]  # fmt: skip


def test_each_distinct_40_card_deck_is_read_once_with_its_record() -> None:
    rows = [
        row("d1", "0", "True", 12, 5, 17, benched_elves=2),
        row("d1", "0", "False", 12, 5, 17, benched_elves=2),
        row("d1", "1", "True", 13, 4, 17),  # rebuilt between matches
    ]
    found = decks_from_game_rows(HEADER, rows, NAMES)

    first, rebuilt = found.decks
    assert (first.wins, first.games) == (1, 2)
    assert first.deck.main == [ORC] * 12 + [ELF] * 5
    assert first.deck.basics == {"B": 17, "G": 6}
    # Sideboard basics are dropped, as the deck builder prunes them.
    assert first.deck.sideboard == [ELF, ELF]
    assert (rebuilt.wins, rebuilt.games, rebuilt.deck.main.count(ORC)) == (1, 1, 13)


def test_decks_not_of_40_cards_or_with_unknown_cards_are_counted_and_left_out() -> None:
    rows = [
        row("d1", "0", "True", 12, 5, 18),  # 41 cards
        row("d2", "0", "True", 12, 4, 17, mystery=1),
        row("d3", "0", "False", 12, 5, 17),
    ]
    found = decks_from_game_rows(HEADER, rows, NAMES)

    assert len(found.decks) == 1
    assert (found.not_40, found.unknown_cards) == (1, 1)

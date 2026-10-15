"""The canonical draft (development plan 3.2).

Every input format (a 17Lands draft link, an Arena `Player.log`, an MTGO log)
is converted into a `DraftLog`, and everything downstream sees only this
shape. Adding a format means writing one function that returns a `DraftLog`.

The model checks its own invariants when it is built, so every parser gets
the same checks for free: a parser that loses a pick, numbers picks from 0,
or puts a card in the pool that was never in a pack fails here, loudly,
instead of producing a review of a draft that never happened.
"""

import datetime as dt
import uuid
from typing import Literal, Self

from pydantic import BaseModel, model_validator

# How many packs a draft opens. Every format v1 supports opens three.
PACKS = 3


class Pick(BaseModel):
    pack_number: int  # 1-3
    pick_number: int  # 1 to the pack size: 14 in a Play Booster set, 15 in older sets
    # The oracle ids in the pack when the pick was made, the picked card
    # included. Duplicates are kept: two copies of a common is a real pack.
    pack_cards: list[uuid.UUID]
    picked: uuid.UUID
    pool_before: list[uuid.UUID]  # everything already drafted, in pick order


class DraftLog(BaseModel):
    set_code: str  # lower case, as in the `sets` table: "hob"
    event_type: str  # PremierDraft, TradDraft, QuickDraft
    drafted_at: dt.datetime | None
    # Where the log came from, and its id there when it has one (a 17Lands
    # draft id). Used to recognise a draft that has been reviewed before.
    source: Literal["17lands", "arena", "mtgo"]
    source_id: str | None = None
    # The event's final record, when the source knows it.
    wins: int | None = None
    losses: int | None = None
    picks: list[Pick]  # in draft order: 3 x the pack size, 42 or 45

    @property
    def pack_size(self) -> int:
        """Picks per pack, read from the log itself, never assumed."""
        return len(self.picks) // PACKS

    @model_validator(mode="after")
    def _check_shape(self) -> Self:
        if not self.picks or len(self.picks) % PACKS:
            raise ValueError(
                f"a draft has {PACKS} packs of equal size; got {len(self.picks)} picks"
            )
        size = self.pack_size
        pool: list[uuid.UUID] = []
        for i, pick in enumerate(self.picks):
            expected = (i // size + 1, i % size + 1)
            where = f"pick {i + 1} (P{pick.pack_number}p{pick.pick_number})"
            if (pick.pack_number, pick.pick_number) != expected:
                raise ValueError(
                    f"{where}: expected P{expected[0]}p{expected[1]}; "
                    "picks must run 1 to the pack size in each of three packs"
                )
            if pick.picked not in pick.pack_cards:
                raise ValueError(f"{where}: the picked card is not in the pack")
            if pick.pool_before != pool:
                raise ValueError(f"{where}: pool_before is not the picks so far")
            pool = [*pool, pick.picked]
        return self

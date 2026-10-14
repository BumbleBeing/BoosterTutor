"""Which cards a set's draft packs can contain.

Not the same as the set's own printings. A Play Booster can also hold cards
from a bonus sheet that Scryfall files under a different set: Special Guests
(`spg`) in Reality Fracture packs, Marvel Universe (`mar`) in Marvel Super
Heroes packs. Scryfall does not link a bonus sheet to its draft set, so the
bonus cards are found the only dependable way: they are the card names in the
set's 17Lands draft dump that are not the set's own (see ingest/scryfall.py).
"""

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class BoosterCard(Base):
    __tablename__ = "booster_cards"

    set_code: Mapped[str] = mapped_column(
        ForeignKey("sets.set_code", ondelete="CASCADE"), primary_key=True
    )
    oracle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cards.oracle_id", ondelete="CASCADE"), primary_key=True
    )
    # "main" for the set's own cards, "bonus" for a bonus sheet's.
    sheet: Mapped[str] = mapped_column(String(16))

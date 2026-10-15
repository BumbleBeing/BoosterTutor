"""What the brief says about a card: the facts printed on it."""

from pydantic import BaseModel


class CardFacts(BaseModel):
    """A card as the brief names it. Loaded by `boostertutor.card_facts`."""

    name: str
    mana_cost: str | None  # "{1}{R}"; None for a land
    rarity: str  # common, uncommon, rare, mythic, special
    type_line: str
    oracle_text: str | None

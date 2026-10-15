"""Matching cards by name.

Shared by the 17Lands ingest and the 17Lands draft parser, so a card that
has statistics always resolves in a draft, and the other way round.
"""


def name_key(name: str) -> str:
    """How a card is matched by name: lower case, front face only.

    17Lands names a double-faced or split card by its front face alone
    ("Bilbo Baggins, Burglar"), where Scryfall names both ("A // B").
    """
    return name.split(" // ")[0].strip().lower()

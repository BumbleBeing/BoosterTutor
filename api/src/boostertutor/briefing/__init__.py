"""The brief: what Claude is told about one pick (ADR 0024 s5).

Pure, like `analysis/`: no network, no database, no clock. The card facts
it names cards with are loaded by `boostertutor.card_facts`.
"""

from .card_facts import CardFacts
from .pick import NoteKind, PickBrief, pick_brief

__all__ = ["CardFacts", "NoteKind", "PickBrief", "pick_brief"]

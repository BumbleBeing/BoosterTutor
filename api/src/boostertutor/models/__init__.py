"""SQLAlchemy models. Importing this package registers every table on Base.metadata."""

from .base import Base
from .booster import BoosterCard
from .card import Card, CardPrint, CardSet
from .deck_ratings import DeckRatingModelRow
from .format_constants import FormatConstants
from .ingest_run import IngestRun
from .llm_call import LlmCall
from .mana_sources import CardManaSource
from .replay import Draft, FetchAttempt
from .stats import ArchetypeStats, CardArchetypeStats, CardDraftStats
from .tags import CardTag, SynergyBaseline, Tag, TagPair

__all__ = [
    "ArchetypeStats",
    "Base",
    "BoosterCard",
    "Card",
    "CardArchetypeStats",
    "CardDraftStats",
    "CardManaSource",
    "CardPrint",
    "CardSet",
    "CardTag",
    "DeckRatingModelRow",
    "Draft",
    "FetchAttempt",
    "FormatConstants",
    "IngestRun",
    "LlmCall",
    "SynergyBaseline",
    "Tag",
    "TagPair",
]

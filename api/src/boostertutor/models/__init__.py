"""SQLAlchemy models. Importing this package registers every table on Base.metadata."""

from .base import Base
from .booster import BoosterCard
from .card import Card, CardPrint, CardSet
from .format_constants import FormatConstants
from .ingest_run import IngestRun
from .stats import ArchetypeStats, CardArchetypeStats, CardDraftStats
from .tags import CardTag, SynergyBaseline, Tag, TagPair

__all__ = [
    "ArchetypeStats",
    "Base",
    "BoosterCard",
    "Card",
    "CardArchetypeStats",
    "CardDraftStats",
    "CardPrint",
    "CardSet",
    "CardTag",
    "FormatConstants",
    "IngestRun",
    "SynergyBaseline",
    "Tag",
    "TagPair",
]

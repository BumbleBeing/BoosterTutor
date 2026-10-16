"""Draft Review without accounts: import a draft, review it, rate a deck.

`ReviewService` is the one thing the `/api/drafts` routes call (ADR 0031).
It owns every rule its three operations share, so no route repeats them:

- a draft id is checked, and a draft not in the Replay Cache is a 404
- Traditional and Open drafts are rated with the Premier statistics
- a format with no statistics yet is a 503
- 17Lands is asked only on a cache miss, and only after the rate limit
- verdicts and Deck Ratings are recomputed on every request: the parsed log
  is the only thing ever stored

Every failure is a `ReviewError` (`errors.py`).

The service's collaborators are small interfaces: the Replay Cache, the
`Catalog` of what the database knows about a set, and the 17Lands fetch,
plus the rate limiter. `postgres.py` builds the real ones; the tests build
in-memory ones, so the whole service runs with no network and no database.
"""

import re
import uuid
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from ..analysis.deck import deck_metrics
from ..analysis.deck_rating import DeckRatingModel, rate_deck
from ..analysis.draft import FormatInputs, analyze_draft
from ..analysis.mana import colour_sources
from ..format_inputs import FormatNotReady, stats_event_type
from ..parsing import seventeen_lands
from ..parsing.errors import DraftInputError
from ..schemas import DraftLog
from ..schemas.deck import DeckError, DeckMetrics, deck_from_pool
from ..schemas.deck_submission import DeckReview, SubmittedDeck
from ..schemas.draft_analysis import DraftAnalysis
from ..schemas.draft_review import CardInfo, DraftReview, ImportResponse
from .errors import ReviewError
from .rate_limit import Bucket, RateLimited, RateLimiter

# A 17Lands draft id: 32 lowercase hex characters.
DRAFT_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class ReplayStore(Protocol):
    """The Replay Cache: parsed logs by 17Lands draft id."""

    def get(self, draft_id: str) -> DraftLog | None: ...
    def has(self, draft_id: str) -> bool: ...
    def add(self, log: DraftLog) -> None: ...


class Catalog(Protocol):
    """What the database knows about a set: its cards, statistics and models."""

    def names(self, set_code: str) -> dict[str, uuid.UUID]:
        """`name_key` -> oracle id, for matching a draft's card names."""
        ...

    def format_inputs(self, set_code: str, event_type: str) -> FormatInputs:
        """The statistics a verdict is computed from, or `FormatNotReady`."""
        ...

    def deck_model(self, set_code: str, event_type: str) -> DeckRatingModel | None:
        """The fitted Deck Ratings, or None when the format has none yet."""
        ...

    def card_infos(
        self, set_code: str, ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, CardInfo]:
        """How to show each card: name, cost, image."""
        ...

    def basic_lands(self, set_code: str) -> dict[str, CardInfo]:
        """The set's own basic lands by colour letter; a missing one is absent."""
        ...


# draft id -> (draft payload, event metadata), or `DraftInputError`.
Fetch = Callable[[str], tuple[dict[str, Any], dict[str, Any]]]


@dataclass(frozen=True)
class _Loaded:
    """A cached draft, ready to analyse.

    `log.event_type` is the event type whose statistics rate it, which is
    what `analyze_draft` checks against `inputs`. `event_type` is what the
    draft really was, which is what the person is shown.
    """

    log: DraftLog
    event_type: str
    inputs: FormatInputs


class ReviewService:
    def __init__(
        self,
        store: ReplayStore,
        catalog: Catalog,
        fetch: Fetch,
        limiter: RateLimiter,
        supported_sets: frozenset[str],
    ) -> None:
        self.store = store
        self.catalog = catalog
        self.fetch = fetch
        self.limiter = limiter
        self.supported_sets = supported_sets

    # ----------------------------------------------------------------------
    # The three operations
    # ----------------------------------------------------------------------

    def import_draft(self, link: str, client: str) -> ImportResponse:
        """Whatever the user pasted (a 17Lands URL or a draft id) into a
        cached draft.

        The order matters. A draft already in the Replay Cache is answered at
        once, with no 17Lands request and no use of the caller's allowance.
        Only a miss is charged, and it is charged before the fetch, so a
        failed fetch still counts.
        """
        try:
            draft_id = seventeen_lands.parse_draft_id(link)
            if self.store.has(draft_id):
                return ImportResponse(draft_id=draft_id, cached=True)

            self._charge("fetch", client)
            draft, metadata = self.fetch(draft_id)

            # Refuse an unsupported set before matching any cards: we may hold
            # no card data for it, and a log of it must not be cached.
            set_code = seventeen_lands.draft_set_code(metadata)
            if set_code not in self.supported_sets:
                raise ReviewError(
                    "unsupported_set",
                    f"BoosterTutor reviews {self._supported_names()} drafts for "
                    "now. More sets are coming.",
                    {"set_code": set_code},
                )

            log = seventeen_lands.parse_draft(
                draft, metadata, self.catalog.names(set_code), draft_id=draft_id
            )
        except DraftInputError as exc:
            raise ReviewError.from_input(exc) from exc
        self.store.add(log)
        return ImportResponse(draft_id=draft_id, cached=False)

    def review(self, draft_id: str) -> DraftReview:
        """Every pick of a cached draft graded against today's statistics."""
        loaded = self._load(draft_id)
        log = loaded.log
        analysis = analyze_draft(log, loaded.inputs)
        return DraftReview(
            draft_id=draft_id,
            set_code=log.set_code,
            event_type=loaded.event_type,
            drafted_at=log.drafted_at,
            wins=log.wins,
            losses=log.losses,
            pack_size=log.pack_size,
            analysis=analysis,
            verdict_counts=dict(Counter(p.verdict for p in analysis.picks)),
            noted_picks=[
                (p.pack_number, p.pick_number) for p in analysis.picks if p.noted
            ],
            cards=self.catalog.card_infos(log.set_code, _cards_named_in(analysis)),
            basic_lands=self.catalog.basic_lands(log.set_code),
        )

    def rate_deck(
        self, draft_id: str, submitted: SubmittedDeck, client: str
    ) -> DeckReview:
        """Deck Ratings for 40 cards built from a cached draft's pool."""
        _check_draft_id(draft_id)
        # Charged before the deck is checked, so a stream of bad decks runs
        # out of allowance too.
        self._charge("deck", client)
        loaded = self._load(draft_id)
        inputs = loaded.inputs
        try:
            deck = deck_from_pool(
                _pool(loaded.log, inputs),
                main=submitted.cards,
                basics=submitted.basics,
            )
        except DeckError as exc:
            raise ReviewError("invalid_deck", str(exc)) from exc

        metrics = deck_metrics(deck, inputs)
        model = self.catalog.deck_model(loaded.log.set_code, inputs.event_type)
        return DeckReview(
            ratings=rate_deck(metrics, model),
            metrics=metrics,
            colour_sources=colour_sources(
                [inputs.cards[oid] for oid in deck.main],
                deck.basics,
                inputs.mana_sources,
            ),
            cards=self.catalog.card_infos(
                loaded.log.set_code, _cards_named_in_metrics(metrics)
            ),
        )

    # ----------------------------------------------------------------------
    # The shared steps
    # ----------------------------------------------------------------------

    def _load(self, draft_id: str) -> _Loaded:
        """A cached draft and the statistics that rate it."""
        _check_draft_id(draft_id)
        log = self.store.get(draft_id)
        if log is None:
            raise ReviewError(
                "draft_not_found",
                "That draft hasn't been imported yet. Submit its 17Lands link first.",
            )
        try:
            inputs = self.catalog.format_inputs(
                log.set_code, stats_event_type(log.event_type)
            )
        except FormatNotReady as exc:
            raise ReviewError(
                "format_not_ready",
                f"There are no statistics for {log.set_code.upper()} "
                f"{log.event_type} yet. Please try again later.",
            ) from exc
        # A Traditional or Open draft is rated with the Premier statistics,
        # so it is analysed as a Premier draft.
        analysed = log.model_copy(update={"event_type": inputs.event_type})
        return _Loaded(log=analysed, event_type=log.event_type, inputs=inputs)

    def _charge(self, bucket: Bucket, client: str) -> None:
        try:
            self.limiter.check_and_record(bucket, client)
        except RateLimited as exc:
            what = (
                "drafts imported from 17Lands"
                if bucket == "fetch"
                else "decks submitted"
            )
            raise ReviewError(
                "rate_limited",
                f"Too many {what} just now. Please try again in a little while.",
                retry_after=exc.retry_after,
            ) from exc

    def _supported_names(self) -> str:
        """ "HOB", or "HOB and MSH": the sets a review is offered for."""
        return " and ".join(sorted(s.upper() for s in self.supported_sets))


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------


def _check_draft_id(draft_id: str) -> None:
    if not DRAFT_ID_RE.match(draft_id):
        raise ReviewError("invalid_input", "that isn't a 17Lands draft id")


def _pool(log: DraftLog, inputs: FormatInputs) -> list[uuid.UUID]:
    """The cards a deck can be built from: every pick but the basic lands.

    A basic land drafted is pruned (ADR 0025 s1); the deck builder's own
    buttons add basics instead.
    """
    return [
        p.picked
        for p in log.picks
        if not inputs.cards.get(p.picked, {})
        .get("type_line", "")
        .startswith("Basic Land")
    ]


def _cards_named_in(analysis: DraftAnalysis) -> set[uuid.UUID]:
    """Every card the review page can show: each pack, and the wheel tables."""
    named = {
        oid
        for p in analysis.picks
        for oid in (p.picked, *(c.oracle_id for c in p.cards))
    }
    for wheel in analysis.wheels:
        for lap in wheel.laps:
            named.update(c.oracle_id for c in (*lap.wheeled, *lap.taken_by_table))
        named.update(c.best_wheeled for c in wheel.colors if c.best_wheeled is not None)
    return named


def _cards_named_in_metrics(metrics: DeckMetrics) -> set[uuid.UUID]:
    """Every card the Deck Ratings panel names: the short spell, the notable
    omission and the synergy firings."""
    named: set[uuid.UUID] = set()
    if metrics.mana_short_spell is not None:
        named.add(metrics.mana_short_spell)
    for firing in metrics.synergy_firings:
        named.add(firing.oracle_id)
        named.update(firing.contributing)
    if metrics.notable_omission is not None:
        named.add(metrics.notable_omission.oracle_id)
        named.add(metrics.notable_omission.instead_of)
    return named

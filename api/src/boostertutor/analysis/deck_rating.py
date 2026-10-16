"""Deck Ratings: where a deck falls among real decks from its format (ADR 0026 s2).

    fit_model([ScoredDeck, ...]) -> DeckRatingModel | None   # offline, in the ingest
    rate_deck(DeckMetrics, DeckRatingModel | None) -> DeckRatings

Each metric is graded by its percentile among the format's 40-card decks in
the 17Lands game dump. The overall grade comes from a logistic regression of
game win on the metrics, fitted per format: it predicts a win rate, and that
is graded by its percentile among the same decks' predicted win rates.

Pure. The regression is fitted here by Newton's method, in plain Python,
rather than with a statistics library: seven features and a few thousand
distinct decks are a small problem, and this keeps the maths readable in
one file (approved by Jackson, 2026-10-15).
"""

import math
from dataclasses import dataclass, replace

from ..schemas.deck import DeckMetrics, DeckRatings, Grade, MetricRating

# The graded metrics, and whether a higher value is better. The regression
# finds how much each matters; the direction is Magic, not data.
METRICS: dict[str, bool] = {
    "card_quality": True,
    "curve_distance": False,
    "synergy": True,
    "creatures": True,
    "removal": True,
    "mana_shortfall": False,
    "land_distance": False,
}
WIN_RATE = "win_rate"  # the quantiles of the predicted win rate, in percent

# Grade bands, by percentile: A from the 80th up, F below the 20th, so a C
# is the middle fifth, an average deck among 17Lands users. PLACEHOLDERS.
GRADE_BANDS: tuple[tuple[int, Grade], ...] = (
    (80, "A"),
    (60, "B"),
    (40, "C"),
    (20, "D"),
    (0, "F"),
)

# Fewer distinct decks than this and a format is not fitted. ADR 0028 notes
# about 20,000 decks per format; this is a PLACEHOLDER floor well below it.
MIN_DECKS = 2000

NOT_ENOUGH_DATA = "not enough data to rate"


@dataclass(frozen=True)
class ScoredDeck:
    """One distinct deck from the game dump: its metric values and its record."""

    values: dict[str, float]
    wins: int
    games: int


@dataclass(frozen=True)
class DeckRatingModel:
    """One format's fit, as stored in `deck_rating_models`.

    `coefficients` are in the metrics' own units, per unit of log-odds, and
    leave out any metric that never varied in the format (an untagged set's
    synergy, say). `quantiles` holds 101 values per metric, the 0th to the
    100th percentile, plus `WIN_RATE`'s.
    """

    intercept: float
    coefficients: dict[str, float]
    standard_errors: dict[str, float]
    quantiles: dict[str, list[float]]
    decks: int
    games: int


def metric_values(metrics: DeckMetrics) -> dict[str, float]:
    return {name: float(getattr(metrics, name)) for name in METRICS}


# --------------------------------------------------------------------------
# Fitting (offline)
# --------------------------------------------------------------------------


def fit_model(
    decks: list[ScoredDeck], *, min_decks: int = MIN_DECKS
) -> DeckRatingModel | None:
    """Percentile tables and the regression, or None for too few decks."""
    if len(decks) < min_decks:
        return None
    games = sum(d.games for d in decks)
    varying = [name for name in METRICS if len({d.values[name] for d in decks}) > 1]
    intercept, coefficients, errors = _logistic(decks, varying)
    model = DeckRatingModel(
        intercept=intercept,
        coefficients=coefficients,
        standard_errors=errors,
        quantiles={
            name: _quantiles([d.values[name] for d in decks]) for name in METRICS
        },
        decks=len(decks),
        games=games,
    )
    predicted = _quantiles([_win_rate(d.values, model) for d in decks])
    return replace(model, quantiles={**model.quantiles, WIN_RATE: predicted})


def _quantiles(values: list[float]) -> list[float]:
    """The 0th to 100th percentiles, by the nearest-rank method."""
    ordered = sorted(values)
    last = len(ordered) - 1
    return [ordered[round(last * p / 100)] for p in range(101)]


def _logistic(
    decks: list[ScoredDeck], features: list[str]
) -> tuple[float, dict[str, float], dict[str, float]]:
    """Logistic regression of game win on `features`, by Newton's method.

    Each deck is a group of games with one set of features, so the
    likelihood is binomial: a deck with k wins in n games contributes
    k log p + (n - k) log(1 - p). That is the same fit as one row per game,
    for a fraction of the work.

    Features are standardised first (mean 0, standard deviation 1, weighted
    by games) so Newton's method is well conditioned, and the answer is
    converted back to each metric's own units at the end. The standard
    errors come from the inverse of the information matrix at the optimum.
    """
    total = sum(d.games for d in decks)
    means = {f: sum(d.values[f] * d.games for d in decks) / total for f in features}
    sds = {
        f: math.sqrt(
            sum((d.values[f] - means[f]) ** 2 * d.games for d in decks) / total
        )
        for f in features
    }
    rows = [
        [1.0] + [(d.values[f] - means[f]) / sds[f] for f in features] for d in decks
    ]
    size = len(features) + 1
    beta = [0.0] * size
    for _ in range(50):
        gradient = [0.0] * size
        information = [[0.0] * size for _ in range(size)]
        for row, deck in zip(rows, decks, strict=True):
            p = _sigmoid(sum(b * x for b, x in zip(beta, row, strict=True)))
            residual = deck.wins - deck.games * p
            weight = deck.games * p * (1 - p)
            for i in range(size):
                gradient[i] += residual * row[i]
                for j in range(size):
                    information[i][j] += weight * row[i] * row[j]
        covariance = _inverse(information)
        step = [
            sum(covariance[i][j] * gradient[j] for j in range(size))
            for i in range(size)
        ]
        beta = [b + s for b, s in zip(beta, step, strict=True)]
        if max(abs(s) for s in step) < 1e-10:
            break

    coefficients = {f: beta[i + 1] / sds[f] for i, f in enumerate(features)}
    intercept = beta[0] - sum(coefficients[f] * means[f] for f in features)
    errors = {
        f: math.sqrt(covariance[i + 1][i + 1]) / sds[f] for i, f in enumerate(features)
    }
    return intercept, coefficients, errors


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def _inverse(matrix: list[list[float]]) -> list[list[float]]:
    """Gauss-Jordan elimination with partial pivoting. The matrix is small."""
    n = len(matrix)
    work = [
        row[:] + [1.0 if i == j else 0.0 for j in range(n)]
        for i, row in enumerate(matrix)
    ]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(work[r][col]))
        work[col], work[pivot] = work[pivot], work[col]
        scale = work[col][col]
        work[col] = [x / scale for x in work[col]]
        for r in range(n):
            if r != col and work[r][col]:
                factor = work[r][col]
                work[r] = [
                    x - factor * y for x, y in zip(work[r], work[col], strict=True)
                ]
    return [row[n:] for row in work]


# --------------------------------------------------------------------------
# Rating (on request)
# --------------------------------------------------------------------------


def rate_deck(metrics: DeckMetrics, model: DeckRatingModel | None) -> DeckRatings:
    return rate_values(metric_values(metrics), model)


def rate_values(values: dict[str, float], model: DeckRatingModel | None) -> DeckRatings:
    """Each metric's grade and the overall grade, or "not enough data to rate"."""
    if model is None:
        return DeckRatings(
            rated=False,
            message=NOT_ENOUGH_DATA,
            metrics=[MetricRating(metric=name, value=values[name]) for name in METRICS],
        )
    metrics = []
    for name, higher_is_better in METRICS.items():
        percentile = _percentile(values[name], model.quantiles[name], higher_is_better)
        metrics.append(
            MetricRating(
                metric=name,
                value=values[name],
                percentile=percentile,
                grade=grade(percentile),
            )
        )
    win_rate = _win_rate(values, model)
    percentile = _percentile(win_rate, model.quantiles[WIN_RATE], True)
    return DeckRatings(
        rated=True,
        metrics=metrics,
        predicted_win_rate=win_rate,
        percentile=percentile,
        grade=grade(percentile),
    )


def grade(percentile: int) -> Grade:
    return next(letter for floor, letter in GRADE_BANDS if percentile >= floor)


def _win_rate(values: dict[str, float], model: DeckRatingModel) -> float:
    """The regression's predicted game win rate, in percent."""
    z = model.intercept + sum(c * values[f] for f, c in model.coefficients.items())
    return 100.0 * _sigmoid(z)


def _percentile(value: float, quantiles: list[float], higher_is_better: bool) -> int:
    """The share of the format's decks this value is at least as good as.

    "At least as good", so ties count in the deck's favour: a deck with no
    mana shortfall, like most decks, is at the 100th percentile, not in the
    middle of a tie.
    """
    if higher_is_better:
        as_good = sum(1 for q in quantiles if q <= value)
    else:
        as_good = sum(1 for q in quantiles if q >= value)
    return round(100 * as_good / len(quantiles))

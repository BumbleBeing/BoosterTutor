"""Deck Ratings: percentile grades and a logistic regression of win (ADR 0026 s2)."""

import math

import pytest

from boostertutor.analysis.deck_rating import (
    METRICS,
    DeckRatingModel,
    ScoredDeck,
    fit_model,
    rate_values,
)


def flat(**values: float) -> dict[str, float]:
    """Every metric at 0, but those given."""
    return {name: 0.0 for name in METRICS} | values


def test_the_regression_recovers_a_known_answer() -> None:
    """Two groups of 100 games, winning 25% and 75%.

    With one binary feature the fit reproduces the groups' own rates
    exactly, so the answer is known without a regression library:
    intercept = logit(0.25) = -ln 3, slope = logit(0.75) - logit(0.25) = 2 ln 3,
    and each standard error is sqrt(1 / (n p (1 - p))) per group involved.
    """
    decks = [
        ScoredDeck(flat(card_quality=0.0), wins=25, games=100),
        ScoredDeck(flat(card_quality=1.0), wins=75, games=100),
    ]
    model = fit_model(decks, min_decks=1)

    assert model.intercept == pytest.approx(-math.log(3), abs=1e-6)
    assert model.coefficients == {"card_quality": pytest.approx(2 * math.log(3))}
    assert model.standard_errors["card_quality"] == pytest.approx(
        math.sqrt(2 / (100 * 0.25 * 0.75)), abs=1e-6
    )
    # Metrics that never vary say nothing, so they are left out of the fit.
    assert set(model.coefficients) == {"card_quality"}
    assert (model.decks, model.games) == (2, 200)


def test_a_format_with_too_few_decks_is_not_fitted() -> None:
    decks = [
        ScoredDeck(flat(card_quality=float(i % 2)), wins=1, games=2) for i in range(9)
    ]
    assert fit_model(decks, min_decks=10) is None


def even_model() -> DeckRatingModel:
    """Every metric spread evenly from 0 to 100 across the decks."""
    spread = [float(i) for i in range(101)]
    return DeckRatingModel(
        intercept=0.0,
        coefficients={"card_quality": 0.01},
        standard_errors={"card_quality": 0.001},
        quantiles={**{name: spread for name in METRICS}, "win_rate": spread},
        decks=101,
        games=1000,
    )


def test_each_metric_is_graded_by_its_percentile_among_the_formats_decks() -> None:
    ratings = rate_values(flat(card_quality=85.0, mana_shortfall=85.0), even_model())
    by_name = {r.metric: r for r in ratings.metrics}

    # Higher card quality is better: 85 beats 85% of decks.
    assert (by_name["card_quality"].percentile, by_name["card_quality"].grade) == (
        85,
        "A",
    )
    # A larger shortfall is worse: 85 is at least as good as 16% of decks.
    assert (by_name["mana_shortfall"].percentile, by_name["mana_shortfall"].grade) == (
        16,
        "F",
    )


def test_the_overall_rating_grades_the_predicted_win_rate() -> None:
    ratings = rate_values(flat(card_quality=50.0), even_model())

    # logistic(0.01 x 50) = 62.2%, which beats the 62 decks predicted below it.
    assert ratings.predicted_win_rate == pytest.approx(62.25, abs=0.01)
    assert (ratings.percentile, ratings.grade) == (62, "B")


def test_an_unfitted_format_has_not_enough_data_to_rate() -> None:
    ratings = rate_values(flat(), None)

    assert not ratings.rated
    assert ratings.message == "not enough data to rate"
    assert all(r.grade is None for r in ratings.metrics)
    assert ratings.grade is None

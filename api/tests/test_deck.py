"""The Submitted Deck's input shape (ADR 0025): 40 cards, from the pool plus basics."""

import uuid

import pytest

from boostertutor.schemas.deck import Deck, DeckError, deck_from_pool

A, B, C = (uuid.uuid4() for _ in range(3))


def test_a_deck_of_pool_cards_and_basics_keeps_the_rest_as_its_sideboard() -> None:
    pool = [A] * 23 + [B, C]
    deck = deck_from_pool(pool, main=[A] * 23, basics={"W": 9, "U": 8})

    assert deck == Deck(main=[A] * 23, basics={"W": 9, "U": 8}, sideboard=[B, C])
    assert deck.size == 40


def test_a_deck_must_be_exactly_40_cards() -> None:
    with pytest.raises(DeckError, match="39 cards"):
        deck_from_pool([A] * 23, main=[A] * 23, basics={"W": 16})


def test_a_deck_may_only_use_cards_in_the_pool_as_often_as_they_were_drafted() -> None:
    with pytest.raises(DeckError, match="not in the pool"):
        deck_from_pool([A] * 22, main=[A] * 23, basics={"W": 17})


def test_basics_are_named_by_colour() -> None:
    with pytest.raises(DeckError, match="basic"):
        deck_from_pool([A] * 23, main=[A] * 23, basics={"C": 17})

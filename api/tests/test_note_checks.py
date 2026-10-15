"""The checks every Pick Note must pass, at runtime and in the eval (ADR 0024 s7, s9).

The core rule: no statistic may appear in the output that was not passed
into the prompt. Every number in the brief is display text, so the check
is a plain string match on the numbers themselves.
"""

from boostertutor.llm.checks import invented_numbers, note_problems
from boostertutor.llm.pick_note import PickNoteOutput

BRIEF = """HOB PremierDraft. Pack 1, pick 12 (pick 12 of 42).
  fitness 52.9 (solid) = GIH WR 57.7% over 49,195 games, colour fit -5.1pp
Gap: the card taken scored 2.1pp below the best card.
"""


def test_a_number_from_the_brief_is_allowed() -> None:
    assert invented_numbers("It cost you 2.1pp, on 49,195 games.", BRIEF) == []


def test_a_number_not_in_the_brief_is_invented() -> None:
    assert invented_numbers("It cost you 2.2pp, about 7% of a game.", BRIEF) == [
        "2.2",
        "7",
    ]


def test_a_sign_is_not_a_different_number() -> None:
    """ "a 5.1pp colour tax" quotes the brief's "-5.1pp" fairly."""
    assert invented_numbers("a 5.1pp colour-fit tax", BRIEF) == []


def test_a_reformatted_number_is_invented() -> None:
    """The brief says 49,195; Claude must copy it, not respell it."""
    assert invented_numbers("over 49195 games", BRIEF) == ["49195"]


def test_punctuation_after_a_number_is_not_part_of_it() -> None:
    assert invented_numbers("Pick 12, at 57.7%.", BRIEF) == []


def note(text: str, pack: int = 1, pick: int = 12) -> PickNoteOutput:
    return PickNoteOutput(pack_number=pack, pick_number=pick, note=text)


def test_a_good_note_has_no_problems() -> None:
    assert note_problems(note("You paid 2.1pp for colour."), BRIEF, (1, 12)) == []


def test_a_note_for_another_pick_is_a_problem() -> None:
    problems = note_problems(note("Fine.", pick=11), BRIEF, (1, 12))
    assert problems == ["the note is for P1p11, not P1p12"]


def test_a_note_over_the_length_cap_is_a_problem() -> None:
    problems = note_problems(note("x" * 601), BRIEF, (1, 12))
    assert problems == ["the note is 601 characters, over the cap of 600"]


def test_an_empty_note_is_a_problem() -> None:
    assert note_problems(note("  "), BRIEF, (1, 12)) == ["the note is empty"]


def test_an_invented_number_is_a_problem() -> None:
    problems = note_problems(note("It cost 3.0pp."), BRIEF, (1, 12))
    assert problems == ["numbers not in the brief: 3.0"]

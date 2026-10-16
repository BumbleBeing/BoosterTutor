"""What a Draft Summary must pass before it is kept (ADR 0030 s1)."""

from dataclasses import dataclass, field

from boostertutor.llm.checks import WORD_CAPS, summary_problems

BRIEF = "Pick 3 came back at pick 11. Card quality +1.5pp, grade A (84th percentile)."
PICKS = [(pack, pick) for pack in (1, 2, 3) for pick in range(1, 15)]


@dataclass
class Pick:
    pack_number: int
    pick_number: int


@dataclass
class Summary:
    draft_arc: str = "Red flowed early, and a good black card came back at pick 11."
    deck: str = "The spells beat the format by +1.5pp, an A."
    lesson: str = "Trust what wheels."
    key_picks: list[Pick] = field(default_factory=lambda: [Pick(1, 3)])


def problems(summary: Summary) -> list[str]:
    return summary_problems(summary, BRIEF, PICKS)


def test_a_summary_within_the_rules_has_no_problems() -> None:
    assert problems(Summary()) == []


def test_a_number_the_brief_never_states_is_named_with_its_field() -> None:
    assert problems(Summary(deck="The spells beat the format by 2.5pp.")) == [
        "deck: numbers not in the brief: 2.5"
    ]


def test_each_field_has_its_own_word_cap() -> None:
    long_lesson = " ".join(["word"] * (WORD_CAPS["lesson"] + 1))
    assert problems(Summary(lesson=long_lesson)) == [
        (
            f"lesson: {WORD_CAPS['lesson'] + 1} words, over the cap of "
            f"{WORD_CAPS['lesson']}"
        )
    ]
    assert problems(Summary(lesson=" ".join(["word"] * WORD_CAPS["lesson"]))) == []


def test_an_empty_field_is_a_problem() -> None:
    assert problems(Summary(draft_arc="  ")) == ["draft_arc: empty"]


def test_at_most_two_key_picks_and_each_must_be_in_the_draft() -> None:
    three = Summary(key_picks=[Pick(1, 1), Pick(1, 2), Pick(2, 1)])
    assert problems(three) == ["3 key picks, over the cap of 2"]
    assert problems(Summary(key_picks=[Pick(4, 1)])) == [
        "key pick P4p1 is not a pick in this draft"
    ]
    assert problems(Summary(key_picks=[Pick(1, 3), Pick(1, 3)])) == [
        "key pick P1p3 is named twice"
    ]
    assert problems(Summary(key_picks=[])) == []

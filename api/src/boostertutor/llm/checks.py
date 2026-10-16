"""What a Pick Note or a Draft Summary must pass before it is kept (ADR 0024 s7, s9; ADR 0030 s1).

Pure. The same checks run on every live call, where a failure means one
retry, and in the eval harness, where it means the prompt is wrong.
"""

import re
from collections.abc import Sequence
from typing import Protocol

MAX_NOTE_CHARS = 600

# A number as the brief writes it: "49,195", "57.7", "12". Signs, "%" and
# "pp" are not part of it, so "a 5.1pp tax" fairly quotes "-5.1pp". The
# thousands form comes first, so "49,195" is one number, while the comma in
# "pick 12, and" is punctuation.
NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")


class NoteOutput(Protocol):
    pack_number: int
    pick_number: int
    note: str


def numbers(text: str) -> list[str]:
    return NUMBER.findall(text)


def invented_numbers(note: str, brief: str) -> list[str]:
    """Every number in `note` that the brief never states, in order."""
    allowed = set(numbers(brief))
    return [n for n in numbers(note) if n not in allowed]


def note_problems(output: NoteOutput, brief: str, pick: tuple[int, int]) -> list[str]:
    """Why this note can't be kept; empty when it can."""
    problems = []
    if (output.pack_number, output.pick_number) != pick:
        problems.append(
            f"the note is for P{output.pack_number}p{output.pick_number}, "
            f"not P{pick[0]}p{pick[1]}"
        )
    text = output.note.strip()
    if not text:
        problems.append("the note is empty")
    if len(text) > MAX_NOTE_CHARS:
        problems.append(
            f"the note is {len(text)} characters, over the cap of {MAX_NOTE_CHARS}"
        )
    invented = invented_numbers(text, brief)
    if invented:
        problems.append(f"numbers not in the brief: {', '.join(invented)}")
    return problems


# --------------------------------------------------------------------------
# The Draft Summary (ADR 0030 s1)
# --------------------------------------------------------------------------

# Each prose field's cap in words: 1.25 times the prompt's target of about
# 60, 100 and 40 words. PLACEHOLDERS, to revisit if a field keeps hitting
# its cap.
WORD_CAPS = {"draft_arc": 75, "deck": 125, "lesson": 50}
MAX_KEY_PICKS = 2


class KeyPickOutput(Protocol):
    pack_number: int
    pick_number: int


class SummaryOutput(Protocol):
    draft_arc: str
    deck: str
    lesson: str

    @property
    def key_picks(self) -> Sequence[KeyPickOutput]: ...


def summary_problems(
    output: SummaryOutput, brief: str, picks: Sequence[tuple[int, int]]
) -> list[str]:
    """Why this summary can't be kept; empty when it can.

    `picks` are the draft's (pack, pick) pairs, which a Key Pick must be.
    """
    problems = []
    for name, cap in WORD_CAPS.items():
        text = getattr(output, name).strip()
        if not text:
            problems.append(f"{name}: empty")
            continue
        words = len(text.split())
        if words > cap:
            problems.append(f"{name}: {words} words, over the cap of {cap}")
        invented = invented_numbers(text, brief)
        if invented:
            problems.append(f"{name}: numbers not in the brief: {', '.join(invented)}")

    if len(output.key_picks) > MAX_KEY_PICKS:
        problems.append(
            f"{len(output.key_picks)} key picks, over the cap of {MAX_KEY_PICKS}"
        )
    seen: set[tuple[int, int]] = set()
    for key in output.key_picks:
        pick = (key.pack_number, key.pick_number)
        label = f"P{pick[0]}p{pick[1]}"
        if pick not in picks:
            problems.append(f"key pick {label} is not a pick in this draft")
        elif pick in seen:
            problems.append(f"key pick {label} is named twice")
        seen.add(pick)
    return problems

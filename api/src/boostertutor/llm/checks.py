"""What a Pick Note must pass before it is kept (ADR 0024 s7, s9).

Pure. The same checks run on every live call, where a failure means one
retry, and in the eval harness, where it means the prompt is wrong.
"""

import re
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

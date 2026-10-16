"""Numbers as display text, written in one place (ADR 0024 s5).

The prompt tells Claude to quote numbers exactly as the brief gives them,
and the eval checks that every number in a note appears in its brief, by
plain string match. So each kind of number has exactly one spelling, and it
is chosen here: a win rate is "57.3%", a difference "+2.1pp", a sample
"18,606 games", a fitness score "57.2".
"""

DECIMALS = 1


def _fixed(value: float) -> str:
    text = f"{value:.{DECIMALS}f}"
    # "-0.0" reads as a loss that is not there: a zero is a zero.
    return "0.0" if text in ("-0.0", "0.0") else text


def win_rate(value: float) -> str:
    """A win rate already in percent: 57.293 -> "57.3%"."""
    return f"{_fixed(value)}%"


def score(value: float) -> str:
    """A fitness score, on the same scale as a win rate but not one: "57.2"."""
    return _fixed(value)


def pp(value: float) -> str:
    """A size in percentage points, unsigned: a gap is never negative."""
    return f"{_fixed(abs(value))}pp"


def signed_pp(value: float) -> str:
    """A difference or a score part: "+2.1pp", "-5.1pp", "0.0pp"."""
    text = _fixed(value)
    if text == "0.0":
        return "0.0pp"
    return f"{text}pp" if text.startswith("-") else f"+{text}pp"


def count(value: float) -> str:
    """An expected count of pool cards: 0.2507 -> "0.3"."""
    return _fixed(value)


def games(value: int) -> str:
    return f"{value:,} games"


def mana_value(value: float) -> str:
    """An average mana value, to two places: 2.96 -> "2.96".

    Two, not one, because a land target turns on a cut such as 3.0, and
    "3.0" for 2.96 would read as the wrong side of it.
    """
    return f"{value:.2f}"


def percentile(value: int) -> str:
    """62 -> "62nd percentile"."""
    if value % 100 in (11, 12, 13):
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix} percentile"

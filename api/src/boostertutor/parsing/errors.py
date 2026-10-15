"""The one error every draft input raises, so the UI can explain any of them.

Development plan 3.1 asks for an input that fails *clearly* ("that draft is
private or not found") rather than mysteriously. Each failure has a `kind`
the frontend can switch on, a message a person can read, and optional
`detail` (for example the full list of card names that did not match).
"""

from typing import Any, Literal

Kind = Literal[
    "invalid_input",  # no draft id in the text, or a log we cannot read
    "draft_not_found",  # 17Lands has no such draft, or it is private
    "unsupported_set",  # we have no card data for the draft's set
    "unsupported_format",  # e.g. a pick-two draft, more than one card per pick
    "unresolved_cards",  # card names that match no card in the set
    "malformed_draft",  # the picks do not add up to three whole packs
    "upstream_failure",  # 17Lands did not answer, or answered something unexpected
]


class DraftInputError(Exception):
    def __init__(self, kind: Kind, message: str, detail: Any = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "message": self.message, "detail": self.detail}

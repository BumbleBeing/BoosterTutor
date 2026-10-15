"""The Anthropic client, built from settings."""

import anthropic

from ..config import settings


def anthropic_client() -> anthropic.Anthropic:
    """A client with the key from `ANTHROPIC_API_KEY` (api/.env or Render).

    Without one in settings, the SDK looks for credentials itself and
    raises when a call is made if it finds none.
    """
    key = settings.anthropic_api_key
    if key is None:
        return anthropic.Anthropic()
    return anthropic.Anthropic(api_key=key.get_secret_value())

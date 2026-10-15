"""Claude: the prose layer (ADR 0024).

Claude explains facts and verdicts that Python has already computed; it
never computes one. This package holds the calls, what they cost, and the
daily spending cap that guards them (ADR 0027). The API key lives in the
environment (`ANTHROPIC_API_KEY`) and never in code.
"""

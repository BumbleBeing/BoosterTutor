# ADR 0021 — Without an account, no Claude

**Status:** Proposed · **Date:** 2026-10-13 · **Amends:** development plan §4.4 item 3 (anonymous rate limit), Phase 7 (nullable `user_id` for anonymous reviews, the claim-by-session-cookie migration, and the "anonymous reviews still work" check) · **Relates to:** ADR 0020 (practice drafts, which need an account)

---

## Context

The development plan lets an anonymous visitor run full reviews, Claude's
written critique included, at a lower rate limit (2 a day against 10). It
plans a claim-by-cookie flow so a review run before signing up can be
attached to the new account.

Practice drafts changed the calculation. They need an account (they are
saved, redrafted and reviewed later), and the end-of-draft Draft Review is
on demand rather than automatic (ADR 0020). That left the question of what
an anonymous visitor gets at all.

## Decision

**Claude is only ever called for a signed-in user.** Without an account:

- **Draft Review** and **Deck Review** both run, but return only their
  Python output: every verdict, every fitness class and score, and the deck
  build analysis. There is no written critique.
- **Practice drafts** are unavailable.
- **Nothing is saved**, so there is nothing to claim later. The
  claim-by-session-cookie flow is dropped.

Signed in, everything is available, under the per-user rate limits in the
plan.

This holds to the project's core rule from the other side. Python computes
every fact and every verdict, so the anonymous product is the *whole*
analysis. The account adds the explanation in prose, saved history and
practice.

## Considered options

- **The plan as written** (anonymous LLM reviews at 2 a day, plus the claim
  flow) was rejected. IP-keyed rate limits are easy to get around, so the
  Claude budget would be exposed to traffic with no identity. The claim flow
  is also one of the fiddliest parts of Phase 7.
- **Draft Review only for anonymous visitors, with Deck Review requiring an
  account** was rejected as an inconsistency with nothing to justify it.
  Both reviews have a Python half worth showing.
- **No anonymous access at all** was rejected. A visitor who sees the
  verdicts first has a concrete reason to sign up for the explanations.

## Consequences

**Phase 7 gets simpler.** `user_id` on saved reviews can be `NOT NULL`,
because anonymous reviews are never stored. The cookie-claim migration and
its edge cases go away. The ownership check stays exactly as planned.

**Every Claude call has a user ID,** so the plan's `llm_calls` log and its
per-user rate limit cover all spend, and the anonymous LLM tier in §4.4 is
deleted. Anonymous Python-only reviews still get an IP-keyed limit, since
they still cost database reads and CPU.

**The landing experience changes.** The first thing an anonymous visitor
sees is a table of verdicts, not prose. The review page must stand up as a
product without the text, which the colour-bordered pick view planned for
practice drafts already aims to do.

**Revisit when:** Python-only reviews prove too little to convert visitors,
in which case a single free LLM review, tied to a verified email, is the
next step to try, not anonymous access.

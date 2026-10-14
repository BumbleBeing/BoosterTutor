# BoosterTutor

**WHAT:** LLM-based Magic: the Gathering Limited coach. Two features at launch: Draft Review (17Lands draft log → a short critique of every pick: 42 in a Play Booster set, 45 in an older 15-card set) and Practice Draft (a draft against fitness-driven bots using real opening packs, with each pick rated as it is made; prototyped in DraftDouble). Deck Review (deck + sideboard → build critique and ranked swap suggestions) is postponed until after launch (ADR 0022). See `CONTEXT.md` for the terms. Advice blends format-level meta (archetype/colour strength) with card-specific synergy.

**WHY:** First production web app for a novice-to-web-dev developer. Full phased plan lives in `/docs/development_plan.md` — check it for the current phase before starting work; don't jump ahead to later phases uninvited.

**HOW / Stack:**
- **Frontend:** SvelteKit + TypeScript + Tailwind CSS (not React/Next), deployed on Vercel at `boostertutor.dev`.
- **Backend:** Python 3.12 + FastAPI, managed with `uv`, deployed on Render at `api.boostertutor.dev`. Owns all parsing, analysis, ingestion, and Claude calls.
- **Database:** Postgres on Supabase, via SQLAlchemy 2.0 + Alembic migrations.
- **Auth:** Supabase Auth (email magic link + Google). SvelteKit holds the session cookie; FastAPI verifies the JWT against Supabase's JWKS. Accounts + saved review history.
- **LLM:** Anthropic Claude API — `claude-sonnet-5` primary, `claude-haiku-4-5-20251001` for cheap classification. Key lives in backend env vars only, never committed.
- **Card data:** Scryfall bulk data (oracle text, images, mana cost, rarity) + 17Lands (ALSA, ATA, GIH WR, IWD, colour-pair and archetype-scoped win rates), pulled by `api/src/boostertutor/ingest/scryfall.py` and `ingest/seventeen_lands.py` into `cards` / `card_prints` / `card_draft_stats` / `card_archetype_stats` / `archetype_stats`. Refreshed nightly by a GitHub Actions cron job.

**Core architectural rule:** Python computes every fact and every verdict; Claude only explains them in prose. No statistic may appear in output that was not passed into the prompt. `parsing/` and `analysis/` stay pure — no network, no DB, no clock — so they can be tested exhaustively.

**Conventions:**
- Small, frequent commits, Conventional Commits style. Feature branches → PR → `main`. `main` stays deployable at all times; CI must pass to merge.
- Prefer plain, well-commented code over clever code — explain non-obvious choices, since I'm learning web dev as we go.
- Confirm before big architectural changes (schema changes, new dependencies, deploy config); proceed on your own for routine work (formatting, small fixes, tests).
- Record real decisions as short files in `docs/decisions/`. Prompts are versioned files in `docs/prompts/` and are never edited in place.
- Be a good citizen with 17Lands: cached snapshots only, at most one request per set/format/day, identifying User-Agent, never called from a user request path.

**Current phase:** Phase 2 — Schema for cards and 17Lands statistics, the Scryfall bulk ingest, and the 17Lands data work. Update this line as phases complete; see `/docs/development_plan.md`.

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues for `BumbleBeing/BoosterTutor`, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default label vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/decisions/` (this repo's existing decision-record convention, used in place of `docs/adr/`) at the repo root. See `docs/agents/domain.md`.

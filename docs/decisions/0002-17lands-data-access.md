# ADR 0002 — 17Lands data: the public datasets only, validated from within

**Status:** Proposed · **Date:** 2026-10-14 · **Amends:** development plan §2.3 ("Path A") and the Phase 2 "Done when" spot check · **Relates to:** ADR 0019 (opening packs, from the same draft dumps), CLAUDE.md's 17Lands etiquette rule · **Amended by:** ADR 0023 (a single draft's replay, fetched when its owner submits the link)

---

## Context

The development plan's §2.3 offered two ways to get 17Lands data:

- **Path A**: the JSON endpoints behind the 17lands.com card ratings pages.
- **Path B**: the public datasets, gzipped CSV dumps on S3, one draft dump
  (a row per pick) and one game dump (a row per game) per set and format.

The plan made Path A the daily source and Path B an offline cross-check, and
its Phase 2 "Done when" asked for our computed GIH WR to match 17Lands'
published figure for five cards.

17Lands has settled the question itself. The site's endpoints answer with:

> This data is only for use on 17Lands.com. The only data permitted for
> outside use (public or private) is available at
> 17lands.com/public_datasets.

and its [usage guidelines](https://www.17lands.com/usage_guidelines)
discourage automated scraping of the site, pointing to the public datasets
instead. Those datasets are released under **CC BY 4.0**. The DraftDouble
prototype found this in September 2026 and has used only the public
datasets since.

## Decision

### 1. The public datasets are the only source

BoosterTutor reads only
`https://17lands-public.s3.amazonaws.com/analysis_data/{draft_data,game_data}/{draft,game}_data_public.{SET}.{FORMAT}.csv.gz`
and computes every statistic itself: ALSA and ATA from the draft dump; GP,
OH, GD, GIH and GND win rates, IWD, and archetype records from the game dump
(`api/src/boostertutor/ingest/seventeen_lands.py`). The endpoints behind
17lands.com are not called, not for data and not for validation. Checked
2026-10-14. (One exception, added later: a user's own draft replay, fetched
when they submit its link. See ADR 0023.)

### 2. It runs on a schedule, politely

With Path A gone, the datasets are the only source, so they are ingested on
a schedule rather than offline:

- one HEAD request per set and format to read the game dump's
  `Last-Modified`; when it matches the last run in `ingest_runs`, nothing
  is downloaded
- otherwise the two dumps are downloaded once, cached under `data/raw/`, and
  named by date
- an identifying `User-Agent` with a contact address; exponential back-off;
  never from a user request path
- the Scryfall ingest also reads the first line of each set's draft dump, to
  find its bonus-sheet cards

That stays inside CLAUDE.md's rule of at most one request per set, format and
day.

### 3. Validation is internal, not against the website

Comparing our figures with 17Lands' published ones would mean using exactly
the data 17Lands restricts to its own site. So the five-card spot check is
dropped. In its place:

- **Hand-worked tests** of every aggregation: ALSA, ATA, and each win rate
  and its game count, on rows small enough to check with a pencil.
- **Identities that must hold on real data**: GIH = OH + GD, GP = GIH + GND,
  and IWD = GIH WR − GND WR, for every card. On HOB's 2026-10-01 snapshot they
  hold for all 193 cards.
- **Agreement with an independent run**: DraftDouble computed HOB from an
  earlier dump with separately written code. GIH WR agrees to 0.33 points on
  average and ALSA to 0.07 picks, the drift expected from 34% more games.
- **Plausibility**: names resolve with none unmatched, a format average in the
  mid-50s (17Lands users are a stronger-than-average population), the lowest
  ALSAs on the bombs.

### 4. Attribution

Anything built on this data carries a visible, top-level 17Lands credit, as
CC BY 4.0 and 17Lands ask; the ingest prints one after every run. 17Lands
also asks third-party tools not to publish a new set's data until its 12th
day on Arena.

## Considered options

- **Path A, as the plan proposed**: rejected. 17Lands says no.
- **A one-off manual comparison with the website, within about 1 point**:
  rejected. It is still using the restricted figures, just by hand. A trial
  on five HOB cards found the win rates within 0.7 points but the game counts
  about twice ours, so the website is not a like-for-like reference for a
  dump anyway: it covers more data, up to the present day.
- **Asking 17Lands whether a manual check is acceptable**: not needed. The
  internal checks above test the same thing, and 17Lands' answer about the
  site's data is already published.

## Consequences

- The Phase 2 "Done when" line about matching 17Lands' published figure is
  replaced by the internal checks in §3.
- **The figures lag.** The dumps are updated less often than the website:
  HOB's latest is 2026-10-01, and MSH's 2026-07-27. A set's first weeks have
  no dump at all; FRA, released 2026-10-02, had a draft dump but no game dump
  on 2026-10-14. The ingest skips such a set until its game dump appears, and
  the review must say "not enough data" for it rather than guess.
- **Our game counts are not 17Lands'.** They are counts from the dump we
  read. Sample-size thresholds (500 games per card, 200 per card per
  archetype) are applied to our counts.

**Revisit when:** 17Lands changes its terms, or offers an official API.

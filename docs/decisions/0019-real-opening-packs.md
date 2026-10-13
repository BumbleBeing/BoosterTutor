# ADR 0019 — Practice drafts use real opening packs

**Status:** Proposed · **Date:** 2026-10-13 · **Relates to:** ADR 0020 (practice draft determinism, which pins packs by index and library), ADR 0008 (fitness classes), the development plan's "only sets 17Lands publishes data for" non-goal

---

## Context

A practice draft needs 24 opening packs: eight drafters, three packs each.
"True to life" is the whole point. A practice table that opens packs no real
table would open teaches the wrong instincts about what is common, what
wheels and how deep a colour runs.

There are two ways to get packs:

- **Generate them from collation rules**: slot counts per rarity, the
  wildcard and foil slots, the land slot, and rarity weights. This is what
  Draftsim does. It needs a hand-written rule set for every set, and the rules
  are only as good as our reading of Wizards' collation, which is not
  published in full.
- **Resample real ones.** The 17Lands draft dump records every drafter's
  first pick of each pack (`pick_number` 0) with the pack's full contents.
  For HOB Premier Draft that is 43,650 drafts × 3 ≈ **130,000 real opening
  packs**, each 14 cards.

## Decision

### 1. Opening packs are resampled, not generated

A practice draft draws its 24 opening packs from the real packs 17Lands
recorded. Collation, print-sheet quirks, wildcard and foil slots and
rarity frequencies are then exactly right without modelling any of them,
and a new set needs no rules, only data.

The pool is enlarged with opening packs from the **QuickDraft** and
**TradDraft** dumps as well as Premier, but only once their makeup has been
checked against Premier. The check compares the distribution of rarity
counts per pack, and how often each card appears. A format whose packs
differ is left out rather than mixed in.

### 2. The pack library is a file, not a table

Each set's opening packs are one compressed file (about 2–4 MB), stored in
**Supabase Storage** and loaded into memory by the backend. Postgres stores
only **pack indices** into that file.

Packs are fixed, read-only reference data that is always read whole. In
Postgres they would cost roughly 15–20 MB per set with indexes, and
300–400 MB across 20 sets: most of Supabase's free tier, spent on data that
never changes. The prototype in DraftDouble keeps the same file format on
local disk.

### 3. Duplicate protection

- No opening pack appears twice in one practice draft.
- A new practice draft skips every pack index already used anywhere in the
  user's drafts. The arithmetic is what makes this necessary: with about
  130,000 packs and 24 per draft, a repeat within one draft is about a
  1-in-500 event. But a user who has played 50 drafts would expect about 5
  repeated packs, and after 100 drafts about 22.
- **Redrafts are exempt.** Replaying the same packs is what a redraft is
  (ADR 0020).
- Deleting a practice draft frees its packs.

### 4. A library file is never edited

A pack index only means something within one library file, and rebuilding
from a newer 17Lands dump would reorder or add packs. So a library file is
**immutable**. Its `library_id` is a hash of its cards and packs, and is part
of its file name, so a rebuild writes a *new* file alongside the old one
instead of changing what an existing index points at. Identical content
gives an identical id, so a rebuild that changes nothing writes the same
file.

Consequently:

- **A stored practice draft records the `library_id` its pack indices
  belong to**, next to its stats snapshot (ADR 0020). A redraft reads the
  same library as its root, just as it uses the same snapshot.
- A library file is kept while any draft refers to it. New drafts use the
  newest library for the set.
- Duplicate protection is keyed by `(library_id, index)`. If exclusions ever
  need to carry over to a newer library, a pack's identity is its sorted
  card list, which both files hold, so no extra data is needed to translate.

Measured on the first build (HOB, DraftDouble, 2026-10-13): 299,042 packs
from Premier, TradDraft and PickTwoDraft, all three passing the §1 check,
4.2 MB gzipped. That is enough for over 12,000 drafts per user before
duplicate protection runs out.

## Considered options

- **Rules-based generation** (the Draftsim route) was rejected as more work
  for a less accurate result. It would only be needed for a set with no
  17Lands data, and the development plan already excludes those.
- **Using rules measured from real packs** was rejected for the same reason:
  it adds a model between us and data we already have.
- **Packs in Postgres, capped at 50,000 per set** was rejected. It trades the
  "packs never repeat" guarantee for storage, when object storage is free at
  this size.

## Consequences

**A set is draftable only once 17Lands has published its dump.** The same is
true of every other feature, so this costs nothing new. A practice draft
also needs the set's tag taxonomy and a stats snapshot (ADR 0020). The set
picker offers exactly the sets that have all three, newest first.

**Supabase Storage becomes a dependency** of the backend. It is the same
provider as the database and auth, so there is no new account or vendor.

**The packs carry 17Lands' sampling.** They are packs opened by 17Lands users
on Arena, which is a sample of Arena packs, not of paper ones. For a coach
aimed at Arena drafters, that is the right population.

**Revisit when:** a set worth drafting has no 17Lands data; or Wizards
changes collation in the middle of a set, in which case the library would
need splitting by date.

# ADR 0028 — Colour Sources, Fixers and the effective land count

**Status:** Proposed · **Date:** 2026-10-15 · **Amends:** ADR 0026 §1 (the mana metric, and a land-count metric added) · **Relates to:** ADR 0004, 0006 (the tag taxonomy file)

---

## Context

ADR 0026 measures a Submitted Deck's mana by comparing its Colour Sources
against Frank Karsten's pip requirements, and it left Fixers to be
designed. Two facts shaped the design:

- **HOB has 18 cards that fix or ramp, of six kinds.** There are fetch
  lands that get any basic (Hobbit Hole, Elven Passage), a Forest-only ramp
  creature (Wood Elves), two-basic ramp (Troop of Ponies), land-to-hand
  tutors (Thrór's Map, Down in the Valley, Old Thrush), a mana rock
  (Giant's Boulder), and Treasure makers. Some make one Treasure (Dori,
  Long-Bodied Grey Dog), and some depend on how the game goes (Bejeweled
  Warg, Orcrist, both Smaugs, The Misty Mountains Cold). The existing
  `fixing` tag is a synergy tag with no colour information.
- **Karsten's 2022 update** ("How Many Sources Do You Need to Consistently
  Cast Your Spells? A 2022 Update", TCGplayer, formerly ChannelFireball)
  has a 40-card column assuming 17 lands and a 90% chance of casting on
  curve. It also gives partial weights for non-land sources, each counting
  only toward spells at or above a minimum mana value.

Which land substitutes exist shifts from set to set, so the kinds and
their weights must be data, not code.

## Decision

### 1. Hand-authored mana sources, per set

The taxonomy file goes to format version 2 with two new sections:

- **`source_kinds`**: each kind the set uses, with its colour weight,
  land weight, minimum mana value and a note. A shared defaults file holds
  the kinds below, and a set copies or overrides them.
- **`mana_sources`**: card name → `{kind, colors, …}`, loaded into a new
  `card_mana_sources` table. `colors` lists what the card **fixes for**
  (`"G"`, `"BR"`), and the card adds sources to those colours only.
  `"basics"` means any basic the deck runs. An entry may override its
  kind's weights, with a note saying why.

The `fixing` synergy tag is unchanged. It prices synergy, and a mana
source entry prices mana. A Fixer is any card, land or not, with a
`mana_sources` entry.

### 2. The default kinds

| Kind | Colour weight | Counts toward spells of mana value | Land weight | Basis |
|---|---|---|---|---|
| `fetch_basic` | 1 | any | 1 | Karsten (fetch lands) |
| `mana_rock` | ¾ | any | ½ | Karsten |
| `ramp_creature` | ½ | 2+ | ½ | Karsten (mana creatures) |
| `ramp_spell_2` | ¾ | 3+ | ½ | Karsten (two-mana ramp) |
| `ramp_spell_3` | ½ | 5+ | ½ | Karsten (three-mana ramp) |
| `treasure` | `expected` × ¼, capped at 1 | 3+ | 0 | Karsten (¼ per Treasure) |
| `land_tutor` | ½ | 3+ | ½ | by analogy, and Jackson |
| `landcycler` | ½ | 3+ | ½ | Jackson |

- **Treasure.** Each `treasure` entry carries `expected`, the number of
  Treasures the card usually makes, authored by hand (Dori 1).
- **Basics.** A `"basics"` entry is a source only for colours whose basic
  land the deck runs. In a deck of three or more colours its colour weight
  is multiplied by ⅔, as Karsten does for fetch lands, because the card
  forces a choice. This applies to every basic-fetcher, including tutors
  and landcyclers.
- **Placeholders.** The land weights other than the landcycler's, and both
  of `land_tutor`'s figures, are placeholders by analogy, to be tuned.

### 3. The requirement, and the mana metric

Each coloured spell's requirement comes from Karsten's 40-card table, by
mana cost. For gold cards, each colour's requirement is raised by one, as
Karsten does. A hybrid symbol is met by sources of either colour.

Each spell's available sources are the deck's lands that produce the
colour, plus the weighted Fixers whose minimum mana value the spell meets.
**Only a shortfall counts:** a deck with more sources than a spell needs is
not penalised.

- **The mana metric** is the deck's **largest shortfall**: the most
  sources any one spell is short, with that spell named as the fact ("this
  needs 10 red sources; your deck has 7").
- **The number of spells short** is passed to the Draft Summary as a
  further fact, not graded.

**Simplifications of Karsten**, stated so they are not mistaken for
oversights:
- His "only if you can cast the fixer reliably" condition is dropped. It
  rarely binds in two-colour Limited.
- The turn-one rule (only untapped sources count) is dropped. Limited
  decks seldom depend on turn-one plays.
- The table is not adjusted for land counts other than 17. Land count is
  measured by §4.

### 4. The effective land count

- **Effective lands** are the sum of every card's land weight: 1 for a
  land, and the table's land weight for a Fixer.
- **The target** depends on the average mana value of the nonland cards:
  16 below `low_curve_mv` = 2.2, 18 above `high_curve_mv` = 3.2, and 17
  otherwise. All are placeholder tunables.
- **The land metric** penalises being short twice as hard as being over:
  `max(0, target − effective) + ½ × max(0, effective − target)`.

Like every metric, it is graded by percentile among the format's 40-card
decks (ADR 0026). When it is built, check once that HOB's dump wins most
near the target, and record the result here.

## Considered options

- **Colour-suffixed tags** (`fixer_g`, `fixer_any`) were rejected. Tags
  cannot carry a kind, an expected Treasure count or an override, and the
  weights would end up in code.
- **Weights in code with no per-set kinds** were rejected, because each
  set's land substitutes differ.
- **Every weight set by hand with no defaults** was rejected. Most cards
  fit a kind, and the kinds give their figures a source.
- **A total or count of shortfalls as the graded metric** was rejected in
  favour of the largest shortfall, which catches the pip-heavy bomb with
  too few sources. The count is still given to the summary.
- **Letting the regression find the best land count** was rejected. About
  20,000 decks per format is not enough to fit a reliable curve.

## Consequences

- Each set needs `mana_sources` authored before its mana and land grades
  are complete. HOB's 18 candidates are listed above.
- Two new tables (`card_mana_sources`, and the ratings table of ADR 0026)
  need a schema confirmation when built.
- The game dump has basic-land columns, and 95% of HOB's decks are exactly
  40 cards, so both metrics can be computed for real decks.

**Revisit when:** the dump check shows a format winning most away from its
target; or a set has a land substitute that no kind fits.

**Glossary:** Fixer is redefined, and Effective Land Count is added, in
`CONTEXT.md`.

# BoosterTutor

An LLM-based Magic: the Gathering Limited coach. Python computes every fact and
every verdict; Claude only explains them in prose.

## Language

### Draft structure

**Pool**:
Everything a drafter has already taken at a given point in a draft.
_Avoid_: deck, collection

**Pack**:
The cards available to choose from for a single pick.
_Avoid_: booster

**Opening Pack**:
A pack as opened, before anyone has picked from it: fourteen cards in a
Play Booster set. Every pack in a draft is what remains of one opening pack.
Practice drafts use real opening packs recorded by 17Lands. See ADR 0019.
_Avoid_: booster, fresh pack, full pack

**Pick**:
One decision: a pack, the pool before it, and the card taken.

**Deck**:
The part of a pool its drafter intends to play.
_Avoid_: maindeck, main, build

**Sideboard**:
The part of a pool its drafter does not intend to play. A pool is its deck
plus its sideboard.
_Avoid_: bench, unplayed, not being played

**Table**:
The eight drafters in one draft and the order packs pass between them.
_Avoid_: pod, lobby

**Practice Draft**:
A draft played inside BoosterTutor, where the user sits at a table with seven
bots and each pick is rated as it is made. Contrasts with a draft imported
from 17Lands, which the user played elsewhere and is reviewed afterwards.
_Avoid_: simulated draft, mock draft, sim draft

**Redraft**:
A practice draft that replays another practice draft from pick 1, with the
same opening packs, seed and stats snapshot. Its bots repeat their original
picks until the user's choices change the packs they see. Redrafts form a
tree under the original practice draft. See ADR 0020.
_Avoid_: re-do, replay, retry, rematch

**Stats Snapshot**:
The frozen figures a practice draft is rated against: card and archetype
statistics, the tag taxonomy and the fitness constants as they stood when
the original draft began. A verdict, once shown, never changes. See ADR
0020.
_Avoid_: data version, stats date

**Bot**:
A simulated drafter at a practice draft's table. A bot usually takes a card
the fitness function rates `solid` for its own pool, occasionally one it
rates `questionable`, and never a `mistake`. See ADR 0020.
_Avoid_: AI drafter, opponent, CPU

**Archetype**:
A two-colour pair a deck can be built toward, named in sorted WUBRG form (`BR`,
`WU`). The ten pairs are the hypotheses the fitness function scores against.
_Avoid_: colour pair, deck type, lane

### Grading

**Fitness**:
A card's value to a specific pool at a specific point in a draft, measured in
percentage points of win rate.
_Avoid_: score, rating, grade

**Fitness Class**:
The band a card in a pack falls into, from the gap between its fitness and the
highest fitness in that pack: `solid` within 2pp, `questionable` within 4pp,
`mistake` beyond. Fixed thresholds in percentage points, with no noise floor
and no absolute floor, so the best card in a weak pack is still `solid`. Every
card in a pack has one, including the cards not taken. See ADR 0008.
_Avoid_: classification, rating, grade, standing, optimal, defensible, reasonable

**Verdict**:
The band a pick falls into. Normally the fitness class of the card taken; the
exception is `indifferent`, a pick where the pack offered no choice worth
making, so no class applies. See ADR 0008.
_Avoid_: grade, judgement, classification, unimportant

**Indifferent**:
A pick where nothing was at stake: the pack held one card, held nothing
scorable, or every card in it was `solid`, so no available choice cost the
deck any equity. Taking a basic land is never indifferent. See ADR 0008.
_Avoid_: unimportant, neutral, skip

**Archetype Float**:
For one archetype, the share of the pool's coloured cards that archetype
could play. Ten of them, one per pair; they overlap, so they do not sum to
one. Colourless cards and basic lands are outside the measure entirely.
See ADR 0012.
_Avoid_: probability, belief, weight

**Predicted Archetype**:
The one two-colour pair the pool is heading toward: the pair with the
highest archetype float. None only when no pair can play anything at all.
One definition, shared by the fitness function, the deck-shape terms, the
UI and the brief. See ADR 0012.
_Avoid_: leading colours, lane, belief

**Colour Options**:
The colour sets a card can be *played* in, each written in sorted WUBRG form.
For a spell, what can pay its cost: a hybrid card has one option per colour,
a gold card a single option holding both. For a land, what it serves — its
colour identity, read the same way a hybrid card is. A colourless card has
one empty option and fits everywhere. See ADR 0007 §5 and ADR 0012 §6.
_Avoid_: castable colours, colour requirements, pips

**Colour Tax**:
What a card's fitness loses for not being what the pool is buying: the gap
between the highest archetype float and the highest float of any archetype
that card could be played in, priced in percentage points and scaled by the
commitment ramp. Never negative, and a matter of degree rather than a
binary on/off. See ADR 0012.
_Avoid_: colour fit penalty, off-colour, mismatch

**ALSA**:
Average Last Seen At: the pick by which a card has usually gone from a pack,
averaged over every pack it appeared in. A measure of what drafters believe
a card is worth, not of what it is worth. Low for bombs, and also for rares
taken early for collection value. Shown to the reader and passed to the
brief, but **not a scoring input**: ADR 0018 retired the one term that read
it, on the finding that what drafters believe adds nothing to what the win
rate says is true.
_Avoid_: pick order, average pick, ATA

**Noted Pick**:
A pick that earns a Pick Note: its verdict is `questionable` or `mistake`,
or it is a Narrow Pick. All other picks are stated, not explained, and a
draft with none at all is a valid outcome. See ADR 0024, which replaced the
mistakes-only Relevant Pick of ADR 0008.
_Avoid_: relevant pick, interesting pick, flagged pick

**Narrow Pick**:
A pick where the pack held at least eight distinct cards, exactly one of
them `solid` and at least two `questionable`, and the drafter took the
`solid` one: there was one right answer among tempting alternatives, and
the drafter found it. Earns a positive Pick Note. See ADR 0024.
_Avoid_: standout pick, good pick, great pick

### Coaching

**Pick Note**:
Claude's written explanation of one Noted Pick, using only what was known
at the moment of the pick. Once shown, it never changes. See ADR 0024.
_Avoid_: blurb, comment, note (alone)

**Draft Summary**:
Claude's review of a whole draft and its Reviewed Deck, written with
hindsight: the colour arc, what wheeled, the deck's ratings and the lesson
to carry forward. See ADR 0024.
_Avoid_: overall note, recap, summary note

**Key Pick**:
One of at most two picks a Draft Summary points to. Claude names only the
pick; Python shows its card, verdict and gap. See ADR 0030.
_Avoid_: highlight, turning point

**Format Primer**:
What every Draft Summary is told about the format: each colour pair's
win rate, the average GIH WR and the best commons of each colour, from
the 17Lands statistics. Cached, and the same for every draft of the
format. See ADR 0030.
_Avoid_: meta summary, format brief

**Submitted Deck**:
A 40-card deck a drafter builds from their pool and submits after the
draft. A later submission replaces the current one. See ADR 0025.
_Avoid_: final deck, build, list

**Reviewed Deck**:
The first Submitted Deck for a draft, the only one a Draft Summary
describes. Later Submitted Decks get Deck Ratings only. See ADR 0025.
_Avoid_: original deck, first build

**Deck Rating**:
A letter grade for a Submitted Deck, overall or for one metric, set by
where the deck falls among real decks from the same format. Relative to
17Lands players, not to all players. See ADR 0026.
_Avoid_: deck score, deck grade

**Colour Source**:
A card that can produce a colour of mana for a deck: a land that taps for
it, or a Fixer. Counted against the deck's pip requirements. See ADR 0026.
_Avoid_: mana source, colour producer

**Fixer**:
Any card, land or not, with a hand-authored mana-source entry saying which
colours it fixes for and how much it counts: a fetch land, a mana creature,
a mana rock, a Treasure maker, a land tutor or a landcycler. Distinct from
the `fixing` synergy tag. See ADR 0028.
_Avoid_: ramp, mana fixing (as a noun for a card)

**Effective Land Count**:
A deck's lands plus the partial land weight of its Fixers, such as half a
land per landcycler. Compared against a target set by the deck's average
mana value. Being short is penalised twice as hard as being over. See ADR
0028.
_Avoid_: land count (when Fixers are meant), mana count

### Tags

Tags are authored per set, not shared between sets. Name a tag after the set's
own mechanic where one exists (`storied`, `ferocious`), and generically where
none does (`go_wide`, `graveyard_payoff`).

Tags are assigned directly and exhaustively, with no hierarchy between them: a
card that makes Treasure is tagged `artifact` outright, rather than tagged
`treasure` and inferred to be an artifact. The tags on a card are the whole
truth about it.

**Tag**:
A named property attached to a card by hand, describing what it supplies to a
deck or what it rewards.
_Avoid_: label, trait, keyword

**Enabler**:
A card that supplies a resource or condition that other cards reward.
_Avoid_: provides, provider, source

**Payoff**:
A card that rewards a resource or condition being present in the deck.
_Avoid_: wants, wanter, needs

**Self-Payoff**:
A tag that synergises only with itself, for a card that rewards having more
copies of that same card in the deck. Normally a vocabulary of one card and
named after it (`seven_dwarves`). Its coefficient sits on the diagonal of the
tag pair grid — the pairing of the tag with itself — and prices what each
further copy is worth to the copies already there. See ADR 0004.
_Avoid_: self-synergy, stacking tag, multiples tag

**Tag Pair**:
One enabler tag coupled to one payoff tag, carrying the importance coefficient
that prices that synergy. A card may carry many tags of both kinds. A
self-payoff is the one case where the two halves are the same tag.
_Avoid_: synergy pair, combo

**Importance Coefficient**:
The weight given to a single tag pair, expressing how much an enabler is
actually worth to its payoff in this set.
_Avoid_: weight, multiplier, synergy score

**Decay Coefficient**:
The second weight on a tag pair, from 0 to 1, saying how much of the previous
copy's value each further copy of the complementary tag is worth. 1 means no
decay and every copy counts in full; 0.5, the default, converges on twice the
importance coefficient; 0 means only the first copy counts at all. See ADR
0009.
_Avoid_: cap, saturation, falloff, threshold synergy

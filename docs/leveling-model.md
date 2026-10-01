# Leveling model (single target)

The model behind the page's level planner, the talent builder's score and the leveling verdicts. Python reference: `models/leveling_sim.py` (fight loop and rest model) and `models/character.py` (the Mage by level, rotations, `evaluate`). The page runs `leveling.js`, a port; `tests/leveling_parity_test.js` checks it against Python fixtures case by case (bit-for-bit equal).

Pulls of several mobs are the AoE model's job (`models/aoe.py`). It reuses this model's character (`make_char`) and rest model (`rest_setup`, `travel_regen`, `rest_solve`).

## What it computes

`evaluate(L, talents, gear, opts)` returns the fastest single-target rotation for a build at level L and its **seconds per kill**:

> seconds per kill = fight + 8 s walking to the next mob + rest back to full mana and health

Each fight starts from a full pool. It runs until the mob dies, the Mage dies, or 240 s pass. A rotation in which the Mage dies (at any of the three mob health values) or the mob outlives 240 s is **infeasible**. It never beats a feasible one.

## Method

**Event loop.** The loop steps 0.02 s at a time, the Warlock lab's pattern. Hit and crit enter every hit as expected values. A crit's value is `1 + crit x (multiplier - 1)`, with 1.5x crits plus Ice Shards (Frost) and Arcane Mind (Arcane).

**Procs that trigger casts use accumulators.** This covers Frostbite freezes, Fingers of Frost charges, Missile Barrage and Hot Streak. Each landed spell adds its expected proc, and the proc fires once a whole one has built up. A player reacts to a 15% proc, but a blended 15% never crosses a decision threshold.

**Proc phases.** Each fight starts its accumulators part way: the three mob health runs start at 1/6, 1/2 and 5/6 (Hot Streak's three stacks at 3 times that), so their average gives the expected proc count. Hot Streak stacks carry to the next pull. They last 20 s, and 8 s of walking plus a few seconds of rest is shorter (ASSUMPTION: no expiry between pulls).

**Blended procs.** Clearcasting, Master of Elements, Winter's Chill stacks, Improved Scorch stacks and Touch of the Grave enter as expected values.

**Engagement.** The mob starts 25 yd out (a 30 yd pull, 5 yd melee reach) and runs at the Mage once the first spell lands. The range talents add to that gap when their school's spell opens: Arcane Geometry +3/6 yd (Arcane), Flame Throwing +3/6 yd (Fire), Arctic Reach +10/20% of Frostbolt's 30 yd. Slows cut the mob's speed; the strongest slow wins. A root or stun stops it. **The Mage takes mob damage only in melee range.** The Warlock model takes it for the whole fight. In melee the mob also pushes back casts, and Frost or Ice Armor chills it.

**Roots and stepping back.** A root (Frost Nova, or a Frostbite freeze) holds the mob with a chance that each damage event breaks. Frostbite's freeze breaks like Frost Nova's: its client aura row is the same (see assumption 13). Stepping back is a choice the rotation search makes, not a rule. It can be never, after Frost Nova's root only, or after any freeze. When on, the Mage walks 2 s away from a mob held within 10 yd before casting again. The step overlaps Frost Nova's global cooldown. The `kite` option switches stepping off entirely. The Warlock model could not value moving at all.

**Rotations.** The search covers 13 base rotations: a filler with or without Fire Blast on cooldown, Arcane Blast then a spender, or the wand. It runs each one the build can cast.
- **Modifier groups:** each is off or one option.
  - how roots are used: Frost Nova without stepping; Nova then step back; Nova and step back after any freeze; with Frostbite, step back after freezes and no Nova
  - melee-range instants (Cone of Cold, Blast Wave, Arcane Explosion)
  - a Pyroblast pull
  - Ice Barrier before the pull
  - a wand finish below 20%
- **Rank of the main spell:** one down, two down, or rank 1. By default this is tried only at level 19 and below (see Low ranks).
- **Automatic casts:** every rotation also casts, when the build has them:
  - Ice Lance on a frozen target or a Fingers of Frost charge
  - a 1.5 s Pyroblast at 3 Hot Streak stacks
  - a free Arcane Missiles on Missile Barrage
  The name gets ' +Ice Lance', ' +Hot Streak Pyroblast' or ' +Missile Barrage' when the rotation casts them, and `policyLabel` says so.

**The search.** Every combination is too many to run on each builder click, so `evaluate` searches:
1. **Probe.** Every base runs plain, at each allowed rank, with "Frost Nova, then step back", and with that option at each allowed rank (a lower rank can pay only once Nova is in); its best probe ranks it.
2. **Local search.** The best six bases each get a search from their best probe. It tries every change of one group and moves to the fastest, until no change helps (steepest descent). For the best two bases it then tries every change of two groups at once, moves to the fastest, and starts over if one helps. Taking the first faster change instead (the first version) could strand the search three changes from the best: 3.3% at level 46.
3. **Memo.** Results are memoized within the call.

`analysis/leveling_search_check.py` compares this with an exhaustive search: every base x every modifier combination x every allowed rank. Its grid covers the four talent orders at every third level, gear 1 and 2, option cases and races. The largest gap is reported in `mage-research/leveling/leveling_v1.md`, and it must stay under 0.5%.

**Cooldowns longer than a kill.** This covers Presence of Mind, Arcane Power, Combustion, Blood Fury, Berserking, Eureka! and Ice Barrier. Each is used on the pull on (kill cycle / cooldown) of pulls. The kill cycle comes from a first pass at mob health x1.0 without them. Wake of Fire's crit applies if the first Fire Blast comes within 30 s of the last kill (walking plus rest plus time into the fight).

**Rest.** Eating and drinking run at once, so rest is the longer of the two, not their sum.
- Spirit and natural health regeneration run on top.
- Conjuring costs a 3 s cast per stack and its mana, both paid by resting.
- Cooldown actions replace drinking and eating time: Evocation, a mana potion, Cannibalize, Rapid Regeneration, Read Ley Line. Rest uses every subset of them. A kill cycle of `spk` uses each one `spk / cooldown` times, so `spk = fight + walk + rest(spk)` is solved by fixed-point iteration. An action counts only if it saves at least 1 s per use.
- Mana gems cost more mana to conjure than they restore (Agate 530 for 400, up to Ruby 1470 for 1100), so the rest model never uses them.

**Data.** Spell values come from `data/mage_spells.json` and talent values from `data/talents.json`. Every embedded row is checked against those files when fixtures are made (`tests/make_leveling_fixtures.py`). That script also checks that every `tv()` lookup in both models names a real talent (a table name in the talent slot reads rank 0 silently: until 1 Oct 2026 Permafrost's extra slow was always 0 that way), and that the chill's slow is 40% plus Permafrost's 3/7/10% at 0 to 3 ranks; `tests/leveling_slow_fixtures.json` carries those values to the parity test.
- **Base stats by level.** Base mana and spell crit per Intellect come from the beta client's `PlayerExpectedStat` (1.60.1.69893). Base health, Intellect, Spirit and Stamina come from Wowhead's Forever gear planner (the arrays the ElliotWood sim takes its level-60 row from). Copies are in `forever-warlock-lab-drafts/mage-research/leveling/mage_base_stats.json`.
- **Mob stats.** Mob health, mob damage, the hit table and the 8 s walk are the Warlock lab's, so the two pages stay comparable.

## Low ranks (option `low_ranks`, test m13)

The evidence:
- **Coefficients.** Forever's client stores low ranks at full coefficients. Frostbolt rank 1's SpellEffect coefficient is 0.407 in 1.60.1 and 0.163 in Classic Era 1.15.9, so Blizzard rewrote them.
- **Level caps.** A rank's max level only caps its base damage growth (the sim's `effect.go`, `Average`).
- **Measurements.** ForeverChanges' downrank page cites DoubleZug's beta measurements. Healing Touch ranks 1 to 3 and Rejuvenation ranks 1 and 3 at levels 18 and 19 land within 2 points of the full coefficient. That rules out both Classic Era's below-20 cut and The Burning Crusade's level rule at those levels.
- **The gap.** No level above 19 has been measured, and a server rule that grows with level would not show in the client.

The options:
- **`measured` (default).** Lower ranks keep full coefficients, and rotations may cast them at level 19 and below. From 20 they cast the highest trained rank only, until test m13 measures a level 30+ character.
- **`full`.** Full coefficients and downranking at every level (untested).
- **`tbc`.** The coefficient x (rank max level + 6) / level, capped at 1. Ruled out at 18 and 19.
- **`classic`.** Classic's cut, 3.75% a level below 20 for spells learned below 20. Ruled out at 18 and 19. The old `below20=True` means this.

## Assumptions

Test ids refer to the merged test list (`mage-research/gap/tests.json`). Values without a source are marked ASSUMPTION.

| # | Input | Value as used | Source or status | Option (Python / page) | Test |
|---|---|---|---|---|---|
| 1 | Spell power | gear x level, gear 1 or 2 | Warlock page convention | `gear` | |
| 2 | Gear stats per level | Int 1.0, Stamina 1.0, Spirit 0.5 | ASSUMPTION | `gear_int`, `gear_sta`, `gear_spi` / `gearInt`, `gearSta`, `gearSpi` | |
| 3 | Base mana, health, Int, Spirit, Stamina by level | client and Wowhead gear planner tables | sourced (see Data) | | |
| 4 | Spell crit | 0.2% + Int x the client's crit per Int by level | 0.2% is Classic's Mage base spell crit, which the sim uses (`sim/core/base_stats.go` ClassBaseCritPercent); the 0.9075% in `base_stats_auto_gen.go` is TBC's level 70 fit | | |
| 5 | Mob health | 18 L + 0.62 L^2, averaged at x0.9, x1.0, x1.1 | Warlock lab | `hp_mults` / `hpMults` | m16 |
| 6 | Mob damage | 0.035 L^2 a second, taken **only in melee range**; the Warlock model takes it the whole fight | Warlock lab (curve) | `mob_dps_mult` / `mobDpsMult` | m16 |
| 7 | Hit chance | 96% same level, 95%, 94%, 83% at +1, +2, +3, plus Arcane Focus (Arcane) or Elemental Precision (Fire, Frost), cap 99% | Warlock lab | `level_diff` / `levelDiff` | m15 |
| 8 | Walking between kills | 8 s | Warlock lab | `travel` | |
| 9 | Pull distance | 25 yd to melee (30 yd pull, 5 yd reach), plus the range talents | ASSUMPTION (gap register meleeRange 5); talent values from data/talents.json | `pull_gap` / `pullGap` | |
| 10 | Mob run speed | 8 yd/s; player 7 yd/s | gap register (sim framework constant; warcraft.wiki.gg) | `mob_speed` / `mobSpeed` | m3 |
| 11 | Stepping back | a searched choice: never, after Frost Nova, or after any freeze; a step is 2 s of walking and no casting | ASSUMPTION | `kite`, `step_s` / `kite`, `stepS` | |
| 12 | Frost Nova break | each damage event (hits, DoT and Ignite ticks) breaks the root with chance 0.5 | ASSUMPTION (gap register) | `nova_break` / `novaBreak` | m12 |
| 13 | Frostbite freeze | breaks like Frost Nova (defaults to `nova_break`) | client: SpellAuraOptions for 12494 equals Frost Nova's (122, 865, 6131, 10230) and Entangling Roots' (339) in 1.15.9 and 1.60.1: ProcChance 100, ProcTypeMask 0x800A22A8, every damage-taken flag; roots that do not break (23694, 19675) have mask 0 or no row | `fb_break` / `fbBreak` (0: never breaks) | m12 |
| 14 | Spell pushback | each melee hit delays a cast 0.5 s; a channel loses one missile a hit; Burning Soul and Improved Channeling protect; none while Ice Barrier holds | ASSUMPTION (register channelPushback) | `pushback`, `pushback_s` / `pushback`, `pushbackS` | |
| 15 | Mob swing time | 2.0 s | ASSUMPTION (register mobSwingTime) | `swing` | |
| 16 | Armor | Frost or Ice Armor below 34, Mage Armor from 34 | brief | `armor` ('auto', 'frost') | |
| 17 | Frost and Ice Armor chill | melee attackers swing 25% slower for 5 s; each chill rolls Frostbite and Fingers of Frost | register armorChill (aura 319 read as attack speed, ASSUMPTION); client chill mask | `armor_slow`, `frostbite_source` / `armorSlow`, `frostbiteSource` | m17 |
| 18 | Casting regen | Mage Armor 50% plus Arcane Meditation 17/33/50%, added, capped at 100% | sim (adds both) | `regen_stack` ('add', 'max') / `regenStack` | m5 |
| 19 | Spirit regen | 6.25 + Spirit/8 a second, after 5 s without spending mana | sim (Classic Mage rule) | | m14 |
| 20 | Health regen out of combat | (6 + 0.1 Spirit) / 2 a second; Troll +10% and 10% of it in combat | ASSUMPTION (Classic lore) | | |
| 21 | Regen while eating and drinking | on | ASSUMPTION: Classic regeneration only pauses for 5 s after mana is spent, and drinking spends none | `spirit_drink` / `spiritDrink` | m10 |
| 22 | Water and food | client values (Crystal Water 4200 over 30 s at 60) | client | `wowhead_drinks` (25/26) / `wowheadDrinks`; `mountain_water` / `mountainWater` | m10, m27 |
| 23 | Levels 1 to 3 (no conjured water) and 1 to 5 (no conjured food) | rest at rank 1's rate | ASSUMPTION | | |
| 24 | Evocation | 8 s at 16x Spirit regen, every 8 min, in rest when it saves time | sim formula | `evocation` | m7 |
| 25 | Mana potions | on: the best one the level allows, one per 2 min, in rest when it saves 1 s or more | Wowhead Forever tooltips (values, levels); price from the client's BuyPrice (auction prices unknown) | `potions` | |
| 26 | Rest cooldown actions | used only when each use saves at least 1 s | ASSUMPTION | | |
| 27 | Mana gems | on, never used: conjuring costs more than they restore | client | `gems` | m24 |
| 28 | Ice Lance coefficient | 0.143; the x4 on a frozen target covers the whole hit | sim placeholder (client stores 0) | `il_coef` / `ilCoef` | m4 |
| 29 | Low ranks | full coefficients; lower ranks cast only at 19 and below | client; DoubleZug (see Low ranks) | `low_ranks` / `lowRanks` ('measured', 'full', 'tbc', 'classic') | m13 |
| 30 | Top-rank tomes | off (Frostbolt 10, Fireball 11, Arcane Missiles 7 at 60) | gap TOMES.md | `top_ranks` / `topRanks` | m6 |
| 31 | Spell values by level | the client's in-game formula (floor of base + per level x levels above learn, to the rank's max level) | sim effect.go | `dd_mode` ('scaled', 'base') / `ddMode` | |
| 32 | Arcane Blast | 15% base mana, +175% a stack; +10% a stack to the client mask (not Arcane Missiles); the rotation builds one stack, then spends it | client; sim | | m8, m21 |
| 33 | Missile Barrage | 40% from Arcane Blast, 20% from Fireball, Frostbolt, Frostfire Bolt | tooltip; sim | | m18 |
| 34 | Ignite | 8% a point of each Fire crit, paid 2 and 4 s later, one Mage's | sim (rolling, no munching) | | m11 |
| 35 | DoT ticks | crit | client flag; sim | | m22 |
| 36 | Improved Scorch, Winter's Chill | personal | client; sim | | m25 |
| 37 | Hot Streak stacks | carried to the next pull (20 s against about 10 s of walking and rest) | ASSUMPTION | | |
| 38 | Wand | 0.9 L + 3 damage a second, no spell power; Wand Specialization +13/25% | Warlock lab; FC-PN | | |
| 39 | Humans | Spirit +5%; +2% crit with a sword from 21 (the Coldflame Saber) | WH | `sword` | m23 |
| 40 | Gnomes | +5% max mana; Eureka! on the pull's first 3 spells, 2 min | WH, FC-PN | | m23 |
| 41 | Orcs | Blood Fury +10% spell power for 15 s on the pull, 2 min | WH | | |
| 42 | Trolls | Beast Slaying +5% on 40% of mobs; Berserking +10% cast speed 10 s, 3 min; Rapid Regeneration in rest | WH; mob share ASSUMPTION (Warlock lab) | `beast_share` / `beastShare` | |
| 43 | Undead | Touch of the Grave: 10% of damaging spell hits drain 5% of max health (not wand shots: FC-PN 70009 says only damaging spells trigger it); Cannibalize in rest on 40% of corpses | WH; FC-PN; share ASSUMPTION (Warlock lab) | `humanoid_share` / `humanoidShare` | m23 |
| 44 | Skyborne | +1% haste; Elemental Insight +5% on 10% of mobs; Read Ley Line 15 s in rest, doubling Spirit and health regen, not drinks | WH; share and drink effect ASSUMPTION | `elemental_share`, `leyline` ('short', 'long', 'off') | m23 |
| 45 | Thrill of Adventure | off; ranks 1 to 5 return 1 to 5% of max health and mana a kill | FC-LP | `thrill` | m23 |

## Options

Python passes them as keyword arguments to `evaluate` (and `make_char`); the page passes the camelCase names in `opts` (`LevelingModel.OPT_MAP`). Race goes in `opts.race`: `none human gnome skyborne orc undead troll`. `hpMults` defaults to `[0.9, 1.0, 1.1]`. The search takes `top` (6) and `pairTop` (2). `leveling.js` remembers its last 256 answers, so a repeated call (the builder's page-plan score at the same level) costs nothing. The results are identical either way.

## What the score cannot see

`LevelingModel.SCORED` lists the 43 talents the score responds to. The other 11, with the reason (`LevelingModel.UNSCORED`):

| Talent | Why not scored |
|---|---|
| Arcane Subtlety | mob resistances are not modelled |
| Magic Absorption | resistances are not modelled |
| Arcane Resilience, Frost Warding | mob damage is a flat rate, not armor-based |
| Arcane Shielding | Mana Shield is not cast |
| Improved Counterspell, Improved Fire Ward | the model has no caster mobs |
| Improved Flamestrike, Improved Blizzard | area spells (the AoE model) |
| Ice Block | defensive |
| Cold Snap | 10 min cooldown, about one extra Frost Nova per 15 kills, not modelled |

Arctic Reach scores through the pull only. Its Frost Nova and Cone of Cold radius half is not modelled.

## Reproduce

| What | Command |
|---|---|
| leveling.js matches Python | `node tests/leveling_parity_test.js` (regenerate: `python tests/make_leveling_fixtures.py`) |
| The search finds the exhaustive best | `python analysis/leveling_search_check.py` |
| Planner and tree-first talent orders | `python analysis/leveling_planner.py` |
| Rotation by level, trees, races, consumables, respec, low ranks, builder checks, sensitivity | `python analysis/leveling_paths.py [section]` |

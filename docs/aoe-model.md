# The AoE leveling model

`models/aoe.py` (spell data, builds, loop variants, the pull mechanics) and `models/aoe_loops.py` (the decision loops, the pull driver and the scoring, served from `aoe` as `aoe.run_pull`, `aoe.best_pull` and so on) ask one question: does pulling several mobs at once level a Forever Mage faster than killing them one at a time, and from which pull size? It answers by level band (20, 25, 30, 40, 50, 60), for five pull archetypes, and shows how the answer moves across every uncertain assumption.

Run `python analysis/aoe_breakeven.py` from the repo root. It prints every section (calibration, defaults, failures, budget, sensitivity, pairs, ranks) in 10 to 20 minutes on 16 cores, depending on load; `python analysis/aoe_breakeven.py calibration` runs one section. `python tests/aoe_test.py` checks the invariants and the calibration. Results and verdicts live in the research report (`forever-warlock-lab-drafts/mage-research/aoe/aoe_v1.txt`), not here, because they move whenever the single-target model changes.

## Calibration: the gate

**The engine is trusted only while one mob through it lands within 10% of the single-target model.** The small-pull loop (`nb`) on the planner build, pulled from range, runs one mob through the AoE engine at 20, 25, 30, 40, 50 and 60, and `tests/aoe_test.py` checks its seconds per kill against `character.evaluate()` on the same build. The runner's calibration section prints the same table at every band. A small-pull claim ships only while this passes.

**The gate is looser than some effects it guards.** The engine runs one mob 3 to 9% slower than the single-target model, never faster, and a two-mob gap of a few percent sits inside that. So the defaults table prints this one-mob bias next to every small-pull row, and a small-pull gap is read net of it.

Getting there took six engine changes, each a real mechanic, not a fudge:
- single-target spells hit one whole mob;
- pulls from range start unaware;
- the expected fight time weights the tail;
- the wand finish;
- Ice Lance when it out-damages Frostbolt;
- Frostbite on a single-target chill as the single-target model's accumulator.

Each is described below.

## Method

### One pull, in expected values

A pull of n identical mobs is simulated in 0.1 s steps, in one dimension: every position is a distance from the Mage.

- **The pack is a list of cohorts.** A cohort is a share of the pack that shares a position, health, freeze and chill.
- **Freezes split cohorts.** When a damage event may break a freeze (Frost Nova, and Frostbite, whose client aura options match Nova's), the frozen cohort splits into the share that stays frozen and the share that breaks free. So a half-broken Nova leaves half the pack in the storm and half on the Mage, rather than one pack walking at half speed.
- **Chills split cohorts too.** A chill lands at full strength on the share a spell hits (its hit chance, times Cone of Cold's share, times a target cap), and the rest of the cohort stays unchilled. A diluted slow on everything would be weaker than the armor chill and lose to it under "strongest slow wins".
- **Single-target spells hit one whole mob.** Frostbolt, Ice Lance and the wand take exactly one mob's weight across cohorts: the most damaged first (focus fire), frozen before free at equal health, then the nearest. Each of those cohorts takes the spell's full damage. Without this, expected values spread a mob over cohorts and a Frostbolt does half its damage for full mana.
- **Frostbite.** A single-target chill (Frostbolt: one mob) feeds the single-target model's expected-value accumulator. The mob freezes whole once it passes 1, starting from the same proc phases (1/6, 1/2, 5/6 over the three mob health multiples). An area chill (Blizzard, Cone of Cold) and the armor chill freeze the chance's share of every cohort they chill at once. Lumps on a pack would make the outcome hinge on which cohorts a lump lands on, and that broke "a stronger slow never adds hits".
- **Fingers of Frost and Winter's Chill** (the planner build has both):
  - **Fingers of Frost:** charges build from every chill, from the same phases. A charge makes the next Frostbolt or Ice Lance count as frozen.
  - **Winter's Chill:** stacks build on the target from Frost hits and add 2% crit a stack to Frostbolt and Ice Lance. They reset when a mob dies.
- **Ice Lance** does x4 on a frozen target (talent value). The loop casts it when it out-damages a Frostbolt: expected damage per global cooldown against Frostbolt's per cast time, on the target's frozen share.
- **Everything else is an expected value,** as in the single-target model: hit, crit, Shatter on frozen targets, target caps, the armor chill, daze and pushback.
- **Strongest slow wins** (register `slowStacking`). A cohort keeps its strongest active chill and, behind it, the strongest weaker chill that outlasts it. So Blizzard's 50% for 2 s followed by Cone of Cold's 50% for 8 s plays out as the stronger, then the longer, not as the stronger for the longer.
- **Cohorts in the same state merge again** (1 yd, 0.5 s, 4% health bins), and past 32 cohorts the lightest folds into its nearest like neighbour.
- **Decisions read the pack by weight, not by its extremes.**
  - The near and far edges of the pack are its 10% and 90% weight quantiles.
  - An area spell is cast only when at least one mob (or 30% of what is left) is inside it.
  - The Mage walks away only when less than that weight of free mobs near her is faster than 85% of her speed.
  - Without these rules, a 1% expected-value sliver steers the loop.
- **The expected fight time weights the tail.** Once under one mob is left in expectation, the pull is already over in the other outcomes. So the fight clock runs at min(1, mobs alive) and a cast then is paid and counted only in that share (`live()`).
  - **One mob:** this is exact.
  - **A pack:** it is an upper bound on the chance some mob is alive, so it never flatters AoE.
  - **Why it matters:** without it, the 19% outcome where Nova broke early set the whole pull's time.
- **The pull ends** when every mob is dead, or when under 0.05 mobs are left in expectation. That tail, and any runners, are finished with Frostbolt after the pull.

### How a pull starts

- **Gathered packs** (`blizzard`, `ae`, `fs`): the pack starts stacked 2 yd behind the Mage, the end of a gather.
- **Groups pulled from range** (`nb`, `cone`): the group stands unaware at the single-target model's pull range (melee reach + its 25 yd pull gap + Arctic Reach) until the first spell lands, as there. So the Mage gets her free casts on the approach.

### The five archetypes

Each archetype is a priority list evaluated whenever the Mage is free. Each has two to six loop variants (`POLICIES`). Each variant is run with and without a potion and gem in the fight, and the fastest surviving one is kept for every level and pull size.

| Archetype | Loop | Build |
|---|---|---|
| `nb` | Small pulls. Frostbolt the group from range. Frost Nova when free mobs come within 5 yd of melee reach (the single-target model's rule). Step back to 12 or 18 yd while most of the group is frozen. Ice Lance when it out-damages Frostbolt (a Fingers of Frost charge, or the frozen share). Else Frostbolt, one whole mob at a time. Free mobs in melee with Nova down: Cone of Cold and walk while they are slowed, Arcane Explosion (variants), else keep casting. A variant wands the last 20% of a mob, as the single-target model's finisher. | the planner build (no respec) |
| `blizzard` | Frost Nova the gathered stack, walk out (21 yd, or Blizzard's full reach), Blizzard aimed so the rear of the pack is just inside the far edge at the first tick. Storm again at once if the pack's front is 4 s or more from melee. If it is closer: with Nova ready by then, let it come (variant `wait`); otherwise walk back while the whole pack is slowed (variant `kite`) or storm anyway. When they arrive: Nova if ready, else Cone of Cold, else run if they are slowed, else Blink if they are slowed, else Arcane Explosion. The channel is broken off only for a ready Nova. Arcane Explosion finishes a pack within two Explosions. The 21 yd step keeps the storm's near edge outside the 5 yd melee reach (18 yd left it 2.8 yd from the Mage). Variant `step='short'`: walk only until a storm centred on the frozen pack keeps its near edge just outside melee reach (about 13.5 yd, 1.6 s of the 8 s root), and storm at once, so more of the root falls inside the channel. | Frost AoE |
| `ae` | Frost Nova, step to 7.5 yd (inside Arcane Explosion's 10 yd, outside melee) or stand, Cone of Cold on cooldown, Arcane Explosion. | Frost AoE |
| `fs` | Frost Nova, step to 12 or 20 yd, Flamestrike on the pack (only when no burn is up), Blast Wave, Arcane Explosion, Cone of Cold. One variant also casts Flamestrike with mobs in melee. | Fire AoE |
| `cone` | Frostbolt from range, Frost Nova and step back, Cone of Cold when they come in, run while they are slowed, Blink when they catch up slowed, Frostbolt one mob, Arcane Explosion to finish. | Frost AoE |

Every loop casts Ice Barrier before the pull (during the gather) and again whenever it breaks, if talented (some `nb` variants never cast it, as the single-target rotations do not), and Mana Shield under half health with a mob in melee.

**Builds** (`FROST_AOE`, `FIRE_AOE`, ASSUMPTION: the model's orders, not searched). They are checked legal after every point.
- **Frost:** Improved Frostbolt 5, Permafrost 3, Frostbite 2, Improved Blizzard 3 (20 to 22, the register's earliest), Frostbite, Frost Channeling 3, Arctic Reach 2, Improved Frost Nova 2, Shatter 3, Piercing Ice 3, Cold Snap, Improved Cone of Cold 2, Ice Barrier at 40, then hit, Ice Shards and Arcane fillers.
- **Fire:** Incineration 3 and Wake of Fire 2, Ignite 5, Improved Flamestrike 3 at 20 to 22, Burning Soul 3, then the rows to Blast Wave at 30, Critical Mass, Fire Power, Improved Frost Nova and Permafrost late.
- **What is left out, and why:**
  - **Cold Snap** is bought only as Ice Barrier's prerequisite (data/talents.json) and is never cast. Its 10 min cooldown covers one pull in several, and a pull plan has to survive the pulls without it.
  - **Ice Block** (5 min) is left out for the same reason.
  - **Health potions** are not modelled, as in the single-target model. They share the potion cooldown with the mana potion, and the scored "with and without a potion" variants already decide that slot.
- **The Frost AoE build is not searched,** so the model makes no claim about what the AoE talents cost when single-targeting.

### Seconds per kill

A pull cycle is fight, then gathering, then rest.

- **Gathering** depends on how the pull starts. The first 8 s is always the walk, with the same regeneration the single-target model gives its 8 s walk.
  - **A gathered pack** (`blizzard`, `ae`, `fs`) pays `8 + 6 (n - 1)` s (register `gatherTime`).
  - **A group pulled from range** (`nb`, `cone`) is not gathered: one spell pulls it where it stands. It pays `8 + find_per (n - 1)` s, where `find_per` is the extra walk to find mobs standing close enough to pull together. Default 3 s a mob (ASSUMPTION): such groups are rarer than single mobs, so the walk to one is longer than the single-target model's 8 s, and with no data on mob spacing, half the register's 6 s a gathered mob sits mid-way between pairs everywhere (0) and walking to fetch the second mob (6). Sensitivity rows at 0 and 6 s.
- **Rest** comes from the single-target model's rest model, imported, not copied: `leveling_sim.rest_setup`, `travel_regen` and `rest_solve`.
- **Seconds per kill** is the cycle divided by n.
- **Consumables count (Omri's rule), scored both ways.** Every loop variant is run twice:
  - **Potion and gem allowed in the fight.** When she uses them: they are not also used in that cycle's rest, the cycle cannot repeat faster than their 2 min cooldown, and a used gem's conjure cast and mana are added to rest.
  - **Kept for the rest, as the single-target model does.** The rest model then uses them on its own cooldown share.
  - The faster surviving variant is kept. So a pull of 4 or fewer that has to drink pays its 120 s / n floor, and one that does not is not held to it.
- **Cooldowns.** By default Frost Nova and Ice Barrier are ready at every pull, the single-target model's convention: its fights all start with every cooldown ready. Both sides of the comparison therefore share it. The stricter reading (a cycle is at least last use + cooldown - first use) is a sensitivity row.
- **Averaging.** Results average mob health 0.9, 1.0 and 1.1 of the curve, as the single-target model does.

**A failed pull is never scored.** A pull fails if the Mage's expected health ever falls below the safety floor (25% of max health by default), or the pull is not over in 240 s. It fails if it fails at any of the three health multiples. Its seconds per kill is `None`, and `breakeven()` skips it.

**Failures say why.**
- **`oom`:** she ran out of mana for her loop's damage spells (mana plus an unused potion and gem could not pay the cheapest of them) before her health first fell under the floor. She is beaten down after.
- **`caught`:** her health fell under the floor first, with mana left.
- **`stall`:** neither, and the pull was not over in 240 s.

The runner's failures table gives the time, her health and the share of the pack's health still standing when she ran dry.

### The baseline

The comparison is `character.evaluate()` on the leveling planner build (`analysis/leveling_paths.PLANNER`), with the same options, called live. The breakeven tables regenerate against whatever the imported model returns. The runner prints the modification times of `models/character.py`, `models/leveling_sim.py` and `analysis/leveling_paths.py` first.

### Breakeven

For each archetype and level the runner sweeps pull sizes 2 to 10 (the register's `pullSize` range is 2 to 8, the default 4). It reports three things:
- the smallest surviving pull size that beats single target;
- the fastest surviving pull size and its gap to single target;
- the largest surviving pull size.

When none survives, it lists why each pull size failed. The sensitivity section repeats this for every assumption at its low and high, re-running the baseline with the same options.

## Assumptions

`reg` is the gap register, `forever-warlock-lab-drafts/mage-research/gap/aoe_assumptions.json`. `tests/aoe_test.py` checks the values marked with a register id against it when the file is present.

| Assumption | Model value | Source | Tested range | Settled by |
|---|---|---|---|---|
| Server-side target cap | none | UNKNOWN; client has no cap on Mage AoE (reg `aoeTargetCap`) | 5, 4 | m1 |
| Blizzard chill slow | Improved Blizzard 15/25/40% plus Permafrost 3/7/10% (50% at 3/3 and 3/3), at full strength on the share a tick hits | client, talents.json (reg `improvedBlizzardSlow`, `permafrostExtraSlow`, `blizzardChillTotal`; tested equal) | 40% (the Chilled row's own 30% + Permafrost), Classic 75% as a reference | m3 |
| Blizzard chill duration | 1.5 s x (1 + Permafrost 11/22/33%), 2.0 s at 3/3 | client 12484 (reg `chillDurationBlizzard`) | 1.5 s, Classic 4.5 s as a reference | m3 |
| Every tick re-applies the chill | yes | sim (reg `chillRefreshInStorm`) | once a cast | m3 |
| Blizzard does not chill without Improved Blizzard | as in Classic | reg `improvedBlizzardSlow` (the chill is the talent's) | | |
| Cone of Cold and Frostbolt chill | 40% + Permafrost's 3/7/10% (50% at 3/3), 6 s and the Frostbolt row's time, x1.33 with Permafrost 3/3 | client via `leveling_sim.fight_consts` (reg `coneOfColdSlow`) | | m3 |
| Share of a pack Cone of Cold catches | 75% | ASSUMPTION (reg `coneOfColdShape`: a 60 degree cone catches part of a pack) | 50%, 100% | |
| Frost Nova | 8 s root, 25 s (23 or 21 s with Improved Frost Nova), 10 yd (12 with Arctic Reach) | client (reg `frostNovaRoot`, `frostNovaRadius`) | | |
| Frost Nova break chance per damage event | 0.5 (the character's `nova_break`) | ASSUMPTION (reg `frostNovaBreakChance`) | 0, 0.1, 1.0 | m12 |
| Frostbite freeze | 5% a rank per chill, 5 s, breaks with the character's `fb_break` (Nova's chance by default, set in `make_char`); the accumulator on Frostbolt, the share on area and armor chills | client 11071, 12494; aura options match Nova's (the single-target model) | moves with the Nova rows | m12, m17 |
| Frostbite rolls on | every chill, every Blizzard tick | sim (reg `frostbiteFreeze`) | first tick of a cast | m17 |
| Fingers of Frost, Winter's Chill | 15% a chill for every charge; +2% crit a stack on Frostbolt and Ice Lance | the single-target model's values (`FOF_CHANCE`, `WC_CRIT`) | | m19 |
| Ice Lance | x4 on a frozen target, instant, cast when it out-damages Frostbolt | talents.json `frozenDamageBonusPct` 300; coefficient from the single-target model | | m19 |
| Frost or Ice Armor chill on attackers | 30% + Permafrost movement slow and 25% attack slow for 5 s; rolls Frostbite | client (reg `armorChill`); attack slow as in the single-target model | Mage Armor from 34 instead | m17 |
| AoE armor | Frost or Ice Armor at every level | AOE.md loop step 1 ("Ice or Frost Armor") | Mage Armor from 34 | |
| Strongest slow wins | yes | Classic lore (reg `slowStacking`) | | m3 |
| Blizzard | 8 yd, 30 yd range (36 with Arctic Reach), 8 ticks at 1 s | client, data/mage_spells.json (reg `blizzardRadius`, `blizzardRange`, `blizzardTicks`) | | |
| First tick | 1 s after the cast | ASSUMPTION (reg `blizzardTicks`) | 0 s | m9 |
| Ticks crit | no (Blizzard and Flamestrike) | sim (reg `blizzardTickCrit`) | yes | m9 |
| Blizzard under melee hits | each hit costs one tick, none while Ice Barrier holds | ASSUMPTION (reg `channelPushback`) | no loss; the first hit ends it | m9 |
| Flamestrike | 3 s cast, 5 yd, 30 yd range, burn 4 ticks at 2 s, one at a time | client (reg `flamestrikeArea`, `flamestrikeTiming`) | | m26 |
| Arcane Explosion, Blast Wave radius | 10 yd | client (reg `arcaneExplosionRadius`, `blastWaveRadius`) | | |
| Blink | 20 yd, 15 s, 35% of base mana, from 20 | client and Wowhead via data/mage_spells.json (reg `blink`) | | |
| Mob run speed | 8 yd/s | sim framework constant (reg `mobRunSpeed`) | 7 yd/s | m3 |
| Player run speed | 7 yd/s | Classic lore (reg `playerRunSpeed`) | | |
| Mob melee reach | 5 yd | ASSUMPTION (reg `meleeRange`) | 8 yd | |
| Mob health | 18 L + 0.62 L^2, averaged at x0.9, x1.0, x1.1 | the Warlock lab (reg `mobHealth`) | x0.8, x1.2 | m16 |
| Mob damage | 0.035 L^2 a second each in melee | the Warlock lab (reg `mobDps`); UNSOURCED there, and it bears mostly on the AoE side | x0.5, x0.7, x1.5 | m16 |
| Mob level | the Mage's own level, on both sides | the single-target model's choice | 3 levels below on both sides: health and damage from the curves at L - 3; spell hit and experience a kill left alone (no source for lower mobs; experience falls for both sides alike) | m16 |
| Mob swing | 2.0 s | ASSUMPTION (reg `mobSwingTime`) | 1.5, 2.5 s | m16 |
| Creature daze | 20% a hit from behind while the Mage runs, 50% for 4 s | Classic lore (reg `creatureDaze`) | | m20 |
| Gathering a pack | 8 + 6 (n - 1) s, no damage taken, no mana spent | the Warlock lab's M2 (reg `gatherTime`) | 8 + 4 (n - 1), 8 + 10 (n - 1) | |
| Finding a group to pull from range | 8 + 3 (n - 1) s: the walk, plus 3 s a mob to find mobs standing together | ASSUMPTION (half of `gatherTime`'s 6 s a mob) | 0, 6 s a mob | m20 |
| How a pull starts | gathered packs stacked 2 yd behind the Mage; small groups unaware at pull range | ASSUMPTION; the range start is the single-target model's | | |
| Pull size | swept 2 to 10 | reg `pullSize` (default 4, range 2 to 8) | | m20 |
| Runners | none: the pack is beasts, as WFB advises | ASSUMPTION (reg `humanoidFlee`: 15% health) | the whole pack flees at 15% | m20 |
| Dungeon kills | out of scope (see Limits) | reg `dungeonKillXp` = 0 | | m2 |
| Safety floor | expected health never under 25% of max | ASSUMPTION: an expected-value pull averages out bad streaks, so it needs a margin | 0, 50% | |
| Mana potions and gems | each pull scored with them in the fight (then a 2 min cycle) and without (then in the rest) | Omri's rule; potion values and gems from `leveling_sim` | off each | |
| Cooldowns between pulls | ready at every pull, as in the single-target model | the single-target model's convention | carry over | |
| Ice Barrier | before the pull (during the gather) and whenever it breaks | FC spellbook: no pushback while it holds | | |
| Mana Shield | under half health with a mob in melee, 2 mana a point | client (data/mage_spells.json) | | |
| Wand | the single-target model's: 0.9 L + 3 dps, Wand Specialization, no freeze breaks, under 20% of a mob's health (a small-pull variant) | `character.make_char`, `leveling_sim.FIN_BELOW` | | |
| Spell ranks | the highest learned rank of every spell; coefficients from the single-target model's `low_ranks` rule (default `'measured'`: full coefficients, no downranking from 20; Blizzard's 1 Oct 2026 notes cut ranks far below your level: the top ranks here are at most 7 levels below you, except Frost Nova, whose rank 1 is the top rank until 26, but its root is the spell itself and its damage scales at only 0.029 a point of spell power) | `leveling_sim.coef_factor`, `downrank_allowed` | the ranks section checks lower ranks under full coefficients; the `'full'` row lets single target downrank | m13 |
| Spell travel time | none: every spell lands the moment its cast ends (`land`), so an Ice Lance cast while a Frostbolt is in the air gets nothing from that window | ASSUMPTION | | m31, m32 |

Everything else comes from the imported single-target model: the character (health, mana, crit, hit, regeneration), spell rows, talent values, the rest model and potion data.

## Limits

- **Expected values, not dice.** A pull that survives in expectation can die to a bad streak. The 25% safety floor is the model's only allowance for variance.
- **One decision path for every outcome.** The cohorts are expected outcomes, but the Mage acts once for all of them. In a minority outcome (Nova broke early, a mob frozen out of range) she does what suits the majority. This is pessimistic, and is part of why one mob runs 3 to 9% slower than the single-target model.
- **Loops are scripted, not optimized.** The policy search picks the best of a few variants per archetype. A better player could beat these loops; the Classic-chill row shows how far the loop itself can go.
- **Not modelled:**
  - Cold Snap, Ice Block and health potions (see Builds).
  - Arcane Concentration and Master of Elements refunds on AoE crits.
  - Evocation mid-pull (its 8 min cooldown would set the cycle).
  - Racial cooldowns.
- **Gathering is free.** No damage is taken and no mana is spent while gathering (the Warlock lab's assumption).
- **Six levels, and mobs of your level.** The model runs at 20, 25, 30, 40, 50 and 60 only (`LEVELS` in the runner), always against mobs of the Mage's level, as the single-target model does. Its verdict holds at those levels and against those mobs. AoE farmers often pull mobs a few levels lower, with less health and damage but less experience a kill. One sensitivity row puts every mob 3 levels below on both sides (health and damage only); it does not price the lost experience, which needs a level-difference experience formula no research file gives.
- **Packs are melee beasts.** Casters, runners and social adds are not modelled beyond the flee sensitivity row.
- **Dungeons are out of scope.** Whether dungeon kills give experience is unknown (m2), and with a tank holding mobs the loop would be a different model whose inputs (tank threat, party XP split) no source gives. The register's default excludes dungeon kills.
- **One-dimensional geometry.** Positions are distances from the Mage. Cone of Cold's angle is a share of the pack (75%), and Flamestrike's 5 yd radius assumes a stacked pack.
- **The comparison rides on the Warlock lab's mob curves.** Absolute seconds per kill are only as good as those curves. The breakeven pull size is more robust than the seconds.

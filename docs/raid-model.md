# The raid model

What it answers: which Mage build does the most single-target damage on a raid boss at level 60, and what moves that answer. `models/raid_model.py` is the reference; `model.js` is a hand port the page runs (parity to 0.001 dps, `tests/parity_test.js`).

## Method

1. **Character.** Spell power, crit, hit per school, mana pool, regen while casting and haste come from the options and the talent build (`data/talents.json` keys, `{key: rank}`). Raid buffs (option `raidBuffs`), Greater Blessing of Kings (`kings`, +10% total Intellect and Spirit, only with raid buffs on), the Mageblood Elixir (`mageblood`) and a Moonkin in the party (`moonkin`, +3% crit, off by default) add to the sheet values the reader enters.
2. **Actions.** Every castable spell and rank is an action with its expected damage, time and mana per use. An action carries its own procs as expected follow-up casts:
   - Frostbolt and Frostfire Bolt: a landed chill gives Fingers of Frost 15% of the time, and its 1 or 2 charges go to Ice Lance (x4 damage, +Shatter crit). This follows the sim, which rolls Fingers on a boss although bosses cannot be chilled or frozen (ASSUMPTION; option `fingersOnBoss`).
   - Fireball, Frostbolt, Frostfire Bolt (20%) and Arcane Blast (40%): Missile Barrage, then a free Arcane Missiles, a missile every 0.5 s.
   - Fireball, Frostfire Bolt, Fire Blast and Scorch crits: a Heating Up stack (Hot Streak until 1 Oct 2026); a Pyroblast at 3 stacks (1.5 s cast). The share of crits that become Pyroblasts accounts for stacks lapsing after 20 s.
   - Every Fire crit: Ignite, 40% of the crit, rolled over as the sim does.
   - Clearcasting (the next spell free) and Master of Elements (30% of base cost back on a Fire or Frost crit) as expected mana.
   - Arcane Blast is cast in cycles: n Blasts (n = 1 to 4, each +175% cost), a spender that takes the +10% per stack (Frostbolt, Fireball or Frostfire Bolt), then Missiles if Barrage came up. With `abMask: 'tooltip'` or `amSpends` on, a cycle can also end on the Barrage Missiles in place of the spender.
   - Cooldown spells (Fire Blast, Blast Wave, Presence of Mind, Evocation) are actions with a cap on uses. A press counts only for the share of the fight left to cash it: Presence of Mind needs a global cooldown after the press, Evocation its 8 s channel.
   - **The wand.** Waiting out mana is an action too: it shoots the wand (`wandDps`, Wand Specialization +13/25%, the hit and partial resist rules) and spends no mana, so Spirit regen runs in full once the five-second rule clears. The model assumes the waiting comes in 15 s blocks, so a third of it regenerates at the casting rate (ASSUMPTION, `IDLE_BLOCK`). It shows in the plan as "Wand, full regen".
3. **The linear program.** Split the fight's time across actions to maximise damage, with the mana spent no more than the budget. Two constraints (time and mana) mean the optimum mixes at most two uncapped actions. The solver enumerates vertices (the uncapped actions on the upper hull of mana per second against damage per second, and each capped action at 0, at its cap, or in the basis), which ports to JavaScript unchanged. Every vertex it accepts has non-negative uses and fits both constraints, so there are no infeasible plans; the wand action makes one always exist.
4. **The mana budget.** Pool + regen while casting over the fight + potions, runes and gems + Evocation (an action) + Eureka's savings.
   - **Items come in lumps.** A Major Mana Potion needs 2250 room, a rune 1500, a gem its top roll. The model assumes the player opens that room with the build's top action (the fastest spender within 1% of the best damage per second) from the pull: the first potion at 2250 / (top mana per second above regen), a rune or gem after it, then each every 2 minutes. That opening is booked as fixed time and mana on the top action.
   - **Runes and gems share one cooldown.** The slots are filled in the better of two orders: runes in every slot, or the Ruby first and then runes (with runes off, the gems in size order). At the defaults runes win, so the gems switch changes nothing unless runes are off.
   - **Stranded mana.** Whatever arrives too late to spend at the top action's rate before the fight ends is taken off the budget (a backward pass over the schedule). This is conservative: Fire Blast could spend some of it.
   - **Skipping an item.** The opening forces the top action for its length. With high mp5 or a short fight the regen above that action is small, the opening runs long, and an item can cost more than it brings. The model tries four item sets (all, no potion, no runes or gems, none) and keeps the best, as a player would skip that item. Without this, 10 more mp5 could lower a Fire build by 2.8%.
   - `analysis/raid_windows.py` solves the same program in windows between potions, under the income curve (mana cannot be spent before it arrives): every spec lands within 0.5% of the one-budget total, so the one budget stands. Two land slightly above it (Fire with Arcane Blast +0.13%, Arcane with Ignite +0.01%) because the one budget strands mana at the top action's rate and the windows let Fire Blast spend it.
5. **Fire Vulnerability.** A build with Improved Scorch is solved twice, with and without keeping 5 stacks (5 Scorches at the pull, then one every 27 s), and keeps the higher.
6. **Fixed point.** Some inputs depend on the plan: the Winter's Chill ramp (stack-casts lost while stacks build), the Heating Up conversion rate, Pyroblast DoT overlap, cooldown drift (a cooldown up mid-cast waits for it; an Arcane Blast cycle counts as one block), Eureka's mana. The model solves, updates them, and repeats 10 times, damping from the third pass. The opening action and the item set are chosen on the first three passes and then kept, so two choices near a tie cannot trade places on every pass. It settles within 0.005 dps on every fixture case (`tests/make_raid_fixtures.py` checks).
7. **Combustion** adds a fixed number of crits per press (3 since Blizzard's 1 Oct 2026 notes, minus what those hits would crit anyway, from a small chain over the rising crit chance). Presses come every 3 minutes from the pull, and each counts only the Fire hits the fight has left after it (the plan's Fire hits per second times the time left), so a press at the last second adds nothing. It is booked after the program at the plan's average value of a Fire crit (crit bonus, Ignite, and a Heating Up stack's share of a Pyroblast), so it cannot feed back into the plan.
8. **Races.** Averaged over the fight: Blood Fury and Berserking by uptime (a press near the end counts only its seconds), Eureka! on 3 average casts per 2 min (fewer when the fight ends first), Touch of the Grave as the Warlock page models it. Arcane Power and the Spellblasting Potion count by uptime the same way.

**More resources never cost more than 0.23%.** A sweep of mp5, Spirit, Intellect, the potion, runes, gems, Mageblood, raid buffs, Kings, Moonkin and the wand over fight lengths of 60 to 600 s finds no cell where more of a resource lowers a spec by more than 0.23%. Those small dips come from the forced opening and the 2 minute item grid. This was measured on 1 Oct 2026, before v1.2's Combustion change, and no script for it is in the repo. A scratch rerun for v1.2 (all seven specs, fight lengths 60 to 600 s in 30 s steps, each resource raised one step at a time with the rest at the defaults) found at most 0.19%: Fire with Arcane Blast, mp5 200 to 210 in a 300 s fight.

## Validation

`analysis/raid_check.py` plays each spec's plan cast by cast with real dice: hit, crit, every proc, stack ramps, the rolling Ignite, DoT refreshes, Arcane Power and Presence of Mind windows, 2 s mana ticks, the five-second rule, and potions, runes, gems and Evocation used when there is room. It reuses only the spell data, character stats and plan from the model. It paces mana as a player would: upgrades to the pricier spell only while the baseline stays affordable up to every future potion and the end of the fight, drinks the potion before the rune, fills rune and gem slots in the model's order, channels Evocation when the pool is low, and shoots the wand whenever it waits (in 15 s blocks when the plan has wand time).

| Check | Result |
|---|---|
| Mana not binding (mp5 3000, 400 fights), every spec | model within 1.7% of the dice |
| Defaults (1000 fights), the four page builds | model +0.1% to +0.8% above the dice |
| Defaults (1000 fights), the sim builds | model +1.4% (Arcane), +3.5% (Fire), +4.7% (Frost) above the dice |
| 120 s fights | model +1.3% (Frost with Barrage), +2.5% (Fire with Arcane Blast), +3.6% (Fire sim) above the dice |
| 60 s fights | model +3.1% (Frost with Barrage), +5.9% (Fire with Arcane Blast), +7.1% (Fire sim) above the dice |

The known limits: short fights and plans with a lot of wand time are optimistic. Steady-state rates miss the ramp at the pull and the ticks lost at the end (Ignite, DoTs, the cast in flight), which weighs most in a 60 s fight and most on Fire. The model treats the fight's mana as one budget spent evenly and ignores the spread of spending, and a plan that sits exactly at its mana limit loses to bad runs of procs. When the model skips an item (high mp5) the dice still drink it, so there the dice can come out above the model.

## Assumptions

| Value | Used | Source |
|---|---|---|
| Spell ranks, damage at 60, coefficients, costs, cast times, DoTs | all spells | `data/mage_spells.json` (client 1.60.1.69893); `check_data()` compares the hardcoded rows |
| Top ranks (Frostbolt 11, Fireball 12, Missiles 8) come from tomes | off by default | gap pass TOMES.md: only source is Ruins of Ahn'Qiraj, not on the roadmap; option `topRanks` |
| Base mana 1213 at 60 | pool | sim `base_stats_auto_gen.go` |
| 15 mana per Intellect (first 20 give 1) | pool | sim `mana.go` |
| 0.0168% crit per Intellect | Arcane Mind's and Gift of the Wild's Intellect | sim `CritPerIntMaxLevel` |
| Spirit regen 12.5 + Spirit/4 per 2 s | regen | sim `mana.go` (Forever keeps level 60 spirit regen), UNVERIFIED (test m14) |
| Full Spirit regen once 5 s pass without spending mana | the wand action | the five-second rule; the sim reports regen after it separately |
| Waiting comes in 15 s blocks (a third at the casting rate) | the wand action | ASSUMPTION (`IDLE_BLOCK`) |
| Wand 57 dps | the wand action | ASSUMPTION: 0.9 x 60 + 3, the leveling model's wand (`models/character.py`); option `wandDps` |
| Wand Specialization +13/25% wand damage | the wand action | curve |
| Mage Armor 50% regen while casting, always on | regen | client 22783; sim default armor |
| Arcane Meditation 17/33/50%, adds to Mage Armor | regen | curve; sim adds them; option `regenStack` (test m5) |
| Greater Blessing of Wisdom 40 mp5 | `raidBuffs` | Forever tooltip, spell 25918 |
| Mana Spring Totem 25 mp5 (10 every 2 s), party only | `raidBuffs: 'all'` | Forever tooltip, spell 10497 |
| Prayer of Spirit +40 Spirit | `raidBuffs` | Forever tooltip, spell 27681 |
| Gift of the Wild +16 all attributes | `raidBuffs` | Forever tooltip, spell 21850 |
| Paladins and Shamans on both factions | `raidBuffs`, `kings` | ForeverChanges racials (Undead Paladin, Dwarf Shaman) |
| Greater Blessing of Kings: total stats +10%; one Blessing per Paladin, so Kings next to Wisdom takes a second Paladin | `kings`, on with raid buffs | Forever tooltip, spell 25898 |
| Moonkin Form: party members within 45 yd +3% critical strike chance, counted for spells | `moonkin`, off | Forever tooltip, spell 24858 |
| Arcane Brilliance is the reader's own, already in Intellect | `int` | option hint |
| Mageblood Elixir 12 mp5 | `mageblood` | Forever tooltip, 20007 |
| Evocation: 8 s at +1500% regen, 8 min | mana | client 12051; the sim's formula 800 + 16 x Spirit + 1.6 x mp5; option `evocation` (test m7) |
| First Evocation not before 30 s | cap on uses | ASSUMPTION |
| Major Mana Potion 1350 to 2250, 2 min | mana | client 13444 |
| Runes 900 to 1500, gems 1100/850/600/400, one 2 min cooldown | mana | client item categories; NOTES (c) |
| Major Spellblasting Potion +47 spell damage for 30 s | option `potion` | Wowhead (client 69893 says 40) |
| Spell hit cap: 16% from gear plus talents vs level 63 | hit | Classic table, UNVERIFIED (test m15); capped counts as 100% landed, as on the Warlock page. The sim keeps a 1% miss floor, so it lands 99% at the cap |
| Arcane Focus covers Arcane, Elemental Precision Fire and Frost | hit | client masks; sim |
| 6% average partial resist from a level 63 boss on non-binary spells | on by default (`levelResist`) | sim `core/spell_resistances.go:81` and `:96-101`. The Warlock page leaves it out, so non-binary damage here reads about 6% lower than a like-for-like Warlock number |
| Frostbolt and Blast Wave are binary (no partial resists) | `levelResist` | sim |
| Ice Lance is binary | `iceLanceBinary`, on | ASSUMPTION: the sim's flag (`ice_lance.go:29`, per the final review); the review reads its client row as a damage effect and a dummy with no slow, so the Classic rule would let it partially resist (test m29) |
| Spell crit 150%; Ice Shards and Arcane Mind +100% of the bonus | crit | sim `spell.go` |
| Damage talents add (Fire Power, Piercing Ice, Arcane Instability, Arcane Power, Blast stacks) | damage | sim DamageDone_Flat mods add |
| Fire Vulnerability +3% a stack, 5, personal, multiplies | Fire damage | client 22959; sim `scorch.go` |
| One Scorch every 27 s keeps it | upkeep | ASSUMPTION (the sim refreshes at 5 s left) |
| Winter's Chill +2% crit a stack on your Frostbolt and Ice Lance, 15 s | crit | client 12579; sim |
| Fingers of Frost 15% per landed chill, charges = rank | Ice Lance | curve; sim |
| Fingers of Frost procs on a boss | `fingersOnBoss`, on | ASSUMPTION: the sim lets the chill roll it although bosses cannot be chilled or frozen; 142 of Frost with Barrage's dps rides on it (test m30) |
| Shatter 17/33/50% crit while Fingers is up | Ice Lance crit | curve; sim |
| Ice Lance x4 on frozen, whole hit | damage | sim `ice_lance.go` |
| Ice Lance coefficient 0.143 | damage | sim estimate; client row reads 0; option `iceLanceCoef` (test m4) |
| Heating Up (Hot Streak until 1 Oct 2026): 3 stacks, 20 s, -25% Pyroblast cast each | Pyroblast | client 400625; build 70009 |
| Ignite 40% of the crit over 4 s, rolled, per Mage | Fire damage | curve; sim; option `igniteMunch` (test m11) |
| Combustion +10% Fire crit a hit, until 3 crits | crit | Blizzard's 1 Oct 2026 notes (the sim's `combustion.go` and the earlier client read 4) |
| Master of Elements 30% of base cost on a Fire or Frost crit | mana | curve; sim |
| Arcane Concentration 10% per landed hit, 1 s cooldown | mana | curve; sim |
| Missile Barrage 40% (Arcane Blast), 20% (Fireball, Frostbolt, Frostfire Bolt) | Missiles | sim; option `mbRate` (test m18) |
| Arcane Blast buff: +10% damage a stack to other spells, not Missiles | damage | client masks; option `abMask` (test m8) |
| Arcane Missiles neither gain nor end Arcane Blast stacks | Blast cycles, `amSpends` off | a reading of the client masks. The rank 5 tooltip (1239700) says the stacks last "8 sec or until any other damage spell is cast" and the sim ends them (`arcane_missiles.go:66-68`), so both point to on (test m28) |
| Arcane Blast costs 15% of base mana, +175% a stack | mana | client; the rounding of 181.95 is UNVERIFIED (test m21) |
| Arcane Power +30% damage and cost, 15 s, 3 min | damage | client 12042 |
| Presence of Mind: the biggest cast-time spell instant, 3 min | time | client 12043 |
| DoT ticks crit | Fireball, Pyroblast, Frostfire Bolt | client flag; sim (test m22) |
| A spammed DoT spell is refreshed each cast (partial ticks lost) | DoTs | sim `dot.go` |
| Pyroblast DoT overlap between Heating Up Pyroblasts: exponential gaps | DoT ticks | ASSUMPTION |
| Top ranks only | downranking | default `downrank: 'top'`, which Blizzard's 1 Oct 2026 notes back: ranks far below your level lose spell damage and proc chance (rank 1 Frostbolt at 60: 0% Frostbite). Option `downrank: 'full'` ignores that and is an upper bound; only the sim's builds use it: Frost with rank 2 Frostbolt at 60 (484.7 to 492.3) and Fire with rank 2 Fireball (421.4 to 458.7) (test m13) |
| Haste cuts cast times, not the GCD or channels | haste | ASSUMPTION |
| No travel time: every spell lands the moment its cast ends | procs | ASSUMPTION (the sim flies bolts); tests m31, m32 |
| Frostfire Bolt blocked on a Fire-immune boss | fireImmune | ASSUMPTION |
| Undead maximum health 4000 | Touch of the Grave | ASSUMPTION; option `maxHp` |
| Eureka! used on 3 average casts, on direct damage only (Blizzard's 1 Oct 2026 notes: no periodic effects) | Gnome | ASSUMPTION |

## Options

| id | default | choices | untested |
|---|---|---|---|
| sp, crit, gearHit, int, spirit, mp5 | 500, 0.10, 0.11, 300, 120, 0 | ranges (mp5 is gear only) | |
| race, sword, maxHp | none, true, 4000 | 7 races | |
| fightLength | 300 | 60 to 600 | |
| fireImmune | off | | |
| raidBuffs | all | all, noTotem, none | |
| kings, moonkin | on, off | | |
| potion | mana | mana, blast, none | |
| runes, gems, mageblood | on, on, on | | |
| wandDps | 57 | 0 to 120 (0 = no wand) | |
| iceLanceCoef | 0.143 | 0, 0.143, 0.429, 0.572 | m4 |
| abMask | client | client, tooltip | m8 |
| amSpends | off | | m28 |
| regenStack | add | add, max, full | m5, m14 |
| evocation | 1 | 1, 0.5, 0 | m7 |
| igniteMunch | 0 | 0, 0.15, 0.3 | m11 |
| downrank | top | top, full | m13 |
| mbRate | 1 | 1, 0.5 | m18 |
| topRanks | off | | m6 |
| levelResist | on | | none yet |
| iceLanceBinary | on | | m29 |
| fingersOnBoss | on | | m30 |

`targets` stays at 1 in DEFAULTS and is not on the page: no Mage build has a cleave plan (every Mage multi-target spell is an AoE, which the AoE model covers). Blizzard and Flamestrike tick crits are not an option for the same reason: no raid spec casts them.

## Defaults

Spell power 500, crit 10% and gear hit 11% match the Warlock page, so the two classes compare at the same gear point. Intellect 300 and Spirit 120 match the ElliotWood sim runner's grid. mp5 0 from gear, with the raid buffs, Greater Blessing of Kings and the Mageblood Elixir on, because a raiding Mage has them and consumables count. Moonkin Form is off: it depends on the party, not the raid. The partial resists from boss level are on, as the sim has them, so this page's damage is not directly comparable with the Warlock page: about 6% lower on non-binary spells.

## Specs

Four builds from `analysis/raid_search.py` (an iterated local search under the point rules, run under the defaults and four untested flips: Ice Lance coefficient 0, the Arcane Blast tooltip reading, low ranks at full strength, no raid buffs), each the most robust of its family across those scenarios, plus the sim's three builds for comparison. The search results and the robustness table are in `mage-research/raid/search_v2.json` (outside the repo).

## Run

```
python tests/make_raid_fixtures.py   # checks data, point rules, convergence; writes the fixtures
node tests/parity_test.js
node tests/raid_options_test.js
node tests/weights_test.js
python analysis/raid_check.py 1000   # the dice
python analysis/raid_specs.py        # ranking and sensitivity tables
python analysis/raid_windows.py      # the mana timing check
python analysis/raid_search.py [scenario]   # the talent search, one scenario a run (writes outside the repo)
python analysis/raid_search.py --merge      # robustness across the scenarios
```

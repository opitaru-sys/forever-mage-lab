# Forever Mage Lab

A theorycraft lab for the Mage class in WoW: Forever. It covers leveling rotations and talent order, whether AoE leveling pays, the level 60 solo build, and the level 60 group spec (Frost, Fire or Arcane, and how much Missile Barrage is worth).

Data is from the Forever beta client, build 1.60.1.69893, read on 30 September and 1 October 2026. Beta data can change before launch on 4 November. Treat every number here as "true for this beta build," not "true forever."

Live page (once published): https://opitaru-sys.github.io/forever-mage-lab/

## The verdict

- **Levels 10 to 19.** Frostbolt and your wand, with Fire Blast from 14, and Improved Frostbolt first. An Arcane wand build is 4.6% faster at these levels, but they are under a tenth of your leveling time, so playing Arcane and respeccing at 20 saves only 0.43%.
- **Levels 20 to 60.** Frost, with Ice Lance on every freeze: this lab's order takes about 105 hours from 10 to 60 in the model, against 114 for Arcane-first and 121 for Fire-first. Frost Nova the mob when it closes and step back; from about 41, drop the wand and the step back.
- **AoE or single target (interim, under review).** In our model, Classic-style Blizzard pulls of 6 or more mobs fail in Forever. The pack walks out of the storm after about 4 of its 8 ticks, and the Mage runs out of mana or gets caught before Frost Nova is back. Small pulls of 2 or 3 are not modelled well enough to judge yet. Tests m3, m12, m16 and m1 settle it.
- **Group at 60.** Frost with Missile Barrage, 18/3/30: 532 dps at the calculator defaults before racials, 6% ahead of Fire with Arcane Blast (19/31/1, 502). One untested number can flip it: if Ice Lance has no spell power scaling, as the client row reads, Fire with Arcane Blast leads by 3% (test m4).
- **Solo at 60.** The leveling order's final build, 5/4/42: Frostbolt, Frost Nova, Ice Lance on every freeze and Fingers of Frost charge. Its last 9 points change nothing at 60 in the model.
- **Race.** Race barely matters. Undead levels about 3% faster and adds 1.6% in raids; every other race is within about 2% for leveling and 1.4% in raids.
- **Dungeons.** The first open at level 13. Whether dungeon kills give experience in Forever is untested (test m2), so the models leave dungeon leveling out.

## How it was built

Data sources:
- The Forever beta client's own tables (build 1.60.1.69893, from the ElliotWood/Forever data cache): base damage, spell power coefficients, costs, cast times and learn levels for 166 spell ranks (`data/mage_spells.json`), and the per-rank talent curves for all 54 talents (`data/talents.json`). Later beta builds up to 70124 changed only Hot Streak, Wake of Fire, Ignite and Arcane Missiles' line of sight; the models use the newer values.
- Wowhead's Forever tooltips (JSON), ForeverChanges (class changes, talents, spellbook, racials, patch notes, and DoubleZug's downranking measurements at levels 18 and 19), and the ElliotWood/Forever sim's code and data.
- `docs/mage-mechanics.md` condenses all of it, with sources.

Models:
- **Leveling** (`models/leveling_sim.py`, `models/character.py`): an expected-value fight simulator in 0.02 s steps, with the mob running at you, slows, roots that damage can break, stepping back, spell pushback, procs counted as they build up, and a rest model (eating and drinking at once, potions, Evocation, racials). For each build and level it searches 13 base rotations with modifiers and keeps the fastest; an exhaustive check on 212 cases found a largest gap of 0.000%. The planner's talent order comes from a search over every point (`analysis/leveling_planner.py`). Method: `docs/leveling-model.md`.
- **Raid** (`models/raid_model.py`): a mana-budget model that finds the mix of spell cycles doing the most damage within the fight's time and mana, with raid buffs, potions, runes, gems, Evocation and a wand while waiting for mana. `analysis/raid_check.py` plays each plan cast by cast with real dice as a check. Method: `docs/raid-model.md`.
- **AoE** (`models/aoe.py`, `models/aoe_loops.py`): pulls of several mobs in 0.1 s steps, through scripted Blizzard, Arcane Explosion, Flamestrike and Cone of Cold loops, compared with the single-target model. The roughest of the three, and under review. Method: `docs/aoe-model.md`.
- The page runs `model.js` and `leveling.js`, hand ports of the Python models. `tests/parity_test.js`, `tests/raid_options_test.js`, `tests/weights_test.js` and `tests/leveling_parity_test.js` check them against Python fixtures case by case.
- **Cross-check against the ElliotWood sim.** On the sim's own three builds and rotations at matching stats (human, 500 spell power, 10.27% crit, 11% hit, 316 Intellect, 185 Spirit, 77 mp5, mana potion and rune, 300 s, level 63 target, 3000 iterations), the sim reads Arcane 472.8, Fire 398.5 and Frost 452.5 dps, and the model 476.7, 406.7 and 468.6: the model is 0.8 to 3.6% higher. The sim keeps a 1% miss floor, and its Frost build runs out of mana for 40 s of the 300.

Every number on the page or in this README comes from a command in the table below.

## Assumptions

The full tables, with sources and test ids, are in `docs/leveling-model.md` (45 rows), `docs/raid-model.md` and `docs/aoe-model.md`. The ones that move results most:

### Leveling model (`models/character.py`, `models/leveling_sim.py`, `leveling.js`)

| Input | Value as used | Status |
|---|---|---|
| Spell power | level x 1 (gear 1, "leveling greens") or x 2 (gear 2) | Warlock lab convention |
| Gear stats | 1 Intellect, 1 Stamina, 0.5 Spirit per level | ASSUMPTION |
| Mob health | 18 L + 0.62 L^2, averaged at x0.9, x1.0, x1.1 | Warlock lab curve, test m16 |
| Mob damage | 0.035 L^2 a second, taken only in melee range | Warlock lab curve, test m16 |
| Mob run speed | 8 yd/s (player 7) | sim constant, test m3 |
| Pull distance | 25 yd to melee, plus range talents | ASSUMPTION |
| Frost Nova and Frostbite freezes | each damage event breaks them with chance 0.5 | ASSUMPTION; Frostbite's client aura row matches Nova's; test m12 |
| Stepping back | a searched choice: 2 s of walking after a root | ASSUMPTION |
| Spell pushback | 0.5 s a melee hit; a channel loses one tick a hit | ASSUMPTION |
| Spirit regen | 6.25 + Spirit/8 a second, after 5 s without spending mana | sim, tests m14 and m10 |
| Regen while eating and drinking | on | ASSUMPTION (Classic rule), test m10 |
| Water and food | client values (Crystal Water 4200 over 30 s) | client; Wowhead reads 25/26, test m10 |
| Mana potions | the best the level allows, one per 2 min, on by default | Wowhead tooltips; vendor price from the client |
| Ice Lance coefficient | 0.143, x4 on a frozen target for the whole hit | sim estimate; client 0; test m4 |
| Low ranks | full coefficients, lower ranks cast only at 19 and below | client and DoubleZug's measurements; test m13 |
| Armor | Frost or Ice Armor below 34, Mage Armor from 34; armor chills roll Frostbite | test m17 |
| Wand | 0.9 L + 3 dps, no spell power | Warlock lab; Blizzard's 24 Sep notes |
| Walking between kills | 8 s | Warlock lab |
| XP per mob (hours only) | 45 + 5 L, Classic XP table | ASSUMPTION |

### Raid model (`models/raid_model.py`, `model.js`)

| Input | Value as used | Status |
|---|---|---|
| Gear point | spell power 500, crit 10%, hit 11% from gear, Intellect 300, Spirit 120, mp5 0 | the Warlock page's gear point; the sim runner's grid |
| Fight | one level 63 boss, 300 s | |
| Raid buffs | on: Greater Blessing of Wisdom 40 mp5, Mana Spring Totem 25 mp5, Prayer of Spirit +40, Gift of the Wild +16 | Forever tooltips |
| Consumables | Major Mana Potion, Demonic or Dark Runes and mana gems on a shared 2 min cooldown, Mageblood Elixir, all on | client item categories (test m24) |
| Hit cap | 16% against a level 63 boss, capped counts as 100% landed | Classic table, test m15 |
| Boss partial resists | 6% average on non-binary spells (Frostbolt, Ice Lance, Blast Wave exempt) | sim; no test before raids |
| Ice Lance coefficient | 0.143 | sim estimate; client 0; test m4 |
| Arcane Blast stacks | +10% a stack to other spells, not Arcane Missiles, Blizzard or Flamestrike | client masks; tooltip says all; test m8 |
| Barrage Missiles | leave Arcane Blast stacks alone | client masks; the sim ends them; test m28 |
| Casting regen | Mage Armor 50% plus Arcane Meditation up to 50%, added | sim; test m5 |
| Evocation | 800 + 16 x Spirit + 1.6 x mp5 | sim formula, test m7 |
| Ignite | 40% of the crit, rolled, one Mage's | sim, test m11 |
| Missile Barrage | 40% from Arcane Blast, 20% from Fireball, Frostbolt, Frostfire Bolt | tooltip and sim, test m18 |
| Spell ranks | highest trainer ranks only; no top-rank tomes | test m13 and m6 |
| Waiting for mana | full Spirit regen and a 57 dps wand, in 15 s blocks | ASSUMPTION |
| Undead max health | 4000 | ASSUMPTION (slider) |

### AoE model, interim (`models/aoe.py`, `models/aoe_loops.py`)

The AoE model is under independent review and its headline is being narrowed. Its inputs:

| Input | Value as used | Status |
|---|---|---|
| Blizzard chill | Improved Blizzard 15/25/40% plus Permafrost 3/7/10%, 50% for about 2.0 s at 3/3 | client; test m3 |
| Server target cap | none | client stores none; test m1 |
| Frost Nova and Frostbite break | 0.5 a damage event | ASSUMPTION, test m12 |
| Mob health and damage | the Warlock lab curves | test m16 |
| Blizzard and Flamestrike ticks | never crit | sim; test m9 |
| Packs | beasts that never flee | ASSUMPTION, test m20 |
| Gathering | free: no damage taken, no mana spent | Warlock lab |
| Safety floor | expected health never under 25% | ASSUMPTION |
| Dungeon kills | out of scope | test m2 |

## How to reproduce each claim

Run every command from the repo root. The leveling sections take 10 to 40 s each; `analysis/raid_check.py 1000` about 40 s.

| Claim | Command |
|---|---|
| Frost levels fastest: this order 104.9 h, Arcane-first 114.0, Fire-first 121.0 (mean 25.0, 26.5, 28.0 s a kill); Fire-first 15.3% slower | `python analysis/leveling_paths.py trees` |
| A Frost-first order stays first in all 18 sensitivity rows; damage breaking roots is worth 19.1%; no Spirit regen while drinking costs 4.2 to 5.3%; Mage Armor is worth 1.5% | `python analysis/leveling_paths.py sensitivity` |
| An Arcane start is 4.6% faster at 10 to 19, but a respec plan saves only 0.43% (upper bound 0.58%) | `python analysis/leveling_paths.py respec` |
| Rotation by level, level 20 jump (32.9 s to 28.2 s), gear 2 vs gear 1 (the planner's phase texts) | `python analysis/leveling_paths.py phases` |
| Mana potions save 9.2% of leveling time, 30 an hour, 0.12 to 18 gold an hour; mana gems never pay | `python analysis/leveling_paths.py consumables` |
| Race leveling: Undead 3.0%, Skyborne 2.1%, Troll 1.7%, Human 1.2%, Gnome 0.8%, Orc 0.4% | `python analysis/leveling_paths.py races` |
| Low ranks at full strength would save about 1.1% from 34 | `python analysis/leveling_paths.py lowranks` |
| The planner's talent order (about 67 minutes on 16 cores) | `python analysis/leveling_planner.py` |
| The planner's last 9 points change nothing at 60 (20.253 s either way) | `node -e "const L=require('./leveling.js'),C=require('./src/class.js');const f=C.planner.order.flatMap(([k,n])=>Array(n).fill(k));const b=n=>{const t={};f.slice(0,n).forEach(k=>t[k]=(t[k]\|\|0)+1);return t};console.log(L.evaluateUncached(60,b(51),1,{}).spk,L.evaluateUncached(60,b(42),1,{}).spk)"` |
| The leveling search matches an exhaustive search (212 cases, largest gap 0.000%) | `python analysis/leveling_search_check.py` |
| Raid ranking at the defaults: Frost with Barrage 532.3, Fire with Arcane Blast 502.0 (6.0%), Arcane with Ignite 487.3, Arcane 483.8; the sim builds 12 to 23% behind; 93 dps of free Missiles; Ice Lance 142 dps | `python analysis/raid_specs.py` (first table) |
| Ice Lance at 0 flips the lead to Fire with Arcane Blast (+3.0%); the tooltip reading lifts the Arcane builds 5 to 8%; Barrage Missiles ending stacks 1.5 to 2.4%; tomes +7% (571); no partial resists leaves a 0.8% lead; the leader-flipping pairs | `python analysis/raid_specs.py` (untested and pairs tables) |
| Raid buffs worth 3% to Frost and 7% to Fire; 2 minute fight a tie in the model (533 vs 531); Spellblasting Potion 535 and 490; 120 mp5 narrows the lead to 1.9% | `python analysis/raid_specs.py` (settings table) |
| The dice agree within 1% for the four page builds; the lead is 5.5% under the dice | `python analysis/raid_check.py 1000` |
| In a 2 minute fight the dice put Frost 1.1% ahead | `python analysis/raid_check.py 1000 frost-mb fire-mb fightLength=120` |
| With mana unlimited, model and dice agree within 1.4% | `python analysis/raid_check.py 400 mp5=3000` |
| Racial raid gains for the top build: Undead 1.6%, Human with a sword 1.4%, the rest 0.5 to 0.7% | `node -e "const m=require('./model.js'),o=m.DEFAULTS,b=m.specTotal(o,'frost-mb');['human','gnome','skyborne','orc','undead','troll'].forEach(r=>console.log(r,(m.specTotal(Object.assign({},o,{race:r}),'frost-mb')/b*100-100).toFixed(2)))"` |
| Model vs the ElliotWood sim on the sim's own builds (model side; the sim side needs the sim and its runner, not in this repo) | `node -e "const m=require('./model.js');console.log(m.rank(Object.assign({},m.DEFAULTS,{race:'human',sword:false,topRanks:true,wandDps:0})).map(r=>r.id+' '+r.total.toFixed(1)).join(', '))"` |
| AoE leveling (interim, under review) | `python analysis/aoe_breakeven.py` |
| Classic vs Forever values in the proof table (Blizzard chill, Shatter, Fireball and Frostbolt top ranks, low-rank coefficients) | `data/talents.json` and `data/mage_spells.json`; `docs/mage-mechanics.md` |
| The talent value table (per-rank values; 43 scored talents, 11 not, with reasons) | `data/talents.json`; `node -e "const L=require('./leveling.js');console.log(L.SCORED.length,L.UNSCORED)"` |
| model.js matches models/raid_model.py | `node tests/parity_test.js` (63 cases) |
| Every raid calculator option matches Python | `node tests/raid_options_test.js` (2111 checks; regenerate with `python tests/make_raid_fixtures.py`) |
| Stat weights and the item comparer behave as specified | `node tests/weights_test.js` (492 checks) |
| leveling.js matches the Python leveling model | `node tests/leveling_parity_test.js` (755 cases; regenerate with `python tests/make_leveling_fixtures.py`) |
| The AoE model's invariants | `python tests/aoe_test.py` |
| Talent rules, share links, presets and the page plan are legal at every level | `node tests/builder_test.js` |
| The page loads, every control works, phone width and both themes | `python src/build.py && python tests/page_check.py` |

## Changelog

- **v1, 1 Oct 2026.** First release: a level planner with a talent order checked at every level, a talent builder that scores any leveling build, a raid calculator with stat weights and an item comparer, an AoE leveling check, and 28 in-game tests.

## How to rebuild the page

`index.html` is generated. Edit `src/page.src.html`, `src/class.js`, `src/content.js`, `src/raid.js`, `src/builder.js`, `model.js` or `leveling.js`, then run `python src/build.py` from the repo root, and rerun the tests in `tests/`.

## How to contribute

If you have tested something in the beta or the live game and it disagrees with a number here, open a [Test result](../../issues/new?template=test-result.yml) issue with what you did and what you saw. The page's "Help test these" list has 28 tests, most important first.

If you think a formula, a spell value or a talent effect here is wrong, open a [Correction](../../issues/new?template=correction.yml) issue with a source.

## Disclosure

Research, models and page were built with Claude (Anthropic). Separate Claude sessions then reviewed the models adversarially from their own checks, and their fixes are applied. Every number traces to a source or a script here.

## Game art

The icons in `assets/icons/` are Blizzard Entertainment's art, downloaded from Wowhead's image server (`wow.zamimg.com`). They are used here in a non-commercial fan project and are not covered by this repo's MIT license.

## License

MIT. See `LICENSE`.

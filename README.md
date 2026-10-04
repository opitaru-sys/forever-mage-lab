# Forever Mage Lab

A theorycraft lab for the Mage class in WoW: Forever. It covers leveling rotations and talent order, whether AoE leveling pays, the level 60 solo build, and the level 60 group spec (Frost, Fire or Arcane, and how much Missile Barrage is worth).

Data is from the Forever beta client, build 1.60.1.69893, read on 30 September and 1 October 2026. Beta data can change before launch on 4 November. Treat every number here as "true for this beta build," not "true forever."

Live page (once published): https://opitaru-sys.github.io/forever-mage-lab/

## The verdict

- **Levels 10 to 19.** Frostbolt and your wand, with Fire Blast from 14, and Improved Frostbolt first. An Arcane wand build is about 4% faster at these levels, but they are under a tenth of your leveling time, so playing Arcane and respeccing at 20 saves only 0.36%.
- **Levels 20 to 60.** Frost, with Ice Lance on every freeze: this lab's order takes about 104 hours of grinding from 10 to 60 in the model (kills only, no quest XP), against 114 for Arcane-first and 121 for Fire-first. Frost Nova the mob when it closes and step back; from about 41, drop the wand and the step back and add Fire Blast on cooldown.
- **AoE leveling.** No, not in our model. At every level we tested (20, 25, 30, 40, 50 and 60), against mobs of your level, Blizzard, Arcane Explosion and Flamestrike pulls of 2 to 10 mobs fail: most run out of mana, and the rest are caught before Frost Nova is back. Two mobs at once, with Frost Nova and Frostbolt, are about even with one at a time at 50 and 60 (within the model's 6 to 9% slow bias there) and 9 to 45% slower from 20 to 40.
- **Group at 60.** A close call: Frost with Missile Barrage, 18/3/30, does 534 dps at the calculator defaults before racials, 6.1% ahead of Fire with Arcane Blast (19/31/1, 503), and 5.7% in a dice simulation. Fire with Arcane Blast leads if Ice Lance has no spell power scaling, as the game's data reads (test m4), or Fingers of Frost does not proc on raid bosses (test m30), by 1.6% over Arcane with Ignite either way. The sim's deep Fire build (0/35/16) edges ahead in fights under about 85 s in the dice (102 s in the model), by up to 2.5% and by under 2%, a tie, from about 75 s; Fire with Arcane Blast never passes Frost in the dice from 60 s up. High gear (700 spell power, 15% crit and hit) leaves Frost 0.3% ahead, a tie; no boss partial resists 0.9%; 15% hit with a Moonkin 1.5%; 15% gear hit 2.5%; Ice Lance partially resisting (test m29) 4.4%; a Moonkin 5.1%.
- **Solo at 60.** The leveling order's final build, 10/6/35: Frostbolt and Fire Blast on cooldown, Frost Nova, Ice Lance on every freeze and Fingers of Frost charge. Its late pick, Arcane Concentration, makes kills at 60 2.2% faster.
- **Race.** Race barely matters. Undead levels about 3% faster and adds 1.6% in raids; every other race is within about 2% for leveling and 1.4% in raids.
- **Dungeons.** The first open at level 13. Whether dungeon kills give experience in Forever is untested (test m2), so the models leave dungeon leveling out.

## How it was built

Data sources:
- The Forever beta client's own tables (build 1.60.1.69893, from the ElliotWood/Forever data cache): base damage, spell power coefficients, costs, cast times and learn levels for 166 spell ranks (`data/mage_spells.json`), and the per-rank talent curves for all 54 talents (`data/talents.json`). Later beta builds up to 70124 changed only Heating Up (then called Hot Streak), Wake of Fire, Ignite and Arcane Missiles' line of sight; the models use the newer values. Blizzard's 1 October 2026 beta notes returned Combustion to 3 charges, which the models use; that build's other Mage changes (Hot Streak renamed Heating Up, Improved Scorch and Winter's Chill without a resist roll, Gnome Eureka! off damage over time, low ranks cut far below your level) move no number here, and its balance pass on Comprehension scrolls, which the models leave out, may have changed the Coldflame Saber stats the page quotes.
- Wowhead's Forever tooltips (JSON), ForeverChanges (class changes, talents, spellbook, racials, patch notes, and DoubleZug's downranking measurements at levels 18 and 19), and the ElliotWood/Forever sim's code and data.
- `docs/mage-mechanics.md` condenses all of it, with sources.

Models:
- **Leveling** (`models/leveling_sim.py`, `models/character.py`): an expected-value fight simulator in 0.02 s steps, with the mob running at you, slows, roots that damage can break, stepping back, spell pushback, procs counted as they build up, and a rest model (eating and drinking at once, potions, Evocation, racials). For each build and level it searches 13 base rotations with modifiers and keeps the fastest; an exhaustive check on 212 cases found a largest gap of 0.000%. The planner's talent order comes from a search over every point (`analysis/leveling_planner.py`). Method: `docs/leveling-model.md`.
- **Raid** (`models/raid_model.py`): a mana-budget model that finds the mix of spell cycles doing the most damage within the fight's time and mana, with raid buffs, potions, runes, gems, Evocation and a wand while waiting for mana. `analysis/raid_check.py` plays each plan cast by cast with real dice as a check. Method: `docs/raid-model.md`.
- **AoE** (`models/aoe.py`, `models/aoe_loops.py`): pulls of 2 to 10 mobs in 0.1 s steps, through five scripted loops (two mobs with Frost Nova and Frostbolt, Blizzard, Arcane Explosion, Flamestrike, Cone of Cold kiting), compared with the single-target model. On one mob it runs 3 to 9% slower than the single-target model, never faster, so it errs against AoE. Reviewed by a separate Claude session. Method: `docs/aoe-model.md`.
- The page runs `model.js` and `leveling.js`, hand ports of the Python models. `tests/parity_test.js`, `tests/raid_options_test.js`, `tests/weights_test.js` and `tests/leveling_parity_test.js` check them against Python fixtures case by case.
- **Cross-check against the ElliotWood sim.** On the sim's own three builds and rotations at matching stats (human, 500 spell power, 10.80% crit, 11% hit, 347.6 Intellect, 203.3 Spirit, 77 mp5, mana potion and rune, 300 s, level 63 target, 3000 iterations; raid buffs with Kings entered as sheet stats), the sim reads Arcane 478.8, Fire 408.1 and Frost 470.3 dps, and the model 479.0, 418.8 and 487.4: the model is 0 to 3.6% higher. The sim still gives Combustion 4 charges and the model 3 since Blizzard's 1 October notes; at 4 the model's Fire read 423.8. The sim keeps a 1% miss floor, and its Frost build runs out of mana for 30 s of the 300.

Every number on the page or in this README comes from a command in the table below.

## Assumptions

The full tables, with sources and test ids, are in `docs/leveling-model.md` (46 rows), `docs/raid-model.md` and `docs/aoe-model.md`. The ones that move results most:

### Leveling model (`models/character.py`, `models/leveling_sim.py`, `leveling.js`)

| Input | Value as used | Status |
|---|---|---|
| Spell power | level x 1 (gear 1, "leveling greens") or x 2 (gear 2) | Warlock lab convention |
| Gear stats | 1 Intellect, 1 Stamina, 0.5 Spirit per level | ASSUMPTION |
| Mob health | 18 L + 0.62 L^2, averaged at x0.9, x1.0, x1.1 | Warlock lab curve, test m16 |
| Mob damage | 0.035 L^2 a second, taken only in melee range | Warlock lab curve, test m16 |
| Mob run speed | 8 yd/s (player 7) | sim constant, test m3 |
| Pull distance | 25 yd to melee, plus range talents | ASSUMPTION |
| Frost Nova and Frostbite freezes | each damage event, wand shots included, breaks them with chance 0.5 | ASSUMPTION; Frostbite's client aura row matches Nova's and reacts to every damage-taken flag; test m12 |
| Stepping back | a searched choice: 2 s of walking after a root | ASSUMPTION |
| Spell pushback | 0.5 s a melee hit; a channel loses one tick a hit | ASSUMPTION |
| Spirit regen | 6.25 + Spirit/8 a second, after 5 s without spending mana | sim, tests m14 and m10 |
| Regen while eating and drinking | on | ASSUMPTION (Classic rule), test m10 |
| Water and food | client values (Crystal Water 4200 over 30 s) | client; Wowhead reads 25/26, test m10 |
| Mana potions | the best the level allows, one per 2 min, on by default; they cut leveling time by 9.2% | Wowhead tooltips; the client's list price (no vendor is known; auction prices are likely far higher) |
| Ice Lance coefficient | 0.143, x4 on a frozen target for the whole hit | sim estimate; client 0; test m4 |
| Low ranks | full coefficients, lower ranks cast only at 19 and below; the highest trained rank from 20 | client and DoubleZug's measurements at 18 and 19; Blizzard's 1 Oct notes cut ranks far below your level; test m13 |
| Armor | Frost or Ice Armor below 34, Mage Armor from 34; armor chills roll Frostbite | test m17 |
| Wand | 0.9 L + 3 dps, no spell power | Warlock lab; Blizzard's 24 Sep notes |
| Touch of the Grave (Undead) | 10% of damaging spells and wand shots drain 5% of max health | Wowhead tooltip ("spells and attacks") and the client proc mask, which includes ranged auto-attacks; spells only is test m23 |
| Walking between kills | 8 s | Warlock lab |
| XP per mob (hours only) | 45 + 5 L, Classic XP table | ASSUMPTION |

### Raid model (`models/raid_model.py`, `model.js`)

| Input | Value as used | Status |
|---|---|---|
| Gear point | spell power 500, crit 10%, hit 11% from gear, Intellect 300, Spirit 120, mp5 0 | the Warlock page's gear point; the sim runner's grid |
| Fight | one level 63 boss, 300 s | |
| Raid buffs | on: Greater Blessing of Wisdom 40 mp5, Greater Blessing of Kings +10% to all stats, Mana Spring Totem 25 mp5, Prayer of Spirit +40, Gift of the Wild +16; Moonkin Form +3% spell crit is a switch, off | Forever tooltips; Kings takes a second Paladin (ASSUMPTION) |
| Consumables | Major Mana Potion, Demonic or Dark Runes and mana gems on a shared 2 min cooldown, Mageblood Elixir, all on | client item categories (test m24) |
| Hit cap | 16% against a level 63 boss, capped counts as 100% landed | Classic table, test m15 |
| Boss partial resists | 6% average on non-binary spells (Frostbolt, Ice Lance, Blast Wave exempt) | sim; no test before raids |
| Ice Lance coefficient | 0.143 | sim estimate; client 0; test m4 |
| Ice Lance partial resists | none: treated as binary | ASSUMPTION, as the sim flags it; test m29 |
| Fingers of Frost on a raid boss | procs from Frostbolt's chill, though bosses cannot be chilled | ASSUMPTION, as the sim does; test m30 |
| Arcane Blast stacks | +10% a stack to other spells, not Arcane Missiles, Blizzard or Flamestrike | client masks; tooltip says all; test m8 |
| Barrage Missiles | leave Arcane Blast stacks alone | a reading of the client masks; the rank 5 tooltip and the sim end them; test m28 |
| Casting regen | Mage Armor 50% plus Arcane Meditation up to 50%, added | sim; test m5 |
| Evocation | 800 + 16 x Spirit + 1.6 x mp5 | sim formula, test m7 |
| Ignite | 40% of the crit, rolled, one Mage's | sim, test m11 |
| Missile Barrage | 40% from Arcane Blast, 20% from Fireball, Frostbolt, Frostfire Bolt | tooltip and sim, test m18 |
| Spell ranks | highest trainer ranks only, which Blizzard's 1 Oct downrank rule backs; no top-rank tomes | test m13 and m6 |
| Waiting for mana | full Spirit regen and a 57 dps wand, in 15 s blocks | ASSUMPTION |
| Undead max health | 4000 | ASSUMPTION (slider) |

### AoE model (`models/aoe.py`, `models/aoe_loops.py`)

The breakeven summary at the defaults: levels 20, 25, 30, 40, 50 and 60, against mobs of your level (gear 1, no race; `python analysis/aoe_breakeven.py`). Seconds per kill; "dies" means the pull never keeps 25% of your health at any size from 2 to 10.

| Level | Single target | Two mobs, Frost Nova and Frostbolt | Blizzard, Arcane Explosion, Flamestrike | Breakeven pull size |
|---|---|---|---|---|
| 20 | 28.2 | 30.8 (+9%) | dies | none |
| 25 | 29.4 | 42.6 (+45%) | dies | none |
| 30 | 28.4 | 34.2 (+20%) | dies | none |
| 40 | 25.2 | 31.8 (+26%) | dies | none; from 5 mobs only with Classic's chill and mobs hitting half as hard |
| 50 | 20.5 | 22.9 (+12%) | dies | none; from 6 under the same pair |
| 60 | 19.8 | 20.8 (+5%) | dies | none; from 7 under the same pair |

- Two mobs at once are about even with single target at 50 and 60, within the engine's own slow bias there (6.4% at 50 and 9.4% at 60 on one mob), and 9 to 45% slower from 20 to 40. With no time to find a pair they are 2% ahead at 60, a tie.
- No single one of the 39 sensitivity rows clearly flips the verdict, including a Frost Nova that never breaks and mobs 3 levels below you: 5 put two mobs 0 to 2% ahead at 50 or 60, ties inside that bias. The only pair that clearly flips it is Blizzard's chill at Classic strength (test m3) with mob damage at half the curve (test m16): the Blizzard loop then pays from 5 mobs at 40 (16% faster at 6), 6 at 50 (25% at 8) and 7 at 60 (34% at 10). Both values lie outside the ranges the research register gives them.
- Why: at 50% for 2 s a freed mob crosses the 16 yd storm in about 4 s, so only about 3 to 6 of a Blizzard's 8 ticks land on each mob, while every mob needs 2.7 to 4.4 full Blizzards. Most failed pulls run out of mana; the rest are caught before Frost Nova is back.

Its inputs:

| Input | Value as used | Status |
|---|---|---|
| Blizzard chill | Improved Blizzard 15/25/40% plus Permafrost 3/7/10%, 50% for about 2.0 s at 3/3 | client; test m3 |
| Server target cap | none | client stores none; test m1 |
| Frost Nova and Frostbite break | 0.5 a damage event | ASSUMPTION, test m12 |
| Mob level | your own; mobs 3 levels below is a sensitivity row, and flips nothing | ASSUMPTION |
| Mob health and damage | the Warlock lab curves | test m16 |
| Blizzard and Flamestrike ticks | never crit | sim; test m9 |
| Packs | beasts that never flee | ASSUMPTION, test m20 |
| Gathering a pack | 6 s a mob, no damage taken, no mana spent | Warlock lab |
| Finding two mobs to pull from range | 3 s a mob (sensitivity 0 and 6 s) | ASSUMPTION, test m20 |
| Safety floor | expected health never under 25% | ASSUMPTION |
| Dungeon kills | out of scope | test m2 |

## How to reproduce each claim

Run every command from the repo root. The leveling sections take 10 to 40 s each; `analysis/raid_check.py 1000` about 40 s.

| Claim | Command |
|---|---|
| Frost levels fastest: this order 104.4 h of grinding, Arcane-first 113.9, Fire-first 121.1 (mean 24.9, 26.5, 28.0 s a kill); Fire-first 16.0% slower | `python analysis/leveling_paths.py trees` |
| A Frost-first order stays first in all 19 sensitivity rows; roots that never break would be 19.2% faster, roots breaking on every hit 2.6% slower; no Spirit regen while drinking costs 4.6 to 5.4%; Mage Armor is worth 1.4% | `python analysis/leveling_paths.py sensitivity` |
| An Arcane start is 3.8% faster at 10 to 19, but a respec plan saves only 0.36% (upper bound 0.50%) | `python analysis/leveling_paths.py respec` |
| Rotation by level, level 20 jump (32.9 s to 28.2 s), gear 2 vs gear 1 (the planner's phase texts) | `python analysis/leveling_paths.py phases` |
| Near-ties in the planner: Frost Nova at 21 within 0.2%, the wand filler at 24 within 0.4%, Fire Blast at 56 to 60 within about 1%; at 42 and 43 Fire Blast costs 7.7% and 4.3% | exhaustive search over every rotation of the planner build at those levels (the method of `analysis/leveling_search_check.py`) |
| Mana potions save 9.2% of leveling time (104.4 h against 114.9), 30 an hour, 0.12 to 18 gold an hour at the client's list price; mana gems never pay | `python analysis/leveling_paths.py consumables` |
| Race leveling: Undead 3.2% (2.9% if Touch of the Grave skips wand shots), Skyborne 1.9%, Troll 1.3%, Human 1.1%, Gnome 0.9%, Orc 0.4% | `python analysis/leveling_paths.py races` |
| Even with every low rank at full strength (option `full`, which Blizzard's rule cuts far below your level), downranking would save at most 1.4% of leveling time from 20 to 60 | `python analysis/leveling_paths.py lowranks` |
| The planner's talent order (25 to 70 minutes on 16 cores) | `python analysis/leveling_planner.py` |
| Arcane Concentration makes the plan's kills at 60 2.2% faster (19.80 s against 20.25 without it) | `node -e "const L=require('./leveling.js'),C=require('./src/class.js');const t={};C.planner.order.forEach(([k,n])=>t[k]=(t[k]\|\|0)+n);const u=Object.assign({},t,{ArcaneConcentration:0});console.log(L.evaluateUncached(60,t,1,{}).spk,L.evaluateUncached(60,u,1,{}).spk)"` |
| The leveling search matches an exhaustive search (212 cases, largest gap 0.000%) | `python analysis/leveling_search_check.py` |
| Raid ranking at the defaults: Frost with Barrage 534.2, Fire with Arcane Blast 503.4 (Frost +6.1%), Arcane with Ignite 495.5, Arcane 486.1; the sim builds 9 to 21% behind; 94 dps of free Missiles; Ice Lance 143 dps | `python analysis/raid_specs.py` (first table) |
| Flips: Ice Lance at 0 and Fingers of Frost off on bosses each put Fire with Arcane Blast first, 1.6% over Arcane with Ignite; no partial resists leaves Frost 0.9% ahead; Ice Lance partially resisting leaves 4.4%; the tooltip reading lifts the Arcane builds 5 to 8% and, paired with a flip or with no partial resists, puts Arcane with Ignite first by 1.7 to 2.3%; Barrage Missiles ending stacks 1.5 to 2.3%; tomes +7% (573), with Arcane 31/3/17 second | `python analysis/raid_specs.py` (untested and pairs tables) |
| Raid buffs worth about 4% to Frost and 9% to Fire (Kings 0.4% and 1.6%; with none, Frost 515 and Fire with Arcane Blast 462, behind both Arcane builds); no Shaman, Fire 499; Moonkin 2 to 4% and a 5.1% lead; gear hit 15% leaves 2.5%; fight length 120 s Frost +1.0% in the model, 60 s the sim's Fire build first by 4.0%; Spellblasting Potion 540 and 493; 120 mp5 leaves 2.4% | `python analysis/raid_specs.py` (settings table) |
| The dice agree within 1% for the four page builds; the lead is 5.7% under the dice (531.5 vs 502.8); plans that wait for mana read 2 to 5% high | `python analysis/raid_check.py 1000` |
| Short fights in the dice: at 120 s Frost leads Fire with Arcane Blast (526.0 vs 514.6); at 90 s the three are within 1% (Frost 522.6, the sim's Fire build 521.1, Fire with Arcane Blast 519.1); at 85 s Frost leads the sim's Fire build (523.2 vs 521.0), at 80 s the sim's Fire build leads (525.8 vs 523.9), so the crossover is about 82 s (about 84 s over 4000 fights); at 70 s the sim's Fire build leads by 2.4% (530.7 vs 518.1); at 60 s it leads by 2.5% (527.4), Frost and Fire with Arcane Blast tie (514.7 vs 512.6), and the model reads 3.1% (Frost), 5.9% (Fire with Arcane Blast) and 7.1% (sim Fire) high | `python analysis/raid_check.py 1000 frost-mb fire-mb fire-sim fightLength=120`, then `fightLength=90`, `85`, `80`, `70` and `60` |
| Short fights in the calculator: Fire with Arcane Blast passes Frost below about 93 s, the sim's Fire build below about 102 s | `node -e "const m=require('./model.js');for(let T=60;T<=120;T++){const o=Object.assign({},m.DEFAULTS,{fightLength:T});console.log(T,['frost-mb','fire-mb','fire-sim'].map(id=>m.specTotal(o,id).toFixed(1)).join(' '))}"` |
| 15% gear hit with a Moonkin leaves Frost 1.5% ahead (dice 1.7%); 700 spell power, 15% crit and 15% hit leaves Frost 0.3% ahead, a tie | `python analysis/raid_check.py 1000 frost-mb fire-mb gearHit=0.15 moonkin=true`; `node -e "const m=require('./model.js');console.log(m.rank(Object.assign({},m.DEFAULTS,{sp:700,crit:0.15,gearHit:0.15})).slice(0,2).map(r=>r.id+' '+r.total.toFixed(1)).join(', '))"` |
| With mana unlimited, model and dice agree within 1.7% | `python analysis/raid_check.py 400 mp5=3000` |
| Racial raid gains for the top build: Undead 1.6%, Human with a sword 1.4%, the rest 0.5 to 0.7% | `node -e "const m=require('./model.js'),o=m.DEFAULTS,b=m.specTotal(o,'frost-mb');['human','gnome','skyborne','orc','undead','troll'].forEach(r=>console.log(r,(m.specTotal(Object.assign({},o,{race:r}),'frost-mb')/b*100-100).toFixed(2)))"` |
| Model vs the ElliotWood sim on the sim's own builds (model side; the sim side needs the sim and its runner, not in this repo) | `node -e "const m=require('./model.js');console.log(m.rank(Object.assign({},m.DEFAULTS,{race:'human',sword:false,topRanks:true,wandDps:0})).map(r=>r.id+' '+r.total.toFixed(1)).join(', '))"` |
| AoE: at 20 to 60, against mobs of your level, no pull of 2 to 10 mobs beats single target; two mobs are about even at 50 and 60 (+12%, +5% against a 6.4% and 9.4% engine bias) and 9 to 45% slower below; only Classic chill with half mob damage clearly flips it, from 5 to 7 mobs at 40 to 60 | `python analysis/aoe_breakeven.py` (17 to 28 minutes; sections `calibration`, `defaults`, `budget`, `sensitivity`, `pairs`) |
| Classic vs Forever values in the proof table (Blizzard chill, Shatter, Fireball and Frostbolt top ranks, low-rank coefficients) | `data/talents.json` and `data/mage_spells.json`; `docs/mage-mechanics.md` |
| The talent value table (per-rank values; 43 scored talents, 11 not, with reasons) | `data/talents.json`; `node -e "const L=require('./leveling.js');console.log(L.SCORED.length,L.UNSCORED)"` |
| model.js matches models/raid_model.py | `node tests/parity_test.js` (63 cases) |
| Every raid calculator option matches Python | `node tests/raid_options_test.js` (2425 checks; regenerate with `python tests/make_raid_fixtures.py`) |
| Stat weights and the item comparer behave as specified | `node tests/weights_test.js` (569 checks) |
| leveling.js matches the Python leveling model | `node tests/leveling_parity_test.js` (771 cases; regenerate with `python tests/make_leveling_fixtures.py`) |
| The AoE model's invariants | `python tests/aoe_test.py` |
| Talent rules, share links, presets and the page plan are legal at every level | `node tests/builder_test.js` |
| The page loads, every control works, phone width (the talent panel pinned above the tree) and both themes | `python src/build.py && python tests/page_check.py` |

## Changelog

- **v1.3, 4 Oct 2026.** The talent builder's description panel now sits above the trees, and on phones it stays pinned under the menu bar while you scroll the tree, so the talent you tap and its text are on screen together. Thanks to a reader on Reddit. Picking a talent no longer moves the tree. "Best rotation" is now "Best leveling rotation", with a note that the builder scores leveling, one mob at a time; for raids, see the spec cards and the raid calculator. No numbers changed.
- **v1.2, 2 Oct 2026.** Blizzard's 1 October beta notes. Combustion is back to 3 charges, so Fire with Arcane Blast drops to 503 dps and Frost with Missile Barrage now leads it by about 6% (5.7% in the dice). No boss partial resists and high gear no longer flip the group pick. Short fights now go to the sim's deep Fire build (under about 85 seconds in the dice, a near tie), not Fire with Arcane Blast, which never passes Frost in the dice. Ice Lance with no spell power scaling or Fingers of Frost not procing on bosses still put Fire with Arcane Blast first, by 1.6% over Arcane with Ignite. Blizzard says ranks far below your level lose spell power and proc chance, so the claim that low ranks may keep full strength is gone, test m13 is rewritten, and the calculator's low-rank switch is relabeled; by default this page never casts a lower rank from 20. Excavation Site: Wetlands is now 26 to 31. Hot Streak is now called Heating Up (old share links still work). The beta reaches 30, so seven more tests can be done now. A new test from a reader (m32): does Ice Lance shatter while a Frostbolt is still in the air?
- **v1.1, 1 Oct 2026.** A new test from a reader (m31): can a Frostbolt in flight share one Fingers of Frost charge with an Ice Lance? Deep links now stay on their target after the page finishes loading.
- **v1, 1 Oct 2026.** First release: a level planner with a talent order checked at every level, a talent builder that scores any leveling build, a raid calculator with stat weights and an item comparer, an AoE leveling check, and 30 in-game tests.

## How to rebuild the page

`index.html` is generated. Edit `src/page.src.html`, `src/class.js`, `src/content.js`, `src/raid.js`, `src/builder.js`, `model.js` or `leveling.js`, then run `python src/build.py` from the repo root, and rerun the tests in `tests/`.

## How to contribute

If you have tested something in the beta or the live game and it disagrees with a number here, open a [Test result](../../issues/new?template=test-result.yml) issue with what you did and what you saw. The page's "Help test these" list has 32 tests (m1 to m32), most important first.

If you think a formula, a spell value or a talent effect here is wrong, open a [Correction](../../issues/new?template=correction.yml) issue with a source.

## Disclosure

Research, models and page were built with Claude (Anthropic). Separate Claude sessions then reviewed the models adversarially from their own checks, and their fixes are applied. Every number traces to a source or a script here.

## Game art

The icons in `assets/icons/` are Blizzard Entertainment's art, downloaded from Wowhead's image server (`wow.zamimg.com`). They are used here in a non-commercial fan project and are not covered by this repo's MIT license.

## License

MIT. See `LICENSE`.

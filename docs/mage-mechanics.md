# Forever Mage mechanics

A reference for the Mage in WoW: Forever as the beta client stores it, condensed from the lab's research notes (spells, talents, racials, mana, raid and AoE mechanics). The models read their values from `data/mage_spells.json` (166 spell ranks) and `data/talents.json` (54 talents); this file explains them and says where each comes from.

**Build.** Client tables are build 1.60.1.69893. The beta has moved on to 1.60.1.70124. Patch notes say builds 69913, 69977, 70058 and 70124 changed no spells, and 70009 changed four Mage things: Hot Streak (20 s), Wake of Fire (a 30 s window), Ignite (no longer counts damage bonuses twice) and Arcane Missiles' line of sight (checked once, at the start of the channel). A diff of the sim's spell data (built from 70009) against the 69893 tables, over all 276 Mage spell ids, found only the Hot Streak and Wake of Fire durations changed.

**How to read a value.** The client stores an average and a variance, not a min and max. At player level L: average = floor(base + per level x (min(L, max level) - learn level)), then min and max = average x (1 -/+ variance/2) (sim `effect.go`). Wowhead shows a rank's value at its max level, which is above 60 for top ranks; all 99 damage ranks checked match the client within 1 point once scaled. Coefficients are per hit, per missile or per tick, as the client stores them.

**"Classic"** below means the Classic Era client, build 1.15.9.69722, the same baseline ForeverChanges uses.

## Source keys

| Key | Source |
|---|---|
| client | Forever beta client tables, build 1.60.1.69893 (SpellEffect, SpellMisc, SpellLevels, SpellPower, SpellAuraOptions, SpellTargetRestrictions, ItemSparse and others), from the ElliotWood/Forever data cache (`tools/data_watch/.cache`) |
| curve | the per-rank talent trait curves the ElliotWood sim reads from the client (`sim/core/spelldata/spells_auto_gen.go`) |
| sim | ElliotWood/Forever sim code (`sim/mage/*.go`, `sim/core/*`) |
| WH | Wowhead Forever tooltip JSON (`nether.wowhead.com/forever/tooltip/spell/<id>`) |
| FC | foreverchanges.pro: class changes, talents, spellbook, racials, patch notes, downrank page, legacy perks, Battle Mage (Comprehension) |
| IV, WCT | Icy Veins Forever Mage overview and Frost guide; Warcraft Tavern Forever Mage guide (guide claims, not tests) |

## 1. Spells at 60

Top ranks at level 60 (client). Pyroblast, Arcane Blast, Ice Lance and Blast Wave come with their talent point; later ranks are trained (FC spellbook).

| Spell (rank) | Cost | Cast | Cooldown | Direct at 60 | Coefficient | Over time | Notes |
|---|---|---|---|---|---|---|---|
| Frostbolt (11) | 290 | 3 s | | 457 to 493 | 0.814 | | 40% slow, 9 s; binary (no partial resists) |
| Fireball (12) | 410 | 3.5 s | | 425 to 541 | 1.0 | 15 x 4 ticks, no coefficient | DoT ticks can crit |
| Arcane Missiles (8) | 655 | 5 s channel | | 209 a missile, 5 missiles | 0.286 a missile (1.43 total) | | line of sight checked once |
| Fire Blast (7) | 340 | instant | 8 s | 415 to 491 | 0.429 | | |
| Scorch (7) | 150 | 1.5 s | | 166 to 196 | 0.429 | | |
| Pyroblast (8, talent) | 440 | 6 s | | 520 to 646 | 1.0 | 53 x 4 ticks, 0.15 a tick | DoT ticks can crit |
| Arcane Blast (5, talent) | 15% of base mana | 2.5 s | | 364 to 424 | 0.714 | | stacking buff, below |
| Ice Lance (6, talent) | 160 | instant | | 136 to 160 | 0 in the client | | x4 on a frozen target; coefficient unknown (test m4) |
| Frostfire Bolt (3) | 370 | 3 s | | 270 to 314 | 0.814 | 19 x 3 ticks, no coefficient | Fire and Frost; 40% slow, 9 s; trained at 40, 50, 60 |
| Blizzard (6) | 1400 | 8 s channel | | | | 146 x 8 ticks, 0.042 a tick | 8 yd; each tick is a separate spell |
| Arcane Explosion (6) | 390 | instant | | 238 to 258 | 0.143 | | 10 yd |
| Cone of Cold (5) | 555 | instant | 10 s | 328 to 358 | 0.129 | | 40% slow, 6 s |
| Flamestrike (6) | 990 | 3 s | | 380 to 466 | 0.157 | 83 x 4 ticks, 0.032 a tick | 5 yd; one per Mage |
| Frost Nova (4) | 145 | instant | 25 s | 71 to 79 | 0.029 | | 8 s root, 10 yd; damage may break it |
| Blast Wave (5, talent) | 545 | instant | 45 s | 453 to 533 | 0.129 | | 10 yd, 50% daze 6 s |

Other spells at 60 (client, Wowhead agrees):

| Spell | Cost | Cooldown | Effect |
|---|---|---|---|
| Evocation | none | 8 min | 8 s channel, +1500% mana regen, full regen while channeling; trained at 20 |
| Mage Armor (3) | 490 | | 50% of mana regen continues while casting (Classic: 30%); learned at 34, 46, 58 |
| Ice Armor (4), Frost Armor (3) | 500, 170 | | +560 and +200 armor; melee attackers are chilled |
| Mana Shield (6) | 140 | | absorbs 570 physical damage at 2 mana a point |
| Ice Barrier (4, talent) | 480 | 30 s | absorbs 811 at 58, no coefficient; casts are not delayed or interrupted while it holds |
| Ice Block (talent) | 15 | 300 s | 10 s immunity |
| Blink | 35% of base mana | 15 s | 20 yd |
| Presence of Mind (talent) | none | 180 s | next spell under 10 s cast is instant |
| Arcane Power (talent) | none | 180 s | 15 s: +30% damage and +30% mana cost |
| Combustion (talent) | none | 180 s | +10% Fire crit a Fire hit, until 4 non-periodic Fire crits (Classic: 3) |
| Cold Snap (talent) | none | 600 s | resets your other Frost cooldowns |
| Arcane Intellect, Arcane Brilliance | 1510, 3400 | | +31 Intellect for 1 hour; Brilliance reaches party and raid |

**Top ranks.** Frostbolt rank 11, Fireball rank 12 and Arcane Missiles rank 8 come from Tome of Frostbolt XI (21214), Tome of Fireball XII (21279) and Tome of Arcane Missiles VIII (21280). Their only known source is Ruins of Ahn'Qiraj, which is not on the Forever roadmap (the lab's gap pass), so the models fall back to Frostbolt 10, Fireball 11 and Arcane Missiles 7 by default (test m6).

## 2. Trainer levels

| Spell | Ranks learned at |
|---|---|
| Fireball | 1, 6, 12, 18, 24, 30, 36, 42, 48, 54, 60 |
| Frostbolt | 4, 8, 14, 20, 26, 32, 38, 44, 50, 56 (rank 11 from a tome) |
| Fire Blast | 6, 14, 22, 30, 38, 46, 54 |
| Arcane Missiles | 8, 16, 24, 32, 40, 48, 56 (rank 8 from a tome) |
| Frost Nova | 10, 26, 40, 54 |
| Arcane Explosion | 14, 22, 30, 38, 46, 54 |
| Flamestrike | 16, 24, 32, 40, 48, 56 |
| Blizzard | 20, 28, 36, 44, 52, 60 |
| Scorch | 22, 28, 34, 40, 46, 52, 58 |
| Cone of Cold | 26, 34, 42, 50, 58 |
| Frostfire Bolt | 40, 50, 60 |
| Pyroblast (talent) | 20 (with the talent), then 24, 30, 36, 42, 48, 54, 60 |
| Arcane Blast (talent) | 20, 30, 40, 50, 60 |
| Ice Lance (talent) | 20, 28, 34, 42, 48, 56 |
| Blast Wave (talent) | 30, 36, 44, 52, 60 |

Frostbolt by rank (client): 1.5 s cast at rank 1, 1.8 s at 2, 2.2 s at 3, 2.6 s at 4, 3 s from rank 5; cost 25 at rank 1 to 260 at rank 10. Water: Conjured Water (rank 1) at 4, Fresh 10, Purified 20, Spring 30, Mineral 40, Sparkling 50, Crystal 60.

## 3. Low ranks (downranking)

- **Coefficients.** Forever's client stores low ranks at full coefficients: Frostbolt rank 1 is 0.407 (Classic 0.163), Fireball rank 1 0.429 (Classic 0.123), Fire Blast ranks 1 and 2 0.429, Arcane Missiles 0.286 a missile at every rank (client; sim).
- **Level caps.** A rank's max level only caps how far its base damage grows (sim `effect.go`).
- **Measured.** ForeverChanges' downrank page cites DoubleZug's beta measurements: Healing Touch ranks 1 to 3 and Rejuvenation ranks 1 and 3 at levels 18 and 19 land within 2 points of the full coefficient. That rules out Classic's below-20 cut and the Burning Crusade level rule at those levels.
- **Not measured.** No level above 19. A level-based rule on the server would not show in the client. So the lab casts only the highest trained rank from 20 by default; full strength above 19 is an option tied to test m13.

## 4. What Forever changed for the spells

| Spell | Change (client against Classic) |
|---|---|
| Fireball | Base damage 29% lower at rank 12 (425 to 541 against 596 to 760), up to 37% lower at rank 7; DoT 60 against 76 at rank 12; DoT ticks can crit |
| Pyroblast | Base 27% lower at rank 8 (520 to 646 against 716 to 890); DoT 53 a tick against 67; DoT ticks can crit |
| Scorch | 30 to 37% lower (rank 7: 163 to 193 against 233 to 275) |
| Frostbolt | Ranks 3 to 11 lower: 28% at rank 5, 11% at rank 11 (457 to 493 against 515 to 555); ranks 1 and 2 unchanged |
| Arcane Missiles | 9 to 21% less a missile (209 against 230 at rank 8), but 0.286 a missile (1.43 total) against 0.24 (1.2 total) |
| Fire Blast | Ranks 2 to 7 are 7 to 13% lower |
| Arcane Explosion, Cone of Cold, Blast Wave, Frost Nova | Slightly lower: Arcane Explosion 4 to 8%, Cone of Cold 3 to 6%, Blast Wave 2 to 4%, Frost Nova up to 4%; Cone of Cold slows 40% for 6 s (Classic 50% for 8 s) |
| Blizzard | 2 to 5% less a tick (146 against 149); rebuilt as an area trigger that casts a tick spell every 1 s |
| Flamestrike | Burn moved to a tick spell every 2 s, 83 a tick against 85, tick coefficient 0.032 against 0.02; one Flamestrike per Mage |
| Arcane Blast, Ice Lance (talents) | New: see sections 1 and 6 |
| Frostfire Bolt | New, trained at 40, 50 and 60 |
| Mage Armor | 50% regen while casting (Classic 30%) |
| Arcane Intellect, Arcane Brilliance | 1 hour; Brilliance reaches party and raid |
| Ice Barrier (talent) | 7 less absorb a rank; casts are not delayed while it holds |
| Wands | No longer gain spell power (Blizzard's 24 Sep beta notes, via FC) |
| Evocation, mana gems, water, Mana Shield, armors, Polymorph, Counterspell, Blink | Unchanged values |

**Not in Forever:** no Water Elemental (the client has no Summon Water Elemental; sim `mage.go`). Icy Veins, Arcane Barrage, Living Bomb, Deep Freeze, Frozen Orb, Arcane Surge and Molten Armor sit in the shared client and on Wowhead as Season of Discovery rune spells, but ForeverChanges and the sim leave them out. Detect Magic was removed. Teleport: Dalaran is new at 50 (Alliance).

## 5. Talents

The 54 talents, their per-rank values and the share-link order are in `data/talents.json` (curve; ForeverChanges' rank texts match all 54). The page's proof section lists every rank. First point at level 10, 51 points at 60, 5 points per row (assumed by every source; no source reads it from the client). Whether a prerequisite needs full ranks is unverified. No Classic talent was removed; three were replaced (Magic Attunement by Arcane Geometry, Improved Fire Blast by Wake of Fire, Improved Mana Shield by Arcane Shielding).

The changes that shape the verdicts:

| Talent | Forever | Classic |
|---|---|---|
| Arcane Focus | Arcane spell hit +1 to 5%, Arcane spells only | +2 to 10% |
| Elemental Precision | Fire and Frost spell hit +1 to 5% | 3 ranks, 2/4/6% |
| Arcane Meditation | 17/33/50% regen while casting | 5/10/15% |
| Arcane Impact | crit +2/4/6% on Arcane Blast, Arcane Explosion and Arcane Missiles | Arcane Explosion only |
| Arcane Mind | Intellect +2 to 10%, Arcane crit damage bonus +20 to 100% | max mana +2 to 10% |
| Arcane Instability | damage and crit +1/2/3%; no longer needs Presence of Mind | |
| Arcane Blast (new) | 2.5 s, 15% of base mana; each cast +10% damage to your other spells and +175% to its own cost, 4 stacks, 8 s | |
| Missile Barrage (new) | Arcane Blast 40%, Fireball, Frostbolt, Frostfire Bolt 20%: next Arcane Missiles free, half the channel, a missile every 0.5 s, 15 s | |
| Wake of Fire | Fire Blast cooldown -1/2 s; the first Fire Blast within 30 s of a kill gets +25/50% crit | replaces Improved Fire Blast |
| Incineration | crit +2/4/6% on Fire Blast, Scorch, Arcane Blast and Ice Lance | 2 ranks, Fire Blast and Scorch |
| Improved Fireball | also shortens Frostfire Bolt | |
| Ignite | 8 to 40% of the crit over 4 s, one rolling burn | 5 stacking ticks |
| Improved Scorch | Fire Vulnerability is personal (below) | shared debuff |
| Hot Streak (new) | non-periodic crits of Fireball, Frostfire Bolt, Fire Blast and Scorch: Pyroblast cast -25% a stack, 3 stacks, 20 s | |
| Combustion | ends after 4 non-periodic Fire crits | 3 |
| Blast Wave | no longer needs Pyroblast | |
| Permafrost | chills last 11/22/33% longer and slow 3/7/10% more | +1/2/3 s |
| Improved Blizzard | chill slows 15/25/40%, 1.5 s | 30/50/65% |
| Shatter | +17/33/50% crit against frozen targets, 3 ranks | 5 ranks to 50%, needed Improved Frost Nova |
| Ice Lance (new) | instant, x4 on frozen targets, 6 ranks | |
| Fingers of Frost (new) | chills have a 15% chance to give 1/2 charges: your next spells treat the target as frozen, 15 s | |
| Winter's Chill | your own Frostbolt and Ice Lance only: +2% crit a stack, up to 1 to 5 stacks | shared debuff |
| Improved Cone of Cold | +12/23/35% | 15/25/35% |
| Ice Barrier | needs Cold Snap; no pushback or interrupts while it holds | needed Ice Block |

**Hit talents.** Arcane Focus covers Arcane spells only; Elemental Precision covers every Fire and Frost damage spell, including Blizzard ticks and Frostfire Bolt, and no Arcane spell (client masks; sim). Unlike the Warlock's Suppression, neither covers every school. Gear hit counts for spells too.

**Data quality.** Wowhead's talent tooltips show the stored base points, which is sometimes the top rank and sometimes not (Arcane Focus 2%, Elemental Precision 6%, Shatter 1%, Winter's Chill "0% chance"). Never read a Forever talent value from Wowhead alone; the curves and ForeverChanges agree on every rank.

## 6. Mana

| Source | Value | Status |
|---|---|---|
| Spirit regen | 12.5 + Spirit/4 every 2 s (6.25 + Spirit/8 a second), after 5 s without spending mana | sim's Classic rule; the five-second rule is unmeasured in Forever (test m14) |
| Regen while casting | Mage Armor 50%, Arcane Meditation 17/33/50% | whether they add up to 100% is untested (test m5); the sim adds them |
| Evocation | 8 s at +1500% regen, 8 min: 800 + 16 x Spirit + 1.6 x mp5 at 60 | derived from the sim's regen rule (test m7) |
| Mana gems | Agate 400, Jade 600, Citrine 850, Ruby 1100 on average; conjuring costs 530, 800, 1130, 1470 mana; single use, one of each | client; Wowhead agrees |
| Shared cooldown | all gems, Demonic Rune and Dark Rune share one 2 min cooldown; mana potions have their own | client item categories (test m24) |
| Major Mana Potion | 1350 to 2250 | client |
| Demonic and Dark Rune | 900 to 1500 mana for 600 to 1000 health | client |
| Major Spellblasting Potion | +47 spell damage for 30 s, on the potion cooldown (client 69893 says 40; ForeverChanges lists it changed in 70009) | Wowhead |
| Mageblood Elixir | 12 mp5 for 1 hour | client |
| Arcane Blast cost | 15% of base mana (1213 at 60, about 182), +175% a stack | client; rounding and stacking untested (test m21) |
| Water | Conjured Crystal Water: 700 every 5 s for 30 s (4200 in all) by the client; Wowhead reads 25/26 of every drink and food (4038) | test m10 |
| Spirit regen while drinking | not stated by any source | test m10 |
| Bottles at 60 | 10 by the client's base value, 20 with a Season of Discovery passive | test m27 |
| Thrill of Adventure (legacy perk) | 1 to 5% of max health and mana over 10 s per killing blow, outside dungeons | FC legacy perks |

## 7. Raid mechanics

- **Fire Vulnerability is personal.** The aura changed from damage taken from everyone (Classic) to damage taken from the caster (client 22959). Every Fire Mage keeps their own 5 stacks (+3% a stack); there is no shared Scorch Mage, and other Fire casters gain nothing (WH, FC, sim; test m25).
- **Winter's Chill is personal** and reaches only your Frostbolt and Ice Lance (client 12579): +10% crit at 5 stacks. It does nothing for Blizzard, Cone of Cold or another Frost Mage.
- **Ignite** is 40% of a crit over 4 s in 2 ticks, one rolling burn (a new spell, 412538); its ticks cannot crit. Whether several Mages share one is untested (test m11).
- **Hot Streak:** 3 stacks give a 1.5 s Pyroblast, spent by the next Pyroblast, 20 s.
- **Arcane Blast's buff** (+10% a stack, 4 stacks, 8 s) reaches Frostbolt, Fireball, Fire Blast, Scorch, Pyroblast, Ice Lance, Frostfire Bolt, Arcane Explosion, Cone of Cold, Frost Nova and Blast Wave by the client masks, but not Arcane Missiles, Blizzard or Flamestrike, whatever the tooltip's "all your other spells" says (test m8). The sim's Arcane rotation spends the stacks on Frostbolt. In the sim, the Arcane Missiles channel ends the stacks; the client masks suggest it does not (test m28).
- **Missile Barrage** proc rates of 40% and 20% are hardcoded in the sim; the talent row also carries a 50% proc chance that could halve them (test m18).
- **Fingers of Frost** is the only Shatter source on a boss in the sim, which assumes bosses cannot be frozen. The sim still rolls Fingers of Frost off Frostbolt's chill on a boss, though bosses cannot be chilled; the calculator follows it as an assumption (test m30).
- **Ice Lance's coefficient** is unknown: the client row reads 0, the sim uses 0.143 and says 0.429 or 0.572 are as likely (test m4).
- **Hit cap.** No Forever source. The sim builds raid targets at level 63 on the Classic table: 17% miss against a +3 target with a 1% floor, so 16% hit caps (test m15).
- **Partial resists.** A level 63 boss resists about 6% of non-binary spell damage on average in the sim (`core/spell_resistances.go`). Frostbolt and Blast Wave are binary; the sim flags Ice Lance as binary too, which is untested (test m29).
- **Damage over time can crit** in Forever: Fireball, Pyroblast and Frostfire Bolt carry the periodic-crit flag, which the Classic client does not (test m22).
- **Raids** open 9 December: The Barrow Deeps (10 players), Hyjal Summit (20) and Onyxia's Lair (40). Raid data is encrypted in the client until then, so Fire or Frost immunity of any boss is unknown.
- **Raid buffs** (Forever tooltips): Greater Blessing of Wisdom 40 mp5, Greater Blessing of Kings +10% to all stats (25898; one Blessing per Paladin, so Kings next to Wisdom takes a second Paladin), Mana Spring Totem 25 mp5 (party), Prayer of Spirit +40 Spirit, Gift of the Wild +16 to all attributes, and Moonkin Form +3% critical strike chance to party members within 45 yd (24858). Both factions have Paladins and Shamans (Undead Paladins, Dwarf Shamans; FC racials).

## 8. AoE mechanics

- **Target caps.** No Mage AoE spell has a target cap in the client: Blizzard, its tick spells, Flamestrike, its tick spells and Cone of Cold store none, and Frost Nova, Arcane Explosion and Blast Wave have no row at all, while other spells do store caps (Whirlwind 4, Thunder Clap 4). A server-side cap is unknown (test m1).
- **Blizzard's chill** belongs to Improved Blizzard: 15/25/40% for 1.5 s, plus Permafrost's 3/7/10% and 11/22/33% longer. At 3/3 and 3/3 that is 50% for about 2.0 s; Classic had 65% plus 10% for 4.5 s (test m3). Some published Forever AoE guides still use the Classic 65%.
- **Cone of Cold** slows 40% for 6 s, about 8 s with Permafrost 3/3 (Classic: 50% for 8 s, 11 with Permafrost).
- **Blizzard and Flamestrike ticks** are separate spells cast by an area trigger. They do not carry the cannot-crit flag, but the sim treats them as unable to crit (test m9).
- **Frost Nova** keeps Classic's wording, "damage caused may interrupt the effect"; how often is unmeasured (test m12). Frostbite's freeze has the same aura options as Frost Nova in the client.
- **Chills.** Frostbite and Fingers of Frost trigger on chill effects, and the client's chill mask includes Frost and Ice Armor's chill on attackers, Improved Blizzard's chill, Frostbolt, Cone of Cold and Frostfire Bolt (test m17).
- **One Flamestrike per Mage** (FC, sim; test m26).
- **Dungeon experience.** Icy Veins says Forever moved dungeon experience into quests; unverified (test m2). Blizzard said on the BlizzCon stream that tanks hold threat on three or four targets at once.

## 9. Racials

Mage races: Human, Gnome and Skyborne High Order (needs a Heroic pack) for the Alliance; Orc (new for Mages), Undead and Troll for the Horde. The Horde Skyborne (Windshapers), Dwarves and Night Elves cannot be Mages (FC racials).

| Race | Racial | Forever effect | Source |
|---|---|---|---|
| Human | Sword Specialization | +2% crit with spells and attacks while a sword is equipped; Mages can use one-hand swords | WH 20597 |
| Human | The Human Spirit | Spirit +5% | WH 20598 |
| Human | Will to Survive | remove stuns, 3 min | WH 1259718 |
| Gnome | Expansive Mind | max mana +5% (Classic: +5% Intellect) | WH 20591 |
| Gnome | Eureka! | next 3 damaging abilities -10% cost, +10% damage, 2 min (before 70009 the Mage version cut cost 50%) | WH 1259817, FC patch notes |
| Gnome | Escape Artist | remove slows and roots, 3 s immunity, 2 min | WH 20589 |
| Skyborne | Wind Blessed | +1% haste | WH 1259710 |
| Skyborne | Elemental Insight | +5% damage against Elementals | WH 1259707 |
| Skyborne | Read Ley Line | health and mana regen +100% for 15 s, or 15 min near a ley line; 2 s cast, 2 min | WH 1259705 |
| Orc | Blood Fury | +10% attack power and spell power, 15 s, 2 min | WH 20572 |
| Orc | Shatter Curse | remove curses and banes, -15% magic damage taken for 8 s, 3 min | WH 1299026 |
| Orc | Hardiness | stuns on you last 20% shorter | WH 20573 |
| Orc | Axe Specialization | +1% crit with an axe; Mages cannot equip axes | WH 20574 |
| Undead | Touch of the Grave (caster version) | "Your spells and attacks" have a 10% chance to drain 5% of your max health from the target, 1 s cooldown; the client's proc mask includes ranged auto-attacks, so wand shots count (build 70009's notes say only damaging spells; test m23) | WH 1260201, client SpellAuraOptions, FC patch notes |
| Undead | Cannibalize | 7% health and 7% mana every 2 s for 10 s from a humanoid or undead corpse, 2 min (Classic: health only) | WH 20577 |
| Undead | Will of the Forsaken | remove charm, fear and sleep, 2 min | WH 7744 |
| Troll | Berserking | +10% cast and attack speed for 10 s, 3 min; flat (Classic scaled 10 to 30% with missing health) | WH 20554 |
| Troll | Beast Slaying | +5% damage against Beasts | WH 20557 |
| Troll | Rapid Regeneration | 50% of max health over a 6 s channel, 3 min | WH 1260270 |
| Troll | Regeneration | health regen +10%, 10% of it in combat | WH 20555 |

**Coldflame Saber** (FC Battle Mage): Shadowfang Keep's Blade of Silverlaine plus the Scroll of the Saber (Comprehension) make a level 21 Mage sword with +32 spell power and +7 Intellect, which turns on a Human's sword crit. Scroll drop rates are unknown.

## 10. Comprehension

The Mage-only research skill (FC Battle Mage). Comprehend Scroll from level 6; Study (1 hour cooldown, needs a library and a Light Feather) gives a Bundle of Scrolls; skill to 300 in four scroll tiers. The scrolls are Mage consumables: Minor Evocation, staff imbues (+4 to +20 Fire or Frost damage, +3 spell hit, +5% spell crit, target resistance), dagger and sword imbues, Intellect familiars and Scroll of Greater Cryoblast. Supply, drop rates and stacking with wizard oils are unknown, so the models leave them out.

## 11. Open questions

Each open value ships as a calculator or model option and an in-game test; the page's "Help test these" list has the steps, most important first. Test ids: m1 target cap, m2 dungeon XP, m3 Blizzard chill and mob speed, m4 Ice Lance coefficient, m5 casting regen stacking, m6 top-rank tomes, m7 Evocation, m8 Arcane Blast mask, m9 tick crits, m10 drinking and Spirit, m11 Ignite, m12 root breaks, m13 low ranks at 30+, m14 five-second rule, m15 miss chance, m16 mob health and damage, m17 Frostbite from chills, m18 Missile Barrage rate, m19 Fingers of Frost on AoE, m20 pack behavior, m21 Arcane Blast cost, m22 DoT crits, m23 racials, m24 shared cooldowns, m25 personal debuffs, m26 Flamestrike overlap, m27 bottles at 60, m28 Barrage Missiles and Arcane Blast stacks, m29 Ice Lance partial resists, m30 Fingers of Frost on a raid boss.

## Sources

- ElliotWood/Forever: https://github.com/ElliotWood/Forever (client table cache `tools/data_watch/.cache`, sim `sim/mage`, `sim/core`, talent trees `ui/sim/talents/trees/mage.json`, APLs `ui/specs/mage/dps/apls`)
- Wowhead Forever tooltips: https://nether.wowhead.com/forever/tooltip/spell/<id> and /tooltip/item/<id>
- ForeverChanges: https://foreverchanges.pro/class/mage, /talents/mage, /spellbook/mage, /racials, /patch-notes, /downrank-calculator, /legacy-perks, /battle-mage, /beta
- Icy Veins: https://www.icy-veins.com/wow-forever/mage-class-overview
- Warcraft Tavern: https://www.warcrafttavern.com/forever/guides/mage

// Forever Mage Lab: the class data object. Everything class-specific the page engine reads lives here.
// A new class forks the repo and replaces this file (plus data/talents.json and the icon list), not the engine.
// Sources: data/talents.json (trees and talents, inlined by src/build.py, never retyped here), the Mage research notes
// (talents FINDINGS section 4 for racials, spells NOTES section (b) for trainer levels), and Wowhead Forever tooltip
// JSON for icon names.
// Any text not written yet is a string starting with TODO-CONTENT; the page renders those as visible placeholders.
(function (root) {
  'use strict';
  const inNode = typeof module !== 'undefined';
  const talentData = inNode ? require('../data/talents.json') : root.FML_TALENT_DATA;
  const talentText = inNode ? {} : (root.FML_TALENT_TEXT || {});
  const REPO = 'https://github.com/opitaru-sys/forever-mage-lab';
  const TODO = 'TODO-CONTENT';

  // advice fields every race carries; the leveling and raid models fill them in later
  const raceAdvice = () => ({
    level: TODO + ': what the race does for leveling speed, from the leveling model.',
    levelPct: null,
    pvp: [TODO + ': PvP headline', ''],
    verdict: TODO + ': one-line race verdict.',
    tip: TODO + ': one practical tip.',
    raidNote: '',
  });

  const CLASS = {
    id: 'mage',
    name: 'Mage',
    title: 'Forever Mage Lab',
    icon: 'classicon_mage',
    repoUrl: REPO,
    liveUrl: 'https://opitaru-sys.github.io/forever-mage-lab/',
    resultsUrl: REPO + '/issues/new?template=test-result.yml',
    correctionUrl: REPO + '/issues/new?template=correction.yml',
    storagePrefix: 'fml.',

    // CSS custom properties. Contrast checked (WCAG): text pairs at least 4.6:1 in light and 6.0:1 in dark mode.
    colors: {
      light: { accent: '#2F4FAE', 'accent-ink': '#FFFFFF', 'accent-soft': '#E4E9F7', bar: '#2F4FAE',
        tree0: '#8E3AA6', 'tree0-soft': '#F3E6F7', tree1: '#B8440F', 'tree1-soft': '#FBE9DF', tree2: '#0B6A9A', 'tree2-soft': '#DDEFF8' },
      dark: { accent: '#86A6F2', 'accent-ink': '#0C0E13', 'accent-soft': '#1C2540', bar: '#86A6F2',
        tree0: '#D59AE8', 'tree0-soft': '#2E1C36', tree1: '#F2995E', 'tree1-soft': '#3A2214', tree2: '#6CC6EE', 'tree2-soft': '#12293A' },
    },

    // ---------------------------------------------------------------- talents (CONTRACTS section 1)
    trees: talentData.trees,
    talents: talentData.talents,
    talentText,                       // {key: [text at rank 1, rank 2, ...]}, derived by build.py from data/mage_talents_research.json
    talentRules: { trees: 3, rows: 7, perRow: 5, firstLevel: 10, maxLevel: 60, gears: [1, 2] },
    treeIcons: ['spell_holy_magicalsentry', 'spell_fire_flamebolt', 'spell_frost_frostbolt02'],
    talentIcons: {
      WandSpecialization: 'inv_wand_01', ArcaneFocus: 'spell_holy_devotion', ImprovedChanneling: 'spell_nature_starfall',
      ArcaneSubtlety: 'spell_holy_dispelmagic', MagicAbsorption: 'spell_nature_astralrecalgroup', ArcaneConcentration: 'spell_shadow_manaburn',
      ArcaneResilience: 'spell_arcane_arcaneresilience', ArcaneGeometry: 'inv_ability_mage_radiantspark', ArcaneImpact: 'spell_nature_wispsplode',
      ArcaneBlast: 'spell_arcane_blast', ArcaneShielding: 'spell_shadow_detectlesserinvisibility', ImprovedCounterspell: 'spell_frost_iceshock',
      ArcaneMeditation: 'spell_shadow_siphonmana', MissileBarrage: 'ability_mage_missilebarrage', PresenceOfMind: 'spell_nature_enchantarmor',
      ArcaneMind: 'spell_shadow_charm', ArcaneInstability: 'spell_shadow_teleport', ArcanePower: 'spell_nature_lightning',
      WakeOfFire: 'spell_fire_lavaspawn', Incineration: 'spell_fire_flameshock', ImprovedFireball: 'spell_fire_flamebolt',
      Ignite: 'spell_fire_incinerate', FlameThrowing: 'spell_fire_flare', Impact: 'spell_fire_meteorstorm',
      BurningSoul: 'spell_fire_fire', ImprovedFlamestrike: 'spell_fire_selfdestruct', Pyroblast: 'spell_fire_fireball02',
      ImprovedScorch: 'spell_fire_windsofwoe', ImprovedFireWard: 'spell_fire_firearmor', HotStreak: 'ability_mage_hotstreak',
      MasterOfElements: 'spell_fire_masterofelements', CriticalMass: 'spell_nature_wispheal', BlastWave: 'spell_holy_excorcism_02',
      FirePower: 'spell_fire_immolation', Combustion: 'spell_fire_sealoffire',
      FrostWarding: 'spell_frost_frostward', ImprovedFrostbolt: 'spell_frost_frostbolt02', ElementalPrecision: 'spell_ice_magicdamage',
      IceShards: 'spell_frost_iceshard', Permafrost: 'spell_frost_wisp', ImprovedFrostNova: 'spell_frost_freezingbreath',
      Frostbite: 'spell_frost_frostarmor', PiercingIce: 'spell_frost_frostbolt', FrostChanneling: 'spell_frost_stun',
      IceLance: 'spell_frost_frostblast', ImprovedBlizzard: 'spell_frost_icestorm', ArcticReach: 'spell_shadow_darkritual',
      IceBlock: 'spell_frost_frost', Shatter: 'spell_frost_frostshock', ImprovedConeOfCold: 'spell_frost_glacier',
      ColdSnap: 'spell_frost_wizardmark', FingersOfFrost: 'ability_mage_wintersgrasp', WintersChill: 'spell_frost_chillingblast',
      IceBarrier: 'spell_ice_lament',
    },
    // talent cell labels: shortened words, and soft hyphens (U+00AD) as clean break points in the small cells
    shortReplace: [['Improved ', 'Imp. ']],
    shortWords: {
      Specialization: 'Special\u00ADization', Channeling: 'Chan\u00ADneling', Subtlety: 'Subt\u00ADlety', Absorption: 'Absorp\u00ADtion',
      Concentration: 'Concen\u00ADtration', Resilience: 'Resil\u00ADience', Geometry: 'Geo\u00ADmetry', Shielding: 'Shield\u00ADing',
      Counterspell: 'Counter\u00ADspell', Meditation: 'Medi\u00ADtation', Barrage: 'Bar\u00ADrage', Presence: 'Pres\u00ADence',
      Instability: 'Insta\u00ADbility', Incineration: 'Incin\u00ADeration', Fireball: 'Fire\u00ADball', Throwing: 'Throw\u00ADing',
      Flamestrike: 'Flame\u00ADstrike', Pyroblast: 'Pyro\u00ADblast', Elements: 'Ele\u00ADments', Critical: 'Criti\u00ADcal',
      Combustion: 'Combus\u00ADtion', Warding: 'Ward\u00ADing', Frostbolt: 'Frost\u00ADbolt', Elemental: 'Ele\u00ADmental',
      Precision: 'Preci\u00ADsion', Permafrost: 'Perma\u00ADfrost', Frostbite: 'Frost\u00ADbite', Blizzard: 'Bliz\u00ADzard',
    },

    // ---------------------------------------------------------------- races (CONTRACTS section 5, FINDINGS section 4)
    // racials: [name, Forever effect, icon]. Skyborne is Skyborne High Order.
    races: {
      human: Object.assign({ label: 'Human', faction: 'Alliance', icon: 'race_human_male', note: '',
        racials: [['Sword Specialization', '+2% crit with spells and attacks while a sword is equipped. Mages can use one-hand swords.', 'ability_meleedamage'],
                  ['The Human Spirit', '+5% Spirit.', 'inv_enchant_shardbrilliantsmall'],
                  ['Will to Survive', 'Remove stuns. 3 min cooldown.', 'spell_shadow_charm']] }, raceAdvice()),
      gnome: Object.assign({ label: 'Gnome', faction: 'Alliance', icon: 'race_gnome_male', note: '',
        racials: [['Expansive Mind', '+5% max mana. In Classic it was +5% Intellect.', 'inv_enchant_essenceeternallarge'],
                  ['Eureka!', 'Your next 3 damaging abilities cost 10% less mana and deal 10% more damage. 2 min cooldown. Before beta build 70009 the Mage version cut the cost by 50%.', 'inv_gnometoy'],
                  ['Escape Artist', 'Remove slows and roots, then 3 sec of immunity to them. 2 min cooldown.', 'ability_rogue_trip']] }, raceAdvice()),
      skyborne: Object.assign({ label: 'Skyborne', fullName: 'Skyborne High Order', faction: 'Alliance', icon: 'race_skyborne_male',
        note: 'Needs a Heroic or higher pack. The Horde Skyborne, the Windshapers, cannot be Mages.',
        racials: [['Wind Blessed', '+1% haste (cast speed).', 'inv_misc_volatileair'],
                  ['Elemental Insight', '+5% damage against Elementals.', 'achievement_raidprimalist_windelemental'],
                  ['Read Ley Line', 'Health and mana regen +100% for 15 sec, or for 15 min near a ley line. 2 sec cast, 2 min cooldown.', 'ability_mage_incantersabsorbtion']] }, raceAdvice()),
      orc: Object.assign({ label: 'Orc', faction: 'Horde', icon: 'race_orc_male', note: 'New for Mages in Forever.',
        racials: [['Blood Fury', '+10% attack power and spell power for 15 sec. 2 min cooldown.', 'racial_orc_berserkerstrength'],
                  ['Shatter Curse', 'Remove curses and banes, and take 15% less magic damage for 8 sec. 3 min cooldown.', 'spell_nature_removecurse'],
                  ['Hardiness', 'Stuns on you last 20% shorter.', 'inv_helmet_23'],
                  ['Axe Specialization', '+1% crit with an axe. Mages cannot equip axes.', 'inv_axe_02']] }, raceAdvice()),
      undead: Object.assign({ label: 'Undead', faction: 'Horde', icon: 'race_scourge_male', note: '',
        racials: [['Touch of the Grave', 'Caster version: each damaging spell has a 10% chance to drain 5% of your max health from the target, at most once per second.', 'spell_shadow_fingerofdeath'],
                  ['Cannibalize', '7% health and 7% mana every 2 sec for 10 sec, from a humanoid or undead corpse. 2 min cooldown. In Classic it restored health only.', 'ability_racial_cannibalize'],
                  ['Will of the Forsaken', 'Remove charm, fear and sleep. 2 min cooldown.', 'spell_shadow_raisedead']] }, raceAdvice()),
      troll: Object.assign({ label: 'Troll', faction: 'Horde', icon: 'race_troll_male', note: '',
        racials: [['Berserking', '+10% casting and attack speed for 10 sec. 3 min cooldown. A flat 10%: in Classic it scaled from 10 to 30% with missing health.', 'racial_troll_berserk'],
                  ['Beast Slaying', '+5% damage against Beasts.', 'inv_misc_pelt_bear_ruin_02'],
                  ['Rapid Regeneration', 'Regain 50% of max health over a 6 sec channel. 3 min cooldown.', 'ability_racial_regeneratin'],
                  ['Regeneration', 'Health regen +10%, and 10% of it continues in combat.', 'spell_nature_regenerate']] }, raceAdvice()),
    },
    defaultRace: 'human',

    // icons for spells named in the planner's rotation steps and elsewhere
    spellIcons: {
      Frostbolt: 'spell_frost_frostbolt02', Fireball: 'spell_fire_flamebolt', 'Arcane Missiles': 'spell_nature_starfall',
      'Fire Blast': 'spell_fire_fireball', 'Frost Nova': 'spell_frost_frostnova', 'Cone of Cold': 'spell_frost_glacier',
      Blizzard: 'spell_frost_icestorm', 'Arcane Explosion': 'spell_nature_wispsplode', Flamestrike: 'spell_fire_selfdestruct',
      Scorch: 'spell_fire_soulburn', Pyroblast: 'spell_fire_fireball02', 'Arcane Blast': 'spell_arcane_blast',
      'Ice Lance': 'spell_frost_frostblast', 'Frostfire Bolt': 'ability_mage_frostfirebolt', 'Blast Wave': 'spell_holy_excorcism_02',
      Evocation: 'spell_nature_purge', 'Mage Armor': 'spell_magearmor', 'Arcane Intellect': 'spell_holy_magicalsentry',
      Wand: 'ability_shootwand',
    },

    // ---------------------------------------------------------------- dungeons (world data, copied from the Warlock page)
    // name, from, to, zone, home side, new in Forever. New dungeons use published ranges; returning dungeons use an
    // estimate around Forever's recommended level.
    dungeons: [
      ['Ragefire Chasm', 13, 18, 'Orgrimmar', 'Horde', false], ['Hall of Thanes', 13, 18, 'Ironforge', 'Alliance', true],
      ['Ruins of Lordaeron', 15, 20, 'Tirisfal Glades', 'Horde', true], ['The Deadmines', 16, 22, 'Westfall', 'Alliance', false],
      ['Wailing Caverns', 17, 23, 'The Barrens', 'Horde', false], ['Shadowfang Keep', 18, 24, 'Silverpine Forest', 'Horde', false],
      ['Blackfathom Deeps', 22, 28, 'Ashenvale', 'Both', false], ['Stormwind Stockade', 23, 28, 'Stormwind City', 'Alliance', false],
      ['Razorfen Kraul', 24, 30, 'The Barrens', 'Horde', false], ['Excavation Site: Wetlands', 24, 29, 'Wetlands', 'Both', true],
      ['Gnomeregan', 25, 31, 'Dun Morogh', 'Alliance', false], ['City of Dalaran', 28, 33, 'Alterac Mountains', 'Both', true],
      ['Scarlet Monastery', 30, 38, 'Tirisfal Glades', 'Both', false], ['Razorfen Downs', 34, 40, 'The Barrens', 'Horde', false],
      ['Uldaman', 35, 41, 'Badlands', 'Both', false], ['The Drowned City', 35, 40, 'Stranglethorn Vale', 'Both', true],
      ["Krol'dok Stronghold", 40, 45, 'Riverglades', 'Both', true], ["Zul'Farrak", 42, 48, 'Tanaris', 'Both', false],
      ['Maraudon', 42, 48, 'Desolace', 'Both', false], ["The Temple of Atal'Hakkar", 45, 51, 'Swamp of Sorrows', 'Both', false],
      ['Alcaz Prison', 48, 53, 'Dustwallow Marsh', 'Both', true], ['Blackrock Depths', 48, 56, 'Burning Steppes', 'Both', false],
      ['Lower Blackrock Spire', 53, 60, 'Burning Steppes', 'Both', false], ['Upper Blackrock Spire', 55, 60, 'Burning Steppes', 'Both', false],
      ['Dire Maul', 54, 60, 'Feralas', 'Both', false], ['Blackmaw Hold', 55, 60, 'zone unconfirmed', 'Both', true],
      ['Stratholme', 55, 60, 'Eastern Plaguelands', 'Both', false], ['Scholomance', 57, 60, 'Western Plaguelands', 'Both', false],
      ["Shaper's Terrace", 58, 60, "Un'Goro Crater", 'Both', true],
    ],

    // ---------------------------------------------------------------- level planner
    planner: {
      order: [],        // TODO-CONTENT: the leveling model's talent order, [[talent key, points], ...], legal at every level
      respec: null,     // optional { level, label, order }: a respec plan from that level on
      chips: [10, 20, 30, 40, 50, 60],
      // phases: the entry with the highest `from` at or below the level applies. steps are spellIcons names.
      // extra: optional [label, value, sub] shown as a fourth fact (the Warlock card's Pet slot).
      phases: [
        { from: 1, name: TODO, rot: TODO + ': what to press at this level, from the leveling model.', sub: '', steps: [], extra: null },
      ],
      gear: [{ from: 1, text: TODO + ': gear advice by level.' }],
      // Trainer levels by rank (spells/NOTES.md section (b), Wowhead tooltips for Mage Armor and Evocation).
      // Frostbolt rank 11, Fireball rank 12 and Arcane Missiles rank 8 come from tomes and are left out.
      // Talent spells list rank 1 at the talent's earliest level; it comes with the talent point, not the trainer.
      ranks: {
        'Fireball': { levels: [1, 6, 12, 18, 24, 30, 36, 42, 48, 54, 60] },
        'Frostbolt': { levels: [4, 8, 14, 20, 26, 32, 38, 44, 50, 56] },
        'Fire Blast': { levels: [6, 14, 22, 30, 38, 46, 54] },
        'Arcane Missiles': { levels: [8, 16, 24, 32, 40, 48, 56] },
        'Frost Nova': { levels: [10, 26, 40, 54] },
        'Arcane Explosion': { levels: [14, 22, 30, 38, 46, 54] },
        'Flamestrike': { levels: [16, 24, 32, 40, 48, 56] },
        'Blizzard': { levels: [20, 28, 36, 44, 52, 60] },
        'Evocation': { levels: [20] },
        'Scorch': { levels: [22, 28, 34, 40, 46, 52, 58] },
        'Cone of Cold': { levels: [26, 34, 42, 50, 58] },
        'Mage Armor': { levels: [34, 46, 58] },
        'Frostfire Bolt': { levels: [40, 50, 60] },
        'Pyroblast': { levels: [20, 24, 30, 36, 42, 48, 54, 60], talent: 'Pyroblast' },
        'Arcane Blast': { levels: [20, 30, 40, 50, 60], talent: 'ArcaneBlast' },
        'Ice Lance': { levels: [20, 28, 34, 42, 48, 56], talent: 'IceLance' },
        'Blast Wave': { levels: [30, 36, 44, 52, 60], talent: 'BlastWave' },
      },
      tomeNote: 'Frostbolt rank 11, Fireball rank 12 and Arcane Missiles rank 8 come from tomes that drop in the world. Where they drop in Forever is not known yet.',
    },

    // ---------------------------------------------------------------- talent builder
    // presets: [{ id, label, order: [[talent key, points], ...] }], legal at every level. The page plan and the raid
    // model's SPECS are added by the builder itself.
    presets: [],
    builder: {
      gears: [[1, 'Leveling greens'], [2, 'Good gear for the level']],
      hpMults: [0.9, 1.0, 1.1],     // mob health 90%, 100% and 110%: kill time snaps to ticks otherwise
    },

    // ---------------------------------------------------------------- content (TODO-CONTENT until the models land)
    // specCards: [{ name, sub, icon, build: {key: rank}, use, grey }]; the point split, talent list and builder link are generated
    specCards: [
      { name: TODO + ': solo spec', sub: 'Placeholder card', icon: 'spell_frost_frostbolt02',
        build: { ArcaneFocus: 5, ArcaneConcentration: 5, ArcaneGeometry: 1, ArcaneImpact: 3, ImprovedFrostbolt: 5, ElementalPrecision: 5,
          IceShards: 5, Frostbite: 3, PiercingIce: 3, IceLance: 1, IceBlock: 1, Shatter: 3, ColdSnap: 1, FingersOfFrost: 2, WintersChill: 5, IceBarrier: 1 },
        use: TODO + ': what the spec does.',
        grey: 'Placeholder build: the ElliotWood sim\'s Frost test build (14/0/35), not a recommendation.' },
    ],
    // claims: [{ id: 'c-...', group: 'proof' | 'test' | 'bust' | 'known', title, body }]
    claims: [],
    // tests: [{ id: 't1', when: 'Test 1 · Level 20 · beta', title, body }]; the checkbox id is the test id plus 'c'
    tests: [],
    // proof tables: { title, intro, head: [...], rows: [[...], ...], so } and { intro, head, rows, note }
    proof: { rule: null, talentValues: null },

    // text slots, filled into elements with data-text. Supports **bold** and [label](#anchor or https://...). {name} is the class name.
    text: {
      title: 'Forever Mage Lab',
      eyebrow: 'WoW: Forever · Mage · beta data · shell v0.1 · 1 Oct 2026',
      lede: 'What to press, which talents to take and which race to play, at every level from 1 to 60. Built on the Forever beta\'s own spell data, with calculators you can play with.',
      trust: TODO + ': how this was built and checked, with links to [the method](#method) and [the changelog](#changelog).',
      navYou: 'Your {name}',
      youTitle: 'Your {name}',
      onramp: TODO + ': **New to Mages?** A short on-ramp for beginners.',
      glossary: [[TODO, 'The terms this page uses, once the content is written.']],
      verdict: [
        { id: 'v-lvl1', k: 'Leveling, early', body: TODO + ': the early leveling answer.', link: ['#lvl-20', 'Open the planner at level 20'] },
        { id: 'v-lvl2', k: 'Leveling, later', body: TODO + ': the later leveling answer.', link: ['#lvl-40', 'Open the planner at level 40'] },
        { id: 'v-solo', k: 'Solo at 60', body: TODO + ': the solo spec.', link: ['#specs', 'See the solo spec'] },
        { id: 'v-group', k: 'Group at 60', body: TODO + ': the group spec, from the raid model.', link: ['#raid', 'Try the raid calculator'] },
        { id: 'v-race', k: 'Race', body: TODO + ': the race answer.', link: ['#you', 'Compare the races'] },
        { id: 'v-dng', k: 'Dungeons', body: '**The first ones open at level 13.** Every dungeon sits on one level line, filtered to your faction, with the ones that fit your level marked.', link: ['#dungeons', 'See every dungeon by level'] },
      ],
      specsTitle: TODO + ': specs for 60',
      specsIntro: TODO + ': one spec for playing alone, one for groups.',
      specsNote: '',
      raidIntro: TODO + ': what the calculator assumes by default, from the raid model.',
      raidNote: TODO + ': which inputs are untested and how much they move the ranking.',
      limits: '**Limits.** ' + TODO + ': what the models cannot see yet.',
      method: [TODO + ': method, data and review.'],
      changelog: [TODO + ': the first release notes.'],
      sources: [
        '[Wowhead Forever Mage talent calculator](https://www.wowhead.com/forever/talent-calc/mage) and Forever spell tooltips',
        '[ForeverChanges: Mage changes vs Classic](https://foreverchanges.pro/class/mage), talents, spellbook, racials and patch notes',
        '[ElliotWood/Forever sim](https://github.com/ElliotWood/Forever): talent trees, client trait curves and spell data',
        '[Icy Veins: Forever Mage overview](https://www.icy-veins.com/wow-forever/mage-class-overview)',
        '[Warcraft Tavern: Forever Mage guide](https://www.warcrafttavern.com/forever/guides/mage)',
        '[zockify: Forever dungeons by level](https://www.zockify.com/forever/dungeons/)',
      ],
    },
  };

  if (inNode) module.exports = CLASS; else root.CLASS = CLASS;
})(this);

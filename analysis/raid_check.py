"""Random-roll check of the raid model (the Mage version of the Warlock's des_check).

For each spec it takes the plan the expected-value model chose (which spells, which ranks, how much of each,
Evocation or not, Fire Vulnerability upkeep or not) and plays it out cast by cast with real dice: hit, crit, Hot
Streak, Missile Barrage, Fingers of Frost, Clearcasting, Master of Elements, Winter's Chill stacks and ramp, Improved
Scorch stacks, Combustion charges, the rolling Ignite, Arcane Blast stacks, DoT refreshes, Arcane Power and Presence
of Mind windows, Blood Fury, Berserking, Eureka!, Touch of the Grave, the Spellblasting Potion, potions, runes, gems
and 2 s mana ticks. Nothing here reuses the model's expected-value formulas: only its spell data, character stats
(pool, regen, spell power, crit, hit) and its plan.

The player it simulates:
  - priorities as the sim's APLs: Scorch when Fire Vulnerability runs short, Ice Lance while Fingers of Frost is up,
    instant cooldowns when ready (never inside an Arcane Blast cycle), Pyroblast at 3 Hot Streak stacks, Barrage
    Missiles when Barrage is up (after the cycle's spender), Presence of Mind on its spell;
  - the model's opening (its top action from the pull until the first potion), then the plan's fillers: the cheaper
    one by default, the pricier one whenever the baseline stays affordable up to every future potion, gem, rune and
    the end of the fight (with a buffer that grows with the horizon), and the top action to spend mana at the end;
  - the potion before a gem or rune (its 2 min chain must start early), each when the pool has room for its top
    roll, the rune and gem slots in the model's order; Evocation once the pool is low, channelled for as long as the
    shortfall needs (at least the plan's share);
  - a cheaper spell rather than standing still when the pool is empty, and the wand whenever it waits. A plan with
    wand time (idle in the model) waits in IDLE_BLOCK blocks; Spirit regen runs in full once 5 s pass without
    spending mana (the five-second rule), at the casting rate before that. No travel time (the model assumes none).

Run from the repo root: python analysis/raid_check.py [fights] [spec ...] [option=value ...]
"""
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'models'))
import raid_model as R  # noqa: E402

TICK = 2.0
FIVE_SEC = R.FIVE_SEC      # full Spirit regen once 5 s pass without spending mana (the five-second rule)
IDLE_BLOCK = R.IDLE_BLOCK  # a player waits out mana in blocks, wanding, as the model assumes
BUFFER = 100.0     # mana held back per sqrt(second) to the next income, against runs of bad luck


class Fight:
    def __init__(self, o, tal, res, rng):
        self.o, self.tal, self.res, self.rng = o, tal, res, rng
        self.r = lambda k: tal.get(k, 0) or 0
        self.T = float(R.opt(o, 'fightLength'))
        # character stats without the fight-averaged buffs (those are simulated here)
        base = R.context(dict(o, race='none' if R.opt(o, 'race') in ('orc', 'troll') else R.opt(o, 'race'),
                              potion='mana' if R.opt(o, 'potion') == 'blast' else R.opt(o, 'potion')),
                         tal, res['fv'], res['state'])
        self.S = base
        self.sp0 = float(R.opt(o, 'sp'))
        self.race = R.opt(o, 'race')
        self.fire_ok = not R.opt(o, 'fireImmune')
        self.max_mana = base['max_mana']
        self.mana = self.max_mana
        self.t = 0.0
        self.next_tick = TICK
        self.dmg = 0.0
        self.parts = {}
        self.cd = {}
        self.aura = {}             # name -> expiry
        self.fv = 0
        self.wc = 0
        self.hs = 0
        self.ab = 0
        self.fof = 0
        self.cc = False
        self.cc_last = -9.0
        self.totg_last = -9.0
        self.comb = None           # [stacks, crits] while active
        self.pom = False
        self.eureka = 0
        self.dots = {}             # key -> [next tick time, ticks left, per tick, crit, bonus]
        self.ignite = None         # [next tick time, ticks left, per tick]
        self.evo_until = -1.0
        self.gem_i = 0
        self.last_spend = -FIVE_SEC
        self.idle_until = -1.0
        self.wand_time = 0.0
        # the rune and gem slots in the model's order (it takes the better of runes only and Ruby first)
        self.slots = [kind for _, _, kind in res['items'] if kind != 'potion']
        self.slot_i = 0
        self.casts = {}
        self.wait = 0.0
        self.evos = 0
        self.plan_setup()

    # ------------------------------------------------------------ plan
    def plan_setup(self):
        """Fillers: the cheapest by mana per second is the baseline B; the other is the upgrade A. A capped
        action below its cap is an upgrade too. An upgrade is cast when the mana now plus the income still to
        come covers B for the rest of the fight (spend early, so potions and gems go out on cooldown)."""
        ch = self.res['chosen']
        self.fillers = [c for c in ch if c['cap'] is None and c['spec']['kind'] in ('filler', 'cycle', 'idle')]
        self.fillers.sort(key=lambda c: c['m'] / c['t'])
        self.base = self.fillers[0] if self.fillers else None
        self.mps_b = self.base['m'] / self.base['t'] if self.base else 0.0
        self.cds = {c['spec']['key']: c for c in ch if c['spec']['kind'] == 'cd'}
        self.cd_count = {k: 0 for k in self.cds}
        self.pom_plan = next((c for c in ch if c['spec']['kind'] == 'pom'), None)
        self.evo_plan = next((c for c in ch if c['spec']['kind'] == 'evo'), None)
        self.evo_able = R.evocation_mana(self.S) > 0     # a player channels it when dry even if the plan did not
        fixed_m = self.res['mana']['fixed']
        fixed_t = self.res.get('fixed_t', 0.0)
        if self.res.get('opening'):     # the opening is spent before the baseline starts
            fixed_m += self.res['opening']['m']
            fixed_t += self.res['opening']['t']
        at_cap = [c for c in ch if c['cap'] is not None and c['x'] >= c['cap'] - 1e-6 and c['spec']['kind'] != 'evo']
        rest = self.T - fixed_t - sum(c['t'] * c['x'] for c in at_cap)
        self.base_rate = (fixed_m + sum(c['m'] * c['x'] for c in at_cap) + rest * self.mps_b) / self.T
        self.cycle = None          # the cycle in progress: its spec
        self.used = [0.0 for _ in self.fillers]
        self.longest = max([self.own_time(c) for c in self.fillers if c['spec']['kind'] == 'filler'] + [R.GCD])
        acts, _ = R.build_actions(self.S)
        unc = [a for a in acts if a['cap'] is None and a['spec']['kind'] in ('filler', 'cycle')]
        best = R.top_action(acts, self.res.get('top'))    # the model's opening action: what it opens room and dumps mana with
        # when behind budget: the best spell that is cheaper per second than the baseline (else the cheapest)
        lower = [a for a in unc if a['m'] / a['t'] < self.mps_b - 1e-9]
        cheap = (max(lower, key=lambda a: a['d'] / a['t']) if lower
                 else (min(unc, key=lambda a: a['m'] / a['t']) if unc else None))
        self.cheap = None
        if cheap is not None:     # what a player casts rather than stand still when the pool runs short
            self.cheap = {'spec': cheap['spec'], 'name': cheap['name'], 'x': 0.0, 'cap': None, 't': cheap['t'],
                          'm': cheap['m'], 'd': cheap['d']}
        self.dump = None
        if best is not None:
            self.dump = {'spec': best['spec'], 'name': best['name'], 'x': 0.0, 'cap': None, 't': best['t'],
                         'm': best['m'], 'd': best['d']}
            for i, f in enumerate(self.fillers):
                if f['spec'] == best['spec']:
                    self.dump['idx'] = i

    def next_slot(self, ahead):
        """What the rune and gem slot `ahead` places from now takes: the model's order, then runes, then gems."""
        i = self.slot_i + ahead
        if i < len(self.slots):
            kind = self.slots[i]
        elif R.opt(self.o, 'runes'):
            kind = 'rune'
        else:
            kind = 'gem'
        gems_used = self.gem_i + sum(1 for k in self.slots[self.slot_i:i] if k == 'gem')
        if kind == 'gem' and (not R.opt(self.o, 'gems') or gems_used >= len(R.GEMS)):
            kind = 'rune' if R.opt(self.o, 'runes') else None
        return kind

    def items_ahead(self, evo=True):
        """Future mana income as (time, mana): potions, gems, runes on their cooldowns, and an unused planned
        Evocation (now: it goes out when the pool has room)."""
        margin = 10.0
        out = []
        if R.opt(self.o, 'potion') == 'mana':
            k = max(self.t, self.cd.get('potion', 0.0))
            while k <= self.T - margin:
                out.append((k, R.POTION_MANA))
                k += R.ITEM_CD
        k = max(self.t, self.cd.get('gem', 0.0))
        gi = self.gem_i
        ahead = 0
        while k <= self.T - margin:
            kind = self.next_slot(ahead)
            if kind == 'gem':
                out.append((k, R.GEMS[gi]))
                gi += 1
            elif kind == 'rune':
                out.append((k, R.RUNE_MANA))
            else:
                break
            ahead += 1
            k += R.ITEM_CD
        if evo and self.evo_plan and self.evos == 0:
            secs = R.EVO_TIME * min(1.0, self.evo_plan['x'])
            out.append((self.t, secs * (R.EVO_MULT * self.S['spirit_regen'] * float(R.opt(self.o, 'evocation'))
                                        + self.S['mp5'] / 5) - secs * self.S['regen_cast']))
        return sorted(out)

    def feasible(self, extra, buffer=True):
        """After spending `extra` more than the baseline now, can the baseline still be paid until every future
        income and to the end of the fight?"""
        net = self.base_rate - self.S['regen_cast']
        cum = self.mana - extra
        for tm, amt in self.items_ahead():
            # a buffer against runs of bad luck (bursts of procced spells), growing with the horizon
            need = BUFFER * math.sqrt(max(0.0, tm - self.t)) if buffer else 0.0
            if cum - net * (tm - self.t) < need:
                return False
            cum += amt
        return cum - net * (self.T - self.t) >= 0

    def can_upgrade(self, c, first_cost):
        """Cast the upgrade c (per use: c['m'] mana over c['t'] seconds) instead of the baseline? Greedy: as
        early as possible (so potions and gems go out on cooldown), as long as the baseline never starves."""
        if self.mana < first_cost:
            return False
        if self.base is not None and self.base['spec']['kind'] == 'idle':
            return True          # spell or wand: when is worth the same, so cast while the mana is there
        return self.feasible(c['m'] - c['t'] * self.mps_b)

    def own_time(self, c):
        sp = c['spec']
        if sp['kind'] == 'idle':
            return 1.0
        if sp['kind'] == 'cycle':
            return (sp['n'] * R.cast_time(self.S, 'arcaneBlast', R.top_row(self.S, 'arcaneBlast'))
                    + R.cast_time(self.S, sp['key'], R.top_row(self.S, sp['key'])))
        row = [rw for rw in R.SPELL_ROWS[sp['key']] if rw[0] == sp['rank']][0]
        if sp['key'] == 'arcaneMissiles':
            return row[9] / 1000.0
        return R.cast_time(self.S, sp['key'], row)

    # ------------------------------------------------------------ time and mana
    def regen_per_tick(self):
        if self.t < self.evo_until:
            return TICK * (R.EVO_MULT * self.S['spirit_regen'] * float(R.opt(self.o, 'evocation')) + self.S['mp5'] / 5)
        if self.t - self.last_spend >= FIVE_SEC:          # outside the five-second rule: full Spirit regen
            return TICK * (self.S['spirit_regen'] + self.S['mp5'] / 5)
        return TICK * self.S['regen_cast']

    def wand_for(self, dt):
        """Shoot the wand for dt seconds (no mana, so the five-second rule keeps running out)."""
        t0 = self.t
        self.advance(dt)
        span = self.t - t0
        if span > 0 and self.S['wand'] > 0:
            self.deal(self.S['wand'] * span, 'Wand')
        self.wand_time += span

    def advance(self, dt):
        end = min(self.T, self.t + dt)
        while True:
            nxt = min([self.next_tick] + [d[0] for d in self.dots.values()] + ([self.ignite[0]] if self.ignite else []))
            if nxt > end:
                break
            self.t = nxt
            if nxt == self.next_tick:
                self.mana = min(self.max_mana, self.mana + self.regen_per_tick())
                self.next_tick += TICK
            for key in list(self.dots):
                d = self.dots[key]
                if d[0] == nxt:
                    crit = self.rng.random() < d[3]
                    self.deal(d[2] * (1 + d[4] if crit else 1), d[6])
                    d[1] -= 1
                    d[0] += d[5]
                    if d[1] <= 0:
                        del self.dots[key]
            if self.ignite and self.ignite[0] == nxt:
                self.deal(self.ignite[2], 'Ignite')
                self.ignite[1] -= 1
                self.ignite[0] += 2.0
                if self.ignite[1] <= 0:
                    self.ignite = None
        self.t = end

    def count(self, label):
        self.casts[label] = self.casts.get(label, 0) + 1

    def deal(self, amount, label):
        if self.t <= self.T:
            self.dmg += amount
            self.parts[label] = self.parts.get(label, 0.0) + amount

    def ready(self, name):
        return self.cd.get(name, 0.0) <= self.t + 1e-9

    def up(self, name):
        return self.aura.get(name, -1.0) > self.t + 1e-9

    # ------------------------------------------------------------ cast mechanics
    def haste(self):
        h = 1.01 if self.race == 'skyborne' else 1.0
        if self.up('berserking'):
            h *= 1.10
        return h

    def spell_power(self):
        sp = self.sp0
        if self.up('blast'):
            sp += R.BLAST_SP
        if self.up('bloodfury'):
            sp *= 1.10
        return sp

    def crit_chance(self, key, sch, frozen):
        r = self.r
        c = self.S['crit']
        if R.fire_ish(sch):
            c += 0.02 * r('CriticalMass')
            if self.comb:
                c += R.COMB_CRIT * self.comb[0]
        if sch == 'arcane':
            c += 0.02 * r('ArcaneImpact')
        if key in ('fireBlast', 'scorch', 'arcaneBlast', 'iceLance'):
            c += 0.02 * r('Incineration')
        if key in ('frostbolt', 'iceLance') and self.up('wc'):
            c += R.WC_PER_STACK * self.wc
        if frozen:
            c += R.AP_TO_SHATTER[r('Shatter')]
        return min(1.0, c)

    def flat(self, sch, stacks):
        r = self.r
        b = 1 + 0.01 * r('ArcaneInstability') + (R.AP_DMG if self.up('ap') else 0.0) + R.AB_STACK_DMG * stacks
        if R.fire_ish(sch):
            b += 0.02 * r('FirePower')
        if R.frost_ish(sch):
            b += 0.02 * r('PiercingIce')
        return b

    def pct(self, sch, binary):
        m = 1.0
        if R.fire_ish(sch) and self.up('fv'):
            m *= 1 + R.FV_PER_STACK * self.fv
        if R.opt(self.o, 'levelResist') and not binary:
            m *= R.LEVEL_RESIST
        return m

    def cost(self, key, row, barrage=False):
        if barrage:
            return 0.0, row[4]
        base = R.AB_COST if key == 'arcaneBlast' else row[4]
        sch = R.SPELL_META[key]['school']
        m = 1 + (R.AP_COST if self.up('ap') else 0.0)
        if R.frost_ish(sch):
            m -= 0.05 * self.r('FrostChanneling')
        if key == 'arcaneBlast':
            m += R.AB_STACK_COST * (self.ab if self.up('ab') else 0)
        c = base * m
        if self.eureka > 0:
            c *= 1 - R.EUREKA
        return c, base

    def cast_secs(self, key, row, pom=False, hs=False):
        if row[3] <= 0 or pom:
            return R.GCD
        sec = row[3] / 1000.0
        if hs:
            sec *= 1 - 0.25 * self.hs
        if key == 'frostbolt':
            sec -= 0.1 * self.r('ImprovedFrostbolt')
        if key in ('fireball', 'frostfire'):
            sec -= 0.1 * self.r('ImprovedFireball')
        return max(R.GCD, sec / self.haste())

    def ab_stacks(self):
        return self.ab if self.up('ab') else 0

    def pay(self, key, row, barrage=False):
        """Mana at cast start. Returns False if the mana is not there."""
        c, base = self.cost(key, row, barrage)
        free = self.cc and base > 0
        if free:
            self.cc = False
            c = 0.0
        if self.mana + 1e-9 < c:
            return None
        self.mana -= c
        return c > 0

    def hit_effects(self, key, row, paid, frozen, stacks_for_damage, mult=1.0, label=None, dot_ticks=True):
        """Roll one hit of `key` and apply everything it triggers. Returns (landed, crit)."""
        meta = R.SPELL_META[key]
        sch = meta['school']
        r = self.r
        h = self.S['h'][sch]
        landed = self.rng.random() < h
        if not landed:
            return False, False
        sp = self.spell_power()
        c = self.crit_chance(key, sch, frozen)
        k = R.crit_bonus(self.S, sch)
        coef = R.coef_of(self.S, key, row, row[7])
        eu = 1 + R.EUREKA if self.eureka > 0 else 1.0
        pc = self.pct(sch, R.is_binary(self.S, key))
        base = (row[6] + coef * sp) * self.flat(sch, stacks_for_damage) * pc * mult * eu
        crit = self.rng.random() < c
        amount = base * (1 + k) if crit else base
        self.deal(amount, label or meta['name'])
        # DoT (reapplying resets it: partial ticks are lost)
        if len(row) >= 12 and dot_ticks:
            label = label or meta['name']
            tcoef = R.coef_of(self.S, key, row, row[11])
            per = (row[8] + tcoef * sp) * self.flat(sch, stacks_for_damage) * pc * eu
            period = row[10] / 1000.0
            self.dots[key] = [self.t + period, row[9], per, c, k, period, label]
        if crit and R.fire_ish(sch) and self.S['ignite'] > 0:
            owed = self.ignite[2] * self.ignite[1] if self.ignite else 0.0
            self.ignite = [self.t + 2.0, 2, (owed + amount * self.S['ignite']) / 2.0]
        if crit and (R.fire_ish(sch) or R.frost_ish(sch)) and paid and r('MasterOfElements'):
            base_cost = row[4]
            self.mana = min(self.max_mana, self.mana + base_cost * 0.10 * r('MasterOfElements'))
        if crit and meta['hs'] and self.S['hs']:
            self.hs = min(3, self.hs + 1)
            self.aura['hs'] = self.t + R.HS_WINDOW
        if self.comb is not None and R.fire_ish(sch):
            self.comb[0] = min(R.COMB_MAX, self.comb[0] + 1)
            if crit:
                self.comb[1] += 1
                if self.comb[1] >= R.COMB_CRITS:
                    self.comb = None
                    self.cd['comb'] = self.t + R.COMB_CD
        if r('ArcaneConcentration') and self.t - self.cc_last >= 1.0 - 1e-9:
            if self.rng.random() < 0.02 * r('ArcaneConcentration'):
                self.cc = True
                self.cc_last = self.t
        if R.frost_ish(sch) and r('WintersChill'):
            if self.rng.random() < 0.2 * r('WintersChill'):
                self.wc = min(r('WintersChill'), (self.wc if self.up('wc') else 0) + 1)
                self.aura['wc'] = self.t + R.WC_WINDOW
        if key == 'scorch' and r('ImprovedScorch'):
            if self.rng.random() < R.ISCORCH[r('ImprovedScorch')]:
                self.fv = min(R.FV_STACKS, (self.fv if self.up('fv') else 0) + 1)
                self.aura['fv'] = self.t + 30.0
        if self.race == 'undead' and self.t - self.totg_last >= 1.0 - 1e-9 and self.rng.random() < R.TOTG_CHANCE:
            self.totg_last = self.t
            self.deal(R.TOTG_HP * float(R.opt(self.o, 'maxHp')), 'Racial')
        return True, crit

    def cast(self, key, row, pom=False, hs=False, barrage=False, label=None):
        """Cast one spell (not Missiles). Returns False if there was not enough mana."""
        frozen = self.fof > 0 and self.up('fof')
        secs = self.cast_secs(key, row, pom=pom, hs=hs)
        paid = self.pay(key, row)
        if paid is None:
            return False
        stacks = self.ab_stacks() if key != 'arcaneBlast' else 0
        self.advance(secs)
        if paid:
            self.last_spend = self.t          # mana is taken as the cast completes
        if self.t >= self.T:
            return True
        mult = R.IL_FROZEN if (key == 'iceLance' and frozen) else 1.0
        self.count(label or R.SPELL_META[key]['name'])
        landed, crit = self.hit_effects(key, row, paid, frozen, stacks, mult=mult, label=label)
        self.after_cast(key, landed, frozen)
        return True

    def after_cast(self, key, landed, frozen):
        r = self.r
        meta = R.SPELL_META[key]
        if frozen:
            self.fof -= 1
        if meta['chill'] and landed and self.S['fof'] and self.rng.random() < R.FOF_CHANCE:
            self.fof = self.S['fof']
            self.aura['fof'] = self.t + 15.0
        if meta['mb'] > 0 and self.S['mb'] > 0 and self.rng.random() < meta['mb'] * self.S['mb']:
            self.aura['mb'] = self.t + 15.0
        if key == 'pyroblast':
            self.hs = 0
            self.aura['hs'] = -1.0
        if key == 'arcaneBlast':
            self.ab = min(4, self.ab_stacks() + 1)
            self.aura['ab'] = self.t + 8.0
        elif key != 'arcaneMissiles':
            self.ab = 0
            self.aura['ab'] = -1.0
        if self.eureka > 0:
            self.eureka -= 1
        if self.pom and key != 'iceLance' and key != 'fireBlast' and key != 'blastWave':
            pass

    def missiles(self, row, barrage):
        """Arcane Missiles: a missile per second, or per 0.5 s with Barrage; stacks go at the end."""
        if barrage:
            self.aura['mb'] = -1.0
        paid = self.pay('arcaneMissiles', row, barrage=barrage)
        if paid is None:
            return False
        if paid:
            self.last_spend = self.t
        stacks = self.ab_stacks() if self.S['ab_tooltip'] else 0
        frozen = self.fof > 0 and self.up('fof')
        step = 0.5 if barrage else 1.0
        for _ in range(row[8]):
            self.advance(step)
            if self.t >= self.T:
                return True
            self.hit_effects('arcaneMissiles', row, paid, frozen, stacks,
                             label='Arcane Missiles (Barrage)' if barrage else 'Arcane Missiles')
        if frozen:
            self.fof -= 1
        self.ab = 0
        self.aura['ab'] = -1.0
        if self.eureka > 0:
            self.eureka -= 1
        return True

    # ------------------------------------------------------------ the rotation
    def off_gcd(self):
        r = self.r
        if r('ArcanePower') and self.ready('ap'):
            self.aura['ap'] = self.t + R.AP_DUR
            self.cd['ap'] = self.t + R.AP_CD
        if r('Combustion') and self.fire_ok and self.comb is None and self.ready('comb'):
            self.comb = [1, 0]
            self.cd['comb'] = 1e9
        if self.pom_plan and self.ready('pom') and not self.pom:
            self.pom = True
            self.cd['pom'] = self.t + R.POM_CD
        if self.race == 'orc' and self.ready('bloodfury'):
            self.aura['bloodfury'] = self.t + 15.0
            self.cd['bloodfury'] = self.t + 120.0
        if self.race == 'troll' and self.ready('berserking'):
            self.aura['berserking'] = self.t + 10.0
            self.cd['berserking'] = self.t + 180.0
        if self.race == 'gnome' and self.ready('eureka'):
            self.eureka = 3
            self.cd['eureka'] = self.t + R.ITEM_CD
        pot = R.opt(self.o, 'potion')
        if pot == 'blast' and self.ready('potion'):
            self.aura['blast'] = self.t + R.BLAST_DUR
            self.cd['potion'] = self.t + R.ITEM_CD
        if pot == 'mana' and self.ready('potion') and self.max_mana - self.mana >= 2250:
            self.mana += self.rng.uniform(1350, 2250)
            self.cd['potion'] = self.t + R.ITEM_CD
        # the potion first: its 2 min chain must start early for the last one to be spendable; a gem or rune
        # waits while a ready potion still needs the room
        pot_waiting = pot == 'mana' and self.ready('potion') and self.cd.get('potion', 0.0) <= self.T - 10.0
        room = self.max_mana - self.mana - (2250 if pot_waiting else 0.0)
        if self.ready('gem'):
            kind = self.next_slot(0)
            if kind == 'gem':
                g = R.GEMS[self.gem_i]
                if room >= g * R.GEM_ROOM:
                    self.mana += self.rng.uniform(g * 1000 / 1100, g * 1200 / 1100)
                    self.gem_i += 1
                    self.slot_i += 1
                    self.cd['gem'] = self.t + R.ITEM_CD
            elif kind == 'rune' and room >= R.RUNE_MAX:
                self.mana += self.rng.uniform(900, 1500)
                self.slot_i += 1
                self.cd['gem'] = self.t + R.ITEM_CD

    def evo_rate(self):
        """Mana per second of Evocation above the casting regen it replaces."""
        return (R.EVO_MULT * self.S['spirit_regen'] * float(R.opt(self.o, 'evocation')) + self.S['mp5'] / 5
                - self.S['regen_cast'])

    def shortfall(self):
        """How much mana the baseline is short, at its worst point, before each future income and the end."""
        net = self.base_rate - self.S['regen_cast']
        cum = self.mana
        worst = 0.0
        for tm, amt in self.items_ahead(evo=False):
            worst = max(worst, net * (tm - self.t) - cum)
            cum += amt
        return max(worst, net * (self.T - self.t) - cum)

    def evocate(self):
        """Evocation as a player uses it: once the pool is low, after potions and gems have their room, channelled for
        as long as the shortfall ahead needs (at least the plan's share)."""
        if not self.evo_able or not self.ready('evo') or self.evos > 0 or self.t <= 5:
            return False
        rate = self.evo_rate()
        if rate <= 0:
            return False
        short = self.shortfall()
        # only once the pool is really low: a short channel early puts it on its 8 min cooldown before it is needed
        if self.mana >= max(600.0, 0.25 * self.max_mana):
            return False
        planned = R.EVO_TIME * min(1.0, self.evo_plan['x']) if self.evo_plan else 0.0
        secs = min(R.EVO_TIME, max(planned, short / rate, 2.0))
        if self.T - self.t < secs + 10:
            return False
        gain = secs * (rate + self.S['regen_cast'])
        room = self.max_mana - self.mana
        if R.opt(self.o, 'potion') == 'mana' and self.ready('potion') and self.t <= self.T - 10:
            room -= R.POTION_MAX
        if self.ready('gem') and self.next_slot(0) is not None:
            room -= R.RUNE_MAX
        if room < gain:
            return False
        self.cd['evo'] = self.t + R.EVO_CD
        self.evos += 1
        self.evo_until = self.t + secs
        self.advance(secs)          # regen ticks inside the channel run at the Evocation rate
        self.evo_until = -1.0
        return True

    def step(self):
        r = self.r
        self.off_gcd()
        if self.evocate():
            return
        top = lambda key: R.top_row(self.S, key)
        # refresh Fire Vulnerability with 5 s left, or sooner if the longest filler cast would outlast it
        if self.res['fv'] and (not self.up('fv') or self.fv < R.FV_STACKS
                               or self.aura['fv'] - self.t <= max(5.0, self.longest + 2.0)):
            if self.cast('scorch', top('scorch'), label='Scorch (Fire Vulnerability)'):
                return
        # Fingers of Frost charges go to Ice Lance before anything else can spend them
        if self.fof > 0 and self.up('fof'):
            if self.cast('iceLance', top('iceLance'), label='Ice Lance (Fingers)'):
                return
        in_cycle = self.cycle is not None
        # instant cooldowns next (outside an Arcane Blast cycle), then the other procs
        for key, c in self.cds.items():
            if self.ready(key) and not in_cycle:      # not in the middle of an Arcane Blast cycle
                row = top(key)
                want = c['x'] >= c['cap'] - 1e-6 or self.can_upgrade(c, self.cost(key, row)[0])
                if want:
                    cdv = (8.0 - self.r('WakeOfFire')) if key == 'fireBlast' else 45.0
                    if self.cast(key, row):
                        self.cd[key] = self.t + cdv - R.GCD
                        self.cd_count[key] += 1
                        return
        if self.S['hs'] and self.hs >= 3 and self.up('hs'):
            if self.cast('pyroblast', top('pyroblast'), hs=True, label='Pyroblast (Hot Streak)'):
                return
        if self.up('mb') and not in_cycle:
            if self.missiles(top('arcaneMissiles'), True):
                return
        if self.pom and not in_cycle:
            key = self.pom_plan['spec']['key']
            if self.cast(key, top(key), pom=True):
                self.pom = False
                return
        self.filler()

    def opening_left(self):
        """Still in the model's opening: no potion (or, without potions, no gem or rune) has gone out yet."""
        if R.opt(self.o, 'potion') == 'mana':
            return 'potion' not in self.cd
        if R.opt(self.o, 'runes') or R.opt(self.o, 'gems'):
            return 'gem' not in self.cd
        return False

    def needs_room(self):
        """A potion (or, without potions, a rune or gem) is ready but the pool has no room for it yet."""
        if R.opt(self.o, 'potion') == 'mana':
            return self.ready('potion') and self.t <= self.T - 10 and self.max_mana - self.mana < R.POTION_MAX
        more = self.next_slot(0) is not None
        return bool(more) and self.ready('gem') and self.t <= self.T - 10 and self.max_mana - self.mana < R.RUNE_MAX

    def pick(self):
        """The upgrade filler if the budget allows it, else the baseline. The build's fastest spender when a
        potion is waiting for room (the model's item schedule assumes this), or with no income ahead and more
        mana than the plan can spend in time."""
        if self.dump is not None and self.opening_left() and self.first_cost(self.dump) <= self.mana:
            return self.dump.get('idx', -1)     # the model's opening: the top action until the first item goes out
        if self.dump is not None and self.fillers:
            top = max(f['m'] / f['t'] for f in self.fillers)
            late = (not any(tm > self.t + 1e-9 for tm, _ in self.items_ahead())
                    and self.mana > (top - self.S['regen_cast']) * (self.T - self.t))
            if (late or self.needs_room()) and self.can_upgrade(self.dump, self.first_cost(self.dump)):
                return self.dump.get('idx', -1)
        for i in range(len(self.fillers) - 1, 0, -1):
            if self.can_upgrade(self.fillers[i], self.first_cost(self.fillers[i])):
                return i
        return 0

    def first_cost(self, c):
        sp = c['spec']
        if sp['kind'] == 'idle':
            return 0.0
        if sp['kind'] == 'cycle':
            return self.cost('arcaneBlast', R.top_row(self.S, 'arcaneBlast'))[0]
        row = [rw for rw in R.SPELL_ROWS[sp['key']] if rw[0] == sp['rank']][0]
        return self.cost(sp['key'], row)[0]

    def filler(self):
        if self.cycle is not None:
            self.run_cycle()
            return
        if not self.fillers:
            self.wand_for(1.0)
            return
        if self.t < self.idle_until:          # inside a block of waiting out mana
            self.wand_for(min(1.0, self.idle_until - self.t))
            return
        i = self.pick()
        if i >= 0 and self.fillers[i]['spec']['kind'] == 'idle':
            self.idle_until = self.t + IDLE_BLOCK
            self.wand_for(1.0)
            self.used[i] += 1.0
            return
        if i >= 0 and self.first_cost(self.fillers[i]) > self.mana and not self.cc:
            if self.cheap is None or self.first_cost(self.cheap) > self.mana:
                self.wand_for(0.5)
                self.wait += 0.5
                return
            i = -2
        c = self.fillers[i] if i >= 0 else {-1: self.dump, -2: self.cheap}[i]
        t0 = self.t
        sp = c['spec']
        if sp['kind'] == 'idle':
            self.wand_for(1.0)
        elif sp['kind'] == 'cycle':
            self.cycle = dict(sp, idx=max(0, i), start=t0)
            self.run_cycle()
            return
        else:
            row = [rw for rw in R.SPELL_ROWS[sp['key']] if rw[0] == sp['rank']][0]
            label = c['name']
            if sp['key'] == 'arcaneMissiles':
                self.missiles(row, self.up('mb'))
            else:
                self.cast(sp['key'], row, label=label)
        if i >= 0:
            self.used[i] += self.t - t0

    def run_cycle(self):
        cy = self.cycle
        t0 = self.t
        top = lambda key: R.top_row(self.S, key)
        stacks = self.ab_stacks()
        if stacks < cy['n']:
            if not self.cast('arcaneBlast', top('arcaneBlast')):
                self.wand_for(0.5)
                self.wait += 0.5
        elif cy['tooltip'] and self.up('mb'):
            self.missiles(top('arcaneMissiles'), True)
            self.cycle = None
        else:
            if self.cast(cy['key'], top(cy['key']), label=R.SPELL_META[cy['key']]['name'] + ' (stacks)'):
                self.cycle = None
            elif self.cheap is not None and self.first_cost(self.cheap) <= self.mana:
                sp = self.cheap['spec']     # out of mana for the spender: a cheap spell rather than stand still
                row = [rw for rw in R.SPELL_ROWS[sp['key']] if rw[0] == sp['rank']][0]
                self.cast(sp['key'], row, label=self.cheap['name'])
                self.cycle = None
            else:
                self.wand_for(0.5)
                self.wait += 0.5
        self.used[cy['idx']] += self.t - t0

    def run(self):
        while self.t < self.T - 1e-9:
            self.step()
        return self.dmg / self.T


def check(o, tal, fights=1000, seed=1, verbose=False):
    res = R.evaluate(o, tal)
    rng = random.Random(seed)
    vals = []
    parts = {}
    diag = {'casts': {}, 'wait': 0.0, 'end_mana': 0.0, 'evos': 0.0, 'used': None}
    for _ in range(fights):
        f = Fight(o, tal, res, rng)
        vals.append(f.run())
        for k, v in f.parts.items():
            parts[k] = parts.get(k, 0.0) + v / f.T / fights
        for k, v in f.casts.items():
            diag['casts'][k] = diag['casts'].get(k, 0.0) + v / fights
        diag['wait'] += f.wait / fights
        diag['end_mana'] += f.mana / fights
        diag['evos'] += f.evos / fights
        u = [x / max(1e-9, sum(f.used)) for x in f.used]
        diag['used'] = u if diag['used'] is None else [a + b for a, b in zip(diag['used'], u)]
    diag['used'] = [x / fights for x in diag['used']]
    mean = sum(vals) / len(vals)
    sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / (len(vals) - 1))
    return res, mean, sd / math.sqrt(len(vals)), parts, diag


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if '=' not in a]
    fights = int(args[0]) if args else 1000
    ids = args[1:] or [s['id'] for s in R.SPECS]
    o = dict(R.DEFAULTS)
    for kv in [a for a in sys.argv[1:] if '=' in a]:
        k, v = kv.split('=')
        d = R.DEFAULTS[k]
        o[k] = (v == 'true') if isinstance(d, bool) else (type(d)(v) if not isinstance(d, str) else v)
    worst = 0.0
    for sid in ids:
        s = R.spec_by_id(sid)
        res, mean, se, parts, diag = check(o, s['talents'], fights)
        diff = (res['total'] / mean - 1) * 100
        worst = max(worst, abs(diff))
        print('%-24s model %7.1f   dice %7.1f +- %.1f   model - dice %+5.2f%%' % (s['name'], res['total'], mean, se, diff))
        keys = sorted(set(parts) | set(res['parts']), key=lambda k: -res['parts'].get(k, 0.0))
        for k in keys:
            print('     %-32s model %6.1f  dice %6.1f' % (k, res['parts'].get(k, 0.0), parts.get(k, 0.0)))
        print('     casts:', ', '.join('%s %.1f' % kv for kv in sorted(diag['casts'].items())))
        print('     model uses:', ', '.join('%s %.1f' % (c['name'], c['x']) for c in res['chosen']))
        print('     filler time %s; waiting %.1f s; end mana %.0f; evocations %.2f' % (
            [round(x, 3) for x in diag['used']], diag['wait'], diag['end_mana'], diag['evos']))
    print('worst gap %.2f%%' % worst)

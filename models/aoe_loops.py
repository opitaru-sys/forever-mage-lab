"""The AoE model's decision loops, the pull driver that runs them, and the scoring (models/aoe.py has the spell
data and the pull mechanics, and serves this module's scoring as aoe.run_pull, aoe.best_pull and so on).

Each archetype is a priority list read whenever the Mage is free: choose_nb, choose_blizzard, choose_ae, choose_fs,
choose_cone (CHOOSE), with loop variants in aoe.POLICIES. Decisions read the pack by weight (scan, edge), not by its
extremes. stop_channel decides when to break off Blizzard. simulate runs one pull: mechanics from aoe, one decision a
step. per_kill, run_pull and best_pull turn pulls into seconds per kill; baseline is the single-target model.
docs/aoe-model.md describes every loop. Either module may be imported first.
"""
from aoe import (AE_RADIUS, ARCH_MAIN, BW_RADIUS, BZ_RADIUS, DT, ETA_MIN, FS_RANGE, LEAD, MAX_T, NEAR, OUTRUN,
                 POLICIES, POTION_CD, Pull, aim_bz, aoe_talents, attacks, cast, char_opts, edge, gather, land, live,
                 merge, move, opts, pick_target, ready, reap, slow_at, spare, speed, spell_consts, take_target, ticks,
                 weight, within)
import leveling_sim as ls
from character import HP_MULTS, evaluate, make_char, mob_hp
from leveling_paths import PLANNER, build
from leveling_sim import FIN_BELOW


# ---------------------------------------------------------------- where the pack will be
def arrival(P, c):
    """Seconds until cohort c reaches melee reach: frozen time left, then its chill, then full speed."""
    t, v = P.t, P.ch.mob_speed
    gap = c.x - P.m - P.reach
    if gap <= 0:
        return 0.0
    now, done = t + max(0.0, c.hold - t), 0.0
    for sl, until in ((c.cs, c.cu), (c.cs2, c.cu2)):
        if until <= now:
            continue
        vs = v * (1 - sl)
        if vs * (until - now) >= gap - done:
            return now - t + (gap - done) / max(vs, 1e-9)
        done, now = done + vs * (until - now), until
    return now - t + (gap - done) / v


def eta(P):
    """When the front of the pack (10% of the weight) reaches melee, in seconds from now."""
    tot, cum = weight(P.mobs), 0.0
    for a, c in sorted(((arrival(P, c), c) for c in P.mobs), key=lambda x: x[0]):
        cum += c.w
        if cum >= 0.1 * tot - 1e-12:
            return a
    return 0.0


def bz_cover(P):
    """Weight of the pack a Blizzard cast now would have in its storm at the first tick."""
    cx, dt = aim_bz(P), P.o['bz_first']
    return sum(c.w for c in P.mobs if abs(c.x - speed(P, c, dt) - cx) <= BZ_RADIUS)


# ---------------------------------------------------------------- the loops (one decision whenever the Mage is free)
def scan(P):
    """Alive weight, frozen weight, free weight within melee reach, the pack's near and far edges (10% and 90% of
    the weight) and the frozen part's near edge."""
    t, m, r = P.t, P.m, P.reach
    alive = held = fnear = 0.0
    for c in P.mobs:
        alive += c.w
        if c.hold > t:
            held += c.w
        elif c.x - m <= r + 1e-9:
            fnear += c.w
    frozen = [c for c in P.mobs if c.hold > t]
    return alive, held, fnear, edge(P, P.mobs, 0.1), edge(P, P.mobs, 0.9), edge(P, frozen, 0.1)


def thr(alive):
    """How much free weight in melee the loop reacts to: a whole mob, or 30% of what is left."""
    return min(1.0, 0.3 * alive)


def outrun(P, r=None):
    """Walking away gains ground: under thr() of the free weight within r yd (default: close enough to hit her within
    a second) moves faster than 85% of her speed for the next second. Mobs outside r close in at 1 yd/s at worst
    (reg mobRunSpeed)."""
    t, v, r = P.t, OUTRUN * P.ch.player_speed, P.reach + 3.0 if r is None else r
    if t < P.daze_u and P.daze_p > 0.3:
        return False
    fast = sum(c.w for c in P.mobs if c.hold <= t + 1.0 and c.x - P.m <= r
               and P.ch.mob_speed * (1 - slow_at(c, t + 1.0)) >= v)
    return fast < thr(weight(P.mobs))


def defensive(P):
    """Ice Barrier whenever it is down and ready (if talented); Mana Shield under half health with a mob in melee."""
    o, K = P.o, P.K
    if o['ice_barrier'] and P.pol.get('ib', True) and K['ib'] and P.ib <= 0 and ready(P, 'IceBarrier'):
        return 'IceBarrier'
    if (o['mana_shield'] and K['ms'] and P.ms <= 0 and P.hp < 0.5 * P.ch.max_hp and within(P, P.reach)
            and ready(P, 'ManaShield')):
        return 'ManaShield'
    return None


def finishable(P, k):
    """90% of the pack is within Arcane Explosion's radius and on average at most k expected Explosions from death."""
    ae = P.K['sp'].get('ArcaneExplosion')
    if not k or not ae:
        return False
    ev = ae['x'] * ae['hit'] * (1 + ae['crit'] * (ae['cm'] - 1))
    hp = sum(c.hp * c.w for c in P.mobs) / weight(P.mobs)
    return edge(P, P.mobs, 0.9) <= AE_RADIUS and hp <= k * ev


def aoe_ok(P, name, r, alive):
    """Cast an area spell only when at least thr(alive) mobs are inside its radius."""
    return weight(within(P, r)) >= thr(alive) and ready(P, name)


def melee_answer(P, alive):
    """Free mobs are on the Mage: Frost Nova, else Cone of Cold, else run if they are slowed, else Arcane Explosion."""
    if ready(P, 'FrostNova'):
        return 'FrostNova'
    if aoe_ok(P, 'ConeOfCold', P.K['coc_r'], alive):
        return 'ConeOfCold'
    if outrun(P):
        return 'walk'
    if P.pol.get('blink', True) and slowed(P) and ready(P, 'Blink'):
        return 'Blink'
    return 'ArcaneExplosion' if aoe_ok(P, 'ArcaneExplosion', AE_RADIUS, alive) else 'wait'


def slowed(P):
    """Most of the free weight in melee is slowed by at least 30% for the next 2 s (Blink then buys real time)."""
    t = P.t
    near = [c for c in P.mobs if c.hold <= t and c.x - P.m <= P.reach + 1e-9]
    w = weight(near)
    return w > 0 and sum(c.w for c in near if slow_at(c, t + 2.0) >= 0.3) >= 0.7 * w


def choose_blizzard(P):
    """Nova the stack, walk out to pol step, Blizzard with the rear of the pack just inside the storm's far edge.
    Storm again at once if the pack's front is ETA_MIN seconds away or more (or pol wait is off); if it is closer,
    let it come when Nova will be ready by then, else walk back while the whole pack is slowed (pol kite) or storm
    anyway. Nova, Cone of Cold or Blink when they arrive; Arcane Explosion to finish (pol finish) or when nothing
    else is ready."""
    pol, K = P.pol, P.K
    alive, held, fnear, gmin, gmax, hmin = scan(P)
    far = K['bz_range'] + LEAD * BZ_RADIUS
    target = far - 0.5 if pol['step'] == 'max' else pol['step']
    d = defensive(P)
    if d:
        return d
    if fnear >= thr(alive):
        return melee_answer(P, alive)
    if held >= 0.5 * alive and hmin < target:
        return 'walk'
    if finishable(P, pol['finish']) and ready(P, 'ArcaneExplosion'):
        return 'ArcaneExplosion'
    kite = pol['kite'] and gmin < far - 0.5 and outrun(P, far)
    if bz_cover(P) >= 0.5 * alive and ready(P, 'Blizzard'):
        soon = eta(P)
        if soon >= ETA_MIN or not pol['wait']:
            return 'Blizzard'
        if P.cd['FrostNova'] <= P.t + soon:
            return 'walk' if kite else 'wait'
        return 'walk' if kite else 'Blizzard'
    if kite:
        return 'walk'
    return 'ArcaneExplosion' if aoe_ok(P, 'ArcaneExplosion', AE_RADIUS, alive) else 'wait'


def choose_ae(P):
    """Nova, step to pol gap (inside Arcane Explosion's 10 yd, outside melee), Cone of Cold on cooldown, Explosion."""
    alive, held, fnear, gmin, gmax, hmin = scan(P)
    d = defensive(P)
    if d:
        return d
    if fnear >= thr(alive) and ready(P, 'FrostNova'):
        return 'FrostNova'
    if P.pol['gap'] and held >= 0.5 * alive and fnear < thr(alive) and hmin < P.pol['gap']:
        return 'walk'
    if aoe_ok(P, 'ConeOfCold', P.K['coc_r'], alive):
        return 'ConeOfCold'
    return 'ArcaneExplosion' if aoe_ok(P, 'ArcaneExplosion', AE_RADIUS, alive) else 'wait'


def choose_fs(P):
    """Nova, step to pol gap, Flamestrike on the pack (while no burn is up; with mobs in melee only if pol melee),
    Blast Wave, Arcane Explosion, Cone of Cold."""
    pol = P.pol
    alive, held, fnear, gmin, gmax, hmin = scan(P)
    d = defensive(P)
    if d:
        return d
    if fnear >= thr(alive) and ready(P, 'FrostNova'):
        return 'FrostNova'
    if held >= 0.5 * alive and fnear < thr(alive) and hmin < pol['gap']:
        return 'walk'
    if ((P.burn is None or P.burn['left'] <= 1) and (pol['melee'] or fnear < thr(alive)) and gmin <= FS_RANGE
            and ready(P, 'Flamestrike')):
        return 'Flamestrike'
    if aoe_ok(P, 'BlastWave', BW_RADIUS, alive):
        return 'BlastWave'
    if aoe_ok(P, 'ArcaneExplosion', AE_RADIUS, alive):
        return 'ArcaneExplosion'
    return 'ConeOfCold' if aoe_ok(P, 'ConeOfCold', P.K['coc_r'], alive) else 'wait'


def choose_cone(P):
    """Nova and step back, Cone of Cold when they come in, run while they are slowed, Frostbolt the nearest mob,
    Arcane Explosion to finish."""
    pol = P.pol
    alive, held, fnear, gmin, gmax, hmin = scan(P)
    d = defensive(P)
    if d:
        return d
    if fnear >= thr(alive):
        return melee_answer(P, alive)
    if ((held >= 0.5 * alive and hmin < pol['gap']) or (outrun(P) and gmin < pol['gap'])):
        return 'walk'
    if aoe_ok(P, 'ConeOfCold', P.K['coc_r'], alive):
        return 'ConeOfCold'
    if finishable(P, pol['finish']) and ready(P, 'ArcaneExplosion'):
        return 'ArcaneExplosion'
    return 'Frostbolt' if ready(P, 'Frostbolt') else 'wait'


def choose_nb(P):
    """Small pulls with the planner build. Frostbolt the group from range (it stands unaware until the first spell
    lands); Frost Nova when free mobs come within NEAR of melee reach; step back to pol gap while most of the group is
    frozen; Ice Lance when it out-damages Frostbolt on the target (lance_pays); else Frostbolt, one whole mob at a
    time. Free mobs in melee with Nova down: Cone of Cold and walk while they are slowed (pol cone), Arcane Explosion
    (pol melee), else keep casting in melee. pol fin 'Wand': wand the target once it is under FIN_BELOW of its health
    (the single-target model's finisher)."""
    pol, K, t = P.pol, P.K, P.t
    alive, held, fnear, gmin, gmax, hmin = scan(P)
    d = defensive(P)
    if d:
        return d
    if not P.engaged:
        return 'Frostbolt' if ready(P, 'Frostbolt') else 'wait'
    if held >= 0.5 * alive and hmin < pol['gap'] and fnear < thr(alive):
        return 'walk'
    if lance_pays(P) and ready(P, 'IceLance'):
        return 'IceLance'
    near = weight([c for c in P.mobs if c.hold <= t and c.x - P.m <= min(K['nova_r'], P.reach + NEAR) + 1e-9])
    if near >= thr(alive) and ready(P, 'FrostNova'):
        return 'FrostNova'
    if fnear >= thr(alive):
        if pol['cone'] and aoe_ok(P, 'ConeOfCold', K['coc_r'], alive):
            return 'ConeOfCold'
        if pol['cone'] and outrun(P):
            return 'walk'
        if pol['melee'] and aoe_ok(P, 'ArcaneExplosion', AE_RADIUS, alive):
            return 'ArcaneExplosion'
    if pol.get('fin') == 'Wand' and P.K['wand'] > 0 and target_hp(P) < FIN_BELOW:
        return 'Wand'
    return 'Frostbolt' if ready(P, 'Frostbolt') else 'wait'


CHOOSE = {'nb': choose_nb, 'blizzard': choose_blizzard, 'ae': choose_ae, 'fs': choose_fs, 'cone': choose_cone}


def stop_channel(P):
    """Break off Blizzard when the pack is on the Mage and Frost Nova is ready (reset the loop), or when under 10%
    of the pack is left in or behind the storm. A Cone of Cold alone is not worth the rest of the channel."""
    ch = P.chan
    alive, held, fnear, gmin, gmax, hmin = scan(P)
    if fnear >= thr(alive) and ready(P, 'FrostNova'):
        return True
    return weight([c for c in P.mobs if c.x >= ch['cx'] - BZ_RADIUS]) < 0.1 * alive


# ---------------------------------------------------------------- one pull
def simulate(ch, K, n, H0, arch, pol, o, phase=0.5):
    """One pull of n mobs of H0 health from full health and mana. Returns the fight: T (seconds), killed, dead,
    feasible (all dead, Mage alive and never under the safety floor), end health and mana, damage dealt and taken,
    hits taken, mana spent, casts, potion and gem used, last Frost Nova and Ice Barrier times, runners' finish."""
    P = Pull(ch, K, n, H0, arch, pol, o, phase)
    choose = CHOOSE[arch]
    costs = [K['sp'][s]['cost'] for s in ARCH_MAIN[arch] if s in K['sp']]
    dry, floor = min(costs) if costs else 0.0, o['safety'] * ch.max_hp
    while P.mobs and P.t < MAX_T:
        land(P)
        ticks(P)
        reap(P)
        if not P.mobs:
            break
        move(P)
        attacks(P)
        rate = ch.mreg if P.t >= P.last_spend + 5.0 else ch.mreg * ch.cast_regen
        P.mana = min(ch.max_mana, P.mana + rate * DT)
        P.hp = min(ch.max_hp, P.hp + ch.hreg_combat * DT)
        P.min_hp = min(P.min_hp, P.hp)
        if P.low_t is None and P.hp < floor:
            P.low_t = P.t
        if P.dry_t is None and P.mana + spare(P) < dry:
            P.dry_t, P.dry_hp = P.t, P.hp / ch.max_hp
            P.dry_left = sum(c.w * max(0.0, c.hp) for c in P.mobs) / (n * H0)     # pack health left
        if P.hp <= 0:
            break
        if P.chan and stop_channel(P):
            P.chan = None
        P.walk = False
        if not (P.chan or P.cast):
            a = choose(P)
            if a == 'walk':
                P.walk = True
            elif a == 'Wand':
                wand(P)
            elif a != 'wait':
                cast(P, a)
                reap(P)
        merge(P)
        if P.t + 1e-9 >= len(P.dealt_at) + 1:
            P.dealt_at.append(P.dealt)
        P.t_ev += DT * live(P)
        P.t += DT
    return result(P)


# ---------------------------------------------------------------- single-target helpers the loops read
def wand(P):
    """One step of wand fire at the target mob, as the single-target model's: no mana, no global cooldown, and
    (as there) it does not break freezes."""
    dmg = P.K['wand'] * DT
    if dmg <= 0:
        return
    P.engaged = True
    for c in take_target(P, 0):
        P.dealt += min(dmg, max(0.0, c.hp)) * c.w
        c.hp -= dmg
    P.casts['Wand'] = P.casts.get('Wand', 0.0) + DT * live(P)


def target_hp(P):
    """Health of the next single-target spell's target, as a share of a mob's full health."""
    pick = pick_target(P)
    tot = sum(w for _, w in pick)
    return sum(c.hp * w for c, w in pick) / tot / P.H0 if tot > 0 else 0.0


def frozen_share(P):
    """Share of the next single-target spell's target that is frozen."""
    pick = pick_target(P)
    tot = sum(w for _, w in pick)
    return sum(w for c, w in pick if c.hold > P.t) / tot if tot > 0 else 0.0


def lance_pays(P):
    """Ice Lance beats Frostbolt now: a Fingers of Frost charge is up, or its expected damage per global cooldown on
    the target (x4 and Shatter on the frozen share) is at least Frostbolt's per cast time."""
    sp, K = P.K['sp'], P.K
    if 'IceLance' not in sp or 'Frostbolt' not in sp:
        return False
    if P.fof >= 1.0:
        return True
    il, fb, fs = sp['IceLance'], sp['Frostbolt'], frozen_share(P)
    wc = ls.WC_CRIT * P.wc

    def ev(s, icy):
        return s['x'] * (s['fm'] if icy else 1.0) * (1 + min(1.0, s['crit'] + wc + (K['shatter'] if icy else 0.0))
                                                     * (s['cm'] - 1))
    lance = (fs * ev(il, True) + (1 - fs) * ev(il, False)) / ls.GCD
    bolt = (fs * ev(fb, True) + (1 - fs) * ev(fb, False)) / max(fb['ct'], ls.GCD)
    return lance >= bolt


# ---------------------------------------------------------------- scoring: one pull, then seconds per kill
def result(P):
    ch, K, o = P.ch, P.K, P.o
    killed = not P.mobs
    T, mana = P.t_ev, P.mana
    fb = K['sp'].get('Frostbolt')
    if P.runners and fb:          # each runner is finished with Frostbolts (reg humanoidFlee: "costs a Frostbolt")
        ev = fb['x'] * fb['hit'] * (1 + fb['crit'] * (fb['cm'] - 1))
        casts = sum(w * max(0.0, hp) for w, hp in P.runners) / ev
        T += casts * max(fb['ct'], ls.GCD)
        mana -= casts * fb['cost']
    feasible = killed and P.hp > 0 and P.min_hp >= o['safety'] * ch.max_hp
    return dict(T=T, killed=killed, dead=P.hp <= 0, min_hp=P.min_hp, feasible=feasible, fail=None if feasible else
                fail_mode(P), hp=max(0.0, P.hp), mana=mana, dealt=P.dealt, taken=P.taken, hits=P.hits, spent=P.spent,
                casts=dict(P.casts), pot=P.pot, gem=P.gem, nova_first=P.nova_first, nova_last=P.nova_last,
                ib_first=P.ib_first, ib_last=P.ib_last, last_spend=min(P.last_spend, P.t_ev), dealt_at=P.dealt_at,
                t_all=P.t,
                dry_t=P.dry_t, low_t=P.low_t, dry_hp=P.dry_hp, dry_left=P.dry_left,
                bz_tpm=P.bz_hit / P.bz_pack if P.bz_pack > 0 else None, runners=sum(w for w, hp in P.runners))


def fail_mode(P):
    """Why a pull failed: 'oom' when the Mage ran out of mana for her loop's damage spells before her health first
    fell under the safety floor (or the pull stalled after she ran dry), 'caught' when the pack brought her under
    the floor first, 'stall' when neither happened and the pull was not over in MAX_T seconds."""
    if P.dry_t is not None and (P.low_t is None or P.dry_t <= P.low_t):
        return 'oom'
    return 'caught' if P.low_t is not None or P.hp <= 0 else 'stall'


def per_kill(ch, K, n, res, o, arch=None):
    """Seconds per kill for a pull cycle: fight, gathering (gather(): its first gather0 seconds are the walk, with
    regen as in the single-target model; a group pulled from range is not gathered, only found), rest from
    leveling_sim.rest_solve. A potion or gem used in the fight is not also used in rest, and the cycle cannot repeat
    faster than their 2 min cooldown. With option cd_carry, Frost Nova and Ice
    Barrier must also be ready again when the next pull first uses them: a cycle is at least last use + cooldown -
    first use (Ice Barrier's first use is its cast at the start of the gather). Without it (the default) they are
    ready at every pull, the single-target model's convention, so both sides of the comparison share it."""
    g = gather(n, o, arch)
    tm, th = ls.travel_regen(ch, res['T'], res['last_spend'], o['gather0'])
    thrill = n * ch.thrill
    gem = [x for x in ls.GEMS if x[0] <= ch.level]
    M = max(0.0, ch.max_mana - res['mana'] - tm - thrill * ch.max_mana + (gem[-1][1] if res['gem'] else 0.0))
    H = max(0.0, ch.max_hp - res['hp'] - th - thrill * ch.max_hp)
    R = ls.rest_setup(ch)
    used = ({'ManaPotion'} if res['pot'] else set()) | ({'ManaGem'} if res['gem'] else set())
    if used:
        R = dict(R, acts=[a for a in R['acts'] if a[0] not in used])
    F = res['T'] + g + (ls.CONJURE_S if res['gem'] else 0.0)
    r = ls.rest_solve(R, F, M, H)
    carry = o['cd_carry']
    nova = res['nova_last'] + K['cd']['FrostNova'] - res['nova_first'] if res['nova_first'] is not None else 0.0
    ib = res['ib_last'] + K['cd']['IceBarrier'] - res['ib_first'] if res['ib_first'] is not None else 0.0
    floor = max(nova if carry else 0.0, ib if carry else 0.0, POTION_CD if used else 0.0)
    cyc = max(r['spk'], floor)
    return cyc / n, dict(cycle=cyc, rest=cyc - F, uses=r['uses'])


def mean(xs):
    return ls.add_up(xs) / len(xs)


def run_pull(L, n, arch, pol, o=None, gear=1, race='none', tal=None, hp_mults=HP_MULTS):
    """One archetype and loop variant at level L and pull size n, averaged over mob health multiples (the single-
    target model's 0.9, 1.0, 1.1). Feasible only if every multiple is; spk is then seconds per kill."""
    o = opts(o)
    tal = tal if tal is not None else aoe_talents(arch, L)
    ch = make_char(L, tal, gear, race, **dict(char_opts(o), armor=o['aoe_armor']))
    K = spell_consts(ch, o)
    rs = []
    for i, m in enumerate(hp_mults):         # proc phases spread as the single-target model's run_policy does
        res = simulate(ch, K, n, mob_hp(L) * m * o['hp_scale'], arch, pol, o, (2 * i + 1) / (2 * len(hp_mults)))
        spk, extra = per_kill(ch, K, n, res, o, arch)
        res.update(extra, spk=spk)
        rs.append(res)
    out = {key: mean([r[key] for r in rs]) for key in ('spk', 'T', 'rest', 'cycle', 'taken', 'hits', 'spent', 'dealt')}
    failed = [r['fail'] for r in rs if r['fail']]
    out.update(feasible=all(r['feasible'] for r in rs), dead=any(r['dead'] for r in rs),
               fail=failed[0] if failed else None,
               min_hp=min(r['min_hp'] for r in rs) / ch.max_hp, pot=any(r['pot'] for r in rs),
               gem=any(r['gem'] for r in rs), casts=rs[len(rs) // 2]['casts'], pol=pol, n=n, arch=arch, L=L,
               runs=rs)
    if not out['feasible']:
        out['spk'] = None             # a failed pull is never scored
    return out


def better(a, b):
    """Feasible first, then fewer seconds per kill."""
    if b is None:
        return True
    if a['feasible'] != b['feasible']:
        return a['feasible']
    if not a['feasible']:
        return a['min_hp'] > b['min_hp']
    return a['spk'] < b['spk'] - 1e-9


def best_pull(L, n, arch, o=None, **kw):
    """The fastest surviving loop variant (POLICIES) for one archetype, level and pull size, each run with and
    without a potion and gem in the fight (pots): a pull that drinks cannot repeat faster than the 2 min potion
    cooldown, one that does not leaves them to the rest model."""
    best = None
    for pol in POLICIES[arch]:
        for pots in (True, False):
            r = run_pull(L, n, arch, dict(pol, pots=pots), o, **kw)
            if better(r, best):
                best = r
    return best


_BASE = {}


def baseline(L, o=None, gear=1, race='none', tal=None):
    """The single-target model's best rotation for the planner build (or tal) with the same options: (name, result)."""
    o = opts(o)
    co = char_opts(o)
    tal = tal if tal is not None else build(PLANNER, L - 9)
    key = (L, gear, race, o['hp_scale'], tuple(sorted(co.items())), tuple(sorted(tal.items())))
    if key not in _BASE:
        _BASE[key] = evaluate(L, tal, gear, race, hp_mults=tuple(m * o['hp_scale'] for m in HP_MULTS), **co)
    return _BASE[key]


def breakeven(base_spk, rows):
    """From [(n, best_pull result)] sorted by n: the smallest surviving n that beats base_spk, the fastest surviving
    n, and the largest surviving n. Failed pulls never count."""
    ok = [(n, r) for n, r in rows if r['feasible']]
    n_star = next((n for n, r in ok if r['spk'] < base_spk), None)
    best = min(ok, key=lambda x: x[1]['spk']) if ok else None
    return dict(n_star=n_star, best_n=best[0] if best else None, best_spk=best[1]['spk'] if best else None,
                max_safe=max((n for n, r in ok), default=None))

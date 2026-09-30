"""
Insects_invasion.py — invasion test from low initial frequency.

Replicates the model of Insects_batchDS17.py, but starts the biased
(blue) type at low frequency to test whether it can invade a population
dominated by unbiased (red) males.

Scenarios (biased type starting rare):
    A: 2 blue males (1%) + 0 blue females
    B: 2 blue males (1%) + 1 blue female
    C: 10 blue males (5%) + 1 blue female
    D: 10 blue males (5%) + 2 blue females
    E: 50 blue males (25%) + 2 blue females

For each scenario, runs N replicates (default 80). Optionally runs a
label-swapped version of each replicate to verify model symmetry.

Output: CSV with one row per replicate.

Summary report per scenario:
    - fixation fraction of the biased type
    - relative fixation (fixation_fraction / p_initial)  <- key metric
    - mean generation (overall, biased-fixed, unbiased-fixed)

Usage:
    python Insects_invasion.py --replicates 80 --output invasion_results.csv
    python Insects_invasion.py --replicates 80 --swap
    python Insects_invasion.py --replicates 80 --workers 12
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
import time
from multiprocessing import Pool, cpu_count

from pygame.math import Vector2


# ============================================================
# CONSTANTS (match Insects_batchDS17.py)
# ============================================================

WIDTH = 800
HEIGHT = 800

baseAccel = 0.21
pheromoneAccel = 0.65
friction = 0.97

MALE_RADIUS = 4
FEMALE_RADIUS = 7

COPULATIONS_PER_GEN = 50
OFFSPRING_PER_COPULATION = 4

MAX_GENERATIONS_DEFAULT = 1600

TOTAL_MALES = 200
TOTAL_FEMALES = 8

# Global flag: controls label swap for symmetry verification.
LABEL_SWAP = False


# ============================================================
# HELPERS
# ============================================================

def point_in_triangle(p, a, b, c):
    def sign(p1, p2, p3):
        return (p1.x - p3.x) * (p2.y - p3.y) - (p2.x - p3.x) * (p1.y - p3.y)
    d1 = sign(p, a, b)
    d2 = sign(p, b, c)
    d3 = sign(p, c, a)
    has_neg = d1 < 0 or d2 < 0 or d3 < 0
    has_pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (has_neg and has_pos)


def binomial_random(n, p):
    if n <= 0 or p <= 0:
        return 0
    if p >= 1:
        return n
    return sum(1 for _ in range(n) if random.random() < p)


def label_for(biased):
    """Return the string label for a given bias state."""
    if LABEL_SWAP:
        return "vermelho" if biased else "azul"
    return "azul" if biased else "vermelho"


def is_biased(t):
    """Return True if the label corresponds to the biased type."""
    if LABEL_SWAP:
        return t == "vermelho"
    return t == "azul"


# ============================================================
# MALE
# ============================================================

class Male:
    def __init__(self, pos, vel, label):
        self.pos = Vector2(pos)
        self.vel = Vector2(vel)
        self.label = label
        self.active = True

    def update(self, blue_pref_angle, females):
        if not self.active:
            return
        acc = Vector2(0, 0)
        in_trail = False
        for f in females:
            if f.contains_point(self.pos):
                in_trail = True
                to_female = f.pos - self.pos
                if to_female.length() != 0:
                    acc += to_female.normalize() * pheromoneAccel
                break
        if not in_trail:
            if self.vel.length() != 0:
                acc += self.vel.normalize() * baseAccel
            if is_biased(self.label):
                pref = Vector2(math.cos(blue_pref_angle), math.sin(blue_pref_angle))
                cur = self.vel.normalize() if self.vel.length() != 0 else Vector2(1, 0)
                acc += (pref - cur) * 0.05
        self.vel += acc
        self.vel *= friction
        self.pos += self.vel
        self.pos.x %= WIDTH
        self.pos.y %= HEIGHT

    def move_to_new_position(self):
        self.pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
        angle = random.uniform(0, 2 * math.pi)
        self.vel = Vector2(math.cos(angle), math.sin(angle)) * 2


# ============================================================
# FEMALE
# ============================================================

class Female:
    def __init__(self, pos, vel, label):
        self.pos = Vector2(pos)
        self.vel = Vector2(vel)
        self.label = label
        self.copulated_with = []

    def update(self):
        self.pos += self.vel
        self.pos.x %= WIDTH
        self.pos.y %= HEIGHT

    def contains_point(self, point):
        trail_length = 310
        half_angle = math.radians(10)
        if self.vel.length() != 0:
            direction = self.vel.normalize()
        else:
            direction = Vector2(1, 0)
        base_center = self.pos - direction * trail_length
        base_half = trail_length * math.tan(half_angle)
        perp = Vector2(-direction.y, direction.x)
        left = base_center + perp * base_half
        right = base_center - perp * base_half
        return point_in_triangle(point, self.pos, left, right)

    def reset_copulations(self):
        self.copulated_with = []


# ============================================================
# NEXT GENERATION
# ============================================================

def create_next_generation(n1, n2, n3, n4, generation, blue_pref_angle):
    blue_from_pure = n1 * OFFSPRING_PER_COPULATION
    red_from_pure = n2 * OFFSPRING_PER_COPULATION
    total_mixed = n3 + n4
    total_offspring_mixed = total_mixed * OFFSPRING_PER_COPULATION
    mixed_blue = binomial_random(total_offspring_mixed, 0.5) if total_offspring_mixed > 0 else 0
    mixed_red = total_offspring_mixed - mixed_blue
    new_biased_males = blue_from_pure + mixed_blue
    new_unbiased_males = red_from_pure + mixed_red
    new_gen = generation + 1

    if new_biased_males <= 0:
        return None, None, "unbiased", new_gen
    if new_unbiased_males <= 0:
        return None, None, "biased", new_gen

    total = new_biased_males + new_unbiased_males
    p_biased_female = new_biased_males / total if total > 0 else 0.5
    n_biased_females = binomial_random(TOTAL_FEMALES, p_biased_female)
    n_unbiased_females = TOTAL_FEMALES - n_biased_females

    new_males = []
    for _ in range(new_biased_males):
        pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
        vel = Vector2(math.cos(blue_pref_angle), math.sin(blue_pref_angle)) * 2
        new_males.append(Male(pos, vel, label_for(True)))
    for _ in range(new_unbiased_males):
        pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
        a = random.uniform(0, 2 * math.pi)
        vel = Vector2(math.cos(a), math.sin(a)) * 2
        new_males.append(Male(pos, vel, label_for(False)))

    new_females = []
    for _ in range(n_biased_females):
        pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
        vel = Vector2(math.cos(blue_pref_angle), math.sin(blue_pref_angle)) * 2
        new_females.append(Female(pos, vel, label_for(True)))
    for _ in range(n_unbiased_females):
        pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
        a = random.uniform(0, 2 * math.pi)
        vel = Vector2(math.cos(a), math.sin(a)) * 2
        new_females.append(Female(pos, vel, label_for(False)))

    return new_males, new_females, None, new_gen


# ============================================================
# SINGLE SIMULATION
# ============================================================

def run_single(n_biased_males_init, n_biased_females_init, seed, max_generations):
    random.seed(seed)
    blue_pref_angle = random.uniform(0, 2 * math.pi)

    n_unbiased_males_init = TOTAL_MALES - n_biased_males_init
    n_unbiased_females_init = TOTAL_FEMALES - n_biased_females_init

    males = []
    for _ in range(n_biased_males_init):
        pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
        vel = Vector2(math.cos(blue_pref_angle), math.sin(blue_pref_angle)) * 2
        males.append(Male(pos, vel, label_for(True)))
    for _ in range(n_unbiased_males_init):
        pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
        a = random.uniform(0, 2 * math.pi)
        vel = Vector2(math.cos(a), math.sin(a)) * 2
        males.append(Male(pos, vel, label_for(False)))

    females = []
    for _ in range(n_biased_females_init):
        pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
        vel = Vector2(math.cos(blue_pref_angle), math.sin(blue_pref_angle)) * 2
        females.append(Female(pos, vel, label_for(True)))
    for _ in range(n_unbiased_females_init):
        pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
        a = random.uniform(0, 2 * math.pi)
        vel = Vector2(math.cos(a), math.sin(a)) * 2
        females.append(Female(pos, vel, label_for(False)))

    generation = 0
    cop_count = 0
    n1 = n2 = n3 = n4 = 0

    while generation < max_generations:
        for f in females:
            f.update()

        for male in males:
            if not male.active:
                continue
            male.update(blue_pref_angle, females)
            for female in females:
                if (male.pos - female.pos).length() < (MALE_RADIUS + FEMALE_RADIUS):
                    if male not in female.copulated_with:
                        m_b = is_biased(male.label)
                        f_b = is_biased(female.label)
                        if m_b and f_b:
                            n1 += 1
                        elif not m_b and not f_b:
                            n2 += 1
                        elif m_b and not f_b:
                            n3 += 1
                        else:
                            n4 += 1
                        cop_count += 1
                        female.copulated_with.append(male)
                        male.move_to_new_position()
                        break

        if cop_count >= COPULATIONS_PER_GEN:
            new_males, new_females, winner, new_gen = create_next_generation(
                n1, n2, n3, n4, generation, blue_pref_angle
            )
            if winner is not None:
                return winner, new_gen
            males = new_males
            females = new_females
            generation = new_gen
            cop_count = 0
            n1 = n2 = n3 = n4 = 0
            blue_pref_angle = random.uniform(0, 2 * math.pi)
            for f in females:
                f.reset_copulations()
            if generation >= max_generations:
                return "inconclusive", max_generations

    return "inconclusive", max_generations


def _run_task(task):
    (scenario, n_biased_males, n_biased_females, rep, seed,
     swap, max_generations) = task

    # Set the global flag in the worker process.
    global LABEL_SWAP
    LABEL_SWAP = swap

    winner, gen = run_single(n_biased_males, n_biased_females, seed, max_generations)

    # In swap mode, "biased" and "unbiased" labels are internally
    # inverted. The physical winner is still the biased or unbiased
    # type, but the label reported by create_next_generation is
    # "biased" if the biased type won, regardless of LABEL_SWAP.
    # So no further adjustment is needed here.
    return (scenario, n_biased_males, n_biased_females, rep, seed,
            swap, winner, gen)


# ============================================================
# MAIN
# ============================================================

SCENARIOS = [
    ("A_1pct_no_female",    2, 0),
 #   ("B_1pct_one_female",   2, 1),
  #  ("C_5pct_one_female",  10, 1),
   # ("D_5pct_two_females", 10, 2),
    #("E_25pct_two_females", 50, 2),
]


def main():
    parser = argparse.ArgumentParser(description="Invasion test for the insect model.")
    parser.add_argument("--replicates", type=int, default=80,
                        help="Replicates per scenario (default: 80).")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="invasion_results.csv")
    parser.add_argument("--workers", type=int, default=cpu_count())
    parser.add_argument("--swap", action="store_true",
                        help="Also run label-swapped controls (symmetry check).")
    parser.add_argument("--max-generations", type=int, default=MAX_GENERATIONS_DEFAULT)
    args = parser.parse_args()

    n_workers = max(1, min(args.workers, cpu_count()))

    # Build task list.
    tasks = []
    for sc_name, bm, bf in SCENARIOS:
        for rep in range(1, args.replicates + 1):
            seed = args.seed + rep + (abs(hash(sc_name)) % 100000)
            tasks.append((sc_name, bm, bf, rep, seed, False, args.max_generations))
        if args.swap:
            for rep in range(1, args.replicates + 1):
                seed = args.seed + rep + (abs(hash(sc_name)) % 100000)
                tasks.append((sc_name, bm, bf, rep, seed, True, args.max_generations))

    total = len(tasks)

    print("=" * 78)
    print("INVASION TEST — model of Insects_batchDS17.py")
    print("=" * 78)
    print(f"Replicates/scenario:   {args.replicates}")
    print(f"Scenarios:             {len(SCENARIOS)}")
    print(f"Swap controls:         {'yes' if args.swap else 'no'}")
    print(f"Total simulations:     {total}")
    print(f"Max generations:       {args.max_generations}")
    print(f"Workers:               {n_workers} of {cpu_count()} CPUs")
    print(f"Output:                {args.output}")
    print("=" * 78)
    for sc_name, bm, bf in SCENARIOS:
        pct = 100 * bm / TOTAL_MALES
        print(f"  {sc_name:22s}  biased_males={bm:3d} ({pct:5.1f}%)  "
              f"biased_females={bf}")
    print("=" * 78)

    t0 = time.perf_counter()
    done = 0
    results = []

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["scenario", "biased_males_init", "biased_females_init",
                         "p_initial", "repetition", "seed", "label_swap",
                         "winner", "generations"])

        with Pool(processes=n_workers) as pool:
            for row in pool.imap_unordered(_run_task, tasks, chunksize=5):
                sc, bm, bf, rep, seed, swap, winner, gen = row
                p_init = bm / TOTAL_MALES
                writer.writerow([sc, bm, bf, f"{p_init:.4f}",
                                 rep, seed, swap, winner, gen])
                results.append(row)
                done += 1
                if done % 50 == 0:
                    elapsed = time.perf_counter() - t0
                    rate = done / elapsed if elapsed > 0 else 0
                    print(f"  {done}/{total}  ({rate:.1f} rep/s)", flush=True)

    elapsed = time.perf_counter() - t0

    # ------------------------------------------------------------
    # Summary: forward runs only (label_swap == False)
    # ------------------------------------------------------------
    print()
    print("=" * 78)
    print("SUMMARY — biased type starting rare")
    print("=" * 78)
    print(f"{'Scenario':22s}  {'p_init':>7s}  {'n':>4s}  "
          f"{'biased':>7s}  {'frac':>7s}  {'rel_fix':>8s}  "
          f"{'mean_gen':>9s}  {'gen_bi':>7s}  {'gen_un':>7s}")
    print("-" * 78)

    for sc_name, bm, bf in SCENARIOS:
        sub = [r for r in results if r[0] == sc_name and not r[5]]
        n = len(sub)
        n_biased = sum(1 for r in sub if r[6] == "biased")
        frac = n_biased / n if n else 0.0
        p_init = bm / TOTAL_MALES
        rel = frac / p_init if p_init > 0 else float("nan")
        gens_all = [r[7] for r in sub if r[6] in ("biased", "unbiased")]
        gens_bi = [r[7] for r in sub if r[6] == "biased"]
        gens_un = [r[7] for r in sub if r[6] == "unbiased"]
        mean_g = statistics.mean(gens_all) if gens_all else float("nan")
        mean_gb = statistics.mean(gens_bi) if gens_bi else float("nan")
        mean_gu = statistics.mean(gens_un) if gens_un else float("nan")
        n_inc = sum(1 for r in sub if r[6] == "inconclusive")
        print(f"{sc_name:22s}  {p_init:7.4f}  {n:4d}  "
              f"{n_biased:7d}  {frac:7.4f}  {rel:8.3f}  "
              f"{mean_g:9.2f}  {mean_gb:7.2f}  {mean_gu:7.2f}")
        if n_inc > 0:
            print(f"  ({n_inc} inconclusive — not shown)")

    # ------------------------------------------------------------
    # Symmetry check (if --swap)
    # ------------------------------------------------------------
    if args.swap:
        print()
        print("=" * 78)
        print("SYMMETRY CHECK — forward vs label-swapped")
        print("=" * 78)
        for sc_name, bm, bf in SCENARIOS:
            fwd = [r for r in results if r[0] == sc_name and not r[5]]
            swp = [r for r in results if r[0] == sc_name and r[5]]
            n_fwd = len(fwd)
            n_swp = len(swp)
            fwd_biased = sum(1 for r in fwd if r[6] == "biased")
            swp_biased = sum(1 for r in swp if r[6] == "biased")
            fwd_frac = fwd_biased / n_fwd if n_fwd else 0.0
            swp_frac = swp_biased / n_swp if n_swp else 0.0
            diff = abs(fwd_frac - swp_frac)
            print(f"  {sc_name:22s}  forward={fwd_frac:.4f}  "
                  f"swap={swp_frac:.4f}  diff={diff:.4f}")

    print()
    print("=" * 78)
    print("INTERPRETATION")
    print("=" * 78)
    print("  relative_fixation = P(biased fixes) / p_initial")
    print("    ~1  → consistent with neutrality")
    print("    >1  → biased type is favored when rare")
    print("    <1  → biased type is disfavored when rare")
    print("=" * 78)
    print(f"Elapsed: {elapsed:.1f} s")
    print(f"Output:  {args.output}")
    print("=" * 78)


if __name__ == "__main__":
    main()
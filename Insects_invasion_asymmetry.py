"""
Insects_invasion_asymmetry.py

Compare fixation of a rare type when:
    A_blue_rare: 2 blue (biased) males + 198 red males, 0 blue females
    B_red_rare:  2 red (unbiased) males + 198 blue males, 0 red females

Both use the SAME physics (blue = biased, red = unbiased).
Only the initial conditions differ.

The comparison isolates the effect of the directional bias itself:
    - If the bias is neutral when rare: both configs fix the rare type ~1%.
    - If the bias is advantageous when rare: blue_rare > 1%, red_rare < 1%.
    - If the bias is deleterious when rare: blue_rare < 1%, red_rare > 1%.

Usage:
    python Insects_invasion_asymmetry.py --replicates 1000 --workers 12
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


# ============================================================
# MALE
# ============================================================

class Male:
    def __init__(self, pos, vel, is_biased):
        self.pos = Vector2(pos)
        self.vel = Vector2(vel)
        self.is_biased = is_biased
        self.active = True

    def update(self, blue_pref_angle, females):
        if not self.active:
            return
        acc = Vector2(0, 0)
        in_trail = False
        for f in females:
            if f.contains_point(self.pos):
                in_trail = True
                d = f.pos - self.pos
                if d.length() != 0:
                    acc += d.normalize() * pheromoneAccel
                break
        if not in_trail:
            if self.vel.length() != 0:
                acc += self.vel.normalize() * baseAccel
            if self.is_biased:
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
        a = random.uniform(0, 2 * math.pi)
        self.vel = Vector2(math.cos(a), math.sin(a)) * 2


# ============================================================
# FEMALE
# ============================================================

class Female:
    def __init__(self, pos, vel, is_biased):
        self.pos = Vector2(pos)
        self.vel = Vector2(vel)
        self.is_biased = is_biased
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
        new_males.append(Male(pos, vel, True))
    for _ in range(new_unbiased_males):
        pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
        a = random.uniform(0, 2 * math.pi)
        vel = Vector2(math.cos(a), math.sin(a)) * 2
        new_males.append(Male(pos, vel, False))

    new_females = []
    for _ in range(n_biased_females):
        pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
        vel = Vector2(math.cos(blue_pref_angle), math.sin(blue_pref_angle)) * 2
        new_females.append(Female(pos, vel, True))
    for _ in range(n_unbiased_females):
        pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
        a = random.uniform(0, 2 * math.pi)
        vel = Vector2(math.cos(a), math.sin(a)) * 2
        new_females.append(Female(pos, vel, False))

    return new_males, new_females, None, new_gen


# ============================================================
# SINGLE SIMULATION
# ============================================================

def run_single(config, seed, max_generations):
    """
    config: "A_blue_rare" or "B_red_rare"
    """
    random.seed(seed)
    blue_pref_angle = random.uniform(0, 2 * math.pi)

    if config == "A_blue_rare":
        n_biased_males_init = 2
        n_biased_females_init = 0
        rare_type = "biased"
    elif config == "B_red_rare":
        # 2 red (unbiased) males, 198 blue (biased) males
        n_biased_males_init = 198
        n_biased_females_init = 8
        rare_type = "unbiased"
    else:
        raise ValueError(config)

    n_unbiased_males_init = TOTAL_MALES - n_biased_males_init
    n_unbiased_females_init = TOTAL_FEMALES - n_biased_females_init

    males = []
    for _ in range(n_biased_males_init):
        pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
        vel = Vector2(math.cos(blue_pref_angle), math.sin(blue_pref_angle)) * 2
        males.append(Male(pos, vel, True))
    for _ in range(n_unbiased_males_init):
        pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
        a = random.uniform(0, 2 * math.pi)
        vel = Vector2(math.cos(a), math.sin(a)) * 2
        males.append(Male(pos, vel, False))

    females = []
    for _ in range(n_biased_females_init):
        pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
        vel = Vector2(math.cos(blue_pref_angle), math.sin(blue_pref_angle)) * 2
        females.append(Female(pos, vel, True))
    for _ in range(n_unbiased_females_init):
        pos = Vector2(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
        a = random.uniform(0, 2 * math.pi)
        vel = Vector2(math.cos(a), math.sin(a)) * 2
        females.append(Female(pos, vel, False))

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
                        if male.is_biased and female.is_biased:
                            n1 += 1
                        elif not male.is_biased and not female.is_biased:
                            n2 += 1
                        elif male.is_biased and not female.is_biased:
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
                return rare_type, winner, new_gen
            males = new_males
            females = new_females
            generation = new_gen
            cop_count = 0
            n1 = n2 = n3 = n4 = 0
            blue_pref_angle = random.uniform(0, 2 * math.pi)
            for f in females:
                f.reset_copulations()
            if generation >= max_generations:
                return rare_type, "inconclusive", max_generations

    return rare_type, "inconclusive", max_generations


def _run_task(task):
    config, rep, seed, max_gen = task
    rare_type, winner, gen = run_single(config, seed, max_gen)
    return config, rep, seed, rare_type, winner, gen


# ============================================================
# MAIN
# ============================================================

CONFIGS = ["A_blue_rare", "B_red_rare"]


def main():
    parser = argparse.ArgumentParser(description="Asymmetry test: 2 blue vs 2 red.")
    parser.add_argument("--replicates", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="invasion_asymmetry.csv")
    parser.add_argument("--workers", type=int, default=cpu_count())
    parser.add_argument("--max-generations", type=int, default=MAX_GENERATIONS_DEFAULT)
    args = parser.parse_args()

    n_workers = max(1, min(args.workers, cpu_count()))

    tasks = []
    for cfg in CONFIGS:
        for rep in range(1, args.replicates + 1):
            seed = args.seed + rep + (abs(hash(cfg)) % 100000)
            tasks.append((cfg, rep, seed, args.max_generations))

    total = len(tasks)

    print("=" * 78)
    print("ASYMMETRY TEST — 2 biased males vs 2 unbiased males")
    print("=" * 78)
    print(f"Replicates per config: {args.replicates}")
    print(f"Configs:               {len(CONFIGS)}")
    print(f"Total simulations:     {total}")
    print(f"Workers:               {n_workers} of {cpu_count()} CPUs")
    print(f"Output:                {args.output}")
    print("=" * 78)
    print("  A_blue_rare:  2 blue (biased) males + 198 red males, 0 blue females")
    print("  B_red_rare:   2 red (unbiased) males + 198 blue males, 0 red females")
    print("=" * 78)

    t0 = time.perf_counter()
    done = 0
    results = []

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["config", "repetition", "seed", "rare_type",
                         "winner", "generations"])

        with Pool(processes=n_workers) as pool:
            for row in pool.imap_unordered(_run_task, tasks, chunksize=20):
                cfg, rep, seed, rare_type, winner, gen = row
                writer.writerow([cfg, rep, seed, rare_type, winner, gen])
                results.append(row)
                done += 1
                if done % 200 == 0:
                    elapsed = time.perf_counter() - t0
                    rate = done / elapsed if elapsed > 0 else 0
                    print(f"  {done}/{total}  ({rate:.1f} rep/s)", flush=True)

    elapsed = time.perf_counter() - t0

    # ---------------- Summary ----------------
    print()
    print("=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"{'Config':18s}  {'n':>5s}  {'rare_fix':>9s}  "
          f"{'p_init':>7s}  {'rel_fix':>8s}  {'mean_gen':>9s}")
    print("-" * 78)

    summary = {}
    for cfg in CONFIGS:
        sub = [r for r in results if r[0] == cfg]
        n = len(sub)
        rare_fix = sum(1 for r in sub if r[4] == r[3])  # winner == rare_type
        p_init = 2 / TOTAL_MALES  # rare type starts at 1%
        rel = (rare_fix / n) / p_init if p_init > 0 else float("nan")
        gens = [r[5] for r in sub if r[4] in ("biased", "unbiased")]
        mean_g = statistics.mean(gens) if gens else float("nan")
        summary[cfg] = {
            "n": n, "rare_fix": rare_fix, "rel_fix": rel, "mean_gen": mean_g,
        }
        print(f"{cfg:18s}  {n:5d}  {rare_fix:9d}  "
              f"{p_init:7.4f}  {rel:8.3f}  {mean_g:9.2f}")

    # ---------------- Interpretation ----------------
    print()
    print("=" * 78)
    print("INTERPRETATION")
    print("=" * 78)
    rel_a = summary["A_blue_rare"]["rel_fix"]
    rel_b = summary["B_red_rare"]["rel_fix"]
    print(f"  rel_fix(A_blue_rare) = {rel_a:.3f}   (expected ~1.0 if neutral)")
    print(f"  rel_fix(B_red_rare)  = {rel_b:.3f}   (expected ~1.0 if neutral)")
    print()
    if abs(rel_a - 1.0) < 0.15 and abs(rel_b - 1.0) < 0.15:
        print("  → Both ~1. The bias is NEUTRAL when rare (in either direction).")
    elif rel_a > 1.15 and rel_b < 0.85:
        print("  → Asymmetry. The biased type is FAVORED when rare.")
    elif rel_a < 0.85 and rel_b > 1.15:
        print("  → Asymmetry. The biased type is DISFAVORED when rare.")
    else:
        print("  → Inconclusive with this sample size.")
    print("=" * 78)
    print(f"Elapsed: {elapsed:.1f} s")
    print(f"Output:  {args.output}")
    print("=" * 78)


if __name__ == "__main__":
    main()
"""
Insects_null_DS1.py  teste de aleatoriedade da simulacao dos insetos  13 set DS

Null-model comparison for Insects_DS4.py.

Purpose
-------
Provide a stripped-down, purely random counterpart to the full spatial
simulation. In this null model:

- Population: 100 blue males + 100 red males; 4 blue females + 4 red females.
- Each generation:
    * 50 males are drawn WITHOUT replacement.
    * 50 females are drawn WITH replacement (so a female can appear multiple
      times).
    * Each male-female pair produces 4 male descendants.
        - same-color parents  : all 4 descendants inherit that color.
        - different-color     : each descendant independently blue/red (p=1/2).
    * The 8 females of the next generation are produced by drawing 8 parent
      pairs at random (with replacement) from the SAME 50 pairs, and applying
      the same Mendelian rule to each.
- The generation advances, repeat, until one color has ZERO males AND ZERO
  females. That color is extinct; the other is fixed.
- Then a new replicate starts from the same initial condition.

There is NO space, NO movement, NO pheromone, NO preferred direction.
Everything is chance. This is the null model against which the full
simulation should be compared.

Usage
-----
python Insects_null_DS1.py --replicates 5000 --output null_results.csv

Outputs
-------
A CSV with one row per replicate:
    replicate, fixed_color, fixation_generation
And a short summary printed at the end.
"""

from __future__ import annotations

import argparse
import csv
import random
import statistics
import time

# ---------------- Constants (match Insects_DS4.py) ----------------
MALES_PER_GENERATION = 200
FEMALES_PER_GENERATION = 8
COPULATIONS_PER_GENERATION = 50
MALE_OFFSPRING_PER_COPULATION = 4

BLUE = "blue"
RED = "red"


# ---------------- One replicate ----------------
def run_one(seed=None):
    """
    Run one null-model replicate.
    Returns (fixed_color, fixation_generation).
    """
    if seed is not None:
        random.seed(seed)
    else:
        random.seed()

    # Initial population.
    males = [BLUE] * 100 + [RED] * 100        # 200 males total
    females = [BLUE] * 4 + [RED] * 4          # 8 females total

    generation = 1

    while True:
        # --- 50 copulations ---
        # Draw 50 distinct males (without replacement).
        chosen_males = random.sample(males, COPULATIONS_PER_GENERATION)
        # Draw 50 females (with replacement, so a female may appear more than once).
        chosen_females = [random.choice(females) for _ in range(COPULATIONS_PER_GENERATION)]

        # Each pair produces 4 male descendants and remembers the parent pair.
        parent_pairs = []           # (father_color, mother_color) per copulation
        next_male_colors = []
        for f_color, m_color in zip(chosen_males, chosen_females):
            parent_pairs.append((f_color, m_color))
            if f_color == m_color:
                # All four sons inherit the same color.
                next_male_colors.extend([f_color] * MALE_OFFSPRING_PER_COPULATION)
            else:
                # Each son independently drawn.
                for _ in range(MALE_OFFSPRING_PER_COPULATION):
                    next_male_colors.append(
                        BLUE if random.random() < 0.5 else RED
                    )

        # Sanity check: exactly 200 male descendants.
        assert len(next_male_colors) == MALES_PER_GENERATION

        # --- 8 daughters ---
        # Same rule as Insects_DS4.py: pick a parent pair at random (with
        # replacement) from the 50 pairs, apply the Mendelian rule.
        next_female_colors = []
        for _ in range(FEMALES_PER_GENERATION):
            f_color, m_color = random.choice(parent_pairs)
            if f_color == m_color:
                next_female_colors.append(f_color)
            else:
                next_female_colors.append(
                    BLUE if random.random() < 0.5 else RED
                )

        # Advance to the next generation.
        males = next_male_colors
        females = next_female_colors
        generation += 1

        # Check extinction.
        n_blue_m = males.count(BLUE)
        n_red_m = males.count(RED)
        n_blue_f = females.count(BLUE)
        n_red_f = females.count(RED)

        if n_blue_m == 0 and n_blue_f == 0:
            return RED, generation     # blue went extinct, red fixed
        if n_red_m == 0 and n_red_f == 0:
            return BLUE, generation    # red went extinct, blue fixed


# ---------------- Main ----------------
def main():
    parser = argparse.ArgumentParser(
        description="Null model for Insects_DS4.py — purely random copulations."
    )
    parser.add_argument("--replicates", type=int, default=1000,
                        help="Number of independent replicates (default: 1000).")
    parser.add_argument("--seed", type=int, default=None,
                        help="Optional base seed. If omitted, seeds are drawn "
                             "from the system (fresh randomness each run).")
    parser.add_argument("--output", default="null_results.csv",
                        help="CSV output (default: null_results.csv).")
    args = parser.parse_args()

    base_seed = args.seed
    print("=" * 72)
    print("Insects null model — purely random copulations")
    print("=" * 72)
    print(f"Replicates:      {args.replicates}")
    print(f"Base seed:       {base_seed if base_seed is not None else 'random'}")
    print(f"Output:          {args.output}")
    print("=" * 72)

    rows = []
    blue_count = 0
    red_count = 0
    gens_blue = []
    gens_red = []
    gens_all = []

    t0 = time.perf_counter()

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["replicate", "fixed_color", "fixation_generation"])

        for rep in range(1, args.replicates + 1):
            if base_seed is not None:
                seed = base_seed + rep
            else:
                seed = None
            color, gen = run_one(seed=seed)
            writer.writerow([rep, color, gen])
            rows.append((rep, color, gen))

            if color == BLUE:
                blue_count += 1
                gens_blue.append(gen)
            else:
                red_count += 1
                gens_red.append(gen)
            gens_all.append(gen)

            # Light progress every 500 replicates.
            if rep % 500 == 0:
                print(f"  replicate {rep:>5}/{args.replicates}  "
                      f"blue={blue_count}  red={red_count}",
                      flush=True)

    elapsed = time.perf_counter() - t0

    # Summary
    n = args.replicates
    blue_frac = blue_count / n
    red_frac = red_count / n

    print()
    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print(f"Replicates:       {n}")
    print(f"Blue fixed:       {blue_count}   ({blue_frac:.3f})")
    print(f"Red fixed:        {red_count}   ({red_frac:.3f})")
    if gens_all:
        print(f"Mean generation:  {statistics.mean(gens_all):.2f}")
        print(f"Median generation:{statistics.median(gens_all):.2f}")
        if len(gens_all) >= 2:
            print(f"SD generation:    {statistics.stdev(gens_all):.2f}")
        print(f"Min generation:   {min(gens_all)}")
        print(f"Max generation:   {max(gens_all)}")
    if gens_blue:
        print(f"  blue-only mean: {statistics.mean(gens_blue):.2f}")
    if gens_red:
        print(f"  red-only mean:  {statistics.mean(gens_red):.2f}")
    print(f"Total wall time:  {elapsed:.2f} s")
    print(f"Output:           {args.output}")
    print("=" * 72)


if __name__ == "__main__":
    main()
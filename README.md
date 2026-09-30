# Insects-Code

Code and data for the manuscript *"Why are insects attracted to light?"*.

## Files

| File | Description |
|---|---|
| `Insects_DS15.py` | Main agent-based simulation (single run, GUI mode) |
| `Insects_batch_DS17.py` | Batch runner: 54 conditions × 80 replicates = 4,320 simulations |
| `Insects_null_DS1.py` | Null model: 100,000 replicates, no spatial dynamics |
| `Insects_invasion.py` | Invasion test: biased type starting rare (5 scenarios) |
| `Insects_invasion_asymmetry.py` | Asymmetry test: 2 biased vs 2 unbiased males (1,000 reps each) |
| `Insects_single_mutation.py` | Single-mutation invasion (A1/B1, 5,000 replicates each) |
| `null_vs_control_tests.py` | Binomial and two-proportion tests reported in the Methods |
| `Insects_gui.py` | Interactive simulator with parameter sliders |
| `invasion_results.csv` | Raw output of `Insects_invasion.py` |
| `invasion_asymmetry.csv` | Raw output of `Insects_invasion_asymmetry.py` |
| `single_mutation_results.csv` | Raw output of `Insects_single_mutation.py` |

## Reproducing the analysis

Install dependencies:

    pip install numpy scipy matplotlib pygame statsmodels

Run the batch (4,320 simulations):

    python Insects_batch_DS17.py

Run the null model (100,000 replicates):

    python Insects_null_DS1.py --replicates 100000 --output null_results.csv

Run the single-mutation invasion test (10,000 simulations):

    python Insects_single_mutation.py --replicates 5000 --workers 12

Run the statistical tests:

    python null_vs_control_tests.py

## Data availability

All code and data are available in this repository. The batch runner and
the invasion tests use deterministic seeds, so the results are reproducible.

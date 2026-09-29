from scipy.stats import binomtest
from statsmodels.stats.proportion import proportions_ztest

# Null dataset vs 0.5
print("Binomial test, null vs 0.5:", binomtest(50016, 100000, 0.5).pvalue)

# Negative control vs null dataset
count = [233, 50016]
nobs  = [480, 100000]
print("Two-proportion test:", proportions_ztest(count, nobs)[1])
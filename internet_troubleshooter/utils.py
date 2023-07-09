import sys
from statistics import mean, variance


def debug(debug, *args, **kwargs):
    if debug:
        print(*args, **kwargs, file=sys.stderr)


def summarize(values, title="", unit=""):
    if len(values) >= 2:
        return "{0}:\n  Mean: {2:.2f}{1}\n  Variance: {3:.2f}{1}\n  Min: {4:.2f}{1}\n  Max: {5:.2f}{1}".format(
            title, unit, mean(values), variance(values), min(values), max(values)
        )
    else:
        return "{0}: Not enough data.".format(title)

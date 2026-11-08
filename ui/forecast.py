"""Forward-looking estimates (Monte Carlo), built only from this run's recorded numbers plus stated assumptions.
Read-only and deterministic (fixed random seed), so the same inputs always draw the same picture.

1. Token savings from the cascade extractor ("rules first, the language model only when the rules are not sure").
   - Tokens one model call costs: resampled from the 15 per-message token counts recorded in this run.
   - How often the cascade still needs the model: uncertain, so drawn from Beta(1 + 5, 1 + 25), i.e. the sandbox
     result in DESIGN_CARD.md (5 model calls in 30 messages) with a flat prior.
   - Saving = tokens if the model reads every message - tokens the cascade spends.
2. Staff time saved handling disruptions.
   - Actions each message needs and the app's own handling time: resampled from this run (per message).
   - Minutes a person would need per action: an ASSUMPTION (triangular distribution the viewer can change),
     because the dataset has no measured manual times.
   - Saving = manual minutes - the app's handling time.
"""
import numpy as np

SEED = 20261108
CASCADE_CALLS, CASCADE_EVENTS = 5, 30  # sandbox comparison in DESIGN_CARD.md (tests/compare_models.py)


def _q(a):
    return {k: float(np.percentile(a, p)) for k, p in (("p5", 5), ("p25", 25), ("p50", 50), ("p75", 75), ("p95", 95))}


def token_savings(token_counts, volumes, sims=4000):
    """For each future message volume N: percentiles of tokens saved by the cascade versus model-on-every-message."""
    rng = np.random.default_rng(SEED)
    tok = np.asarray([t for t in token_counts if t], dtype=float)
    out = []
    for n in volumes:
        p = rng.beta(1 + CASCADE_CALLS, 1 + CASCADE_EVENTS - CASCADE_CALLS, sims)
        calls = rng.binomial(n, p)
        # sum of n resampled per-message costs ~ normal by the central limit theorem (exact resampling is too slow
        # for 10k-message volumes); same for the cascade's `calls` model calls
        mu, sd = tok.mean(), tok.std(ddof=1)
        full = rng.normal(n * mu, np.sqrt(n) * sd)
        used = rng.normal(calls * mu, np.sqrt(np.maximum(calls, 1)) * sd)
        saved = np.maximum(full - used, 0)
        out.append({"n": int(n), **_q(saved), "share": float(np.median(saved / np.maximum(full, 1)))})
    return out


def time_savings(actions, app_seconds, n_messages, minutes_low, minutes_mode, minutes_high, sims=4000):
    """Distribution of staff hours saved for `n_messages` future messages; returns histogram rows + percentiles."""
    rng = np.random.default_rng(SEED + 1)
    acts = np.asarray(actions, dtype=float)
    secs = np.asarray(app_seconds, dtype=float)
    idx = rng.integers(0, len(acts), size=(sims, n_messages))       # which past message each future one resembles
    per_action = rng.triangular(minutes_low, minutes_mode, minutes_high, size=(sims, 1))
    manual_min = (acts[idx] * per_action).sum(axis=1)
    app_min = secs[idx].sum(axis=1) / 60
    hours = np.maximum(manual_min - app_min, 0) / 60
    counts, edges = np.histogram(hours, bins=40)
    hist = [{"h0": float(edges[i]), "h1": float(edges[i + 1]), "mid": float((edges[i] + edges[i + 1]) / 2),
             "share": float(counts[i] / sims)} for i in range(len(counts))]
    app_hours = float(np.median(app_min) / 60)
    return hist, _q(hours), app_hours

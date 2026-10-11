"""Threshold calibration with FIRMS detections as weak labels (brief §6.5).

Positives are cropland pixels within 150 m of a high- or nominal-confidence VIIRS detection,
sampled at the first valid Sentinel-2 observation up to 6 days after it. A VIIRS pixel is 375 m
wide, so many of these pixels did not burn: recall measured on them is a floor, not the true
recall. Clear negatives are pixels that are obviously not char on the same date.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from affine import Affine

from afterpass.burns import PixelState, Thresholds, observations
from afterpass.sentinel import Scene

plt.switch_backend("Agg")

POSITIVE_RADIUS_M = 150.0
POSITIVE_MAX_AGE = timedelta(days=6)
SAMPLES_PER_DATE = 20_000
MAX_FPR = 0.02
SCORE_TOLERANCE = 0.01
MIN_GAIN = 0.10
FEATURES = ("nbr", "mirbi", "b8a", "dnbr")
CAVEATS = [
    "Positives are weak labels. A VIIRS pixel is 375 m wide, so many pixels within 150 m of a "
    "detection did not burn; recall on them understates recall on real burns.",
    "Clear negatives are defined by NBR and B8A, the same indices the rule tests, so the "
    "false-positive rate on them is optimistic. The visual QA sheet gives the real precision.",
    "Thresholds come from one district and one season.",
]
GRID = {
    "t_nbr": (-0.15, -0.10, -0.05, 0.0, 0.05),
    "t_mirbi": (1.3, 1.4, 1.5, 1.6, 1.7, 1.8),
    "t_nir": (0.14, 0.16, 0.18, 0.20, 0.22, 0.24),
    "t_dnbr": (0.05, 0.10, 0.15, 0.20, 0.25),
}


@dataclass(frozen=True)
class Samples:
    """Feature rows (columns in FEATURES order) for each labelled group."""

    positives: np.ndarray
    negatives: np.ndarray
    background: np.ndarray


def _disc_offsets(radius_px: float) -> tuple[np.ndarray, np.ndarray]:
    reach = int(np.ceil(radius_px)) + 1
    dy, dx = np.mgrid[-reach : reach + 1, -reach : reach + 1]
    return dy.ravel(), dx.ravel()


def clear_negative(nbr: np.ndarray, b8a: np.ndarray) -> np.ndarray:
    """Obviously not char: green crop, or bright straw."""
    return (nbr > 0.3) | ((b8a > 0.25) & (nbr > 0.05))


def collect(
    scenes: Iterable[Scene],
    mask: np.ndarray,
    detections: gpd.GeoDataFrame,
    transform: Affine,
    seed: int = 0,
) -> Samples:
    """Stream the scenes once and sample features for positives, clear negatives and a random
    background of cropland pixels. `detections` are confident VIIRS points in the grid's CRS."""
    rng = np.random.default_rng(seed)
    pixel_m = abs(transform.a)
    dy, dx = _disc_offsets(POSITIVE_RADIUS_M / pixel_m)
    height, width = mask.shape
    state = PixelState(mask.shape)

    # Seconds since the Unix epoch; 0 means "no pending detection" / "never".
    pending_until = np.zeros(mask.shape, np.int64)
    sampled = np.zeros(mask.shape, bool)
    queue = detections.sort_values("acq_dt_utc")
    epoch = pd.Timestamp("1970-01-01", tz="UTC")
    det_time = ((queue["acq_dt_utc"] - epoch) // pd.Timedelta(seconds=1)).to_numpy()
    det_x, det_y = queue.geometry.x.to_numpy(), queue.geometry.y.to_numpy()
    first_label_time = det_time.min() if len(det_time) else 0
    cursor = 0

    groups: dict[str, list[np.ndarray]] = {"positives": [], "negatives": [], "background": []}
    for obs in observations(scenes, mask):
        now = int(obs.scene.acquired.timestamp())
        # Register detections made before this pass.
        while cursor < len(det_time) and det_time[cursor] < now:
            col = (det_x[cursor] - transform.c) / pixel_m
            row = (transform.f - det_y[cursor]) / pixel_m
            rows = np.floor(row).astype(int) + dy
            cols = np.floor(col).astype(int) + dx
            near = np.hypot(rows + 0.5 - row, cols + 0.5 - col) * pixel_m <= POSITIVE_RADIUS_M
            inside = near & (rows >= 0) & (rows < height) & (cols >= 0) & (cols < width)
            rows, cols = rows[inside], cols[inside]
            free = ~sampled[rows, cols] & (pending_until[rows, cols] < det_time[cursor])
            expiry = det_time[cursor] + int(POSITIVE_MAX_AGE.total_seconds())
            pending_until[rows[free], cols[free]] = expiry
            cursor += 1

        drop = state.nbr_drop(obs.scene.day, obs.valid, obs.nbr)
        layers = np.stack([obs.nbr, obs.mirbi, obs.b8a, drop], axis=-1)

        take = obs.valid & (pending_until >= now) & ~sampled
        groups["positives"].append(layers[take])
        sampled |= take
        pending_until[take] = 0

        if now >= first_label_time:
            for name, candidates in (
                ("negatives", obs.valid & clear_negative(obs.nbr, obs.b8a)),
                ("background", obs.valid),
            ):
                index = np.flatnonzero(candidates)
                if len(index) > SAMPLES_PER_DATE:
                    index = rng.choice(index, SAMPLES_PER_DATE, replace=False)
                groups[name].append(layers.reshape(-1, len(FEATURES))[index])
        state.observe(obs.scene.day, obs.valid, obs.nbr)

    return Samples(**{k: np.concatenate(v).astype(np.float32) for k, v in groups.items()})


def flag_rate(rows: np.ndarray, th: Thresholds) -> float:
    """Share of sample rows the full rule would flag. A missing NBR drop never passes."""
    if len(rows) == 0:
        return float("nan")
    nbr, mirbi, b8a, dnbr = rows.T
    fired = (nbr < th.t_nbr) & (mirbi > th.t_mirbi) & (b8a < th.t_nir) & (dnbr > th.t_dnbr)
    return float(fired.mean())


def grid_search(samples: Samples) -> list[dict]:
    """Recall, clear-negative FPR and background flag rate for every threshold combination."""
    results = []
    for values in itertools.product(*GRID.values()):
        th = Thresholds(**dict(zip(GRID.keys(), values, strict=True)))
        results.append(
            {
                "thresholds": th,
                "recall": flag_rate(samples.positives, th),
                "fpr": flag_rate(samples.negatives, th),
                "background": flag_rate(samples.background, th),
            }
        )
    return results


def _score(result: dict) -> float:
    return result["recall"] ** 2 / result["background"]


def best_scoring(results: list[dict]) -> dict:
    """The combination with the best positive-unlabelled score among those under the FPR limit.

    The score is recall squared divided by the background flag rate, a stand-in for precision
    times recall when only positive and unlabelled samples exist (Lee and Liu, 2003). Scores
    within SCORE_TOLERANCE of the best count as ties and the most selective set wins.
    """
    feasible = [r for r in results if r["fpr"] <= MAX_FPR and r["background"] > 0]
    if not feasible:
        raise ValueError("No threshold combination keeps the clear-negative FPR under the limit")
    best = max(_score(r) for r in feasible)
    tied = [r for r in feasible if _score(r) >= best * (1 - SCORE_TOLERANCE)]
    return max(tied, key=lambda r: r["recall"] / r["background"])


def choose(results: list[dict]) -> dict:
    """Pick the threshold set for detection.

    The brief asks for the highest recall with a clear-negative FPR under 2%. Clear negatives
    are defined by the same indices the rule tests, so every combination on the grid passes
    that limit and recall alone would pick the loosest thresholds. Combinations are therefore
    ranked by a positive-unlabelled score (see best_scoring). The labels are weak, so the
    brief's starting thresholds are kept unless the best-scoring set beats them by more than
    MIN_GAIN; a smaller gain is within the noise of the labels and is not a reason to flag
    more area. Detections are reported as a lower bound.
    """
    best = best_scoring(results)
    start = next((r for r in results if r["thresholds"] == Thresholds()), None)
    if (
        start is not None
        and start["fpr"] <= MAX_FPR
        and start["background"] > 0
        and _score(best) <= _score(start) * (1 + MIN_GAIN)
    ):
        return start
    return best


def most_recall(results: list[dict]) -> dict:
    """The brief's literal rule, reported for comparison."""
    feasible = [r for r in results if r["fpr"] <= MAX_FPR]
    return max(feasible, key=lambda r: r["recall"])


def metrics(samples: Samples, th: Thresholds) -> dict[str, float]:
    return {
        "recall_on_firms_positives": round(flag_rate(samples.positives, th), 4),
        "fpr_on_clear_negatives": round(flag_rate(samples.negatives, th), 4),
        "background_flag_rate": round(flag_rate(samples.background, th), 4),
    }


def plot(samples: Samples, chosen: Thresholds, path: Path) -> None:
    """Index distributions for each group with the starting and calibrated thresholds."""
    start = Thresholds()
    panels = (
        ("NBR", 0, (-0.5, 0.8), start.t_nbr, chosen.t_nbr, "char below"),
        ("MIRBI", 1, (0.4, 2.6), start.t_mirbi, chosen.t_mirbi, "char above"),
        ("B8A reflectance", 2, (0.0, 0.5), start.t_nir, chosen.t_nir, "char below"),
        ("NBR drop since last valid pass", 3, (-0.4, 0.8), start.t_dnbr, chosen.t_dnbr, "above"),
    )
    groups = (
        ("Near VIIRS fire (weak positives)", samples.positives, "#FF6B1A"),
        ("Clear negatives", samples.negatives, "#34D399"),
        ("Random cropland", samples.background, "#94A3B8"),
    )
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.5), facecolor="#0B0F14")
    for ax, (title, column, limits, guess, calibrated, side) in zip(axes.flat, panels, strict=True):
        ax.set_facecolor("#0B0F14")
        bins = np.linspace(*limits, 90)
        for label, rows, colour in groups:
            values = rows[:, column]
            ax.hist(
                values[np.isfinite(values)],
                bins=bins,
                density=True,
                histtype="step",
                linewidth=1.6,
                color=colour,
                label=label,
            )
        ax.axvline(guess, color="white", linestyle=":", linewidth=1.2, label="Starting guess")
        ax.axvline(calibrated, color="#FBBF24", linewidth=1.8, label="Calibrated")
        ax.set_title(f"{title}  (threshold {calibrated:g}, {side})", color="white", fontsize=11)
        ax.tick_params(colors="#94A3B8", labelsize=8)
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_color("#334155")
    axes[0, 0].legend(facecolor="#0B0F14", edgecolor="none", labelcolor="white", fontsize=8)
    fig.suptitle(
        "Calibration: index distributions by label group (density)", color="white", fontsize=13
    )
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, facecolor="#0B0F14")
    plt.close(fig)

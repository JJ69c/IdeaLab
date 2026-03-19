"""Convergence tracking for simulation dynamics.

Records per-tick snapshots and detects:
- interest stabilization (are opinions still changing?)
- objection convergence (are the same concerns repeating?)
- polarization (is the population splitting into camps?)
- outcome stability (has the simulation reached a steady state?)
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class TickSnapshot:
    """A frozen picture of population state at the end of a tick."""
    tick: int
    interest_scores: list[float]
    stance_counts: dict[str, int]
    objections: list[str]  # flat list of all objections raised this tick

    @property
    def mean_interest(self) -> float:
        if not self.interest_scores:
            return 0.0
        return sum(self.interest_scores) / len(self.interest_scores)

    @property
    def interest_variance(self) -> float:
        if len(self.interest_scores) < 2:
            return 0.0
        mu = self.mean_interest
        return sum((x - mu) ** 2 for x in self.interest_scores) / len(self.interest_scores)


@dataclass
class ConvergenceState:
    """Tracks convergence signals across ticks."""

    # Stability: is interest still moving?
    interest_stable: bool = False
    interest_delta: float = 0.0       # mean interest change from last tick
    stability_streak: int = 0         # consecutive ticks with |delta| < threshold

    # Polarization: is the population splitting?
    polarization_score: float = 0.0   # 0 = consensus, 1 = fully bimodal
    polarized: bool = False

    # Objection convergence: are concerns concentrating or fragmenting?
    objection_concentration: float = 0.0  # 0 = fragmented, 1 = single dominant objection
    top_objections: list[str] = field(default_factory=list)

    # Overall
    converged: bool = False           # stable + low polarization change

    def to_dict(self) -> dict:
        return {
            "interest_stable": self.interest_stable,
            "interest_delta": round(self.interest_delta, 4),
            "stability_streak": self.stability_streak,
            "polarization_score": round(self.polarization_score, 3),
            "polarized": self.polarized,
            "objection_concentration": round(self.objection_concentration, 3),
            "top_objections": self.top_objections[:5],
            "converged": self.converged,
        }


class ConvergenceTracker:
    """Accumulates per-tick snapshots and computes convergence metrics."""

    STABILITY_THRESHOLD = 0.015  # mean interest must move less than this
    STABILITY_STREAK_REQUIRED = 2  # consecutive stable ticks to declare stable
    POLARIZATION_THRESHOLD = 0.35  # above this → polarized

    def __init__(self):
        self.snapshots: list[TickSnapshot] = []
        self._all_objections: Counter[str] = Counter()
        self.state = ConvergenceState()

    def record_tick(self, tick: int, aware_npcs: list) -> ConvergenceState:
        """Record a snapshot at the end of a tick and update convergence state.

        Args:
            tick: Current tick number.
            aware_npcs: List of NPC objects that are aware of the idea.

        Returns:
            Updated ConvergenceState.
        """
        scores = [n.state.interest_score for n in aware_npcs]
        stances: Counter[str] = Counter()
        tick_objections: list[str] = []

        for n in aware_npcs:
            stances[n.state.stance] += 1
            tick_objections.extend(n.state.objections)

        snap = TickSnapshot(
            tick=tick,
            interest_scores=scores,
            stance_counts=dict(stances),
            objections=tick_objections,
        )
        self.snapshots.append(snap)

        # Accumulate global objections
        for obj in tick_objections:
            self._all_objections[_normalize_objection(obj)] += 1

        self._update_stability(snap)
        self._update_polarization(snap)
        self._update_objection_convergence()
        self._update_overall()

        return self.state

    # -------------------------------------------------------------------
    # Internal computations
    # -------------------------------------------------------------------

    def _update_stability(self, snap: TickSnapshot):
        if len(self.snapshots) < 2:
            self.state.interest_delta = 0.0
            self.state.interest_stable = False
            self.state.stability_streak = 0
            return

        prev = self.snapshots[-2]
        delta = abs(snap.mean_interest - prev.mean_interest)
        self.state.interest_delta = snap.mean_interest - prev.mean_interest

        if delta < self.STABILITY_THRESHOLD:
            self.state.stability_streak += 1
        else:
            self.state.stability_streak = 0

        self.state.interest_stable = (
            self.state.stability_streak >= self.STABILITY_STREAK_REQUIRED
        )

    def _update_polarization(self, snap: TickSnapshot):
        """Detect bimodality in interest scores.

        Uses a simple approach: split at 0.5 and measure how much mass
        is concentrated at the extremes vs the middle.
        """
        if len(snap.interest_scores) < 4:
            self.state.polarization_score = 0.0
            self.state.polarized = False
            return

        low = sum(1 for s in snap.interest_scores if s < 0.35)
        high = sum(1 for s in snap.interest_scores if s > 0.65)
        mid = len(snap.interest_scores) - low - high
        n = len(snap.interest_scores)

        # Polarization = (extreme mass) × (balance between extremes)
        extreme_ratio = (low + high) / n
        if low + high == 0:
            balance = 0.0
        else:
            balance = 1.0 - abs(low - high) / (low + high)

        score = extreme_ratio * balance
        self.state.polarization_score = round(score, 3)
        self.state.polarized = score > self.POLARIZATION_THRESHOLD

    def _update_objection_convergence(self):
        """Measure how concentrated objections are.

        If one objection dominates, concentration is high.
        If many unique objections with similar frequency, it's fragmented.
        """
        if not self._all_objections:
            self.state.objection_concentration = 0.0
            self.state.top_objections = []
            return

        total = sum(self._all_objections.values())
        top_items = self._all_objections.most_common(5)
        self.state.top_objections = [obj for obj, _ in top_items]

        if total == 0:
            self.state.objection_concentration = 0.0
            return

        # Herfindahl-style concentration: sum of squared shares
        shares = [count / total for _, count in self._all_objections.items()]
        hhi = sum(s * s for s in shares)
        # Normalize: 1/N (uniform) → 0, 1.0 (single objection) → 1
        n = len(shares)
        if n <= 1:
            self.state.objection_concentration = 1.0
        else:
            min_hhi = 1.0 / n
            self.state.objection_concentration = round(
                (hhi - min_hhi) / (1.0 - min_hhi), 3
            )

    def _update_overall(self):
        self.state.converged = (
            self.state.interest_stable
            and not self.state.polarized
            and len(self.snapshots) >= 3
        )

    # -------------------------------------------------------------------
    # Summary for report
    # -------------------------------------------------------------------

    def to_report_dict(self) -> dict:
        """Full convergence summary for the simulation report."""
        snapshots_summary = []
        for snap in self.snapshots:
            snapshots_summary.append({
                "tick": snap.tick,
                "mean_interest": round(snap.mean_interest, 3),
                "variance": round(snap.interest_variance, 4),
                "stance_counts": snap.stance_counts,
                "aware_count": len(snap.interest_scores),
            })

        return {
            "final_state": self.state.to_dict(),
            "per_tick": snapshots_summary,
        }


def _normalize_objection(obj: str) -> str:
    """Lowercase and strip punctuation for rough dedup."""
    return obj.lower().strip().rstrip(".")

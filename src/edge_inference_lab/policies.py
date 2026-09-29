"""Equation-guided primal-dual policies, with disclosed implementation choices."""
import math
from dataclasses import dataclass, replace
from typing import Dict

from .economics import ServiceValue
from .network import Network
from .domain import Resolution


@dataclass(frozen=True)
class Policy:
    name: str
    theta: int = 2
    retention: str = "fixed"
    admission: str = "dual"
    preload: bool = True
    no_control: bool = False

    def __post_init__(self):
        if isinstance(self.theta, bool) or not isinstance(self.theta, int) or self.theta < 1:
            raise ValueError("policy.theta: positive integer required")
        if self.retention not in ("fixed", "history") or self.admission not in ("dual", "greedy"):
            raise ValueError("policy: unknown retention/admission")


@dataclass(frozen=True)
class Bounds:
    phi1: float
    phi2: float
    rmax: float
    nmax: float
    a: float
    b: float

    @classmethod
    def from_config(cls, config):
        # Bounds come only from configuration, never observed/test requests.
        prices = [p for rows in config.raw["pricing"]["payments"].values() for tiers in rows.values() for p in tiers]
        resolutions = [r for rows in config.models.values() for r in rows]
        phi1 = max(prices) / min(r.vcpu for r in resolutions)
        network = Network(config)
        max_link = max(r.cost_per_mb for r in network.routes.values()) * config.workload["data_mb"][1]
        max_upload = max(n.upload_cost_per_second * 8 * config.workload["data_mb"][1] / n.upload_mbps for n in config.nodes)
        lower_profit = min(prices) - max(r.cost for r in resolutions) - max_link - max_upload
        phi2 = lower_profit / max(r.vcpu for r in resolutions)
        if not math.isfinite(phi1) or not math.isfinite(phi2) or phi2 <= 0:
            raise ValueError("bounds.phi2: configured global profit lower bound must be positive")
        rmax = max(r.vcpu for r in resolutions) / config.algorithm["resource_unit"]
        nmax = 1 / config.algorithm["concurrency"]  # smallest nonempty existing group has n=1
        a = math.exp(math.log1p(rmax) / rmax)
        b = math.exp(math.log1p(nmax) / nmax)
        if not math.isfinite(a) or not math.isfinite(b) or a <= 1 or b <= 1:
            raise ValueError("bounds: parameter scale makes a/b numerically unusable")
        return cls(phi1, phi2, rmax, nmax, a, b)


@dataclass(frozen=True)
class Candidate:
    mode: str
    node: str
    model: str
    resolution: Resolution
    value: ServiceValue
    score: float = 0

    @property
    def key(self):
        return self.node, self.model, self.resolution.id


class DualState:
    def __init__(self, config, residual, counts, bounds):
        self.config, self.residual, self.counts, self.bounds = config, dict(residual), dict(counts), bounds
        self.alpha = {n.id: 0.0 for n in config.nodes}
        self.beta = {key: 0.0 for key in counts}

    def choose(self, candidates, no_control=False, greedy=False):
        scored = []
        for candidate in candidates:
            if greedy:
                score = candidate.value.profit
            elif candidate.mode == "new":
                score = candidate.value.profit - candidate.resolution.vcpu * self.alpha[candidate.node]
            else:
                score = candidate.value.profit - self.beta[candidate.key]
            if not math.isfinite(score):
                raise ValueError("state: non-finite candidate score")
            scored.append(replace(candidate, score=score))
        if not scored:
            return None
        chosen = min(scored, key=lambda c: (-c.score, c.mode != "existing", c.node, c.resolution.id))
        # Absolute tolerance handles round-off at exact zero, documented in the map.
        if chosen.score <= 1e-12 and not no_control:
            return None
        return chosen

    def update(self, candidate):
        if candidate.mode == "new":
            capacity = self.residual[candidate.node]
            if capacity <= 0:
                raise ValueError("state: cannot update alpha with nonpositive residual")
            ratio = candidate.resolution.vcpu / capacity
            self.alpha[candidate.node] = self.alpha[candidate.node] * (1 + ratio) + self.bounds.phi1 / (self.bounds.a - 1) * ratio
            value = self.alpha[candidate.node]
        else:
            count = self.counts[candidate.key]
            if count < 1:
                raise ValueError("state: cannot update beta for empty existing group")
            denominator = self.config.algorithm["concurrency"] * count
            self.beta[candidate.key] = self.beta[candidate.key] * (1 + 1 / denominator) + candidate.value.profit / ((self.bounds.b - 1) * denominator)
            value = self.beta[candidate.key]
        if not math.isfinite(value):
            raise ValueError("state: non-finite dual value")


def study_policies():
    return [Policy(f"pd_theta_{theta}", theta=theta) for theta in (2, 4, 8, 16)] + [
        Policy("pd_history", retention="history"),
        Policy("no_control_interpretation", no_control=True),
        Policy("no_pre_new_only", preload=False),
        Policy("greedy_hard_cap", admission="greedy"),
    ]

"""Pair labels within model × time block while keeping the base trace fixed."""
import hashlib
import json
import random
from collections import Counter, defaultdict
from dataclasses import asdict, replace

from .domain import Request


def generate_traces(config, seed):
    rng = random.Random(seed)
    settings = config.workload
    base = []
    groups = defaultdict(list)
    for slot in range(settings["slots"]):
        for order in range(settings["requests_per_slot"]):
            model = rng.choice(list(config.models))
            req = Request(f"s{slot:04d}-r{order:05d}", slot, rng.choice(config.nodes).id,
                          model, 0, 0, rng.uniform(*settings["data_mb"]))
            groups[(model, slot // settings["block_slots"])].append(len(base))
            base.append(req)
    result = {name: list(base) for name in ("high_tight", "high_loose", "random", "switch")}
    for (model, _), indices in groups.items():
        rows = config.models[model]
        low, high = min(r.accuracy for r in rows), max(r.accuracy for r in rows)
        nlow = (len(indices) + 1) // 2
        accuracies = [low] * nlow + [high] * (len(indices) - nlow)
        rng.shuffle(accuracies)
        deadlines = [settings["deadline_ms"][0]] * (len(indices) - nlow) + [settings["deadline_ms"][1]] * nlow
        # Same multiset for every scenario, including odd-sized groups.
        ranked = sorted(range(len(indices)), key=lambda j: (accuracies[j], j))
        tight = [0] * len(indices)
        loose = [0] * len(indices)
        for rank, j in enumerate(ranked):
            tight[j] = sorted(deadlines, reverse=True)[rank]
            loose[j] = sorted(deadlines)[rank]
        random_deadlines = rng.sample(deadlines, len(deadlines))
        for j, index in enumerate(indices):
            req = base[index]
            choices = {"high_tight": tight[j], "high_loose": loose[j], "random": random_deadlines[j],
                       "switch": tight[j] if req.slot < settings["switch_slot"] else loose[j]}
            for name, deadline in choices.items():
                result[name][index] = replace(req, min_accuracy=accuracies[j], deadline_ms=deadline)
    validate_pairing(result, settings["block_slots"])
    return result


def validate_pairing(traces, block_slots):
    if not traces or block_slots < 1:
        raise ValueError("pairing: empty traces or invalid block")
    reference = next(iter(traces.values()))
    fixed = [(r.id, r.slot, r.source, r.model, r.data_mb) for r in reference]

    def marginals(rows):
        return Counter((r.model, r.slot // block_slots, r.min_accuracy) for r in rows), Counter(
            (r.model, r.slot // block_slots, r.deadline_ms) for r in rows)

    expected = marginals(reference)
    for name, rows in traces.items():
        if [(r.id, r.slot, r.source, r.model, r.data_mb) for r in rows] != fixed:
            raise ValueError(f"pairing {name}: fixed fields changed")
        if marginals(rows) != expected:
            raise ValueError(f"pairing {name}: block marginal distribution changed")


def trace_hash(requests):
    encoded = json.dumps([asdict(r) for r in requests], sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

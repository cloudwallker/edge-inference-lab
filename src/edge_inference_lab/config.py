"""Validate units and feasible preloaded resource floors before a run."""
import copy
import json
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, Tuple

from .domain import Link, Node, Resolution


def number(value, field, minimum=0, strict=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{field}: expected finite number")
    if value < minimum or (strict and value == minimum):
        raise ValueError(f"{field}: out of range")
    return float(value)


def integer(value, field, minimum=0):
    number(value, field, minimum)
    if int(value) != value:
        raise ValueError(f"{field}: expected integer")
    return int(value)


@dataclass(frozen=True)
class Config:
    nodes: Tuple[Node, ...]
    links: Tuple[Link, ...]
    models: Dict[str, Tuple[Resolution, ...]]
    workload: dict
    algorithm: dict
    seeds: dict
    raw: dict

    @classmethod
    def from_dict(cls, payload):
        if not isinstance(payload, dict):
            raise ValueError("configuration: expected object")
        raw = copy.deepcopy(payload)
        try:
            for key in ("models", "workload", "algorithm", "seeds", "pricing"):
                if not isinstance(raw[key], dict):
                    raise ValueError(f"{key}: expected object")
            nodes = tuple(Node(str(n["id"]),
                               number(n["capacity"], "nodes.capacity", strict=True),
                               number(n["upload_mbps"], "nodes.upload_mbps", strict=True),
                               number(n["upload_cost_per_second"], "nodes.upload_cost_per_second"))
                          for n in raw["nodes"])
            ids = {n.id for n in nodes}
            if not nodes or len(ids) != len(nodes) or any(not n.id for n in nodes):
                raise ValueError("nodes.id: empty or duplicate")
            links = tuple(Link(str(e["source"]), str(e["target"]),
                               number(e["latency_ms_per_mb"], "links.latency_ms_per_mb"),
                               number(e["cost_per_mb"], "links.cost_per_mb")) for e in raw["links"])
            seen = set()
            for link in links:
                key = tuple(sorted((link.source, link.target)))
                if link.source not in ids or link.target not in ids or link.source == link.target or key in seen:
                    raise ValueError("links: unknown node, self link or duplicate")
                seen.add(key)
            reached = {nodes[0].id}
            while True:
                adjacent = {v for e in links if e.source in reached or e.target in reached for v in (e.source, e.target)}
                expanded = reached | adjacent
                if expanded == reached:
                    break
                reached = expanded
            if reached != ids:
                raise ValueError("links: disconnected network")
            models = {}
            for model, rows in raw["models"].items():
                resolutions = []
                for r in rows:
                    accuracy = number(r["accuracy"], "models.accuracy", strict=True)
                    if accuracy > 1:
                        raise ValueError("models.accuracy: must be <= 1")
                    resolutions.append(Resolution(
                        str(r["id"]), accuracy,
                        number(r["vcpu"], "models.vcpu", strict=True),
                        number(r["inference_ms"], "models.inference_ms", strict=True),
                        number(r["init_ms"], "models.init_ms"),
                        number(r["cost"], "models.cost", strict=True)))
                if not model or not resolutions or len({r.id for r in resolutions}) != len(resolutions):
                    raise ValueError("models: empty model or duplicate resolution")
                models[str(model)] = tuple(resolutions)
            if not models:
                raise ValueError("models: cannot be empty")
            workload = raw["workload"]
            for key in ("slots", "requests_per_slot", "block_slots"):
                workload[key] = integer(workload[key], f"workload.{key}", 1)
            workload["switch_slot"] = integer(workload["switch_slot"], "workload.switch_slot")
            if workload["switch_slot"] > workload["slots"] or workload["switch_slot"] % workload["block_slots"]:
                raise ValueError("workload.switch_slot: must align with a block")
            for key in ("data_mb", "deadline_ms"):
                pair = workload[key]
                if len(pair) != 2:
                    raise ValueError(f"workload.{key}: requires [min, max]")
                low, high = (number(x, f"workload.{key}", strict=True) for x in pair)
                if low > high:
                    raise ValueError(f"workload.{key}: min exceeds max")
                workload[key] = [low, high]
            algorithm = raw["algorithm"]
            for key, minimum in (("concurrency", 1), ("floor", 0), ("theta", 1)):
                algorithm[key] = integer(algorithm[key], f"algorithm.{key}", minimum)
            unit = number(algorithm["resource_unit"], "algorithm.resource_unit", strict=True)
            for value in [n.capacity for n in nodes] + [r.vcpu for rows in models.values() for r in rows]:
                if (not math.isfinite(value / unit) or round(value / unit) < 1 or
                        not math.isclose(value / unit, round(value / unit), rel_tol=0, abs_tol=1e-8)):
                    raise ValueError("algorithm.resource_unit: capacities/resources must be integer multiples")
            nodes = tuple(replace(n, capacity=round(n.capacity / unit) * unit) for n in nodes)
            models = {m: tuple(replace(r, vcpu=round(r.vcpu / unit) * unit) for r in rows) for m, rows in models.items()}
            # Canonical saved configuration reflects normalized, actually simulated values.
            for record, node in zip(raw["nodes"], nodes):
                record["capacity"] = node.capacity
            for model, rows in models.items():
                for record, resolution in zip(raw["models"][model], rows):
                    record["vcpu"] = resolution.vcpu
            floor_resource = algorithm["floor"] * sum(r.vcpu for rows in models.values() for r in rows)
            if any(n.capacity < floor_resource for n in nodes):
                raise ValueError("nodes.capacity: cannot fit instance floor")
            pricing = raw["pricing"]
            if not isinstance(pricing["payments"], dict) or set(pricing["payments"]) != set(models):
                raise ValueError("pricing.payments: model keys must exactly match models")
            levels = pricing["deadline_levels_ms"]
            if not levels or any(number(x, "pricing.deadline_levels_ms", strict=True) <= 0 for x in levels):
                raise ValueError("pricing: invalid deadline levels")
            if sorted(set(levels)) != levels:
                raise ValueError("pricing: deadline levels must increase")
            for model, rows in models.items():
                if (not isinstance(pricing["payments"][model], dict) or
                        set(pricing["payments"][model]) != {r.id for r in rows}):
                    raise ValueError("pricing.payments: resolution keys must exactly match models")
                for resolution in rows:
                    prices = pricing["payments"][model][resolution.id]
                    if len(prices) != len(levels):
                        raise ValueError("pricing: wrong number of payment levels")
                    for price in prices:
                        number(price, "pricing.payments", strict=True)
            seeds = raw["seeds"]
            for key in ("development", "test"):
                values = seeds[key]
                if not values or len(values) != len(set(values)):
                    raise ValueError("seeds: empty or duplicate")
                for seed in values:
                    integer(seed, "seeds")
            if set(seeds["development"]) & set(seeds["test"]):
                raise ValueError("seeds: development/test overlap")
        except (KeyError, TypeError) as exc:
            raise ValueError(f"missing or malformed configuration: {exc}") from exc
        return cls(nodes, links, models, workload, algorithm, seeds, raw)


def load_config(path):
    return Config.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

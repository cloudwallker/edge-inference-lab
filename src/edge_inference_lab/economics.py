"""Eq. (1)–(4), with explicit effective bandwidth and user-supplied pricing."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceValue:
    payment: float
    upload_cost: float
    link_cost: float
    inference_cost: float
    profit: float
    delay_ms: float
    accuracy_ok: bool
    deadline_ok: bool


def payment(config, request):
    pricing = config.raw["pricing"]
    rows = sorted(config.models[request.model], key=lambda r: r.accuracy)
    required = next((r for r in rows if r.accuracy >= request.min_accuracy), rows[-1])
    levels = pricing["deadline_levels_ms"]
    tier = next((i for i, limit in enumerate(levels) if request.deadline_ms <= limit), len(levels) - 1)
    return pricing["payments"][request.model][required.id][tier]


def evaluate(config, request, node_id, resolution, route, cold):
    # 1 MB = 8 Mbit; Mbps -> seconds. τ and varphi are per request, not per MB.
    source = next(n for n in config.nodes if n.id == request.source)
    upload_seconds = 8 * request.data_mb / source.upload_mbps
    delay = 1000 * upload_seconds + request.data_mb * route.latency_ms_per_mb + resolution.inference_ms
    if cold:
        delay += resolution.init_ms
    upload = source.upload_cost_per_second * upload_seconds
    link = request.data_mb * route.cost_per_mb
    inference = resolution.cost
    revenue = payment(config, request)
    return ServiceValue(revenue, upload, link, inference, revenue - upload - link - inference,
                        delay, resolution.accuracy >= request.min_accuracy,
                        delay <= request.deadline_ms + 1e-9)

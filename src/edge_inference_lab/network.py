"""Deterministic minimum-delay paths; transmission fees follow that path."""
import heapq
from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    nodes: tuple
    latency_ms_per_mb: float
    cost_per_mb: float


class Network:
    def __init__(self, config):
        adjacency = {n.id: [] for n in config.nodes}
        for link in config.links:
            adjacency[link.source].append((link.target, link.latency_ms_per_mb, link.cost_per_mb))
            adjacency[link.target].append((link.source, link.latency_ms_per_mb, link.cost_per_mb))
        self.routes = {}
        for source in adjacency:
            queue = [(0.0, (source,), 0.0)]
            visited = set()
            while queue:
                delay, path, cost = heapq.heappop(queue)
                node = path[-1]
                if node in visited:
                    continue
                visited.add(node)
                self.routes[(source, node)] = Route(path, delay, cost)
                for target, link_delay, link_cost in adjacency[node]:
                    if target not in visited:
                        heapq.heappush(queue, (delay + link_delay, path + (target,), cost + link_cost))

    def route(self, source, target):
        try:
            return self.routes[(source, target)]
        except KeyError as exc:
            raise ValueError("network: unknown or unreachable node") from exc

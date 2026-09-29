from dataclasses import dataclass


@dataclass(frozen=True)
class Node:
    id: str
    capacity: float
    upload_mbps: float
    upload_cost_per_second: float


@dataclass(frozen=True)
class Link:
    source: str
    target: str
    latency_ms_per_mb: float
    cost_per_mb: float


@dataclass(frozen=True)
class Resolution:
    id: str
    accuracy: float
    vcpu: float
    inference_ms: float
    init_ms: float
    cost: float


@dataclass(frozen=True)
class Request:
    id: str
    slot: int
    source: str
    model: str
    min_accuracy: float
    deadline_ms: float
    data_mb: float

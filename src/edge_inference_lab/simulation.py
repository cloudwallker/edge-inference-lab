"""Slot-frozen online scheduling and an auditable physical instance ledger."""
import math
from collections import defaultdict
from dataclasses import dataclass

from .config import integer, number
from .economics import evaluate, payment
from .network import Network
from .policies import Bounds, Candidate, DualState


@dataclass
class Instance:
    id: str
    node: str
    model: str
    resolution: object
    protected: bool
    idle: int = 0
    uses: int = 0

    @property
    def key(self):
        return self.node, self.model, self.resolution.id


@dataclass
class RunResult:
    events: list


def _validate_requests(config, requests):
    ids = set()
    last_slot = -1
    nodes = {n.id for n in config.nodes}
    for req in requests:
        if not req.id or req.id in ids:
            raise ValueError("requests.id: empty or duplicate")
        ids.add(req.id)
        integer(req.slot, "requests.slot")
        if req.slot < last_slot or req.slot >= config.workload["slots"]:
            raise ValueError("requests.slot: out of range or unordered")
        last_slot = req.slot
        if req.source not in nodes or req.model not in config.models:
            raise ValueError("requests: unknown source/model")
        accuracy = number(req.min_accuracy, "requests.min_accuracy")
        if accuracy > 1:
            raise ValueError("requests.min_accuracy: must be <= 1")
        number(req.deadline_ms, "requests.deadline_ms", strict=True)
        number(req.data_mb, "requests.data_mb", strict=True)
        if not config.workload["data_mb"][0] <= req.data_mb <= config.workload["data_mb"][1]:
            raise ValueError("requests.data_mb: outside configured bounds")


def simulate(config, requests, policy):
    _validate_requests(config, requests)
    network = Network(config)
    bounds = Bounds.from_config(config)
    events, instances = [], []
    L = config.algorithm["concurrency"]
    serial = 0
    history, last_use = defaultdict(list), {}

    def create(slot, node, model, resolution, protected):
        nonlocal serial
        serial += 1
        instance = Instance(f"i{serial:06d}", node, model, resolution, protected)
        instances.append(instance)
        events.append({"kind": "create", "slot": slot, "instance_id": instance.id, "node": node,
                       "model": model, "resolution": resolution.id, "vcpu": resolution.vcpu, "protected": protected})
        return instance

    if policy.preload:
        for node in config.nodes:
            for model, rows in config.models.items():
                for resolution in rows:
                    for _ in range(config.algorithm["floor"]):
                        create(-1, node.id, model, resolution, True)
    cursor = 0
    for slot in range(config.workload["slots"]):
        for instance in instances:
            instance.uses = 0
        existing = defaultdict(list)
        for instance in instances:
            existing[instance.key].append(instance)
        counts = {key: len(rows) for key, rows in existing.items()}
        unit = config.algorithm["resource_unit"]
        occupied_units = {n.id: sum(round(i.resolution.vcpu / unit) for i in instances if i.node == n.id) for n in config.nodes}
        residual = {n.id: (round(n.capacity / unit) - occupied_units[n.id]) * unit for n in config.nodes}
        state = DualState(config, residual, counts, bounds)
        new_groups, x_load, y_load = defaultdict(list), defaultdict(float), defaultdict(int)
        events.append({"kind": "slot_start", "slot": slot, "residual": residual,
                       "existing_counts": {"|".join(k): v for k, v in counts.items()},
                       "new_disabled_nodes": [n for n, value in residual.items() if value <= 0]})
        while cursor < len(requests) and requests[cursor].slot == slot:
            req = requests[cursor]
            cursor += 1
            candidates = []
            accuracy_possible = warm_possible = cold_possible = False
            strict_blocked = False
            for node in config.nodes:
                route = network.route(req.source, node.id)
                for resolution in config.models[req.model]:
                    key = node.id, req.model, resolution.id
                    warm = evaluate(config, req, node.id, resolution, route, False)
                    cold = evaluate(config, req, node.id, resolution, route, True)
                    accuracy_possible |= warm.accuracy_ok
                    warm_possible |= warm.accuracy_ok and warm.deadline_ok
                    cold_possible |= cold.accuracy_ok and cold.deadline_ok
                    if counts.get(key, 0) and warm.accuracy_ok and warm.deadline_ok:
                        if policy.admission == "greedy" and all(i.uses >= L for i in existing[key]):
                            strict_blocked = True
                        else:
                            candidates.append(Candidate("existing", node.id, req.model, resolution, warm))
                    if cold.accuracy_ok and cold.deadline_ok:
                        if policy.admission == "greedy":
                            reusable = any(i.uses < L for i in new_groups[key])
                            live = sum(i.resolution.vcpu for i in instances if i.node == node.id)
                            allowed = reusable or live + resolution.vcpu <= node.capacity + 1e-9
                        else:
                            # Explicit boundary rule: the printed alpha denominator is undefined at C^t<=0.
                            allowed = residual[node.id] > 0
                        if allowed:
                            candidates.append(Candidate("new", node.id, req.model, resolution, cold))
                        else:
                            strict_blocked = True
            chosen = state.choose(candidates, no_control=policy.no_control, greedy=policy.admission == "greedy")
            event = {"kind": "request", "slot": slot, "request_id": req.id, "source": req.source,
                     "model": req.model, "min_accuracy": req.min_accuracy, "deadline_ms": req.deadline_ms,
                     "data_mb": req.data_mb, "potential_payment": payment(config, req),
                     "intrinsically_feasible": warm_possible, "cold_deadline_blocked": warm_possible and not cold_possible,
                     "accepted": chosen is not None, "reason": None, "mode": None, "node": None,
                     "resolution": None, "instance_id": None, "created_now": False,
                     "payment": 0.0, "upload_cost": 0.0, "link_cost": 0.0, "inference_cost": 0.0,
                     "profit": 0.0, "delay_ms": None, "score": None, "qualified": False,
                     "concurrency_excess": 0, "alpha_after": None, "beta_after": None}
            if chosen is None:
                if not accuracy_possible:
                    event["reason"] = "accuracy"
                elif not warm_possible:
                    event["reason"] = "deadline"
                elif not candidates and strict_blocked:
                    event["reason"] = "strict_resource" if policy.admission == "greedy" else "nonpositive_residual"
                elif not candidates:
                    event["reason"] = "cold_deadline_no_instance"
                else:
                    event["reason"] = "admission_control"
            else:
                key = chosen.key
                pool = existing[key] if chosen.mode == "existing" else new_groups[key]
                available = [i for i in pool if i.uses < L]
                if available:
                    instance = min(available, key=lambda i: i.id)
                elif chosen.mode == "existing":
                    # Preserve the printed relaxed policy; record any overflow instead of silently clipping it.
                    instance = min(pool, key=lambda i: (i.uses, i.id))
                else:
                    instance = create(slot, chosen.node, req.model, chosen.resolution, False)
                    new_groups[key].append(instance)
                    event["created_now"] = True
                instance.uses += 1
                if chosen.mode == "new":
                    x_load[chosen.node] += chosen.resolution.vcpu
                else:
                    y_load[key] += 1
                if policy.admission == "dual":
                    state.update(chosen)
                value = chosen.value
                event.update({"mode": chosen.mode, "node": chosen.node, "resolution": chosen.resolution.id,
                              "instance_id": instance.id, "payment": value.payment, "upload_cost": value.upload_cost,
                              "link_cost": value.link_cost, "inference_cost": value.inference_cost,
                              "profit": value.profit, "delay_ms": value.delay_ms, "score": chosen.score,
                              "qualified": value.accuracy_ok and value.deadline_ok,
                              "concurrency_excess": max(0, instance.uses - L),
                              "alpha_after": state.alpha[chosen.node], "beta_after": state.beta.get(key, 0)})
            events.append(event)
        used_groups = {i.key for i in instances if i.uses}
        for key in used_groups:
            if key in last_use:
                history[key].append(slot - last_use[key])
                history[key] = history[key][-16:]
            last_use[key] = slot
        physical = {n.id: sum(i.resolution.vcpu for i in instances if i.node == n.id) for n in config.nodes}
        violations = {n.id: max(0.0, physical[n.id] - n.capacity) for n in config.nodes}
        logical_new = sum(max(0.0, x_load[n.id] - L * max(0, residual[n.id])) for n in config.nodes)
        warm_violation = sum(max(0, load - L * counts[key]) for key, load in y_load.items())
        idle_resource = sum(i.resolution.vcpu for i in instances if not i.uses)
        survivors = []
        for instance in instances:
            instance.idle = 0 if instance.uses else instance.idle + 1
            threshold = policy.theta
            if policy.retention == "history" and history[instance.key]:
                gaps = history[instance.key]
                threshold = min(16, max(2, math.ceil(sum(gaps) / len(gaps)) + 1))
            expired = not instance.protected and (not policy.preload or instance.idle >= threshold)
            if expired:
                events.append({"kind": "release", "slot": slot, "instance_id": instance.id,
                               "node": instance.node, "model": instance.model, "resolution": instance.resolution.id,
                               "vcpu": instance.resolution.vcpu, "protected": instance.protected,
                               "idle": instance.idle, "threshold": threshold})
            else:
                survivors.append(instance)
        instances = survivors
        events.append({"kind": "slot_end", "slot": slot, "physical_vcpu": physical,
                       "idle_vcpu": idle_resource, "resource_violation_vcpu": sum(violations.values()),
                       "node_violations": violations, "logical_new_violation": logical_new,
                       "warm_slot_violation": warm_violation, "surviving_instances": len(instances)})
    return RunResult(events)

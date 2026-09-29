"""Reconstruct scalar metrics from saved events, checking the money ledger."""
import math
from collections import Counter


def summarize(events):
    requests = [e for e in events if e["kind"] == "request"]
    slots = [e for e in events if e["kind"] == "slot_end"]
    for event in requests:
        expected = event["payment"] - event["upload_cost"] - event["link_cost"] - event["inference_cost"]
        if not math.isfinite(expected) or not math.isclose(expected, event["profit"], rel_tol=1e-9, abs_tol=1e-10):
            raise ValueError("ledger: request profit does not match revenue minus costs")
        if not event["accepted"] and any(event[k] != 0 for k in ("payment", "upload_cost", "link_cost", "inference_cost")):
            raise ValueError("ledger: rejected request has monetary side effects")
    count = len(requests)
    accepted = sum(e["accepted"] for e in requests)
    qualified = sum(e["qualified"] for e in requests)
    reasons = Counter(e["reason"] for e in requests if not e["accepted"])
    summary = {"requests": count, "accepted": accepted, "qualified": qualified,
               "admission_ratio": accepted / count if count else 0,
               "qualified_ratio": qualified / count if count else 0,
               "intrinsically_feasible": sum(e["intrinsically_feasible"] for e in requests),
               "new_branch_requests": sum(e["mode"] == "new" for e in requests),
               "cold_blocked_rejections": sum(e["cold_deadline_blocked"] and not e["accepted"] for e in requests),
               "created_floor": sum(e["kind"] == "create" and e["protected"] for e in events),
               "created_extra": sum(e["kind"] == "create" and not e["protected"] for e in events),
               "released": sum(e["kind"] == "release" for e in events),
               "mean_idle_vcpu": sum(e["idle_vcpu"] for e in slots) / len(slots) if slots else 0,
               "peak_vcpu": max((sum(e["physical_vcpu"].values()) for e in slots), default=0),
               "resource_violation_slots": sum(e["resource_violation_vcpu"] > 1e-9 for e in slots),
               "peak_resource_violation_vcpu": max((e["resource_violation_vcpu"] for e in slots), default=0),
               "peak_logical_new_violation": max((e["logical_new_violation"] for e in slots), default=0),
               "warm_slot_violation_total": sum(e["warm_slot_violation"] for e in slots),
               "concurrency_excess_requests": sum(e["concurrency_excess"] > 0 for e in requests)}
    for key in ("potential_payment", "payment", "upload_cost", "link_cost", "inference_cost", "profit"):
        summary["revenue" if key == "payment" else key] = math.fsum(e[key] for e in requests)
    for reason in ("accuracy", "deadline", "strict_resource", "nonpositive_residual", "cold_deadline_no_instance", "admission_control"):
        summary[f"rejected_{reason}"] = reasons[reason]
    return summary


def by_slot(events):
    slot_events = {e["slot"]: e for e in events if e["kind"] == "slot_end"}
    grouped = {slot: [] for slot in slot_events}
    for event in events:
        if event["kind"] == "request":
            grouped[event["slot"]].append(event)
    rows = []
    for slot, state in slot_events.items():
        requests = grouped[slot]
        count = len(requests)
        rows.append({"slot": slot, "requests": count,
                     "profit": math.fsum(r["profit"] for r in requests),
                     "qualified_ratio": sum(r["qualified"] for r in requests) / count if count else 0,
                     "idle_vcpu": state["idle_vcpu"], "resource_violation_vcpu": state["resource_violation_vcpu"],
                     "warm_slot_violation": state["warm_slot_violation"]})
    return rows

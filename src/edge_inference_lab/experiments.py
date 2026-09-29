"""Frozen development/test protocol, provenance, ledgers and real reports."""
import csv
import hashlib
import json
import math
import platform
import statistics
import time
import tracemalloc
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .domain import Request
from .metrics import by_slot, summarize
from .policies import Bounds, study_policies
from .report import aggregate, paired_differences, plot_matrix, plot_switch, write_csv, write_summary
from .simulation import simulate
from .traces import generate_traces, trace_hash


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf8")).hexdigest()


def source_hash():
    hasher = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        hasher.update(path.name.encode("utf8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def select_fixed_theta(rows):
    scores = {}
    for row in rows:
        if row["phase"] == "development" and row["policy"].startswith("pd_theta_"):
            scores.setdefault(row["policy"], []).append(row["profit"])
    if not scores:
        raise ValueError("selection: no development fixed-theta results")
    return min(scores, key=lambda name: (-statistics.mean(scores[name]), int(name.rsplit("_", 1)[1])))


def _prepare(output):
    path = Path(output)
    if path.exists() and any(path.iterdir()):
        raise FileExistsError("output must be a new or empty directory")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_ledger(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf8", newline="\n") as handle:
        for event in events:
            handle.write(canonical(event) + "\n")


def read_ledger(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf8").splitlines() if line]


def _environment():
    return {"python": platform.python_version(), "system": platform.system(), "machine": platform.machine(),
            "package_version": __version__, "source_sha256": source_hash(),
            "memory_method": "tracemalloc peak Python allocations; not process peak RSS"}


def _manifest(path):
    return {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(path.rglob("*")) if p.is_file() and p.name != "metadata.json"}


def run_study(config, output, save_all_events=False, progress=None):
    bounds = Bounds.from_config(config)
    path = _prepare(output)
    start = time.perf_counter()
    tracemalloc.start()
    rows, slots, hashes, ledgers = [], [], {}, []
    selected = None
    policies = study_policies()
    try:
        for phase in ("development", "test"):
            if phase == "test":
                selected = select_fixed_theta(rows)
            for seed in config.seeds[phase]:
                traces = generate_traces(config, seed)
                for scenario, requests in traces.items():
                    sha = trace_hash(requests)
                    hashes[f"{phase}/{seed}/{scenario}"] = sha
                    if phase == "test" and seed == config.seeds["test"][0]:
                        target = path / "traces" / f"seed{seed}_{scenario}.csv"
                        target.parent.mkdir(parents=True, exist_ok=True)
                        write_csv(target, [asdict(r) for r in requests])
                    for policy in policies:
                        started = time.perf_counter()
                        run = simulate(config, requests, policy)
                        summary = summarize(run.events)
                        row = {"phase": phase, "seed": seed, "scenario": scenario, "policy": policy.name,
                               "trace_sha256": sha, "ledger_sha256": digest(run.events), **summary,
                               "runtime_seconds": time.perf_counter() - started}
                        rows.append(row)
                        if phase == "test":
                            for slot in by_slot(run.events):
                                slots.append({"seed": seed, "scenario": scenario, "policy": policy.name, **slot})
                            if policy.name == selected:
                                rows.append({**row, "policy": "pd_dev_selected"})
                        save = save_all_events or (phase == "test" and seed == config.seeds["test"][0] and scenario == "switch")
                        if save:
                            name = f"events/{phase}_seed{seed}_{scenario}_{policy.name}.jsonl"
                            _save_ledger(path / name, run.events)
                            # Verify from actual bytes, not the in-memory summary alone.
                            reread = read_ledger(path / name)
                            if summarize(reread) != summary or digest(reread) != row["ledger_sha256"]:
                                raise ValueError("ledger: saved event replay differs")
                            ledgers.append({"file": name, "phase": phase, "seed": seed,
                                            "scenario": scenario, "policy": policy.name,
                                            "ledger_sha256": row["ledger_sha256"]})
                if progress:
                    progress(f"{phase}: seed {seed} completed")
        aggregates = aggregate(rows)
        write_csv(path / "runs.csv", rows)
        write_csv(path / "slot_metrics.csv", slots)
        write_csv(path / "aggregate.csv", aggregates)
        write_csv(path / "paired_differences.csv", paired_differences(rows, selected))
        plot_matrix(path / "profit_matrix.svg", aggregates)
        plot_switch(path / "switch_timeseries.svg", slots, config.workload["switch_slot"])
        write_summary(path / "summary.md", aggregates, selected, len(config.seeds["test"]))
        (path / "config.json").write_text(json.dumps(config.raw, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf8")
        _, memory_peak = tracemalloc.get_traced_memory()
        metadata = {"status": "complete", "experiment": "paired_accuracy_deadline_study",
                    "environment": _environment(), "config_sha256": digest(config.raw),
                    "development_seeds": config.seeds["development"], "test_seeds": config.seeds["test"],
                    "selected_fixed_policy": selected, "selection_rule": "development mean profit over all scenarios; smallest theta breaks ties",
                    "bounds": asdict(bounds), "trace_hashes": hashes, "saved_ledgers": ledgers,
                    "ledger_scope": "all runs" if save_all_events else "first test seed, switch scenario, all eight policies; other ledgers regenerate with --save-all-events",
                    "runtime_seconds": time.perf_counter() - start, "peak_python_allocation_bytes": memory_peak,
                    "files_sha256": _manifest(path)}
        (path / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf8")
        return metadata
    finally:
        tracemalloc.stop()


def load_requests(path):
    required = set(Request.__dataclass_fields__)
    with Path(path).open(encoding="utf8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(reader.fieldnames) != len(required) or set(reader.fieldnames) != required:
            raise ValueError("requests CSV: exactly seven unique Request field names are required")
        rows = []
        for line, record in enumerate(reader, 2):
            if None in record or any(record[k] is None for k in required):
                raise ValueError(f"requests CSV line {line}: wrong column count")
            try:
                rows.append(Request(record["id"], int(record["slot"]), record["source"], record["model"],
                                    float(record["min_accuracy"]), float(record["deadline_ms"]), float(record["data_mb"])))
            except ValueError as exc:
                raise ValueError(f"requests CSV line {line}: invalid numeric field") from exc
    if not rows:
        raise ValueError("requests CSV: empty trace")
    return rows


def verify_study(directory, progress=None):
    """Recompute every recorded run without profiling, checking hashes and scalars."""
    from .config import load_config
    path = Path(directory)
    metadata = json.loads((path / "metadata.json").read_text(encoding="utf8"))
    for name, expected in metadata["files_sha256"].items():
        if hashlib.sha256((path / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"manifest: changed artifact {name}")
    config = load_config(path / "config.json")
    if digest(config.raw) != metadata["config_sha256"]:
        raise ValueError("manifest: configuration differs")
    with (path / "runs.csv").open(encoding="utf8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    policies = {p.name: p for p in study_policies()}
    cached_traces = {}
    checked = 0
    for row in rows:
        if row["policy"] == "pd_dev_selected":
            continue
        key = row["phase"], int(row["seed"])
        if key not in cached_traces:
            cached_traces[key] = generate_traces(config, key[1])
        requests = cached_traces[key][row["scenario"]]
        if trace_hash(requests) != row["trace_sha256"]:
            raise ValueError("replay: trace hash differs")
        run = simulate(config, requests, policies[row["policy"]])
        if digest(run.events) != row["ledger_sha256"]:
            raise ValueError("replay: event hash differs")
        for metric, value in summarize(run.events).items():
            if not math.isclose(float(row[metric]), value, rel_tol=1e-10, abs_tol=1e-10):
                raise ValueError(f"replay: scalar differs: {metric}")
        checked += 1
        if progress and checked % 32 == 0:
            progress(f"verified {checked} runs")
    selected = select_fixed_theta([{**r, "profit": float(r["profit"])} for r in rows])
    if selected != metadata["selected_fixed_policy"]:
        raise ValueError("replay: development selection differs")
    lookup = {(r["phase"], r["seed"], r["scenario"], r["policy"]): r for r in rows}
    for row in rows:
        if row["policy"] == "pd_dev_selected":
            base = lookup[(row["phase"], row["seed"], row["scenario"], selected)]
            if {k: v for k, v in row.items() if k != "policy"} != {k: v for k, v in base.items() if k != "policy"}:
                raise ValueError("replay: selected-policy alias differs")
    return {"status": "match", "checked_runs": checked, "checked_rows": len(rows),
            "recorded_package_sha256": metadata["environment"]["source_sha256"],
            "verified_package_sha256": source_hash(), "config_sha256": metadata["config_sha256"],
            "verification": "all artifact hashes, regenerated traces, full event hashes, scalar metrics and development selection; excludes runtime/memory replay"}


def run_case(config, requests, policy, output):
    path = _prepare(output)
    started = time.perf_counter()
    tracemalloc.start()
    try:
        run = simulate(config, requests, policy)
        summary = summarize(run.events)
        _save_ledger(path / "events.jsonl", run.events)
        if summarize(read_ledger(path / "events.jsonl")) != summary:
            raise ValueError("ledger: saved case replay differs")
        (path / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf8")
        write_csv(path / "requests.csv", [asdict(r) for r in requests])
        (path / "config.json").write_text(json.dumps(config.raw, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
        _, peak = tracemalloc.get_traced_memory()
        metadata = {"status": "complete", "experiment": "manual_case", "policy": asdict(policy),
                    "environment": _environment(), "config_sha256": digest(config.raw), "trace_sha256": trace_hash(requests),
                    "ledger_sha256": digest(run.events), "runtime_seconds": time.perf_counter() - started,
                    "peak_python_allocation_bytes": peak, "files_sha256": _manifest(path)}
        (path / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
        return metadata
    finally:
        tracemalloc.stop()

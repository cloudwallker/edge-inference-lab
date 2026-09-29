"""python -m edge_inference_lab: reproducible local experiments."""
import argparse
import json
import sys
from pathlib import Path

from .config import load_config
from .experiments import load_requests, read_ledger, run_case, run_study, verify_study
from .metrics import summarize
from .policies import study_policies


def main(argv=None):
    parser = argparse.ArgumentParser(description="CPU-only edge inference scheduling learning lab")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--save-all-events", action="store_true", help="save every run ledger instead of the representative subset")
    parser.add_argument("--requests", type=Path, help="seven-field CSV for a manual case")
    parser.add_argument("--policy", choices=[p.name for p in study_policies()], help="manual-case policy; requires --requests")
    parser.add_argument("--audit", type=Path, help="reconstruct a saved JSONL event ledger")
    parser.add_argument("--verify", type=Path, help="regenerate all runs and verify recorded results")
    args = parser.parse_args(argv)
    try:
        if args.policy is not None and args.requests is None:
            parser.error("--policy requires --requests")
        if args.verify:
            print(json.dumps(verify_study(args.verify), indent=2))
            return 0
        if args.audit:
            print(json.dumps(summarize(read_ledger(args.audit)), indent=2))
            return 0
        if args.config is None or args.output is None:
            parser.error("--config and --output are required unless --audit is used")
        config = load_config(args.config)
        if args.requests:
            policy = next(p for p in study_policies() if p.name == (args.policy or "pd_theta_2"))
            metadata = run_case(config, load_requests(args.requests), policy, args.output)
        else:
            metadata = run_study(config, args.output, args.save_all_events, progress=lambda message: print(message, flush=True))
        print(f'completed: {metadata["runtime_seconds"]:.3f}s; peak Python allocations {metadata["peak_python_allocation_bytes"]/1048576:.2f} MiB')
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

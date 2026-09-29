"""Optional publication figures from actual CSV results (requires matplotlib)."""
import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import statistics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    args.output.mkdir(parents=True, exist_ok=True)
    meta = json.loads((args.results / "metadata.json").read_text(encoding="utf8"))
    with (args.results / "aggregate.csv").open(encoding="utf8", newline="") as file:
        aggregates = list(csv.DictReader(file))
    with (args.results / "slot_metrics.csv").open(encoding="utf8", newline="") as file:
        rows = list(csv.DictReader(file))
    policies = ["pd_theta_2", "pd_theta_4", "pd_theta_8", "pd_theta_16", "pd_history", "pd_dev_selected"]
    scenarios = ["high_tight", "high_loose", "random", "switch"]
    lookup = {(r["scenario"], r["policy"]): r for r in aggregates}
    matrix = np.array([[float(lookup[(s, p)]["profit_mean"]) for s in scenarios] for p in policies])
    fig, ax = plt.subplots(figsize=(9, 5.0))
    image = ax.imshow(matrix, cmap="Blues", aspect="auto")
    ax.set_xticks(range(4), labels=scenarios)
    ax.set_yticks(range(6), labels=policies)
    for i, policy in enumerate(policies):
        for j, scenario in enumerate(scenarios):
            row = lookup[(scenario, policy)]
            value = matrix[i, j]
            color = "white" if image.norm(value) > .6 else "#182c3c"
            ax.text(j, i, f'{value:.1f} ± {float(row["profit_sd"]):.1f}', ha="center", va="center", color=color, fontsize=10)
    ax.set_title(f'Mean simulated profit ± seed SD ({len(meta["test_seeds"])} test seeds)', pad=15)
    fig.colorbar(image, ax=ax, label="Simulated USD")
    fig.text(.02, .02, "Same admission and floor. Teaching prices; read resource slack alongside profit.", fontsize=9)
    fig.tight_layout(rect=(0, .04, 1, 1))
    fig.savefig(args.output / "profit-matrix.png", dpi=160, metadata={"Software": "EdgeInferenceLab"})
    plt.close(fig)

    groups = defaultdict(list)
    for row in rows:
        if row["scenario"] == "switch" and row["policy"] in policies[:-1]:
            groups[(row["policy"], int(row["slot"]))].append(row)
    slots = sorted({s for _, s in groups})
    fig, axes = plt.subplots(2, 1, figsize=(10, 6.6), sharex=True)
    colors = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#6a4c93"]
    for policy, color in zip(policies[:-1], colors):
        for ax, metric in zip(axes, ("profit", "qualified_ratio")):
            series = [statistics.mean(float(r[metric]) for r in groups[(policy, slot)]) for slot in slots]
            ax.plot(slots, series, label=policy, color=color, linewidth=1.8)
    for ax in axes:
        ax.axvline(meta["config"]["workload"]["switch_slot"] - .5 if "config" in meta else
                   json.loads((args.results / "config.json").read_text(encoding="utf8"))["workload"]["switch_slot"] - .5,
                   color="#555", linestyle="--", linewidth=1)
        ax.grid(alpha=.2)
    axes[0].set_ylabel("Simulated USD / slot")
    axes[1].set_ylabel("Accuracy + deadline ratio")
    axes[1].set_ylim(0, 1.05)
    axes[1].set_xlabel("Time slot")
    axes[0].legend(ncol=3, fontsize=9, loc="lower center", bbox_to_anchor=(.5, 1.02))
    fig.suptitle("Pairing switch: high-tight to high-loose (test-seed means)", y=.99)
    fig.text(.02, .01, "Nominal accuracy and simulated latency; neither actual neural inference nor strict physical goodput.", fontsize=9)
    fig.tight_layout(rect=(0, .035, 1, .95))
    fig.savefig(args.output / "switch-response.png", dpi=160, metadata={"Software": "EdgeInferenceLab"})
    plt.close(fig)
    manifest = {"source_config_sha256": meta["config_sha256"], "source_package_sha256": meta["environment"]["source_sha256"],
                "test_seeds": meta["test_seeds"], "matplotlib": matplotlib.__version__,
                "csv_sha256": {name: hashlib.sha256((args.results / name).read_bytes()).hexdigest()
                               for name in ("aggregate.csv", "slot_metrics.csv")},
                "images_sha256": {name: hashlib.sha256((args.output / name).read_bytes()).hexdigest()
                                  for name in ("profit-matrix.png", "switch-response.png")}}
    (args.output / "figures.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf8")


if __name__ == "__main__":
    main()

"""Small deterministic CSV/Markdown/SVG reports without plotting dependencies."""
import csv
import html
import statistics
from collections import defaultdict
from pathlib import Path


def write_csv(path, rows):
    if not rows:
        raise ValueError("report: no rows")
    with Path(path).open("w", encoding="utf8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def aggregate(rows):
    groups = defaultdict(list)
    for row in rows:
        if row["phase"] == "test":
            groups[(row["scenario"], row["policy"])].append(row)
    metrics = ("profit", "potential_payment", "revenue", "upload_cost", "link_cost", "inference_cost",
               "qualified_ratio", "created_extra", "new_branch_requests", "mean_idle_vcpu", "peak_vcpu",
               "resource_violation_slots", "peak_resource_violation_vcpu", "warm_slot_violation_total")
    result = []
    for (scenario, policy), values in sorted(groups.items()):
        row = {"scenario": scenario, "policy": policy, "n_seeds": len(values)}
        for metric in metrics:
            series = [v[metric] for v in values]
            row[f"{metric}_mean"] = statistics.mean(series)
            row[f"{metric}_sd"] = statistics.stdev(series) if len(series) > 1 else 0.0
        result.append(row)
    return result


def paired_differences(rows, baseline):
    tests = [r for r in rows if r["phase"] == "test" and r["policy"] != "pd_dev_selected"]
    reference = {(r["seed"], r["scenario"]): r for r in tests if r["policy"] == baseline}
    result = []
    for row in tests:
        base = reference[(row["seed"], row["scenario"])]
        if base["trace_sha256"] != row["trace_sha256"]:
            raise ValueError("report: paired comparison has different traces")
        result.append({"seed": row["seed"], "scenario": row["scenario"], "policy": row["policy"],
                       "baseline": baseline, "profit_difference": row["profit"] - base["profit"],
                       "qualified_ratio_difference": row["qualified_ratio"] - base["qualified_ratio"],
                       "idle_vcpu_difference": row["mean_idle_vcpu"] - base["mean_idle_vcpu"],
                       "resource_violation_slots_difference": row["resource_violation_slots"] - base["resource_violation_slots"]})
    return result


def _svg_start(width, height, title):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">',
            f'<title>{html.escape(title)}</title>', '<rect width="100%" height="100%" fill="#fff"/>',
            '<style>text{font-family:Arial,sans-serif;fill:#183042} .muted{fill:#586c7b}</style>']


def _text(parts, x, y, value, size=14, extra=""):
    parts.append(f'<text x="{x}" y="{y}" font-size="{size}" {extra}>{html.escape(str(value))}</text>')


def plot_matrix(path, rows):
    scenarios = ["high_tight", "high_loose", "random", "switch"]
    policies = ["pd_theta_2", "pd_theta_4", "pd_theta_8", "pd_theta_16", "pd_history", "pd_dev_selected",
                "no_control_interpretation", "no_pre_new_only", "greedy_hard_cap"]
    lookup = {(r["scenario"], r["policy"]): r for r in rows}
    max_profit = max(r["profit_mean"] for r in rows) or 1
    parts = _svg_start(1000, 430, "Mean simulated profit across test seeds")
    _text(parts, 24, 30, "Mean simulated profit (USD); each cell shows mean ± seed SD", 19)
    _text(parts, 24, 53, "Teaching prices and disclosed primal-dual interpretation; resource slack is reported separately.", 13)
    for column, scenario in enumerate(scenarios):
        _text(parts, 390 + 160 * column, 82, scenario, 13, 'text-anchor="middle"')
    for i, policy in enumerate(policies):
        y = 95 + i * 32
        _text(parts, 22, y + 21, policy, 13)
        if i == 6:
            parts.append(f'<line x1="20" y1="{y-3}" x2="974" y2="{y-3}" stroke="#8da0ae"/>')
        for j, scenario in enumerate(scenarios):
            row = lookup[(scenario, policy)]
            value = row["profit_mean"]
            shade = int(245 - 75 * max(0, value) / max_profit)
            x = 312 + j * 160
            parts.append(f'<rect x="{x}" y="{y}" width="154" height="28" rx="3" fill="rgb({shade},{min(250,shade+10)},245)"/>')
            _text(parts, x + 77, y + 19, f'{value:.2f} ± {row["profit_sd"]:.2f}', 13, 'text-anchor="middle"')
    _text(parts, 24, 416, "First six rows share admission and initialization; bottom rows are separate interpretation / teaching baselines.", 12)
    parts.append("</svg>")
    Path(path).write_text("\n".join(parts), encoding="utf8")


def plot_switch(path, slot_rows, switch_slot):
    policies = ["pd_theta_2", "pd_theta_4", "pd_theta_8", "pd_theta_16", "pd_history"]
    colors = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#6a4c93"]
    groups = defaultdict(list)
    for row in slot_rows:
        if row["scenario"] == "switch" and row["policy"] in policies:
            groups[(row["policy"], row["slot"])].append(row)
    slots = sorted({slot for _, slot in groups})
    values = {key: {metric: statistics.mean(r[metric] for r in rows) for metric in ("profit", "qualified_ratio")} for key, rows in groups.items()}
    width, height = 900, 535
    parts = _svg_start(width, height, "Switch response: mean slot profit and qualified service ratio")
    _text(parts, 20, 28, "Pairing switch: high-tight → high-loose (test-seed means)", 19)
    for i, (policy, color) in enumerate(zip(policies, colors)):
        x = 50 + i * 165
        parts.append(f'<line x1="{x}" y1="51" x2="{x+20}" y2="51" stroke="{color}" stroke-width="3"/>')
        _text(parts, x + 26, 56, policy, 12)
    left, plot_width, plot_height = 80, 770, 150
    for panel, metric in enumerate(("profit", "qualified_ratio")):
        top = 95 + 230 * panel
        maximum = max(values[(policy, slot)][metric] for policy in policies for slot in slots) if metric == "profit" else 1
        maximum = maximum or 1
        _text(parts, left, top - 13, "Simulated profit / slot (USD)" if metric == "profit" else "Quality and deadline qualified / arriving requests", 14)
        parts.append(f'<path d="M {left} {top} V {top+plot_height} H {left+plot_width}" fill="none" stroke="#708797"/>')
        for tick in range(5):
            y = top + plot_height * (1 - tick / 4)
            _text(parts, left - 10, y + 4, f"{maximum*tick/4:.2f}", 11, 'text-anchor="end"')
            parts.append(f'<line x1="{left}" y1="{y}" x2="{left+plot_width}" y2="{y}" stroke="#e0e7ed"/>')
        denominator = max(1, len(slots) - 1)
        if switch_slot <= slots[-1]:
            x = left + (switch_slot - 0.5) / denominator * plot_width
            parts.append(f'<line x1="{x}" y1="{top}" x2="{x}" y2="{top+plot_height}" stroke="#333" stroke-dasharray="5,4"/>')
        for policy, color in zip(policies, colors):
            points = " ".join(f'{left+i/denominator*plot_width:.2f},{top+plot_height*(1-values[(policy,slot)][metric]/maximum):.2f}' for i, slot in enumerate(slots))
            parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/>')
        for i, slot in enumerate(slots):
            _text(parts, left + i / denominator * plot_width, top + plot_height + 18, slot, 11, 'text-anchor="middle"')
    _text(parts, 22, 523, "Nominal accuracy and simulated delays; this is not measured neural-model quality or deployed service goodput.", 12)
    parts.append("</svg>")
    Path(path).write_text("\n".join(parts), encoding="utf8")


def write_summary(path, aggregates, selected, test_count):
    lines = ["# 实测模拟结果", "", f"测试种子数：{test_count}。开发集选定固定策略：`{selected}`。", "",
             "数字为模拟美元和标称精度/期限合格比例；费用、定价与资源松弛见配置及实现对照。", "",
             "| 配对 | 策略 | 利润均值 ± 种子标准差 | 合格比例均值 | 闲置 vCPU 均值 | 物理违规时间片均值 | 暖服务槽超额总量均值 |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for row in aggregates:
        lines.append(f'| {row["scenario"]} | {row["policy"]} | {row["profit_mean"]:.3f} ± {row["profit_sd"]:.3f} | {row["qualified_ratio_mean"]:.3f} | {row["mean_idle_vcpu_mean"]:.3f} | {row["resource_violation_slots_mean"]:.2f} | {row["warm_slot_violation_total_mean"]:.2f} |')
    lines += ["", "`pd_dev_selected` 是开发集选定固定策略的别名，未重复运行，也未用测试结果选择。",
              "第一组六种保留策略可作匹配对照；取消预置、去接纳控制和硬容量贪心分别改变更多条件，不单独归因于保留。",
              "结果是当前参数下的学习评估，不证明新颖性、全局最优、论文原图复现或真实部署收益。", ""]
    Path(path).write_text("\n".join(lines), encoding="utf8")

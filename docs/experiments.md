# 实验协议与复现

协议冻结日期：2026-09-29。当前实验检验一个受控学习问题：**精度和期限各自分布不变时，二者配对关系是否改变实例保留策略的模拟结果？** 同时观察一次固定时刻的配对切换，不声称已经完成切换时机扫描。

## 输入及不变量

两阶段使用3个固定模拟节点、3模型×4分辨率、每片60请求、L=2，分开分析：

| 阶段 | 配置 | 时间片/请求数 | 开发种子 | 测试种子 | 切换位置 |
|---|---|---:|---|---|---|
| 先导 | [`study.json`](../configs/study.json) | 12/720 | 1–3 | 101–110 | slot6 |
| 扩展 | [`study24.json`](../configs/study24.json) | 24/1440 | 11–13 | 201–210 | slot12 |

每节点底座9模拟vCPU；电脑不需要9个物理核。模型精度和实例资源来自原表；推理时间、费用和初始化时延取报告区间的固定中点。有效上传速率、固定三角网络、阶梯定价、二元精度与期限需求是教学设定，全部来源见配置 `provenance`。

先导的θ16大于12片时域，不能观察其闲置满16片后的释放。扩展因此延长为24片，使用全新的开发和测试种子，保留原先导全部结果；它不是重复挑选有利种子。代表性扩展账本中θ16确实发生额外实例释放。扩展仍只有一次固定时刻切换，未检验阶段顺序或相位的独立影响。

每个种子先生成相同到达顺序、源节点、模型序列和数据量。按照**模型×2时间片块**分组，该组一半需求取模型最低标称精度，另一半取最高精度；奇数样本时低精度多一个。期限值集合由100/450ms构成，同样固定。只重新配对标签：

- `high_tight`：较高精度尽量配较紧期限。
- `high_loose`：较高精度尽量配较松期限。
- `random`：同一个期限值集合随机重排。
- `switch`：先导slot 0–5使用high_tight，slot 6–11使用high_loose；扩展在slot12切换。

奇数组的配对不能恰好只有两种组合，需查看实际列联表/轨迹，不以名称代替检查。所有组的两个边际**逐模型逐块严格相同**，固定字段逐请求相同。程序生成后运行校验器；不只是全局均值匹配。策略逐请求决定，未查看同片后续请求或下一片配对。

随机性来自模型、来源、数据量和random配对；**网络、模型参数和成本不跨种子随机改变**。10个测试种子是独立合成工作负载，不能称10个独立拓扑，也不能声称覆盖论文25拓扑实验。

## 基线、调优和评价边界

各阶段分别使用上表的开发和测试种子，四组种子互不重叠。配置在各自实验前冻结。先在开发轨迹的四种情形上平均模拟利润，选θ=2/4/8/16中一个固定策略，并列时取较小θ。测试结果不用于选θ；四个固定θ都保留，`pd_dev_selected`只是所选策略的结果别名。两阶段均在开发集选出θ16，没有将两个阶段结果合并调参。

`pd_history`共享原式接纳及底座，仅将保留阈值替换为组内最近16次**实际服务时间片**间隔的均值，ceil+1并截断至[2,16]。初始值2，无预测未来访问。它属于已有间隔思想的简单变体，未实现文献的完整直方图或预热机制。

`no_control_interpretation`、`no_pre_new_only`、`greedy_hard_cap`用于理解机制，改变了接纳/初态/严格资源限制。它们不属于只改变保留的公平消融，也不等于原作者精确基线。[逐项定义与偏离](implementation-map.md)。

## 输出和指标

每次完整运行输出：

| 文件 | 内容 |
|---|---|
| `config.json`, `metadata.json` | 实际配置、种子、代码包SHA256、参数界、轨迹哈希、文件哈希、实际CPU耗时和tracemalloc内存 |
| `runs.csv` | 开发及每测试种子的每场景每策略利润分解、服务比例、实例、闲置及违规指标 |
| `aggregate.csv` | 测试种子均值和样本标准差；不挑种子 |
| `paired_differences.csv` | 同种子、同轨迹相对开发选定固定策略的差值 |
| `slot_metrics.csv` | 各时间片的利润、精度/期限合格比例、闲置及违规 |
| `traces/` | 第一测试种子的四种合成轨迹 |
| `events/` | 默认保存第一测试种子switch场景的八策略完整JSONL事件 |
| `summary.md`, 两张SVG | 真实结果表、配对矩阵和切换后的时间序列 |

所有运行汇总先从内存事件重建。保存的代表账本另从实际JSONL回读核对。默认只公开一小组审阅账本，避免膨胀仓库；其他运行保存账本内容哈希，可用 `--save-all-events`重新生成全部。没有保存的原始账本不写成已附在仓库中。

利润与潜在付款必须一起分析。收费依赖精度×期限，重新配对可以改变总潜在付款；跨情形的绝对利润差不是保留的纯因果效应。主要看同一轨迹上的策略差值，再检查接纳、费用、创建和资源。当前未进行显著性检验、置信区间推断或最优解比较。

`qualified_ratio`仅为标称精度+模拟期限合格/到达请求。它不包含严格资源可执行性，必须与物理vCPU、暖槽超额一起读。实例创建数≠new分支请求数；累计`concurrency_excess`不能相加，总暖槽缺口由槽末统计。精度、延迟、美元均为模拟量；程序耗时和Python分配内存是本机测量量，tracemalloc并非进程峰值RSS。

## 运行

Python 3.9+。在项目根目录运行，无需安装依赖。输出目录必须新建或为空，避免覆盖已有研究数据。

```bash
python run_lab.py --config configs/smoke.json --output results/local/smoke
python run_lab.py --config configs/study.json --output results/local/study
python run_lab.py --config configs/study24.json --output results/local/study24
```

保存全量账本的独立复跑：

```bash
python run_lab.py --config configs/study24.json --output results/local/study24-all-events --save-all-events
```

逐事件审核：

```bash
python run_lab.py --audit results/study/events/test_seed101_switch_pd_theta_2.jsonl
```

完整数值复核会重新生成全部轨迹、事件内容哈希及汇总，并核对保存文件的哈希、开发选择和结果别名：

```bash
python run_lab.py --verify results/study
python run_lab.py --verify results/study24
```

每阶段有416次实际策略运行及456行结果（其中40行为测试集所选策略别名）。最终包代码已完成两阶段共832次运行的数值复核，记录见[先导复核](../results/verification-pilot.json)和[扩展复核](../results/verification-study24.json)。原性能测量发生在最终输入校验修正之前，保留当时的代码哈希和耗时；复核另外记录最终代码哈希，不追改历史测量。

模拟器自动生成SVG；首页使用的独立PNG可从真实CSV重新绘制，需另装matplotlib：

```bash
python scripts/plot_figures.py --help
```

手工例在[示例说明](../data/examples/README.md)。两条命令比较θ，输入完全相同：

```bash
python run_lab.py --config configs/retention-case.json --requests data/examples/retention-case.csv --policy pd_theta_2 --output results/local/case-theta2
python run_lab.py --config configs/retention-case.json --requests data/examples/retention-case.csv --policy pd_theta_4 --output results/local/case-theta4
```

测试包括手算更新、单请求成本、暖冷延迟、分组、释放时点、底座、资源松弛、配对校验、调优隔离、事件回读和CLI。Windows PowerShell：

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -t . -v
```

其他shell设置`PYTHONPATH=src`再运行同一unittest命令。已完成的测量及可解释局限见[发现](findings.md)，不可将小规模耗时外推为论文全规模运行保证。

# 相关工作与已排除的宽泛想法

核查截止：2026-09-29。近期窗口为 2026-06-29–2026-09-29；更早的直接近邻保留。本文是有界查新，不是系统综述，也未确认研究空白。版本和章节固定在下表；日期区分首次提交、修订和正式发表。

## 问题：候选实验到底改变什么？

**解释。** 固定到达、模型、源节点和数据量；在同模型、同评估块内保持最低精度与期限各自的值集合，通过重新配对改变联合分布，再单独考察配对关系的切换时机。精度是服务配置的标称准确率，实例是完整模型配置的服务实例；不能混称量化位宽、KV cache 或 MoE expert。

**证据。** 主论文 §III-C、§V-A、§VI-A 与 Fig. 7 已覆盖精度、期限、启动延迟、利润及 θ 敏感性。[原始论文](https://www.cs.cityu.edu.hk/~weliang/papers/ZLXJY25.pdf)

**疑问。** 查到的相邻研究是否已做完全相同的固定边际配对干预？目前尚未核定；不能把未找到视为不存在。

**实现影响。** 首期称“受控学习评估”，不称首次提出或新缓存算法；实验开始前和结论形成前更新检索。

## 证据：直接近邻与最近三个月记录

| 原始来源与核对章节 | 日期 / 状态 | 已覆盖内容 | 对候选问题的限制 |
| --- | --- | --- | --- |
| Zhang 等，[Profit Maximization…](https://www.cs.cityu.edu.hk/~weliang/papers/ZLXJY25.pdf)，§III-C、§V-A、§VI-A、Fig. 7 | TMC 24(7)，2025-07；[DOI](https://doi.org/10.1109/TMC.2025.3540017) | 精度/期限、实例保留、接纳利润；比较 θ=2/4/8/16 和期限范围 | 期限影响保留效果已被研究；原文未明确两字段联合采样规则 |
| Qiu 等，[CoCaR / CoCaR-OL v2](https://arxiv.org/html/2511.03159v2)，§VI、§VII-D | v1 2025-11-05，v2 2026-05-12；[机构记录](https://research.cuhk.edu.hk/en/publications/joint-optimization-of-dnn-model-caching-and-request-routing-in-mo/)确认 ToN 34:5287–5302，2026-05-13 | 联合子模型缓存和路由；精度、加载延迟、容量及模型热度变化 | 质量感知缓存和在线适应已有直接先例；简化保留规则不能冒称复现 CoCaR-OL |
| Ai 等，[Joint Optimization…](https://www.cs.cityu.edu.hk/~weliang/papers/ALL26.pdf)，§IV、§V-B–D、§VI | ToN 34，2026；首次发表 2025-11-18，current version 2026-01-08 | LSTM 请求预测、MAB 资源比例、重训与推理竞争 | 加预测或联合重训/推理不是新颖性证据；不是空闲实例 TTL 对照 |
| Chang 等，[TeDiServe v2](https://arxiv.org/html/2606.29094v2)，§3.2–3.5、§5、附录 F | [版本记录](https://arxiv.org/abs/2606.29094)：v1 2026-06-27，v2 **2026-09-25**；作者版本标注 EuroSys ’27，正式接收记录未独立复核 | 扩散语言模型的期限调度、质量感知重配置、近似 KV 缓存 | 质量/期限联合控制已有机制；§3.5 实际评估同一 latency SLO、等优先级，非本项目最低精度配对实验 |
| Vestrum 等，[Beyond Binary Priorities v1](https://arxiv.org/html/2608.16336v1)，§4 | [版本记录](https://arxiv.org/abs/2608.16336)：**2026-08-17** 预印本；接收状态未核定 | Vidur 仿真多级 SLA、迁移/路由及不同优先级分布 | 改需求组成不自动新颖；优先级分布不等于固定精度/期限边际 |
| Chen 等，[Goodput Maximization… v1](https://arxiv.org/html/2608.25543v1)，§II–III、§V | [版本记录](https://arxiv.org/abs/2608.25543)：**2026-08-26**；关联 IEEE WCL DOI，最终刊登状态未独立复核 | 边缘 LLM 卸载与带宽；期限达标、显存可行的 goodput | SLO 合格吞吐量已有先例；不是完整模型配置实例的 TTL 评估 |
| Wang 等，[SeqMoE v1](https://arxiv.org/html/2609.12978v1)，§6–7、§9 | [版本记录](https://arxiv.org/abs/2609.12978)：**2026-09-11** 预印本；接收状态未核定 | deadline 预取调度及未来访问预测驱逐 | expert 权重及内部计算 deadline 不同于服务实例和用户期限；预测驱逐本身已有先例 |

较早的机制祖先是 [Serverless in the Wild，USENIX ATC 2020](https://www.usenix.org/conference/atc20/presentation/shahrad)：利用函数访问间隔直方图安排保留和预热。它说明按访问历史调 keepalive 不是新的起点，不把旧作当近期发现。

梁维发参与的 [Efficient and Fault Tolerant Data Stream Processing With Uncertain Data Rates](https://www.cs.cityu.edu.hk/~weliang/papers/XLXLXXZL26.pdf)（TSC 19(1)，首次发表 2025-12-23、current version 2026-02-05）研究预测数据率、调整函数实例与容错；[Enabling Streaming Analytics for Digital Twin Applications](https://www.cs.cityu.edu.hk/~weliang/papers/XLXRLXXZLF26.pdf)（TPDS 37(6)，首次发表 2026-03-13、current version 2026-04-17）研究 DT 放置与模型选择。二者均早于近期窗口，同作者也不能直接称为主论文的引文后继。

## 解释：已排除的广泛想法

| 宽泛主张 | 排除理由 | 仍需更具体核验的内容 |
| --- | --- | --- |
| “首次按负载变化自适应缓存” | CoCaR-OL、访问间隔 keepalive 已有先例 | 特定状态、成本和信息边界是否不同 |
| “首次考虑准确率与期限” | 主论文、CoCaR、TeDiServe 已联合处理相邻要求 | 固定边际配对控制是否与既有实验重复 |
| “加 LSTM / 强化学习就有创新” | ALL26 已用 LSTM 与 MAB；结论也提出其他预测机制 | 预测误差、增益来源和额外开销 |
| “期限感知保留或预测驱逐是空白” | 期限调度、预测驱逐已有研究 | 粒度是实例、子模型、KV 还是 expert；期限含义是否相同 |
| “改优先级分布 / 统计合格请求是新方法” | Multi-Tier SLA、goodput 工作已覆盖 | 控制变量、评价目标和因果解释是否增加可检验证据 |

## 疑问：哪些证据还缺？

没有核定新的直接引用 ZLXJY25 的论文，意味着**直接引文核验尚未完成**，不意味着没有后续工作。还需补查质量/期限联合分布干预、实例价值评估与公开 artifact；核对相同机制是否换了术语。

TeDiServe 的工作负载结合 ShareGPT 长度与 BurstGPT 到达统计，不应写成完整原始生产 trace 回放；其无 GPU smoke 输出也不能测真实模型质量。论文发表状态与作者预印本标注分开记录。

## 实现影响：怎样避免把输入效应当策略效果？

- 配对检查到“模型 × 评估块”，保存二维列联表；全局均值相同不足以证明各块边际相同。
- 配对关系与切换时机分开干预；只证明全局计数相同，就只报告全局不变量。
- ψ 同时依赖精度和期限，配对可能改变潜在总付款。保存付款机会、收入和原式费用，比较同轨迹的策略差值。
- 保留规则共享接纳、路由、创建、初始实例和容量；策略只读过去信息。不同系统的论文分数不放在同一排行榜。
- 包含无差异和失败情况，测试种子冻结后不调参。缺结果时保留假设，不填写预期提升数字。

当前候选假设与撤回条件见 [决策记录](decision-log.md)；原文歧义见 [主论文笔记](reading/01-main-paper.md)。

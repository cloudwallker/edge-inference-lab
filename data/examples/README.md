# 合成手工案例

`retention-case.csv` 是可手算的人工轨迹，不是生产服务数据。字段和单位为：`id`、`slot`、`source`、`model`、`min_accuracy`（0–1 标称准确率）、`deadline_ms`、`data_mb`。

配套配置为 [`retention-case.json`](../../configs/retention-case.json)：一个模拟节点、一档 R-FCN 240p、L=2、常驻底座一份。容量 4 vCPU 为教学设定，模型参数为原表报告值或范围中点；完整来源在配置 `provenance`。

slot 0 的四个请求期限为 450 ms，能进入 new 分支并组成一个额外实例。slot 1/2 没有请求。slot 3 的四个请求期限变为 100 ms，暖延迟为 29 ms，new 延迟为 179 ms。因此 θ=2 已在 slot 2 末释放额外实例，slot 3 只能接纳两次暖服务；θ=4 留下额外实例，能接纳四次。每个收益可从事件账本重算。

这验证保留机制确实被触发，不证明新算法优势。其两次到达的期限不同，不能当作“固定两个边际”的主研究轨迹；主研究使用 `generate_traces` 另行生成并核验配对控制。

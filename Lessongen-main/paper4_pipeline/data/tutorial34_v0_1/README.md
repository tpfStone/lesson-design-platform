# 教程 3/4 小规模集成测试数据集

这是用于组件开发和系统联调的 `tutorial34-v0.1-dev` 数据集，不是论文 Benchmark，也不是正式课程标准语料。

当前包含 5 个基础任务、每个任务中英双语，共 10 条开发实例：数学、英语、化学、科学、信息技术各 1 个。每条实例都有本地参考材料、预期大纲、事实锚点和风险点，可用于：

- 教程 3 多智能体流水线 smoke test；
- 教程 4 Autonomous/HITL 对照；
- 人工 `approve/edit/reject` 行为测试；
- 输入、节点输出、人工反馈与运行轨迹的 Schema 校验。

## 校验

在仓库根目录运行：

```bat
cd /d <仓库目录>\paper4_pipeline
python tutorials\common\validate_dataset.py --root data\tutorial34_v0_1
```

## 边界

- `sources/` 内容是项目自编的工程测试夹具，不代表任何官方教材或课程标准；
- 当前只有 `dev`，用于调试 Prompt 和流程；
- 冻结 `test` 集必须在学科人员审核真实来源后另行建立；
- 历史模型生成结果不得作为参考材料或标准答案混入本数据集。

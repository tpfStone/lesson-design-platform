# 真实模型验收记录（2026-09-15）

## 结论

Web Engine 已分别完成一次真实“生成”和一次真实“上传 Word 优化”，均调用 `deepseek-v4-flash`，进入正式 `PipelineService` / LangGraph，并以 `completed / quality_passed` 结束。自动测试不调用付费模型。

## 生成验收

- run：`20260911-152924-数学-高二-导数与函数的单调性-000001`
- 最佳/最后版本：`v0 / v0`
- 正式模型调用：4 次
- token：输入 20,684，输出 8,454
- 估算费用：$0.02026024
- 运行时间：约 345 秒
- Word：47,683 bytes
- SHA-256：`aa63a9fd332204c2b03b2764579e5a6266ef311e3a49594ded333da8e7d85e49`

## 优化验收

- run：`20260915-143053-数学-五年级-分数的意义-000004`
- 最佳/最后版本：`v1 / v1`
- 规范化器：1 次调用，输入 4,252、输出 1,427 token，估算 $0.00375452
- Pipeline：7 次调用，输入 62,392、输出 13,727 token，估算 $0.04557212
- Web 合计：8 次调用，输入 66,644、输出 15,154 token，估算 $0.04932664
- 运行时间：约 91 秒
- 改写映射：5 项 accepted 意见均形成可追溯的 implemented change
- 解析警告：7 项，已随结果保留，不被静默吞掉
- Word：46,781 bytes
- SHA-256：`43b9571316b6f842009e7e246c21f9801bbce94382e3f8a67872e32ee6228692`

## 配置与 Prompt 版本

- 模型配置：`configs/deepseek_v4_flash.json`
- 规范化器 Prompt：1.0
- Judge：1.3；Subject Critic：1.2；Pedagogy Critic：1.3；Alignment Critic：1.1；Validator：1.6；Rewriter：1.5

## 人工检查

- 两份 DOCX 已逐页渲染检查：生成稿 7 页，优化稿 5 页；未发现文字裁切、重叠、缺字、断裂表格或页眉页脚异常。
- 内部 Judge 分数仅用于 Pipeline 路由与版本比较，不代表真实课堂效果；教学有效性仍需教师/师范生实验验证。

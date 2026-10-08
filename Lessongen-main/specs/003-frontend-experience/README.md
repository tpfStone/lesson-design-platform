# 003 · 前端体验改进

状态：`S0–S5_LOCAL_IMPLEMENTED / RELEASE_GATES_PENDING`  
基线日期：2026-09-24  
目标视觉方向：**温润的专业教学工作台**  
实施仓库：`F:\comalesson\Lessongen`

本规格是 [001 Web MVP](../../web/specs/001-lesson-plan-web/README.md) 和 [002 工程改进](../002-project-improvement/README.md) 的增量，不重写教案生成逻辑或后端契约。用户体验的成功标准是：教师能快速开始、放心离开运行页、准确理解结果和未完成原因，并在手机上完成关键操作。

| 文档 | 用途 |
| --- | --- |
| [baseline.md](./baseline.md) | 已核实的现状、问题和不确定项 |
| [spec.md](./spec.md) | 用户目标、功能需求、非目标及验收标准 |
| [ui-system.md](./ui-system.md) | 视觉语言、状态反馈、动效及无障碍规范 |
| [plan.md](./plan.md) | 分阶段实现、技术选型、测试和回滚 |
| [tasks.md](./tasks.md) | 可执行任务与完成证据 |
| [s0-acceptance.md](./s0-acceptance.md) | 第一批实施与本地验收记录 |
| [s1-s4-acceptance.md](./s1-s4-acceptance.md) | 工作台、表单、运行页和结果页的实施及验收边界 |
| [s5-product-polish.md](./s5-product-polish.md) | 产品级精修的新增需求、设计目标与量化验收 |
| [s5-acceptance.md](./s5-acceptance.md) | 产品级精修的代码、浏览器和视觉本地验收及未完成发布门槛 |
| [evidence/](./evidence/) | 本地模拟接口场景截图，不代表真实教案质量 |

S0–S5 的前端修改及本地自动化验证已完成；发布前仍需真实后台任务、屏幕阅读器、200% 浏览器缩放、教师走查和真实用户性能数据。截图漂亮不等于功能完成。不得用动画伪造进度、用内部分数冒充教学效果，或把未实际修改的教案标成优化完成。

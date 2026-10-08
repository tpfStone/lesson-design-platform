# F1 API 协议 v1.0

本文档用于固定 F1「教案智能诊断 Agent」接入总平台时的接口与数据协议。

## 1. 固定结论

F1 在总平台中负责「教案评分、批注、诊断、报告生成」。

根据老师当前要求，F1 接入总平台时采用以下固定配置：

| 项目 | 固定值 | 说明 |
|---|---|---|
| 评分标准 | `student` | 只采用学生标准，不再暴露竞赛标准切换 |
| 提示词变体 | `v2_guided` | 采用引导流程版提示词 |
| 改进建议 | `suggest=true` | 默认生成细化建议 |
| 输出形式 | JSON + DOCX + MD + 已批注 DOCX/PDF | 前端展示 JSON，用户下载文件产物 |

因此，前端和主平台后端不需要让用户选择：

- `competition / student`
- `default / v2_guided / v3_strict`

这些选项由 F1 服务端内部固定。

## 2. 模块边界

### F1 负责

- 读取教案文本
- 调用 LLM 评分
- 按学生标准输出维度评分
- 生成批注列表
- 检索知识库与课标依据
- 生成细化建议
- 生成评分报告、评分清单、已批注文件

### 主平台负责

- 保存教案与版本
- 调用 F1 API
- 保存 F1 运行记录
- 将 F1 结果展示到 Vue 页面
- 把 F1 诊断结果交给 F2/F3/F4 继续使用

### Vue 前端负责

- 上传或选择教案版本
- 发起评分
- 展示总分、维度评分、批注详情、下载入口
- 不直接调用 F1 内部 Python 代码

推荐调用关系：

```text
Vue3 前端
  ↓
Spring Boot 主平台后端
  ↓
F1 FastAPI 适配层
  ↓
F1 原评分流程 run_annotation()
```

## 3. F1 学生标准维度

当前学生标准为 100 分制，维度如下：

| 维度 | 满分 |
|---|---:|
| 教学理念 | 5 |
| 课程思政 | 5 |
| 学情分析 | 5 |
| 教学目标 | 5 |
| 教学内容 | 10 |
| 教学资源 | 10 |
| 教学方法 | 10 |
| 过程设计 | 20 |
| 课堂互动 | 10 |
| 评价反馈 | 10 |
| 版式观感 | 5 |
| 结构完整 | 5 |

注意：前端不要写死 12 个卡片。应按 `dimensions` 或原始 `维度评分` 数组动态渲染，以便后续标准微调。

## 4. 接口总览

| 接口 | 方法 | 作用 |
|---|---|---|
| `/internal/v1/runs/annotate` | POST | 创建一次 F1 评分任务 |
| `/internal/v1/runs/{runId}` | GET | 查询任务状态 |
| `/internal/v1/runs/{runId}/result` | GET | 获取评分 JSON 结果 |
| `/internal/v1/runs/{runId}/artifacts/{kind}` | GET | 下载报告/批注文件 |

## 5. 创建评分任务

### POST `/internal/v1/runs/annotate`

主平台后端调用 F1。

### 请求参数

```json
{
  "lesson_id": "lesson_001",
  "version_id": "v0",
  "subject": "英语",
  "grade": "六年级",
  "topic": "Unit2 Last weekend",
  "content": "教案正文文本",
  "suggest": true
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `lesson_id` | string | 是 | 主平台中的教案 ID |
| `version_id` | string | 是 | 主平台中的教案版本 ID |
| `subject` | string | 建议 | 学科 |
| `grade` | string | 建议 | 年级 |
| `topic` | string | 建议 | 课题 |
| `content` | string | 是 | 教案正文 |
| `suggest` | boolean | 否 | 建议固定为 `true` |

### 服务端固定行为

即使请求中没有传，F1 服务端也应固定使用：

```json
{
  "criteria_type": "student",
  "variant": "v2_guided",
  "suggest": true
}
```

### 返回参数

```json
{
  "runId": "run_20261002_001",
  "lessonId": "lesson_001",
  "versionId": "v0",
  "status": "RUNNING"
}
```

### 状态枚举

| 状态 | 含义 |
|---|---|
| `QUEUED` | 已创建，等待执行 |
| `RUNNING` | 正在评分 |
| `COMPLETED` | 已完成 |
| `FAILED` | 失败 |

## 6. 查询任务状态

### GET `/internal/v1/runs/{runId}`

### 返回示例

```json
{
  "runId": "run_20261002_001",
  "lessonId": "lesson_001",
  "versionId": "v0",
  "status": "COMPLETED",
  "createdAt": "2026-10-02T02:50:00+08:00",
  "finishedAt": "2026-10-02T02:51:20+08:00",
  "artifacts": {
    "json": ".../评分清单.json",
    "md": ".../评分清单.md",
    "docx": ".../批注报告.docx",
    "docx_annotated": ".../已批注.docx"
  }
}
```

## 7. 获取评分结果

### GET `/internal/v1/runs/{runId}/result`

F1 原始结果保留中文字段，主平台可以在转发时转换为前端友好的英文结构。

### F1 原始结果结构

```json
{
  "教案基本信息": {
    "课题名称": "Unit2 Last weekend",
    "学科": "英语",
    "年级": "六年级",
    "课型": "新授课"
  },
  "总体评价": "整体评价文本",
  "维度评分": [
    {
      "维度名称": "教学理念",
      "满分": 5,
      "得分": 4,
      "得分理由": "理由文本",
      "批注列表": [
        {
          "位置": "教学目标部分",
          "原文引用": "原文片段",
          "评价": "基本达标",
          "具体分析": "分析文本",
          "建议": "诊断结论",
          "细化建议": "可操作修改建议",
          "依据来源": "教学设计理论 / 课标标准"
        }
      ]
    }
  ],
  "评分汇总": {
    "总分": 80,
    "各维度得分": {
      "教学理念": 4
    }
  }
}
```

### 推荐给前端的统一结构

```json
{
  "runId": "run_20261002_001",
  "lesson": {
    "lessonId": "lesson_001",
    "versionId": "v0",
    "subject": "英语",
    "grade": "六年级",
    "topic": "Unit2 Last weekend"
  },
  "config": {
    "criteria": "student",
    "variant": "v2_guided",
    "suggest": true
  },
  "score": {
    "total": 80,
    "maximum": 100
  },
  "summary": "整体评价文本",
  "dimensions": [
    {
      "name": "教学理念",
      "score": 4,
      "maxScore": 5,
      "rate": 0.8,
      "reason": "理由文本",
      "comments": [
        {
          "location": "教学目标部分",
          "quote": "原文片段",
          "level": "基本达标",
          "analysis": "分析文本",
          "diagnosis": "诊断结论",
          "suggestion": "可操作修改建议",
          "evidence": "教学设计理论 / 课标标准"
        }
      ]
    }
  ],
  "radar": {
    "labels": ["教学理念"],
    "values": [4],
    "maxValues": [5]
  },
  "artifacts": {
    "reportDocx": "/internal/v1/runs/run_20261002_001/artifacts/docx",
    "scoreJson": "/internal/v1/runs/run_20261002_001/artifacts/json",
    "scoreMarkdown": "/internal/v1/runs/run_20261002_001/artifacts/md",
    "annotatedDocx": "/internal/v1/runs/run_20261002_001/artifacts/docx_annotated"
  }
}
```

## 8. 下载产物

### GET `/internal/v1/runs/{runId}/artifacts/{kind}`

### kind 枚举

| kind | 文件 |
|---|---|
| `json` | 评分清单 JSON |
| `md` | 评分清单 Markdown |
| `docx` | 批注报告 Word |
| `docx_annotated` | 已批注 Word |
| `pdf` | 已批注 PDF，仅当原文件为 PDF 时存在 |

前端按钮建议：

- 下载评分报告
- 下载已批注教案
- 下载评分清单

## 9. 前端展示映射

| 页面区域 | 数据来源 |
|---|---|
| 总分卡片 | `score.total / score.maximum` |
| 总体评价 | `summary` |
| 雷达图 | `radar.labels + radar.values + radar.maxValues` |
| 六/多维评分表 | `dimensions[]` |
| 批注详情 | `dimensions[].comments[]` |
| 下载按钮 | `artifacts` |

批注详情建议展示顺序：

1. 位置
2. 原文引用
3. 评价等级
4. 具体分析
5. 诊断结论
6. 细化建议
7. 依据来源

## 10. 不建议变动的字段

以下字段进入 v1.0 后应尽量保持稳定：

| 字段 | 原因 |
|---|---|
| `runId` | 任务状态、结果、下载都依赖它 |
| `lessonId` | 与主平台教案表关联 |
| `versionId` | 与教案版本表关联 |
| `status` | 前端轮询和历史记录依赖 |
| `score.total` | 总分展示与排序依赖 |
| `dimensions[]` | F1/F2/F3/F4 共用诊断结果 |
| `dimensions[].comments[]` | 批注详情与后续优化建议依赖 |
| `artifacts` | 下载文件入口 |
| `config.criteria` | 固定记录为 `student` |
| `config.variant` | 固定记录为 `v2_guided` |

## 11. 当前 D1 开发结论

D1 阶段不再修改 F1 核心评分逻辑。

下一步应做：

1. 在 F1 API 适配层强制固定 `student + v2_guided + suggest=true`
2. 在主平台后端保存 `runId/status/result/artifacts`
3. 在 F2 Vue 前端开发 F1 结果展示页
4. 展示页按动态 `dimensions[]` 渲染，不写死维度数量
5. 演示文档统一称 F1 为「教案智能诊断 Agent」


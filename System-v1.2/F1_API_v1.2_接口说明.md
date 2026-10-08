# F1 API v1.2 接口说明

版本：F1-student-V3 平台适配版  
接口基址：`http://127.0.0.1:8002`

## 1. 固定评审口径

统一平台调用 F1 时固定采用：

- 评分标准：`student`
- 提示词：`v2_guided`
- `suggest`：默认 `true`

`criteriaType` 和 `variant` 不由前端传入，避免统一平台误切换标准。现有请求字段保持不变；`suggest` 字段仍保留，默认开启。

启动命令：

```bash
python -m uvicorn platform_api:app --host 127.0.0.1 --port 8002 --http h11
```

## 2. 接口清单

### GET `/internal/v1/health`

用途：检查 F1 API 是否存活，以及当前固定口径和模型 Key 配置状态。

成功响应示例：

```json
{
  "status": "up",
  "rubric": "F1-student-V3",
  "criteriaType": "student",
  "variant": "v2_guided",
  "suggestDefault": true,
  "mode": "real",
  "model_configured": true
}
```

兼容入口 `/health` 继续保留。

### POST `/internal/v1/runs/annotate`

用途：提交一份已经由统一平台保存的教案版本正文，创建异步评审任务。

请求字段保持现有接口不变：

```json
{
  "lesson_id": "lesson-001",
  "version_id": "version-007",
  "subject": "数学",
  "grade": "六年级",
  "topic": "分数加减法",
  "content": "教案正文……",
  "suggest": true
}
```

返回 HTTP 202，示例：

```json
{
  "runId": "<32位run id>",
  "lessonId": "lesson-001",
  "versionId": "version-007",
  "status": "QUEUED",
  "criteriaType": "student",
  "variant": "v2_guided",
  "suggest": true,
  "createdAt": "2026-10-04T00:00:00+00:00",
  "artifacts": {}
}
```

### GET `/internal/v1/runs/{runId}`

用途：查询任务状态。

状态流转：

```text
QUEUED → RUNNING → COMPLETED
                 ↘ FAILED
```

`COMPLETED` 后会在 `artifacts` 中返回下载地址映射。

### GET `/internal/v1/runs/{runId}/result`

用途：获取结构化评审结果。任务未完成时返回 HTTP 409。

平台兼容策略：

- `rubric.groups`：继续保留，兼容当前统一 Web；
- `rubric.dimensions`：新增，提供 12 个二级维度及 A/B/C；
- `gradingScale`：新增 A/B/C 含义；
- `files`：新增产物数组；
- `artifacts`：旧下载地址映射继续保留；
- `rawResult`：保留 F1 v1.2 原始中文结果结构；
- `lessonId/versionId`：继续原样回传。

结构示例：

```json
{
  "runId": "...",
  "lessonId": "lesson-001",
  "versionId": "version-007",
  "criteriaType": "student",
  "variant": "v2_guided",
  "suggest": true,
  "status": "COMPLETED",
  "score": {
    "total": 57,
    "maximum": 100
  },
  "summary": "...",
  "rubric": {
    "standard": "F1-student-V3",
    "score": 57,
    "maximum": 100,
    "groups": [
      {
        "name": "思想理念",
        "score": 7,
        "maximum": 10,
        "items": []
      }
    ],
    "dimensions": [
      {
        "name": "教学理念",
        "score": 5,
        "maximum": 5,
        "grade": "A"
      }
    ],
    "gradingScale": {
      "A": "达到该维度较高要求",
      "B": "基本达到要求，仍需改进",
      "C": "存在明显不足"
    }
  },
  "rawResult": {},
  "files": [
    {
      "kind": "json",
      "name": "lesson_评分清单.json",
      "url": "/internal/v1/runs/.../artifacts/json"
    }
  ],
  "artifacts": {
    "json": "/internal/v1/runs/.../artifacts/json"
  },
  "elapsedSeconds": 0
}
```

## 3. 六个一级维度

1. 思想理念：10 分
2. 学情与目标分析：10 分
3. 内容与方法：30 分
4. 过程与实施：30 分
5. 评价反馈：10 分
6. 文档规范：10 分

## 4. 十二个二级维度

| 二级维度 | 满分 | 所属一级维度 |
| --- | ---: | --- |
| 教学理念 | 5 | 思想理念 |
| 课程思政 | 5 | 思想理念 |
| 学情分析 | 5 | 学情与目标分析 |
| 教学目标 | 5 | 学情与目标分析 |
| 教学内容 | 10 | 内容与方法 |
| 教学资源 | 10 | 内容与方法 |
| 教学方法 | 10 | 内容与方法 |
| 过程设计 | 20 | 过程与实施 |
| 课堂互动 | 10 | 过程与实施 |
| 评价反馈 | 10 | 评价反馈 |
| 版式观感 | 5 | 文档规范 |
| 结构完整 | 5 | 文档规范 |

总分由 12 个二级维度得分重新求和，不再信任模型自行计算的总分字段。

## 5. A/B/C 等级规则

- 5 分维度：A=4–5，B=2–3，C=0–1；
- 10 分维度：A=8–10，B=5–7，C=0–4；
- 20 分维度：A=14–20，B=7–13，C=0–6。

等级由后处理代码按分数换算，不要求模型自行输出。每条批注的 `评价` 会统一覆盖为所属二级维度的 A/B/C，避免旧五档评价混入平台结果。

## 6. 下载接口

### GET `/internal/v1/runs/{runId}/artifacts/{kind}`

当前 v1.2 对 DOCX 教案通常可产生：

- `json`：评分清单 JSON；
- `docx`：批注报告 Word；
- `md`：Markdown 评分清单；
- `docx_annotated`：在教案 Word 上写入原生批注后的 Word。

接口只允许下载当前 `runId` 任务目录中的真实文件，不暴露任意本机路径。

## 7. OCR 范围

本轮统一平台仍只按现有文本/DOCX 链路接入，不开放 PDF 上传。因此：

- v1.2 的 OCR 检测、扫描 PDF 判断、EasyOCR 回退源码继续保留；
- `tools/install_ocr.bat` 与 OCR 说明文档继续保留；
- `easyocr` 仍为可选依赖，不写入默认安装依赖；
- DOCX 评审不依赖 OCR。

## 8. 统一 Web 对接提示

本包已经为总平台提供十二维雷达图所需的 `rubric.dimensions`：`name / score / maximum / grade`。雷达图建议使用 `score / maximum * 100` 的归一化得分率。

本轮没有修改 F2/F3/F4，也没有把 F1 的 Streamlit 批量页搬入统一 Web。统一 Web 的十二维雷达图、一级维度摘要卡和 A/B/C 彩色标签应在总项目窗口中完成 UI 对接。

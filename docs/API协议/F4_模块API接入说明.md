# F4 模块API接入说明

## 1. 模块说明

- 模块：F4（NoviceTeacher-AI / PedagoLoop）
- 功能定位：教案迭代优化、人机协同修改与版本管理。
- 当前状态：F4 原项目本身已经提供 FastAPI，不是本次整合过程中重新封装的。
- 当前已验证：F4 API 可以独立启动并通过 HTTP 被外部程序调用。
- 当前已完成与 F3 的自动联调。

---

## 2. API 是否为原项目自带

是。

F4 原项目源码中已经存在 FastAPI：

```python
app = FastAPI(title="PedagoLoop", version="0.2.0-alpha")
```

并且原项目已经定义了：

```text
POST /api/sessions
GET  /api/sessions/{session_id}/current-state
POST /api/sessions/{session_id}/suggestions
POST /api/sessions/{session_id}/suggestions/{suggestion_id}/decision
POST /api/sessions/{session_id}/complete-section
POST /api/sessions/{session_id}/rounds/{round_id}/continue
POST /api/sessions/{session_id}/terminate
GET  /api/sessions/{session_id}/final
GET  /api/sessions/{session_id}/export
```

因此：

```text
F4 API = 原项目已有
F4 → F3 Adapter = 本次整合中新开发
F4 → F3 自动联调 = 本次整合中新完成
```

---

## 3. F4 主流程

创建 session 的主流程可以概括为：

```text
POST /api/sessions
→ CreateSession 校验
→ Workflow.create_session()
→ 保存 LessonPlan
→ section_parser.parse()
→ 创建 Sections
→ 创建 SectionVersion
→ 创建 Round
→ 返回 current-state
```

获取当前状态：

```text
GET /api/sessions/{session_id}/current-state
→ Workflow.resume_session()
→ Workflow.get_current_state()
→ 返回 session / lesson_plan / round / sections / lesson_plan_versions
```

---

## 4. 启动方式

当前用户本地测试时，F4 使用：

```powershell
.\scripts\start.ps1 -Mock
```

当前实际验证的后端地址：

```text
http://127.0.0.1:8000
```

Swagger：

```text
http://127.0.0.1:8000/docs
```

健康检查：

```http
GET /api/health
```

---

## 5. 创建 Session

### API

```http
POST /api/sessions
```

### 请求结构

F4 `CreateSession` 要求：

```text
request_key: UUID
metadata:
    subject: str
    grade: str
    topic: str
    objective: optional
    textbook: optional
    additional_context: optional
content: str
```

### 已实际使用的请求示例

```json
{
  "request_key": "b71c7116-a459-48c4-9756-17e8d4fe888f",
  "metadata": {
    "subject": "数学",
    "grade": "四年级",
    "topic": "数字编码",
    "objective": "理解数字编码的基本规律",
    "textbook": "接口联调测试",
    "additional_context": "用于F4到F3接口联调"
  },
  "content": "教学目标\n理解数字编码的基本规律。\n\n情境导入\n教师展示生活中的身份证号码和邮政编码，引导学生思考数字的作用。\n\n新知探究\n教师引导学生观察不同编码，讨论每一位数字所表示的含义，并总结数字编码的基本规律。\n\n巩固练习\n学生尝试根据给出的规则设计自己的编号，并说明每一位数字代表的含义。\n\n课堂小结\n教师带领学生总结数字编码的特点以及数字编码在生活中的应用。"
}
```

### 返回结果

创建成功后，F4 不是只返回一个 ID，而是直接返回 current-state。

最外层结构实际验证为：

```json
{
  "session": {
    "id": "c16c8e7d-ee4a-4b75-b673-98fdcfa59f3a",
    "status": "ACTIVE",
    "current_round_number": 1
  },
  "lesson_plan": {
    "id": "7cc1d6df-b630-4a80-9697-4e4da67bf59d"
  },
  "round": {
    "id": "dbfc8eed-925b-4fc6-8d69-02f95fbee6a8",
    "round_number": 1,
    "status": "ACTIVE"
  },
  "sections": [
    "...省略..."
  ],
  "lesson_plan_versions": [
    "...省略..."
  ]
}
```

注意：

后续调用：

```text
/api/sessions/{session_id}/...
```

使用的是：

```text
session.id
```

本次测试中：

```text
c16c8e7d-ee4a-4b75-b673-98fdcfa59f3a
```

不是：

```text
request_key
participant_id
lesson_plan.id
round.id
current_section_id
```

---

## 6. 获取 Current State

### API

```http
GET /api/sessions/{session_id}/current-state
```

### 本次真实测试

请求：

```text
GET /api/sessions/c16c8e7d-ee4a-4b75-b673-98fdcfa59f3a/current-state
```

已实际返回：

```text
HTTP 200
```

### 返回主要结构

```json
{
  "session": {},
  "lesson_plan": {},
  "round": {},
  "sections": [],
  "lesson_plan_versions": []
}
```

---

## 7. sections 真实结构

本次真实测试中，F4 把教案解析成了 5 个 section：

```text
1. 教学目标
   section_type = objectives
   order_index = 0

2. 情境导入
   section_type = introduction
   order_index = 1

3. 新知探究
   section_type = exploration
   order_index = 2

4. 巩固练习
   section_type = practice
   order_index = 3

5. 课堂小结
   section_type = summary
   order_index = 4
```

单个真实 section 包含：

```json
{
  "lesson_plan_id": "...",
  "title": "情境导入",
  "order_index": 1,
  "section_type": "introduction",
  "parent_section_id": null,
  "current_content": "情境导入\n教师展示生活中的身份证号码和邮政编码，引导学生思考数字的作用。\n\n",
  "id": "31c69fe9-584e-4f52-95b0-c289b2cba787",
  "version": {},
  "review": {},
  "suggestions": []
}
```

F4 → F3 联调目前主要读取：

```text
id
title
order_index
section_type
current_content
```

---

## 8. 生成修改建议

### API

```http
POST /api/sessions/{session_id}/suggestions
```

请求模型：

```text
round_id
section_id
```

用途：

对当前 section 生成修改建议。

注意：

当前本地测试配置中 `provider` 为 `mock`，因此如果使用当前 Mock 配置生成建议，生成内容属于 Mock，而 API、Workflow、数据库状态流转仍是真实执行。

---

## 9. 接受 / 拒绝建议

### API

```http
POST /api/sessions/{session_id}/suggestions/{suggestion_id}/decision
```

请求字段包括：

```text
decision: ACCEPT / REJECT
confirm_append: bool
expected_version_id: optional UUID
```

接受建议后，F4 Workflow 会更新 section 内容并维护版本。

---

## 10. 其他已有 API

### 标记当前内容已查看

```http
POST /api/sessions/{session_id}/view
```

### 完成当前 section

```http
POST /api/sessions/{session_id}/complete-section
```

### 继续下一轮

```http
POST /api/sessions/{session_id}/rounds/{round_id}/continue
```

### 终止 session

```http
POST /api/sessions/{session_id}/terminate
```

### 获取最终状态

```http
GET /api/sessions/{session_id}/final
```

### 导出

```http
GET /api/sessions/{session_id}/export
```

### Session 历史

```http
GET /api/sessions
```

### Chat

```http
GET /api/sessions/{session_id}/chat
```

---

## 11. F4 → F3 Adapter

本次整合中新建：

```text
C:\Users\宸洱\Desktop\LLM教案系统\adapters\f4_f3_adapter.py
```

作用：

```text
F4 sections
→ 过滤适合课堂模拟的 section
→ 转成 F3 materials
```

当前允许进入 F3 的 section_type：

```text
introduction
exploration
teaching_process
practice
summary
```

本次真实测试：

```text
F4 sections = 5
F3 materials = 4
```

其中：

```text
objectives
```

被过滤。

---

## 12. F4 → F3 自动联调

自动脚本：

```text
C:\Users\宸洱\Desktop\LLM教案系统\run_f4_to_f3_auto.py
```

已实际运行命令：

```powershell
python run_f4_to_f3_auto.py --f4-url http://127.0.0.1:8000 --f4-session-id c16c8e7d-ee4a-4b75-b673-98fdcfa59f3a --message "学生回答：我觉得这些数字代表不同的信息。"
```

实际结果：

```text
F4 /current-state 状态码: 200
F4 sections 数量: 5
Adapter 转换后的 F3 materials 数量: 4
F3 /start 状态码: 200
F3 /message 状态码: 200
F3 /state 状态码: 200
```

因此目前已经确认：

```text
F4在线API
→ current-state
→ Adapter
→ F3 API
→ Classroom Agent
→ F3 state
```

整条链路实际跑通。

---

## 13. 是否真实

### F4 HTTP API

真实。

### F4 session 创建、section parsing、current-state

真实。

### F4 → F3 HTTP 联调

真实。

### 当前模型 Provider

当前测试 session 的配置为：

```text
provider = mock
```

因此：

- 系统状态流、HTTP、数据库流程是真实的。
- 当前使用 Mock provider 生成的模型建议不属于正式 LLM 结果。

---

## 14. 已知问题 / 当前限制

1. 当前联调使用的是 Mock provider。
2. 当前验证重点是 API 与模块间数据流，不是最终模型生成质量。
3. F4 → F3 目前通过独立 Adapter 完成，尚未并入最终 Gateway。
4. 当前测试使用固定的本地端口 8000；正式总平台中应通过配置管理服务地址，而不是在业务代码中写死。
5. 当前测试 UUID 均为一次测试产生的数据，正式代码不得写死这些测试 ID。
6. 目前 Vue 总平台尚未接入这些 API。

---

## 15. 给 Vue / Gateway 的接入结论

F4 原项目已经可以作为独立 HTTP 服务使用。

后续总平台不需要重新给 F4 封 API。

推荐：

```text
Vue
↓
Gateway / Workflow
↓
F4 HTTP API
↓
Adapter
↓
其他模块
```

而不是让 Vue 直接 import F4 Python 源码。

---

## 16. 当前完成状态

```text
主流程确认                         ✅
原有 FastAPI 确认                  ✅
启动方式与端口验证                 ✅
创建 Session API 验证              ✅
current-state API 验证             ✅
真实 sections 结构验证             ✅
请求 JSON 示例                     ✅
返回 JSON 示例                     ✅
最小 HTTP 测试                     ✅
F4 → F3 Adapter                    ✅
F4 → F3 自动 HTTP 联调             ✅
模块 API 接入说明                  ✅
```

结论：

```text
F4 本身原来就已经 API 化。
本次整合不需要重新封装 F4 API。
本次新增工作的重点是：
F4 输出分析 + F4→F3 Adapter + F4→F3 自动联调。
```

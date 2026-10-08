# F3 模块API接入说明

## 1. 模块说明

- 模块：F3（SimClass 课堂模拟多智能体系统）
- 目标：将原 CLI 课堂模拟能力封装成本地 HTTP API，供后续 Vue 总平台调用。
- 当前状态：API 开发联调版已完成并通过本地最小测试。
- 核心课堂决策、Manager、Executor、Agent 逻辑未重写；本次只增加 API 调用入口与单步返回能力。
- 当前 LLM：MockLLM，因此 HTTP/API 链路是真实运行，模型生成内容为 Mock。

---

## 2. 原项目主流程入口

原 CLI 入口：

```text
app/main.py
```

原主流程：

```text
main.py
→ 创建 Classroom
→ Classroom.run()
→ Manager.decide()
→ FunctionExecutor.execute()
→ Agent
→ LLM
→ DialogueEntry
→ ClassState
```

API 封装后仍复用原 `Classroom`、`Manager`、`FunctionExecutor`、Agent 与 `ClassState`。

---

## 3. API 相关文件

主要文件：

```text
SimClass-main/
└─ app/
   ├─ api/
   │  └─ classroom_api.py
   └─ classroom/
      ├─ classroom.py
      └─ classroom_v2.py
```

其中：

- `classroom_api.py`：FastAPI HTTP 接口。
- `classroom_v2.py`：给 Classroom 增加适合 HTTP 请求的单步 `step()` 调用。
- `classroom.py`：成功执行一轮后返回已有的 `DialogueEntry`，用于 API 返回；课堂决策算法未改变。

---

## 4. 启动方式

项目目录：

```text
C:\Users\宸洱\Desktop\LLM教案系统\SimClass-main
```

启动命令：

```powershell
python -m app.api.classroom_api
```

当前端口：

```text
8003
```

服务地址：

```text
http://127.0.0.1:8003
```

Swagger：

```text
http://127.0.0.1:8003/docs
```

---

## 5. API 接口

### 5.1 创建课堂

```http
POST /api/classroom/start
```

请求示例：

```json
{
  "lesson_id": "7cc1d6df-b630-4a80-9697-4e4da67bf59d",
  "materials": [
    {
      "id": 1,
      "title": "情境导入",
      "teaching_script": "教师展示生活中的身份证号码和邮政编码，引导学生思考数字的作用。",
      "key_points": []
    }
  ]
}
```

已验证返回示例：

```json
{
  "session_id": "b88c2f10-337b-42bf-ba16-457ce52c63ff",
  "status": "started"
}
```

---

### 5.2 发送课堂消息

```http
POST /api/classroom/message
```

请求示例：

```json
{
  "session_id": "b88c2f10-337b-42bf-ba16-457ce52c63ff",
  "message": "学生回答：我觉得这些数字代表不同的信息。"
}
```

已验证返回示例：

```json
{
  "speaker": "teacher",
  "function": "teach",
  "content": "[MockLLM] 下面开始讲解这一部分，先明确概念，再逐条讲要点，最后用例子帮助理解。（模拟回复）"
}
```

说明：

- HTTP 请求与课堂 Agent 调用链是真实运行。
- `content` 当前由 MockLLM 生成，因此内容属于 Mock。

---

### 5.3 查询课堂状态

```http
GET /api/classroom/{session_id}/state
```

已验证返回示例：

```json
{
  "session_id": "b88c2f10-337b-42bf-ba16-457ce52c63ff",
  "status": "active",
  "history": [
    {
      "speaker": "user",
      "function": "user_message",
      "content": "学生回答：我觉得这些数字代表不同的信息。"
    },
    {
      "speaker": "teacher",
      "function": "teach",
      "content": "[MockLLM] 下面开始讲解这一部分，先明确概念，再逐条讲要点，最后用例子帮助理解。（模拟回复）"
    }
  ]
}
```

内部真实历史字段为：

```text
dialogue_history
```

API 对外返回字段命名为：

```text
history
```

---

## 6. F3 输入结构

当前 `materials` 单项结构：

```json
{
  "id": 1,
  "title": "情境导入",
  "teaching_script": "教学脚本",
  "key_points": []
}
```

当前 F3 Agent 会使用：

- `title`
- `teaching_script`
- `key_points`

进行课堂上下文构造。

---

## 7. 最小测试结果

已经完成本地真实 HTTP 联调：

```text
POST /api/classroom/start    → 200
POST /api/classroom/message  → 200
GET  /api/classroom/{id}/state → 200
```

验证结果：

- 能创建课堂 session。
- 能向课堂发送用户消息。
- Manager / Executor / Agent 调用链能够运行。
- 能返回 `speaker / function / content`。
- 用户消息和 Agent 回复能够写入并查询课堂历史。

---

## 8. F4 → F3 联调状态

F4 原项目本身已有 FastAPI。

当前已完成：

```text
F4 GET /api/sessions/{session_id}/current-state
→ f4_f3_adapter.py
→ F3 materials
→ POST F3 /api/classroom/start
→ POST F3 /api/classroom/message
→ GET F3 /state
```

已实际自动联调成功。

自动联调脚本：

```text
C:\Users\宸洱\Desktop\LLM教案系统\run_f4_to_f3_auto.py
```

Adapter：

```text
C:\Users\宸洱\Desktop\LLM教案系统\adapters\f4_f3_adapter.py
```

---

## 9. 当前真实性说明

### API 是否真实

真实。

FastAPI 服务、HTTP 请求、session 创建、课堂状态更新、Manager/Executor/Agent 调用链均在本地实际运行。

### 模型输出是否真实

当前为 Mock。

返回文本带有：

```text
[MockLLM]
```

因此当前验证的是系统链路和 API 接口，而不是正式 LLM 生成质量。

---

## 10. 已知问题 / 当前限制

1. F3 session 当前保存在进程内存字典中，服务重启后 session 会丢失。
2. 当前 LLM 为 MockLLM。
3. 尚未增加生产级鉴权。
4. 尚未增加持久化的 API session 管理。
5. CLI `Classroom.run()` 会在初始化时自动进行第一轮决策；当前 HTTP `/start` 只负责创建课堂，课堂 Agent 响应主要由 `/message` 触发。
6. 当前为开发联调版 API，不等同于生产部署完成。

---

## 11. 给 Vue 总平台的调用结论

F3 当前已经可以通过 HTTP 被 Vue 总平台或 Gateway 调用。

建议后续总平台只依赖 HTTP API，不直接 import F3 内部 Python 代码。

当前可用基础链路：

```text
Vue / Gateway
→ POST /api/classroom/start
→ 获得 session_id
→ POST /api/classroom/message
→ GET /api/classroom/{session_id}/state
```

---

## 12. 当前完成状态

```text
主流程入口确认             ✅
FastAPI封装                ✅
启动命令与端口             ✅
API路径                    ✅
请求JSON示例               ✅
返回JSON示例               ✅
最小测试                   ✅
模块API接入说明            ✅
F4→F3自动联调              ✅
```

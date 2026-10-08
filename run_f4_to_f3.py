import json
import requests


F3_BASE_URL = "http://127.0.0.1:8003"


# ============================================================
# 1. 读取 F4 当前状态
# ============================================================

with open(
    "f4_state.json",
    "r",
    encoding="utf-8"
) as f:

    f4_state = json.load(f)


# ============================================================
# 2. 读取已经转换好的 F3 materials
# ============================================================

with open(
    "f3_materials.json",
    "r",
    encoding="utf-8"
) as f:

    materials_with_metadata = json.load(f)


# ============================================================
# 3. 生成严格符合 F3 API 的 materials
# ============================================================

materials = []

for item in materials_with_metadata:

    materials.append(
        {
            "id": item["id"],
            "title": item["title"],
            "teaching_script": item["teaching_script"],
            "key_points": item["key_points"]
        }
    )


# ============================================================
# 4. 获取真实 F4 lesson_plan id
# ============================================================

lesson_id = f4_state["lesson_plan"]["id"]


print("F4 lesson_id:")
print(lesson_id)

print()

print("准备发送给 F3 的 materials 数量:")
print(len(materials))


# ============================================================
# 5. 调用 F3 /start
# ============================================================

start_response = requests.post(
    f"{F3_BASE_URL}/api/classroom/start",

    json={
        "lesson_id": lesson_id,
        "materials": materials
    },

    timeout=30
)


print()
print("F3 /start 状态码:")
print(start_response.status_code)

print()
print("F3 /start 返回:")
print(start_response.text)


start_response.raise_for_status()


start_data = start_response.json()

session_id = start_data["session_id"]


# ============================================================
# 6. 给 F3 发送一条测试课堂消息
# ============================================================

message_response = requests.post(
    f"{F3_BASE_URL}/api/classroom/message",

    json={
        "session_id": session_id,
        "message": "学生回答：我觉得身份证号码中的数字都有不同的含义。"
    },

    timeout=30
)


print()
print("F3 /message 状态码:")
print(message_response.status_code)

print()
print("F3 /message 返回:")
print(message_response.text)


message_response.raise_for_status()


# ============================================================
# 7. 查询 F3 当前课堂状态
# ============================================================

state_response = requests.get(
    f"{F3_BASE_URL}/api/classroom/{session_id}/state",
    timeout=30
)


print()
print("F3 /state 状态码:")
print(state_response.status_code)

print()
print("F3 /state 返回:")

print(
    json.dumps(
        state_response.json(),
        ensure_ascii=False,
        indent=2
    )
)


print()
print("==========================================")
print("F4 -> Adapter -> F3 联调完成")
print("F3 session_id:", session_id)
print("==========================================")
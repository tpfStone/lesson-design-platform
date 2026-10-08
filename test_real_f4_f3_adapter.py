import json

from adapters.f4_f3_adapter import (
    convert_f4_sections_to_f3_materials
)


# 1. 读取 F4 真实 current-state
with open(
    "f4_state.json",
    "r",
    encoding="utf-8"
) as f:
    state = json.load(f)


# 2. 获取 sections
sections = state.get("sections")

if not isinstance(sections, list):
    raise ValueError(
        "F4 current-state 中没有找到有效的 sections 列表"
    )


print("F4 sections 数量：", len(sections))


# 3. F4 sections -> F3 materials
materials = convert_f4_sections_to_f3_materials(
    sections
)


print("F3 materials 数量：", len(materials))


# 4. 打印转换结果
print(
    json.dumps(
        materials,
        ensure_ascii=False,
        indent=2
    )
)


# 5. 保存转换结果
with open(
    "f3_materials.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        materials,
        f,
        ensure_ascii=False,
        indent=2
    )


print("已生成 f3_materials.json")
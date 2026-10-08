"""加载内置 demo course（不依赖外部数据库）。"""
import json
import os


def load_materials() -> list[dict]:
    path = os.path.join(os.path.dirname(__file__), "course.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)["materials"]

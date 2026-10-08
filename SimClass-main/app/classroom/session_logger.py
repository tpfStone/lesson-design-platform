"""SessionLogger —— 每轮保存决策与发言，最终写入 logs/session_YYYYMMDD_HHMMSS.json。"""
from __future__ import annotations

import json
import os
from datetime import datetime


class SessionLogger:
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.path = os.path.join(
            log_dir, f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        self.records: list[dict] = []
        self._turn_id = 0

    def log_turn(self, speaker: str, function: str, reason: str,
                 user_message, response: str, trigger_type=None,
                 consecutive_timeout_count=None, autonomous_mode=None) -> None:
        self._turn_id += 1
        self.records.append({
            "turn_id": self._turn_id,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "trigger_type": trigger_type,
            "consecutive_timeout_count": consecutive_timeout_count,
            "autonomous_mode": autonomous_mode,
            "speaker": speaker,
            "function": function,
            "reason": reason,
            "user_message": user_message,
            "response": response,
        })
        self.save()  # 每轮落盘，防止意外退出丢失

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.records, f, ensure_ascii=False, indent=2)

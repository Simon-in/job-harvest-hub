import json
import queue
import threading
from collections import defaultdict
from datetime import datetime
from typing import Any


class ProgressHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[queue.Queue[dict[str, Any]]]] = defaultdict(list)

    def subscribe(self, platform: str) -> queue.Queue[dict[str, Any]]:
        q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=200)
        with self._lock:
            self._subscribers[platform].append(q)
        return q

    def unsubscribe(self, platform: str, q: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            arr = self._subscribers.get(platform, [])
            if q in arr:
                arr.remove(q)

    def publish(self, platform: str, message: str, current: int | None = None, total: int | None = None) -> None:
        payload = {
            "platform": platform,
            "message": message,
            "current": current,
            "total": total,
            "ts": datetime.now().isoformat(timespec="seconds"),
        }
        with self._lock:
            targets = list(self._subscribers.get(platform, []))
        for q in targets:
            try:
                q.put_nowait(payload)
            except queue.Full:
                # 丢弃过载订阅者的最旧消息，尽量保留最新进度
                try:
                    q.get_nowait()
                    q.put_nowait(payload)
                except Exception:
                    pass

    @staticmethod
    def to_sse(payload: dict[str, Any], event: str = "progress") -> str:
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


progress_hub = ProgressHub()

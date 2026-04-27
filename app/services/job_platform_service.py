from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from threading import Event
from typing import Any

from app.services.progress_hub import progress_hub


@dataclass
class PlatformTaskState:
    platform: str
    running: bool = False
    last_error: str | None = None
    last_count: int = 0
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None


class JobPlatformService(ABC):
    def __init__(self, platform: str):
        self.platform = platform
        self.state = PlatformTaskState(platform=platform)
        self.stop_event = Event()

    @abstractmethod
    def start(self, payload: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError

    def status(self) -> PlatformTaskState:
        return self.state

    def emit_progress(self, message: str, current: int | None = None, total: int | None = None) -> None:
        progress_hub.publish(self.platform, message=message, current=current, total=total)

import json
import os
from dataclasses import dataclass, field

from core.deno_runner import run_deno_script

HOOK_EVENT_TASK_ADDED = "task_added"
HOOK_EVENT_TASK_COMPLETED = "task_completed"
HOOK_EVENT_TASK_FAILED = "task_failed"


@dataclass
class HookConfig:
    enabled: bool = False
    deno_path: str = ""
    script_path: str = ""
    events: list = field(default_factory=lambda: [HOOK_EVENT_TASK_ADDED, HOOK_EVENT_TASK_COMPLETED, HOOK_EVENT_TASK_FAILED])
    timeout_seconds: int = 6


def load_hook_config(config_path):
    if not config_path or not os.path.exists(config_path):
        return HookConfig()
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return HookConfig()

    if not isinstance(data, dict):
        return HookConfig()

    return HookConfig(
        enabled=bool(data.get("enabled", False)),
        deno_path=data.get("deno_path", "") or "",
        script_path=data.get("script_path", "") or "",
        events=list(data.get("events") or []),
        timeout_seconds=int(data.get("timeout_seconds") or 6),
    )


def dump_hook_payload(event_name, task):
    return {
        "event": event_name,
        "task": {
            "id": getattr(task, "id", ""),
            "status": getattr(task, "status", ""),
            "title": getattr(task, "final_title", "") or getattr(task, "get_display_name", lambda: "")(),
            "url": getattr(task, "url", ""),
            "task_type": getattr(task, "task_type", ""),
            "source_platform": getattr(task, "source_platform", ""),
            "output_path": getattr(task, "save_path", ""),
        },
    }


class HookDispatcher:
    def __init__(self, config_path, logger):
        self.config_path = config_path
        self.logger = logger
        self._config = load_hook_config(config_path)

    def reload(self):
        self._config = load_hook_config(self.config_path)

    def emit(self, event_name, task):
        config = self._config
        if not config.enabled:
            return
        if event_name not in (config.events or []):
            return
        payload = dump_hook_payload(event_name, task)
        result = run_deno_script(
            config.deno_path,
            config.script_path,
            payload,
            timeout=config.timeout_seconds,
        )
        if result.get("ok"):
            self.logger(f"[Hook] {event_name} executed ({result.get('duration', 0):.2f}s)")
        else:
            self.logger(
                f"[Hook] {event_name} failed: {result.get('stderr') or 'unknown'}",
                level="WARN",
            )
        if result.get("stdout"):
            self.logger(f"[Hook] stdout: {result['stdout'][:200]}")
        if result.get("stderr") and result.get("stderr") not in {"deno_not_found", "script_not_found", "timeout"}:
            self.logger(f"[Hook] stderr: {result['stderr'][:200]}", level="WARN")

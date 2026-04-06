import copy
import json
import os
import queue
import re
import subprocess
import threading
import time
from dataclasses import fields as dataclass_fields
from urllib.parse import urlparse

from core.history_repo import YouTubeHistoryRepository
from core.hooks import HookDispatcher, HOOK_EVENT_TASK_ADDED, HOOK_EVENT_TASK_COMPLETED, HOOK_EVENT_TASK_FAILED
from core.log_sink import LogFileSink
from core.settings import write_json_atomic
from core.youtube_metadata import detect_auth_diagnostic
from core.youtube_models import (
    AUDIO_FMT,
    TASK_STATUS_FAILED,
    TASK_STATUS_RUNNING,
    TASK_STATUS_STOPPED,
    TASK_STATUS_SUCCESS,
    TASK_STATUS_WAITING,
    URL_TYPE_YOUTUBE,
    YouTubeDownloadProfile,
    YouTubeTaskRecord,
)
from core.ytdlp_builder import build_ytdlp_command

YTDLP_PROGRESS_RE = re.compile(r'\[download\]\s+([\d.]+)%.*?at\s+([\d.]+)([KMG]?i?B/s)', re.IGNORECASE)
SECTION_RANGE_RE = re.compile(r'^\*(?P<start>(?:\d{1,2}:)?\d{1,2}:\d{2})-(?P<end>(?:\d{1,2}:)?\d{1,2}:\d{2})$')


def convert_to_MBps(value, unit):
    """将速度值转换为 MB/s。"""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return 0.0

    u = (unit or "").lower()
    if u in ('b/s', 'ib/s'):
        return num / 1024 / 1024
    if u in ('kib/s', 'kb/s'):
        return num / 1024
    if u in ('mib/s', 'mb/s'):
        return num
    if u in ('gib/s', 'gb/s'):
        return num * 1024
    return num


class YouTubeDownloadManager:
    """负责 YouTube 下载任务的调度、执行与历史写入。"""

    def __init__(
        self,
        app_instance,
        history_file,
        yt_dlp_path,
        ffmpeg_path,
        cookies_file_path,
        startupinfo=None,
        max_concurrent=2,
        mode='ytdlp',
    ):
        self.app = app_instance
        self.mode = mode
        self.max_concurrent = max_concurrent
        self.task_queue = []
        self.running_tasks = {}
        self._state_lock = threading.RLock()
        self._pending_ui_refresh = False
        self.sort_column = None
        self.sort_descending = False
        self._last_ui_refresh_ts = 0.0
        self._ui_refresh_interval = 0.1
        self.log_queue = queue.Queue()
        log_dir = os.path.join(os.path.dirname(os.path.abspath(history_file)), "logs")
        log_path = os.path.join(log_dir, "ycb_downloader.log")
        self.log_sink = LogFileSink(log_path)
        self.task_tree = None
        self.log_text = None
        self.input_frame = None
        self.history_repo = YouTubeHistoryRepository(history_file)
        self.yt_dlp_path = yt_dlp_path
        self.ffmpeg_path = ffmpeg_path
        self.cookies_file_path = cookies_file_path
        self.startupinfo = startupinfo
        self.force_cleanup = False
        self.pending_queue_path = os.path.join(os.path.dirname(os.path.abspath(history_file)), "pending_tasks.json")
        self.hook_dispatcher = HookDispatcher(
            os.path.join(os.path.dirname(os.path.abspath(history_file)), "hooks.json"),
            self.log,
        )

        if not self.history_repo.db_available and self.history_repo.init_error:
            summary = self.app.get_text("runtime_history_db_init_failed")
            self.record_runtime_issue(
                summary,
                self.history_repo.init_error,
                level="WARN",
            )
            self.log_queue.put((f"{summary}: {self.history_repo.init_error}", "WARN"))
        elif self.history_repo.db_available:
            self.log_queue.put((self.app.get_text("runtime_history_db_enabled").format(path=self.history_repo.db_path), "INFO"))

        self.log_queue.put((self.app.get_text("runtime_app_started"), "INFO"))
        self.log_queue.put((self.app.get_text("runtime_history_file").format(path=history_file), "INFO"))
        if self.yt_dlp_path:
            self.log_queue.put((self.app.get_text("runtime_yt_dlp_path").format(path=self.yt_dlp_path), "INFO"))
        if self.ffmpeg_path:
            self.log_queue.put((self.app.get_text("runtime_ffmpeg_path").format(path=self.ffmpeg_path), "INFO"))
        if self.cookies_file_path:
            self.log_queue.put((self.app.get_text("runtime_cookies_file").format(path=self.cookies_file_path), "INFO"))

    def log(self, message, level="INFO"):
        """写入日志队列。"""
        self.log_queue.put((message, level))
        try:
            self.log_sink.write(message, level=level)
        except Exception as exc:
            self.log_queue.put((self.app.get_text("runtime_log_write_failed").format(error=exc), "WARN"))

    def _queue_log(self, tag_key, message_key, fallback, level="INFO", **kwargs):
        tag = self.app.get_text(tag_key, "")
        message = self.app.get_text(message_key, fallback).format(**kwargs)
        prefix = f"[{tag}] " if tag else ""
        self.log(f"{prefix}{message}", level)

    def _runtime_text(self, value):
        text = str(value or "").strip()
        if not text:
            return ""
        return self.app.get_text(text, text)

    def save_pending_tasks(self):
        """保存等待中/运行中的任务快照，用于下次启动恢复。"""
        try:
            snapshot = self._build_pending_snapshot()
            if not snapshot:
                if os.path.exists(self.pending_queue_path):
                    os.remove(self.pending_queue_path)
                return
            write_json_atomic(self.pending_queue_path, snapshot)
        except Exception as exc:
            self.log_queue.put((self.app.get_text("runtime_pending_tasks_save_failed").format(error=exc), "WARN"))

    def load_pending_tasks(self):
        """加载上次未完成任务并恢复到等待队列。"""
        if not self.pending_queue_path or not os.path.exists(self.pending_queue_path):
            return 0
        try:
            with open(self.pending_queue_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            tasks = self._restore_pending_tasks(payload)
            restored_count = 0
            if tasks:
                with self._state_lock:
                    existing_ids = {getattr(t, "id", "") for t in self.task_queue}
                    existing_ids.update(self.running_tasks.keys())
                    for task in tasks:
                        if not getattr(task, "id", "") or task.id in existing_ids:
                            continue
                        task.stop_flag = False
                        if (task.archive_root or task.archive_subdir) and not task.save_path:
                            task.save_path = task.resolve_output_dir() or task.save_path
                        if not task.save_path:
                            task.save_path = getattr(self.app, "shared_save_dir_var", None).get() if getattr(self.app, "shared_save_dir_var", None) else ""
                        self.task_queue.append(task)
                        restored_count += 1
            os.remove(self.pending_queue_path)
            self._safe_after(0, self.update_list)
            return restored_count
        except Exception as exc:
            self.log_queue.put((self.app.get_text("runtime_pending_tasks_load_failed").format(error=exc), "WARN"))
            return 0

    def _build_pending_snapshot(self):
        with self._state_lock:
            candidates = list(self.task_queue) + list(self.running_tasks.values())
        candidates = sorted(
            candidates,
            key=lambda task: (getattr(task, "add_time", 0.0), getattr(task, "id", "")),
        )
        snapshot = []
        for task in candidates:
            if task.status in {TASK_STATUS_SUCCESS, TASK_STATUS_FAILED}:
                continue
            snapshot.append(self._serialize_task(task))
        return snapshot

    def _serialize_task(self, task):
        profile = getattr(task, "profile", None)
        profile_data = {}
        if profile:
            for field_def in dataclass_fields(YouTubeDownloadProfile):
                profile_data[field_def.name] = getattr(profile, field_def.name)
        return {
            "id": getattr(task, "id", ""),
            "url": getattr(task, "url", ""),
            "save_path": getattr(task, "save_path", ""),
            "task_type": getattr(task, "task_type", ""),
            "source_platform": getattr(task, "source_platform", URL_TYPE_YOUTUBE),
            "url_type": getattr(task, "url_type", URL_TYPE_YOUTUBE),
            "final_title": getattr(task, "final_title", None),
            "needs_cookies": bool(getattr(task, "needs_cookies", False)),
            "source_type": getattr(task, "source_type", ""),
            "source_name": getattr(task, "source_name", ""),
            "source_id": getattr(task, "source_id", ""),
            "channel_name": getattr(task, "channel_name", ""),
            "channel_id": getattr(task, "channel_id", ""),
            "upload_date": getattr(task, "upload_date", ""),
            "archive_root": getattr(task, "archive_root", ""),
            "archive_subdir": getattr(task, "archive_subdir", ""),
            "add_time": float(getattr(task, "add_time", 0.0) or 0.0),
            "status": getattr(task, "status", TASK_STATUS_WAITING),
            "progress": getattr(task, "progress", "0%"),
            "speed": getattr(task, "speed", "0 M/s"),
            "start_time": getattr(task, "start_time", None),
            "profile": profile_data,
        }

    def _restore_pending_tasks(self, payload):
        if not isinstance(payload, list):
            return []
        tasks = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            profile_data = item.get("profile", {})
            try:
                profile = YouTubeDownloadProfile(**profile_data)
            except Exception:
                profile = YouTubeDownloadProfile()
            task = YouTubeTaskRecord(
                url=item.get("url") or "",
                save_path=item.get("save_path") or "",
                profile=profile,
                task_type=item.get("task_type") or "ytdlp",
                source_platform=item.get("source_platform") or URL_TYPE_YOUTUBE,
                url_type=item.get("url_type") or URL_TYPE_YOUTUBE,
                id=item.get("id") or "",
            )
            task.final_title = item.get("final_title")
            task.needs_cookies = bool(item.get("needs_cookies"))
            task.source_type = item.get("source_type") or "manual"
            task.source_name = item.get("source_name") or ""
            task.source_id = item.get("source_id") or ""
            task.channel_name = item.get("channel_name") or ""
            task.channel_id = item.get("channel_id") or ""
            task.upload_date = item.get("upload_date") or ""
            task.archive_root = item.get("archive_root") or ""
            task.archive_subdir = item.get("archive_subdir") or ""
            original_status = item.get("status") or TASK_STATUS_WAITING
            task.progress = item.get("progress") or task.progress
            task.speed = item.get("speed") or task.speed
            task.start_time = item.get("start_time")
            setattr(task, "restored_from_status", original_status)
            setattr(task, "restored_from_snapshot", True)
            if original_status == TASK_STATUS_RUNNING:
                task.status = TASK_STATUS_WAITING
                restore_message = "上次退出时任务处于下载中，已恢复为等待中，可重新启动。"
                task.latest_error_summary = task.latest_error_summary or restore_message[:300]
                task.latest_error_detail = task.latest_error_detail or restore_message
            else:
                task.status = original_status
            try:
                task.add_time = float(item.get("add_time", task.add_time) or task.add_time)
            except (TypeError, ValueError):
                pass
            if task.url and task.url.strip():
                tasks.append(task)
        return tasks

    def record_runtime_issue(self, summary, detail="", level="WARN"):
        issue = {
            "summary": (summary or "").strip(),
            "detail": (detail or summary or "").strip(),
            "level": level,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.app.latest_runtime_issue = issue
        top_bar = getattr(self.app, "top_bar", None)
        refresh = getattr(top_bar, "refresh_runtime_status", None)
        if callable(refresh):
            self._safe_after(0, refresh)
        return issue

    def process_log_queue(self):
        """将日志队列刷新到文本框。"""
        if self.log_text is None:
            # UI 还没准备好，稍后再试，不弹出数据
            self._safe_after(100, self.process_log_queue)
            return

        try:
            while True:
                message, level = self.log_queue.get_nowait()
                if isinstance(message, bytes):
                    message = message.decode('utf-8', errors='replace')
                else:
                    message = str(message)
                display_level = "SUMMARY" if ("[摘要]" in message or "[Summary]" in message) else level
                self.log_text.insert("end", f"{message}\n", display_level)
                self.log_text.see("end")
        except queue.Empty:
            pass
        finally:
            try:
                self.log_sink.flush()
            except Exception as exc:
                self.log_queue.put((self.app.get_text("runtime_log_flush_failed").format(error=exc), "WARN"))
            self._safe_after(100, self.process_log_queue)

    def update_list(self):
        """刷新任务列表。"""
        if self.task_tree is None:
            return
        selected_ids = set(self.task_tree.selection())
        focused_id = self.task_tree.focus()
        yview = self.task_tree.yview()
        xview = self.task_tree.xview()
        all_tasks = self._snapshot_tasks_for_ui()
        existing_ids = set(self.task_tree.get_children(""))
        ordered_ids = []
        for index, task in enumerate(all_tasks):
            status_text = self.app.get_text({
                TASK_STATUS_WAITING: "task_status_waiting",
                TASK_STATUS_RUNNING: "task_status_running",
                TASK_STATUS_SUCCESS: "task_status_success",
                TASK_STATUS_FAILED: "task_status_failed",
                TASK_STATUS_STOPPED: "task_status_stopped",
            }.get(task.status, "task_status_waiting"))
            item_values = (
                task.id,
                status_text,
                task.progress,
                task.speed,
                task.get_display_name(),
                task.task_type,
            )
            ordered_ids.append(task.id)
            if task.id in existing_ids:
                self.task_tree.item(task.id, values=item_values)
                self.task_tree.move(task.id, "", index)
            else:
                self.task_tree.insert("", index, iid=task.id, values=item_values)
        stale_ids = existing_ids - set(ordered_ids)
        if stale_ids:
            self.task_tree.delete(*stale_ids)
        kept_selection = [item_id for item_id in ordered_ids if item_id in selected_ids]
        if kept_selection:
            self.task_tree.selection_set(kept_selection)
        else:
            self.task_tree.selection_remove(self.task_tree.selection())
        if focused_id and focused_id in ordered_ids:
            self.task_tree.focus(focused_id)
        if yview:
            self.task_tree.yview_moveto(yview[0])
        if xview:
            self.task_tree.xview_moveto(xview[0])

    def _schedule_update_list(self):
        if not self._can_schedule():
            return
        now = time.time()
        if self._pending_ui_refresh:
            return
        elapsed = now - self._last_ui_refresh_ts
        delay_ms = 0 if elapsed >= self._ui_refresh_interval else int((self._ui_refresh_interval - elapsed) * 1000)
        self._pending_ui_refresh = True

        def _run_refresh():
            self._pending_ui_refresh = False
            self._last_ui_refresh_ts = time.time()
            self.update_list()

        self._safe_after(delay_ms, _run_refresh)

    def _can_schedule(self):
        return bool(getattr(self.app, "root", None))

    def _safe_after(self, delay_ms, callback, *args):
        if not self._can_schedule() or not callback:
            return
        try:
            top_bar = getattr(self.app, "top_bar", None)
            if top_bar:
                if callback == top_bar.refresh_runtime_status or callback == top_bar.refresh_auth_status:
                    self.app.root.after(delay_ms, callback, *args)
                    return
            self.app.root.after(delay_ms, callback, *args)
        except Exception as exc:
            self.log_queue.put((self.app.get_text("runtime_ui_schedule_failed").format(error=exc), "WARN"))

    def _refresh_history_ui(self):
        try:
            if hasattr(self.app, "load_history"):
                self.app.load_history("ytdlp")
            history_page = getattr(self.app, "history_page", None)
            if history_page and hasattr(history_page, "refresh"):
                history_page.refresh()
        except Exception as exc:
            self.log_queue.put((self.app.get_text("runtime_history_ui_refresh_failed").format(error=exc), "WARN"))

    def _parse_progress_value(self, progress_text):
        text = str(progress_text or "").strip()
        match = re.search(r'([\d.]+)\s*%', text)
        if not match:
            return 0.0
        try:
            return float(match.group(1))
        except Exception:
            return 0.0

    def _task_sort_key(self, task, column):
        if column == "status":
            status_rank = {
                TASK_STATUS_RUNNING: 0,
                TASK_STATUS_WAITING: 1,
                TASK_STATUS_FAILED: 2,
                TASK_STATUS_STOPPED: 3,
                TASK_STATUS_SUCCESS: 4,
            }
            return (status_rank.get(getattr(task, "status", ""), 99), getattr(task, "add_time", 0.0), getattr(task, "id", ""))
        if column == "progress":
            return (self._parse_progress_value(getattr(task, "progress", "0%")), getattr(task, "add_time", 0.0), getattr(task, "id", ""))
        return (getattr(task, "add_time", 0.0), getattr(task, "id", ""))

    def _snapshot_tasks_for_ui(self):
        """生成 UI 列表用的任务快照。

        规则：
        - 默认保持“添加时间顺序”（add_time / id），不因为暂停/运行等状态变化而改变。
        - 点击列头时，仅在 UI 展示层面做排序（status / progress），不改变队列内部顺序。
        - 为避免 running_tasks(dict) 的无序性导致列表抖动，默认顺序统一按 add_time 排。
        """
        with self._state_lock:
            all_tasks = list(self.running_tasks.values()) + list(self.task_queue)

        # 列头排序（仅影响展示顺序）
        if self.sort_column in {"status", "progress"}:
            return sorted(
                all_tasks,
                key=lambda t: self._task_sort_key(t, self.sort_column),
                reverse=bool(self.sort_descending),
            )

        # 默认顺序：严格按添加时间（再按 id 兜底），保持稳定
        return sorted(
            all_tasks,
            key=lambda t: (getattr(t, "add_time", 0.0), getattr(t, "id", "")),
        )

    def set_sort(self, column):
        if column in {None, "", "default", "added"}:
            self.sort_column = None
            self.sort_descending = False
            self.update_list()
            return
        if column not in {"status", "progress"}:
            return
        if self.sort_column == column:
            self.sort_descending = not self.sort_descending
        else:
            self.sort_column = column
            self.sort_descending = False
        self.update_list()

    def add_task(self, task):
        """添加任务到等待队列。"""
        with self._state_lock:
            if any(getattr(existing, 'id', None) == task.id for existing in self.task_queue):
                self._queue_log("queue_log_tag_warn", "queue_log_duplicate_waiting_task", "已存在同 ID 等待任务，已跳过重复入队: [{task_id}]", "WARN", task_id=task.id)
                return False
            if task.id in self.running_tasks:
                self._queue_log("queue_log_tag_warn", "queue_log_duplicate_running_task", "任务正在运行中，已跳过重复入队: [{task_id}]", "WARN", task_id=task.id)
                return False
            self.task_queue.append(task)
        self.update_list()
        add_time_str = time.strftime("%H:%M:%S", time.localtime(task.add_time))
        self._queue_log("queue_log_tag_add", "queue_log_task_added", "任务已添加到队列 | 时间: {time}", "INFO", time=add_time_str)
        self.log(f" {self.app.get_text('queue_log_link', '链接: {url}').format(url=task.url)}", "INFO")
        self.log(f" {self.app.get_text('queue_log_title', '标题: {title}').format(title=task.get_display_name())}", "INFO")
        try:
            self.hook_dispatcher.emit(HOOK_EVENT_TASK_ADDED, task)
        except Exception as exc:
            self._queue_log("queue_log_tag_warn", "queue_log_task_added_hook_failed", "任务添加 Hook 执行失败: {error}", "WARN", error=exc)
        return True

    def start_next_task(self):
        """启动下一个等待中的任务。"""
        with self._state_lock:
            if len(self.running_tasks) >= self.max_concurrent:
                return False
            waiting_tasks = [t for t in self.task_queue if t.status == TASK_STATUS_WAITING]
            if not waiting_tasks:
                return False
            task = waiting_tasks[0]
            if task not in self.task_queue:
                return False
            self.task_queue.remove(task)
            self.running_tasks[task.id] = task
        threading.Thread(target=lambda: self.run_task(task), daemon=True).start()
        return True

    def _start_task_by_id(self, task_id):
        """优先启动指定的等待任务，不影响其他等待任务的顺序。"""
        if not task_id:
            return False
        with self._state_lock:
            if len(self.running_tasks) >= self.max_concurrent:
                return False
            task = None
            for existing in self.task_queue:
                if existing.id == task_id:
                    task = existing
                    break
            if task is None or task.status != TASK_STATUS_WAITING:
                return False
            self.task_queue.remove(task)
            self.running_tasks[task.id] = task
        threading.Thread(target=lambda: self.run_task(task), daemon=True).start()
        return True

    def start_all_tasks(self):
        """启动所有等待中的任务，直到达到并发上限。"""
        with self._state_lock:
            waiting_count = sum(1 for t in self.task_queue if t.status == TASK_STATUS_WAITING)
        if waiting_count == 0:
            self.log(self.app.get_text("queue_log_no_waiting_tasks", "没有等待中的任务"), "INFO")
            return
        self._queue_log("queue_log_tag_run", "queue_log_starting_waiting_tasks", "开始启动 {count} 个等待中的任务...", "INFO", count=waiting_count)
        while True:
            with self._state_lock:
                if len(self.running_tasks) >= self.max_concurrent:
                    break
            if not self.start_next_task():
                break

    def run_task(self, task):
        """运行单个任务。"""
        task.status = TASK_STATUS_RUNNING
        task.start_time = time.time()
        start_time_str = time.strftime("%H:%M:%S", time.localtime(task.start_time))
        self._queue_log("queue_log_tag_run", "queue_log_task_started", "任务开始运行 | 时间: {time}", "INFO", time=start_time_str)
        self.log(f" {self.app.get_text('queue_log_title', '标题: {title}').format(title=task.get_display_name())}", "INFO")
        
        self._safe_after(0, self.update_list)
        self._run_ytdlp_task(task)

        with self._state_lock:
            if task.id in self.running_tasks:
                del self.running_tasks[task.id]
            should_requeue = (
                task.status in {TASK_STATUS_SUCCESS, TASK_STATUS_FAILED, TASK_STATUS_STOPPED}
                and task not in self.task_queue
                and not getattr(task, "_delete_after_stop", False)
            )
            if should_requeue:
                self.task_queue.append(task)
        self._safe_after(0, self.update_list)
        self._safe_after(100, self.start_next_task)

    def _notify_auth_issue(self, diagnostic, used_cookies=False):
        if not diagnostic or diagnostic.ok:
            return
        self.app.latest_auth_diagnostic = diagnostic
        cookies_status = getattr(self.app, "latest_cookies_status", None)
        if cookies_status is not None:
            try:
                cookies_status.update_from_diagnostic(diagnostic, used_cookies=used_cookies)
            except Exception as exc:
                self._queue_log("queue_log_tag_warn", "queue_log_auth_sync_failed", "认证状态同步失败: {error}", "WARN", error=exc)
        summary_text = self._runtime_text(diagnostic.summary or self.app.get_text("queue_log_auth_issue_detected"))
        action_hint_text = self._runtime_text(getattr(diagnostic, "action_hint", ""))
        detail_text = self._runtime_text(getattr(diagnostic, "detail", "")) or action_hint_text or summary_text
        self.record_runtime_issue(
            summary_text or self.app.get_text("queue_log_auth_issue_detected"),
            detail_text,
            level="ERROR" if diagnostic.is_auth_related else "WARN",
        )
        self.log(f"[{self.app.get_text('queue_log_tag_error', '错误')}] {summary_text}", "ERROR" if diagnostic.is_auth_related else "WARN")
        if action_hint_text:
            self.log(f"[{self.app.get_text('queue_log_tag_hint', '提示')}] {action_hint_text}", "ERROR" if diagnostic.is_auth_related else "WARN")
        if diagnostic.is_auth_related:
            self._safe_after(0, lambda diag=diagnostic: self.app.notify_cookies_error(diag))
            top_bar = getattr(self.app, "top_bar", None)
            refresh_auth = getattr(top_bar, "refresh_auth_status", None)
            if callable(refresh_auth):
                self._safe_after(0, refresh_auth)

    def _refine_network_diagnostic(self, diagnostic):
        if not diagnostic or getattr(diagnostic, "category", "") != "network":
            return diagnostic
        raw_text = (getattr(diagnostic, "raw_output", "") or getattr(diagnostic, "detail", "") or "").lower()
        if not raw_text:
            return diagnostic

        if any(token in raw_text for token in ("http error 407", "proxy authentication required", "proxyconnect", "proxy tunnel request failed")):
            diagnostic.summary = "runtime_diag_proxy_auth_summary"
            diagnostic.action_hint = "runtime_diag_proxy_auth_hint"
            return diagnostic
        if any(token in raw_text for token in ("name resolution", "getaddrinfo failed", "failed to resolve", "temporary failure in name resolution")):
            diagnostic.summary = "runtime_diag_dns_summary"
            diagnostic.action_hint = "runtime_diag_dns_hint"
            return diagnostic
        if any(token in raw_text for token in ("ssl", "tls", "certificate verify failed", "ssl handshake failed")):
            diagnostic.summary = "runtime_diag_tls_summary"
            diagnostic.action_hint = "runtime_diag_tls_hint"
            return diagnostic
        if any(token in raw_text for token in ("timed out", "read timed out", "connection reset", "connection aborted", "connection refused", "network is unreachable")):
            diagnostic.summary = "runtime_diag_network_timeout_summary"
            diagnostic.action_hint = "runtime_diag_network_timeout_hint"
            return diagnostic
        return diagnostic

    def _build_command_summary(self, task, output_dir, command):
        preset_key = getattr(task.profile, "preset_key", "manual")
        format_expr = task.profile.format
        summary = {
            "task_id": task.id,
            "url": task.url,
            "preset_key": preset_key,
            "format": format_expr,
            "output_dir": output_dir,
            "audio_mode": preset_key == "audio_only" or format_expr == AUDIO_FMT,
            "use_cookies": bool(task.needs_cookies),
            "use_po_token": bool(getattr(task.profile, "use_po_token", False)),
            "merge_output_format": getattr(task.profile, "merge_output_format", "mp4"),
            "custom_filename": task.profile.custom_filename or "",
            "download_sections": getattr(task.profile, "download_sections", ""),
            "sponsorblock_enabled": bool(getattr(task.profile, "sponsorblock_enabled", False)),
            "sponsorblock_categories": getattr(task.profile, "sponsorblock_categories", ""),
            "proxy_url": getattr(task.profile, "proxy_url", ""),
            "advanced_args": getattr(task.profile, "advanced_args", ""),
            "cookies_mode": getattr(task.profile, "cookies_mode", "file"),
            "cookies_browser": getattr(task.profile, "cookies_browser", ""),
            "speed_limit": task.profile.speed_limit,
            "retry_interval": getattr(task.profile, "retry_interval", 0),
            "sleep_interval": getattr(task.profile, "sleep_interval", 0),
            "max_sleep_interval": getattr(task.profile, "max_sleep_interval", 0),
            "sleep_requests": getattr(task.profile, "sleep_requests", 0),
        }
        if command:
            safe_preview = " ".join(str(part) for part in command[:12])
            if len(command) > 12:
                safe_preview = f"{safe_preview} ..."
            summary["command_preview"] = safe_preview
        return summary
 
    def _mask_proxy_url_for_log(self, value):
        text = (value or "").strip()
        if not text:
            return ""
        try:
            parsed = urlparse(text)
            scheme = (parsed.scheme or "proxy").strip()
            host = (parsed.hostname or "").strip()
            port = parsed.port
            if host:
                host_label = host if len(host) <= 8 else f"{host[:4]}...{host[-2:]}"
                if port:
                    return f"{scheme}://{host_label}:{port}"
                return f"{scheme}://{host_label}"
        except Exception:
            pass
        return "configured"

    def _mask_browser_for_log(self, value):
        text = (value or "").strip().lower()
        return text if text in {"chrome", "edge", "firefox"} else "configured"

    def _mask_advanced_args_for_log(self, value):
        text = (value or "").strip()
        if not text:
            return ""
        token_count = len(text.split())
        return f"configured({token_count} tokens)"

    def _log_command_summary(self, task, output_dir, command):
        summary = self._build_command_summary(task, output_dir, command)
        self._queue_log("queue_log_tag_summary", "queue_log_prepare_command", "准备执行下载命令", "INFO")
        self._queue_log("queue_log_tag_summary", "queue_log_summary_main", "task_id={task_id} | preset={preset_key} | format={format} | audio={audio_mode}", "INFO", **summary)
        self._queue_log("queue_log_tag_summary", "queue_log_summary_url", "url={url}", "INFO", url=summary["url"])
        self._queue_log("queue_log_tag_summary", "queue_log_summary_output", "output={output_dir} | cookies={use_cookies} | po_token={use_po_token} | merge={merge_output_format}", "INFO", **summary)
        if summary.get("custom_filename"):
            self._queue_log("queue_log_tag_summary", "queue_log_summary_custom_filename", "custom_filename={custom_filename}", "INFO", custom_filename=summary["custom_filename"])
        if summary.get("download_sections"):
            self._queue_log("queue_log_tag_summary", "queue_log_summary_sections", "sections={download_sections}", "INFO", download_sections=summary["download_sections"])
        if summary.get("sponsorblock_enabled"):
            categories = summary.get("sponsorblock_categories") or "sponsor"
            self._queue_log("queue_log_tag_summary", "queue_log_summary_sponsorblock", "sponsorblock={categories}", "INFO", categories=categories)
        if summary.get("proxy_url"):
            self._queue_log("queue_log_tag_summary", "queue_log_summary_proxy", "proxy={proxy}", "INFO", proxy=self._mask_proxy_url_for_log(summary["proxy_url"]))
        if summary.get("cookies_mode") == "browser" and summary.get("cookies_browser"):
            self._queue_log("queue_log_tag_summary", "queue_log_summary_cookies_browser", "cookies_browser={cookies_browser}", "INFO", cookies_browser=self._mask_browser_for_log(summary["cookies_browser"]))
        if summary.get("advanced_args"):
            self._queue_log("queue_log_tag_summary", "queue_log_summary_advanced_args", "advanced_args={advanced_args}", "INFO", advanced_args=self._mask_advanced_args_for_log(summary["advanced_args"]))
        extra_options = []
        if summary.get("speed_limit"):
            extra_options.append(f"speed_limit={summary['speed_limit']}M")
        if summary.get("retry_interval"):
            extra_options.append(f"retry_interval={summary['retry_interval']}")
        if summary.get("sleep_interval"):
            extra_options.append(f"sleep_interval={summary['sleep_interval']}")
        if summary.get("max_sleep_interval"):
            extra_options.append(f"max_sleep_interval={summary['max_sleep_interval']}")
        if summary.get("sleep_requests"):
            extra_options.append(f"sleep_requests={summary['sleep_requests']}")
        if extra_options:
            self._queue_log("queue_log_tag_summary", "queue_log_summary_options", "options={options}", "INFO", options=", ".join(extra_options))
        if summary.get("command_preview"):
            self._queue_log("queue_log_tag_summary", "queue_log_summary_cmd_preview", "cmd_preview={command_preview}", "INFO", command_preview=summary["command_preview"])
        return summary

    def _classify_failure_stage(self, error_output_buffer):
        if not error_output_buffer:
            return "download"
        text = "\n".join(error_output_buffer).lower()
        postprocess_keywords = [
            "postprocessor",
            "post-process",
            "ffmpeg",
            "merging",
            "recode",
            "conversion",
        ]
        if any(keyword in text for keyword in postprocess_keywords):
            return "postprocess"
        return "download"

    def _parse_download_section_range(self, raw_value):
        match = SECTION_RANGE_RE.match((raw_value or "").strip())
        if not match:
            return None, None
        return match.group("start"), match.group("end")

    def _find_media_output(self, output_dir, base_name):
        if not os.path.isdir(output_dir):
            return ""
        media_exts = {".mp4", ".mkv", ".webm", ".m4a", ".mp3", ".opus", ".wav", ".flac", ".mov"}
        exact_candidates = []
        fuzzy_candidates = []
        for name in os.listdir(output_dir):
            full_path = os.path.join(output_dir, name)
            if not os.path.isfile(full_path):
                continue
            root, ext = os.path.splitext(name)
            if ext.lower() not in media_exts:
                continue
            target_bucket = None
            if root == base_name:
                target_bucket = exact_candidates
            elif root.startswith(base_name):
                target_bucket = fuzzy_candidates
            if target_bucket is None:
                continue
            try:
                stat = os.stat(full_path)
                target_bucket.append((stat.st_mtime, stat.st_size, full_path))
            except OSError:
                continue
        for bucket in (exact_candidates, fuzzy_candidates):
            if bucket:
                bucket.sort(key=lambda item: (item[0], item[1]), reverse=True)
                return bucket[0][2]
        return ""

    def _run_local_section_fallback(self, task, output_dir):
        section_value = getattr(task.profile, "download_sections", "") or ""
        start_time, end_time = self._parse_download_section_range(section_value)
        if not start_time or not end_time:
            return False, self.app.get_text("queue_log_section_fallback_parse_range_failed")

        temp_base = f"ycb_section_full_{task.id}"
        fallback_profile = copy.copy(task.profile)
        fallback_profile.download_sections = ""
        fallback_profile.custom_filename = temp_base
        fallback_profile.sponsorblock_enabled = False
        fallback_profile.sponsorblock_categories = ""
        fallback_profile.advanced_args = ""
        fallback_task = YouTubeTaskRecord(
            url=task.url,
            save_path=task.save_path,
            profile=fallback_profile,
            task_type=task.task_type,
            source_platform=getattr(task, "source_platform", URL_TYPE_YOUTUBE),
            url_type=getattr(task, "url_type", URL_TYPE_YOUTUBE),
        )
        fallback_task.needs_cookies = task.needs_cookies
        fallback_task.archive_root = getattr(task, "archive_root", "")
        fallback_task.archive_subdir = getattr(task, "archive_subdir", "")

        self._queue_log("queue_log_tag_fallback", "queue_log_section_fallback_start", "区段下载失败，尝试全量下载后本地裁剪: {range}", "WARN", range=f"{start_time}-{end_time}")
        if getattr(task.profile, "sponsorblock_enabled", False):
            self._queue_log("queue_log_tag_fallback", "queue_log_section_fallback_no_sponsorblock", "为提高成功率，区段 fallback 阶段暂不附加 SponsorBlock", "WARN")
        if getattr(task.profile, "advanced_args", ""):
            self._queue_log("queue_log_tag_fallback", "queue_log_section_fallback_no_advanced_args", "为提高成功率，区段 fallback 阶段暂不附加高级参数", "WARN")

        fallback_cmd = build_ytdlp_command(
            self.yt_dlp_path,
            self.ffmpeg_path,
            self.cookies_file_path,
            fallback_task,
        )

        try:
            proc = subprocess.run(
                fallback_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                startupinfo=self.startupinfo,
                timeout=1200,
            )
        except subprocess.TimeoutExpired:
            return False, self.app.get_text("queue_log_section_fallback_download_timeout")
        except Exception as exc:
            return False, self.app.get_text("queue_log_section_fallback_download_start_failed").format(error=exc)

        if proc.returncode != 0:
            output = (proc.stdout or "").strip().replace("\r", " ").replace("\n", " ")
            return False, self.app.get_text("queue_log_section_fallback_download_failed").format(output=output[:220])

        source_path = self._find_media_output(output_dir, temp_base)
        if not source_path:
            return False, self.app.get_text("queue_log_section_fallback_output_missing")

        final_base_raw = task.profile.custom_filename or (task.final_title or f"section_{task.id}")
        final_base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', final_base_raw).strip(' .')
        if not final_base:
            final_base = f"section_{task.id}"
        _, source_ext = os.path.splitext(source_path)
        target_path = os.path.join(output_dir, f"{final_base}{source_ext}")

        ffmpeg_cmd = [
            self.ffmpeg_path,
            "-y",
            "-ss",
            start_time,
            "-to",
            end_time,
            "-i",
            source_path,
            "-c",
            "copy",
            target_path,
        ]

        try:
            cut_proc = subprocess.run(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                startupinfo=self.startupinfo,
                timeout=600,
            )
        except subprocess.TimeoutExpired:
            return False, self.app.get_text("queue_log_section_fallback_cut_timeout")
        except Exception as exc:
            return False, self.app.get_text("queue_log_section_fallback_cut_failed").format(error=exc)

        if cut_proc.returncode != 0:
            output = (cut_proc.stdout or "").strip().replace("\r", " ").replace("\n", " ")
            return False, self.app.get_text("queue_log_section_fallback_ffmpeg_cut_failed").format(output=output[:220])

        try:
            if os.path.exists(source_path):
                os.remove(source_path)
        except OSError:
            pass

        task.archive_output_path = output_dir
        self._queue_log("queue_log_tag_done", "queue_log_section_fallback_success", "区段 fallback 裁剪成功: {filename}", "INFO", filename=os.path.basename(target_path))
        return True, ""

    def _cleanup_task_process(self, task, kill_timeout=3):
        proc = getattr(task, "process", None)
        if proc is None:
            return
        try:
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=kill_timeout)
                except Exception:
                    proc.kill()
                    try:
                        proc.wait(timeout=kill_timeout)
                    except Exception as exc:
                        self._queue_log("queue_log_tag_warn", "queue_log_process_wait_terminate_timeout", "进程等待终止超时: {error}", "WARN", error=exc)
        except Exception as exc:
            self._queue_log("queue_log_tag_warn", "queue_log_process_cleanup_failed", "进程清理失败: {error}", "WARN", error=exc)
        finally:
            try:
                if proc.stdout:
                    proc.stdout.close()
            except Exception as exc:
                self._queue_log("queue_log_tag_warn", "queue_log_process_stdout_close_failed", "进程输出流关闭失败: {error}", "WARN", error=exc)
            task.process = None

    def _prepare_task_title(self, task):
        if task.profile.custom_filename:
            task.final_title = task.profile.custom_filename
            self._queue_log("queue_log_tag_done", "queue_log_custom_filename_used", "使用自定义文件名: {title}", "INFO", title=task.final_title)
            return
        if task.final_title or task.stop_flag:
            return

        self._queue_log("queue_log_tag_fetch", "queue_log_fetch_title_start", "正在获取标题: [{task_id}]", "INFO", task_id=task.id)
        try:
            title_result = self.app.metadata_service.fetch_title(task.url)
            if title_result["used_cookies"]:
                task.needs_cookies = True
                self._queue_log("queue_log_tag_done", "queue_log_fetch_title_with_cookies", "已使用 cookies 成功获取标题", "INFO")
            else:
                self._queue_log("queue_log_tag_info", "queue_log_fetch_title_without_cookies", "标题获取未使用 cookies", "INFO")
            if title_result["returncode"] != 0:
                self._queue_log("queue_log_tag_warn", "queue_log_fetch_title_failed_continue", "标题获取失败，将记录诊断信息并继续进入下载阶段", "WARN")

            diagnostic = title_result.get("auth_diagnostic")
            if diagnostic and not diagnostic.ok:
                if getattr(diagnostic, "is_auth_related", False):
                    self._notify_auth_issue(diagnostic, used_cookies=task.needs_cookies)
                elif getattr(diagnostic, "summary", ""):
                    self.log(f"[{self.app.get_text('queue_log_tag_warn', '警告')}] {self._runtime_text(diagnostic.summary)}", "WARN")
                    if getattr(diagnostic, "action_hint", ""):
                        self.log(f"[{self.app.get_text('queue_log_tag_hint', '提示')}] {self._runtime_text(diagnostic.action_hint)}", "WARN")
                    if getattr(diagnostic, "detail", ""):
                        detail_preview = diagnostic.detail.strip().replace("\r", " ").replace("\n", " ")
                        self._queue_log("queue_log_tag_diagnostic", "queue_log_title_fetch_diagnostic", "标题获取诊断: {detail}", "INFO", detail=detail_preview[:180])

            if title_result["ok"] and title_result["title"]:
                task.final_title = title_result["title"]
                self._queue_log("queue_log_tag_done", "queue_log_title_fetch_success", "标题获取成功: [{task_id}] {title}", "INFO", task_id=task.id, title=f"{task.final_title[:40]}...")
            else:
                task.final_title = task.get_display_name()
                error_out = title_result["error_output"]
                self._queue_log("queue_log_tag_error", "queue_log_title_fetch_failed", "获取标题失败 (码:{code}),输出: {output}", "ERROR", code=title_result["returncode"], output=f"{error_out.strip()[:60]}...")
                if error_out.strip():
                    raw_preview = error_out.strip().replace("\r", " ").replace("\n", " ")
                    self._queue_log("queue_log_tag_log", "queue_log_title_fetch_raw", "标题获取原始日志: {output}", "INFO", output=raw_preview[:220])

                task.latest_error_detail = error_out.strip() if error_out.strip() else self.app.get_text("auth_summary_unknown")
                task.latest_error_summary = task.latest_error_detail[:300]
        except Exception as exc:
            task.final_title = task.get_display_name()
            task.latest_error_detail = str(exc)
            task.latest_error_summary = task.latest_error_detail[:300]
            self._queue_log("queue_log_tag_error", "queue_log_title_fetch_exception", "获取标题异常: {error},使用默认名称: {title}", "ERROR", error=exc, title=task.final_title)
        finally:
            self._safe_after(0, self.update_list)

    def _log_task_success(self, task, completed_message, hook_warn_message):
        task.status = TASK_STATUS_SUCCESS
        task.end_time = time.time()
        duration = task.end_time - (task.start_time or task.add_time)
        end_time_str = time.strftime("%H:%M:%S", time.localtime(task.end_time))
        self.log(self.app.get_text("queue_log_completed_with_timing").format(message=self._runtime_text(completed_message), time=end_time_str, duration=f"{duration:.1f}"), "INFO")
        self.log(f" {self.app.get_text('queue_log_title', '标题: {title}').format(title=task.get_display_name())}", "INFO")
        self._save_to_history(task)
        self._safe_after(0, self._refresh_history_ui)
        try:
            self.hook_dispatcher.emit(HOOK_EVENT_TASK_COMPLETED, task)
        except Exception as exc:
            self.log(f"[{self.app.get_text('queue_log_tag_warn', '警告')}] {self._runtime_text(hook_warn_message)}: {exc}", "WARN")
        self.log("-" * 40, "INFO")

    def _handle_final_download_failure(self, task, return_code, error_output_buffer):
        task.status = TASK_STATUS_FAILED
        task.end_time = time.time()
        duration = task.end_time - (task.start_time or task.add_time)
        end_time_str = time.strftime("%H:%M:%S", time.localtime(task.end_time))
        self._queue_log("queue_log_tag_error", "queue_log_task_download_failed", "任务下载失败 | 时间: {time} | 耗时: {duration}秒", "ERROR", time=end_time_str, duration=f"{duration:.1f}")
        self.log(f" {self.app.get_text('queue_log_title', '标题: {title}').format(title=task.get_display_name())}", "INFO")

        failure_summary = ""
        failure_stage = "download"
        if error_output_buffer:
            task.latest_error_detail = "\n".join(error_output_buffer)
            failure_summary = error_output_buffer[-1][:300]
            diagnostic = detect_auth_diagnostic(task.latest_error_detail)
            diagnostic = self._refine_network_diagnostic(diagnostic)
            if not diagnostic.ok:
                self._notify_auth_issue(diagnostic, used_cookies=task.needs_cookies)
                failure_summary = self._runtime_text(diagnostic.summary) or failure_summary
                failure_stage = "auth" if diagnostic.is_auth_related else "network"
            else:
                failure_stage = self._classify_failure_stage(error_output_buffer)
        task.latest_error_summary = failure_summary or self.app.get_text("queue_log_task_failed_summary").format(return_code=return_code)
        if not task.latest_error_detail:
            task.latest_error_detail = task.latest_error_summary
        self.record_runtime_issue(
            self.app.get_text("queue_log_task_failed_issue").format(title=task.get_display_name()),
            task.latest_error_summary,
            level="ERROR",
        )
        self._save_failed_history(
            task,
            failure_stage=failure_stage,
            failure_summary=task.latest_error_summary,
            return_code=return_code,
        )
        try:
            self.hook_dispatcher.emit(HOOK_EVENT_TASK_FAILED, task)
        except Exception as exc:
            self._queue_log("queue_log_tag_warn", "queue_log_failed_hook_failed", "失败 Hook 执行失败: {error}", "WARN", error=exc)
        self.log("-" * 40, "INFO")

    def _handle_runtime_exception(self, task, exc, is_last_attempt):
        task.latest_error_detail = str(exc)
        task.latest_error_summary = task.latest_error_detail[:300]
        self.record_runtime_issue(self.app.get_text("queue_log_runtime_exception_issue").format(title=task.get_display_name()), task.latest_error_summary, level="ERROR")
        self._queue_log("queue_log_tag_error", "queue_log_runtime_exception", "任务异常: [{task_id}] - {error}", "ERROR", task_id=task.id, error=exc)
        if not is_last_attempt:
            return
        task.status = TASK_STATUS_FAILED
        self._save_failed_history(
            task,
            failure_stage="runtime",
            failure_summary=task.latest_error_summary,
            return_code=None,
        )
        try:
            self.hook_dispatcher.emit(HOOK_EVENT_TASK_FAILED, task)
        except Exception as hook_exc:
            self._queue_log("queue_log_tag_warn", "queue_log_runtime_failed_hook_failed", "运行时失败 Hook 执行失败: {error}", "WARN", error=hook_exc)

    def _should_retry_attempt(self, task, attempt, max_retries):
        if task.stop_flag:
            task.status = TASK_STATUS_STOPPED
            self._queue_log("queue_log_tag_stop", "queue_log_task_stopped", "任务已停止: [{task_id}]", "INFO", task_id=task.id)
            return False
        if attempt <= 0:
            return True
        retry_summary = getattr(task, "latest_error_summary", "")
        if retry_summary:
            self._queue_log("queue_log_tag_warn", "queue_log_previous_failure_summary", "上次失败摘要: {summary}", "WARN", summary=self._runtime_text(retry_summary))
            self._queue_log("queue_log_tag_retry", "queue_log_retry_attempt", "[{task_id}] 第 {attempt}/{max_retries} 次", "INFO", task_id=task.id, attempt=attempt, max_retries=max_retries)
        time.sleep(5)
        return True

    def _reset_watchdog(self, task):
        now = time.time()
        task._last_output_ts = now
        task._last_progress_ts = now
        task._last_progress_value = task.progress

    def _watchdog_tick(self, task, timeout_idle, timeout_no_progress):
        if not task.process or task.process.poll() is not None:
            return True
        now = time.time()
        last_output = getattr(task, "_last_output_ts", now)
        last_progress = getattr(task, "_last_progress_ts", now)
        if timeout_idle and (now - last_output) > timeout_idle:
            self._queue_log("queue_log_tag_timeout", "queue_log_no_output_timeout", "下载无输出超过 {seconds}s: [{task_id}]", "WARN", seconds=timeout_idle, task_id=task.id)
            return False
        if timeout_no_progress and (now - last_progress) > timeout_no_progress:
            self._queue_log("queue_log_tag_timeout", "queue_log_no_progress_timeout", "下载无进度超过 {seconds}s: [{task_id}]", "WARN", seconds=timeout_no_progress, task_id=task.id)
            return False
        return True

    def _stream_download_output(self, task, error_output_buffer, timeout_idle, timeout_no_progress):
        if not task.process or not task.process.stdout:
            return True
        for line in task.process.stdout:
            if task.stop_flag:
                task.process.kill()
                return False
            line = line.strip()
            if not line:
                continue

            task._last_output_ts = time.time()

            if any(keyword in line.lower() for keyword in ['error', 'warning', 'failed', 'unavailable', 'forbidden', 'sign in']):
                error_output_buffer.append(line)

            match = YTDLP_PROGRESS_RE.search(line)
            if match:
                pct = match.group(1)
                speed_val = match.group(2)
                speed_unit = match.group(3)
                speed_mbps = convert_to_MBps(speed_val, speed_unit)
                task.progress = f"{pct}%"
                task.speed = f"{speed_mbps:.2f} M/s"
                if task.progress != getattr(task, "_last_progress_value", ""):
                    task._last_progress_ts = time.time()
                    task._last_progress_value = task.progress
                self._schedule_update_list()

            if not self._watchdog_tick(task, timeout_idle, timeout_no_progress):
                return False
        return True

    def _terminate_process(self, task, reason):
        if task.process and task.process.poll() is None:
            self._queue_log("queue_log_tag_terminate", "queue_log_terminating_process", "{reason}，准备结束进程: [{task_id}]", "WARN", reason=self._runtime_text(reason), task_id=task.id)
            try:
                task.process.terminate()
                task.process.wait(timeout=3)
            except Exception:
                try:
                    task.process.kill()
                except Exception:
                    pass
        return

    def _execute_download_attempt(self, task, cmd, output_dir, timeout_idle=300, timeout_no_progress=600):
        error_output_buffer = []
        os.makedirs(output_dir, exist_ok=True)
        task.archive_output_path = output_dir
        task.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1,
            startupinfo=self.startupinfo,
        )
        self._reset_watchdog(task)

        ok = self._stream_download_output(task, error_output_buffer, timeout_idle, timeout_no_progress)
        if not ok:
            self._terminate_process(task, self.app.get_text("queue_log_watchdog_timeout_reason"))
            error_output_buffer.append(self.app.get_text("queue_log_watchdog_timeout_error"))
            return 124, error_output_buffer
        if task.stop_flag:
            task.status = TASK_STATUS_STOPPED
            self._queue_log("queue_log_tag_stop", "queue_log_task_stopped", "任务已停止: [{task_id}]", "INFO", task_id=task.id)
            return None, error_output_buffer
        return_code = task.process.wait()
        return return_code, error_output_buffer

    def _build_download_command(self, task):
        try:
            cmd = build_ytdlp_command(
                self.yt_dlp_path,
                self.ffmpeg_path,
                self.cookies_file_path,
                task,
            )
            output_dir = task.resolve_output_dir() if hasattr(task, "resolve_output_dir") else task.save_path
            return cmd, output_dir
        except Exception as exc:
            task.status = TASK_STATUS_FAILED
            task.end_time = time.time()
            task.latest_error_detail = self.app.get_text("queue_log_command_build_failed_detail").format(error=exc)
            task.latest_error_summary = task.latest_error_detail[:300]
            self.record_runtime_issue(
                self.app.get_text("queue_log_command_build_failed_issue").format(title=task.get_display_name()),
                task.latest_error_summary,
                level="ERROR",
            )
            self._queue_log("queue_log_tag_error", "queue_log_command_build_failed", "命令构建失败: [{task_id}] - {error}", "ERROR", task_id=task.id, error=exc)
            self._save_failed_history(
                task,
                failure_stage="command_build",
                failure_summary=task.latest_error_summary,
                return_code=None,
            )
            return None, None

    def _handle_last_attempt_failure(self, task, output_dir, return_code, error_output_buffer):
        fallback_ok = False
        section_value = getattr(task.profile, "download_sections", "") or ""
        if section_value:
            fallback_ok, fallback_error = self._run_local_section_fallback(task, output_dir)
            if fallback_ok:
                self._log_task_success(task, "queue_log_section_fallback_completed", "queue_log_section_fallback_hook_failed")
                return True
            if fallback_error:
                error_output_buffer.append(fallback_error)
        self._handle_final_download_failure(task, return_code, error_output_buffer)
        return True

    def _run_ytdlp_task(self, task):
        """执行 yt-dlp 下载链路。"""
        self._prepare_task_title(task)
        
        # 移除重复的 "▶	开始下载" 日志，改为更详细的展示
        if task.needs_cookies:
            self.log(self.app.get_text("queue_log_task_uses_cookies"), "INFO")

        cmd, output_dir = self._build_download_command(task)
        if not cmd:
            return

        self._log_command_summary(task, output_dir, cmd)
        max_retries = task.profile.retries

        for attempt in range(max_retries + 1):
            if not self._should_retry_attempt(task, attempt, max_retries):
                return

            try:
                return_code, error_output_buffer = self._execute_download_attempt(
                    task,
                    cmd,
                    output_dir,
                    timeout_idle=getattr(task.profile, "timeout_idle", 300),
                    timeout_no_progress=getattr(task.profile, "timeout_no_progress", 600),
                )
                if return_code is None:
                    return
                if return_code == 0:
                    self._log_task_success(task, "queue_log_download_completed", "queue_log_completed_hook_failed")
                    return

                if attempt == max_retries:
                    self._handle_last_attempt_failure(task, output_dir, return_code, error_output_buffer)
                    return
            except Exception as exc:
                self._handle_runtime_exception(task, exc, attempt == max_retries)
                if attempt == max_retries:
                    return
            finally:
                self._cleanup_task_process(task)

    def _save_to_history(self, task):
        """将成功任务写入历史。"""
        try:
            db_saved = self.history_repo.save_task(task)
            archive_path = getattr(task, "archive_output_path", "") or getattr(task, "save_path", "")
            if archive_path:
                self.log(self.app.get_text("queue_log_archive_path").format(path=archive_path), "INFO")
            if db_saved:
                self.log(self.app.get_text("queue_log_saved_history_db"), "INFO")
            else:
                self.log(self.app.get_text("queue_log_saved_history_json"), "INFO")
        except Exception as exc:
            task.latest_error_summary = str(exc)[:300]
            self.record_runtime_issue(
                self.app.get_text("queue_log_save_history_failed_issue").format(title=task.get_display_name()),
                task.latest_error_summary,
                level="WARN",
            )
            self.log(self.app.get_text("queue_log_save_history_failed").format(error=exc), "WARN")

    def _save_failed_history(self, task, failure_stage="download", failure_summary="", return_code=None):
        """将失败任务写入历史。"""
        try:
            db_saved = self.history_repo.save_failed_task(
                task,
                failure_stage=failure_stage,
                failure_summary=failure_summary,
                return_code=return_code,
            )
            if db_saved:
                self.log(self.app.get_text("queue_log_saved_failed_history_db"), "INFO")
            else:
                self.log(self.app.get_text("queue_log_saved_failed_history_json"), "INFO")
        except Exception as exc:
            task.latest_error_summary = str(exc)[:300]
            self.record_runtime_issue(
                self.app.get_text("queue_log_save_history_failed_issue").format(title=task.get_display_name()),
                task.latest_error_summary,
                level="WARN",
            )
            self.log(self.app.get_text("queue_log_save_failed_history_failed").format(error=exc), "WARN")

    def stop_task(self, task_id):
        """停止指定任务。"""
        with self._state_lock:
            task = self.running_tasks.get(task_id)
        if not task:
            return
        task.stop_flag = True
        if task.process:
            try:
                pid = task.process.pid
                subprocess.run(
                    ['taskkill', '/F', '/T', '/PID', str(pid)],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=10,
                )
                try:
                    task.process.wait(timeout=3)
                except Exception as exc:
                    self._queue_log(
                        "queue_log_tag_warn",
                        "queue_log_wait_process_exit_timeout",
                        "等待任务进程退出超时: {error}",
                        "WARN",
                        error=exc,
                    )
            except Exception as exc:
                self.log(self.app.get_text("queue_log_terminate_process_error").format(error=exc), "WARN")
            finally:
                self._cleanup_task_process(task)
        self._queue_log("queue_log_tag_stop", "queue_log_stopping_task", "正在停止任务: [{task_id}]", "INFO", task_id=task.id)
        return

    def stop_all(self):
        """停止所有运行中的任务。"""
        with self._state_lock:
            task_ids = list(self.running_tasks.keys())
        for task_id in task_ids:
            self.stop_task(task_id)

    def clear_completed(self):
        """清理已结束任务。"""
        with self._state_lock:
            remaining = []
            for task in self.task_queue:
                if task.status == TASK_STATUS_SUCCESS:
                    continue
                remaining.append(task)
            self.task_queue = remaining
        self.update_list()

    def _collect_tasks_by_ids(self, task_ids):
        target_ids = {str(task_id or "").strip() for task_id in (task_ids or []) if str(task_id or "").strip()}
        if not target_ids:
            return [], set()
        with self._state_lock:
            task_map = {task.id: task for task in list(self.running_tasks.values()) + list(self.task_queue)}
            running_ids = {task_id for task_id in target_ids if task_id in self.running_tasks}
        tasks = [task_map[task_id] for task_id in target_ids if task_id in task_map]
        return tasks, running_ids

    def _delete_tasks(self, task_ids):
        tasks, running_ids = self._collect_tasks_by_ids(task_ids)
        if not tasks:
            return 0, 0

        for task in tasks:
            setattr(task, "_delete_after_stop", True)

        for task_id in running_ids:
            self.stop_task(task_id)

        target_ids = {task.id for task in tasks}
        with self._state_lock:
            for task_id in target_ids:
                self.running_tasks.pop(task_id, None)
            self.task_queue = [queued for queued in self.task_queue if queued.id not in target_ids]

        removed_file_count = 0
        for task in tasks:
            if not self._should_cleanup_related_files_on_delete(task):
                continue
            removed_file_count += len(self._delete_task_related_files(task))

        self.update_list()
        return len(tasks), removed_file_count

    def _should_cleanup_related_files_on_delete(self, task):
        status = getattr(task, "status", None)
        if status in {TASK_STATUS_SUCCESS, TASK_STATUS_FAILED}:
            return False
        return True

    def _get_single_selected_task_id(self, task_tree):
        if task_tree is None:
            return ""
        selection = task_tree.selection()
        if selection:
            return selection[0]
        focus_id = task_tree.focus()
        return focus_id or ""

    def retry_task(self, task_tree):
        """重试选中的失败/停止任务。"""
        task_id = self._get_single_selected_task_id(task_tree)
        if not task_id:
            return
        task = self._find_task(task_id)
        if not task:
            return
        if task.status in {TASK_STATUS_FAILED, TASK_STATUS_STOPPED}:
            task.status = TASK_STATUS_WAITING
            task.progress = "0%"
            task.speed = "0 M/s"
            task.stop_flag = False
            with self._state_lock:
                if task_id not in self.running_tasks and task not in self.task_queue:
                    self.task_queue.append(task)
        self.update_list()
        if task.status == TASK_STATUS_WAITING:
            self._start_task_by_id(task_id)

    def stop_selected(self, task_tree):
        """停止选中的运行任务。"""
        task_id = self._get_single_selected_task_id(task_tree)
        if task_id:
            self.stop_task(task_id)

    def _get_task_output_dir(self, task):
        output_dir = (getattr(task, "archive_output_path", "") or "").strip()
        if output_dir:
            return output_dir
        try:
            if hasattr(task, "resolve_output_dir"):
                output_dir = (task.resolve_output_dir() or "").strip()
        except Exception:
            output_dir = ""
        if output_dir:
            return output_dir
        return (getattr(task, "save_path", "") or "").strip()

    def _build_filename_stem_variants(self, value):
        text = (value or "").strip()
        if not text:
            return set()
        variants = {text}
        underscore_variant = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', text).strip(' .')
        if underscore_variant:
            variants.add(underscore_variant)
        fullwidth_map = str.maketrans({
            '<': '＜',
            '>': '＞',
            ':': '：',
            '"': '＂',
            '/': '／',
            '\\': '＼',
            '|': '｜',
            '?': '？',
            '*': '＊',
        })
        fullwidth_variant = text.translate(fullwidth_map).strip(' .')
        if fullwidth_variant:
            variants.add(fullwidth_variant)
        return {item for item in variants if item}

    def _matches_task_stem(self, stem, stem_candidates):
        text = (stem or "").strip()
        if not text:
            return False
        if text in stem_candidates:
            return True

        for candidate in stem_candidates:
            if not candidate:
                continue
            prefix = f"{candidate}."
            if not text.startswith(prefix):
                continue
            suffix = text[len(prefix):]
            if re.match(r"^f\d+(?:\.[A-Za-z0-9_-]+)?$", suffix, re.IGNORECASE):
                return True
            if re.match(r"^f\d+\.[A-Za-z0-9_-]+(?:\.part)?$", suffix, re.IGNORECASE):
                return True
            if re.match(r"^fhls[_-][A-Za-z0-9_.-]+$", suffix, re.IGNORECASE):
                return True
            if re.match(r"^frag\d+$", suffix, re.IGNORECASE):
                return True
            if re.match(r"^part-frag\d+$", suffix, re.IGNORECASE):
                return True
        return False

    def _is_task_output_artifact(self, file_name, stem_candidates):
        lowered = (file_name or "").lower()
        if lowered.endswith(".ytdl"):
            stem = file_name[:-5]
            return self._matches_task_stem(stem, stem_candidates)
        if lowered.endswith(".info.json"):
            stem = file_name[:-10]
            return self._matches_task_stem(stem, stem_candidates)

        stem, ext = os.path.splitext(file_name)
        if not self._matches_task_stem(stem, stem_candidates):
            return False

        safe_extensions = {
            ".mp4", ".mkv", ".webm", ".m4a", ".mp3", ".opus", ".wav", ".flac",
            ".jpg", ".jpeg", ".png", ".webp", ".info.json", ".description",
            ".vtt", ".srt", ".ass", ".lrc", ".ttml", ".sbv",
            ".part", ".temp", ".tmp",
        }
        return ext.lower() in safe_extensions

    def _delete_task_related_files(self, task):
        output_dir = self._get_task_output_dir(task)
        if not output_dir or not os.path.isdir(output_dir):
            return []

        stem_candidates = set()
        custom_name = getattr(getattr(task, "profile", None), "custom_filename", "") or ""
        stem_candidates.update(self._build_filename_stem_variants(custom_name))
        stem_candidates.update(self._build_filename_stem_variants(getattr(task, "final_title", "") or ""))

        temp_prefix = f"ycb_section_full_{task.id}"
        removed = []
        for name in os.listdir(output_dir):
            full_path = os.path.join(output_dir, name)
            if not os.path.isfile(full_path):
                continue

            should_delete = name.startswith(temp_prefix) or self._is_task_output_artifact(name, stem_candidates)
            if not should_delete:
                continue
            try:
                os.remove(full_path)
                removed.append(full_path)
            except OSError as exc:
                self.log(self.app.get_text("queue_log_delete_related_files_failed").format(path=full_path, error=exc), "WARN")
        return removed

    def delete_selected(self, task_tree):
        """删除选中的任务。"""
        task_id = self._get_single_selected_task_id(task_tree)
        if not task_id:
            return
        removed_tasks, removed_file_count = self._delete_tasks([task_id])
        if removed_tasks and removed_file_count:
            self._queue_log(
                "queue_log_tag_cleanup",
                "queue_log_deleted_related_files",
                "已删除任务关联文件 {count} 个: [{task_id}]",
                "INFO",
                count=removed_file_count,
                task_id=task_id,
            )

    def delete_all_tasks(self):
        """删除全部任务；已完成/失败任务保留本地文件，其余任务清理关联缓存/临时文件。"""
        with self._state_lock:
            all_task_ids = [task.id for task in list(self.running_tasks.values()) + list(self.task_queue)]
        if not all_task_ids:
            return

        confirmed = self.app.SilentMessagebox.askyesno(
            self.app.get_text("queue_delete_all_confirm_title"),
            self.app.get_text("queue_delete_all_confirm_message"),
            parent=getattr(self.app, "root", None),
        )
        if not confirmed:
            return

        removed_tasks, removed_file_count = self._delete_tasks(all_task_ids)
        if removed_tasks:
            self._queue_log("queue_log_tag_cleanup", "queue_log_deleted_all_tasks", "已删除全部任务 {count} 个", "INFO", count=removed_tasks)
        if removed_file_count:
            self._queue_log("queue_log_tag_cleanup", "queue_log_deleted_all_related_files", "删除全部任务时已清理任务关联文件 {count} 个", "INFO", count=removed_file_count)

    def _find_task(self, task_id):
        with self._state_lock:
            if task_id in self.running_tasks:
                return self.running_tasks[task_id]
            for task in self.task_queue:
                if task.id == task_id:
                    return task
        return None

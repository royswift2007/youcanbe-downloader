import os
import queue
import re
import subprocess
import threading
import time

from core.history_repo import YouTubeHistoryRepository
from core.youtube_metadata import detect_auth_diagnostic
from core.youtube_models import (
    TASK_STATUS_FAILED,
    TASK_STATUS_RUNNING,
    TASK_STATUS_STOPPED,
    TASK_STATUS_SUCCESS,
    TASK_STATUS_WAITING,
)
from core.ytdlp_builder import build_ytdlp_command

YTDLP_PROGRESS_RE = re.compile(r'\[download\]\s+([\d.]+)%.*?at\s+([\d.]+)([KMG]?i?B/s)', re.IGNORECASE)


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
        self.log_queue = queue.Queue()
        self.task_tree = None
        self.log_text = None
        self.input_frame = None
        self.history_repo = YouTubeHistoryRepository(history_file)
        self.yt_dlp_path = yt_dlp_path
        self.ffmpeg_path = ffmpeg_path
        self.cookies_file_path = cookies_file_path
        self.startupinfo = startupinfo
        self.force_cleanup = False

        if not self.history_repo.db_available and self.history_repo.init_error:
            self.record_runtime_issue(
                "历史数据库初始化失败，已回退 JSON 历史",
                self.history_repo.init_error,
                level="WARN",
            )
            self.log_queue.put((f"历史数据库初始化失败，已回退 JSON 历史: {self.history_repo.init_error}", "WARN"))
        elif self.history_repo.db_available:
            self.log_queue.put((f"历史数据库已启用: {self.history_repo.db_path}", "INFO"))

    def log(self, message, level="INFO"):
        """写入日志队列。"""
        self.log_queue.put((message, level))

    def record_runtime_issue(self, summary, detail="", level="WARN"):
        issue = {
            "summary": (summary or "").strip(),
            "detail": (detail or summary or "").strip(),
            "level": level,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.app.latest_runtime_issue = issue
        if hasattr(self.app, 'top_bar'):
            try:
                self.app.root.after(0, self.app.top_bar.refresh_runtime_status)
            except Exception:
                pass
        return issue

    def process_log_queue(self):
        """将日志队列刷新到文本框。"""
        if self.log_text is None:
            # UI 还没准备好，稍后再试，不弹出数据
            if hasattr(self.app, 'root') and self.app.root:
                self.app.root.after(100, self.process_log_queue)
            return

        try:
            while True:
                message, level = self.log_queue.get_nowait()
                if isinstance(message, bytes):
                    message = message.decode('utf-8', errors='replace')
                else:
                    message = str(message)
                self.log_text.insert("end", f"{message}\n", level)
                self.log_text.see("end")
        except queue.Empty:
            pass
        finally:
            if hasattr(self.app, 'root') and self.app.root:
                self.app.root.after(100, self.process_log_queue)

    def update_list(self):
        """刷新任务列表。"""
        if self.task_tree is None:
            return
        self.task_tree.delete(*self.task_tree.get_children())
        all_tasks = list(self.running_tasks.values()) + list(self.task_queue)
        for task in all_tasks:
            self.task_tree.insert(
                "",
                "end",
                iid=task.id,
                values=(
                    task.id,
                    task.status,
                    task.progress,
                    task.speed,
                    task.get_display_name(),
                    task.task_type,
                ),
            )

    def add_task(self, task):
        """添加任务到等待队列。"""
        if any(getattr(existing, 'id', None) == task.id for existing in self.task_queue):
            self.log(f"[警告] 已存在同 ID 等待任务，已跳过重复入队: [{task.id}]", "WARN")
            return False
        if task.id in self.running_tasks:
            self.log(f"[警告] 任务正在运行中，已跳过重复入队: [{task.id}]", "WARN")
            return False
        self.task_queue.append(task)
        self.update_list()
        add_time_str = time.strftime("%H:%M:%S", time.localtime(task.add_time))
        self.log(f"[添加] 任务已添加到队列 | 时间: {add_time_str}")
        self.log(f" 链接: {task.url}")
        self.log(f" 标题: {task.get_display_name()}")
        return True

    def start_next_task(self):
        """启动下一个等待中的任务。"""
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

    def start_all_tasks(self):
        """启动所有等待中的任务，直到达到并发上限。"""
        waiting_count = sum(1 for t in self.task_queue if t.status == TASK_STATUS_WAITING)
        if waiting_count == 0:
            self.log("没有等待中的任务")
            return
        self.log(f"[开始] 开始启动 {waiting_count} 个等待中的任务...")
        while len(self.running_tasks) < self.max_concurrent:
            if not self.start_next_task():
                break

    def run_task(self, task):
        """运行单个任务。"""
        task.status = TASK_STATUS_RUNNING
        task.start_time = time.time()
        start_time_str = time.strftime("%H:%M:%S", time.localtime(task.start_time))
        self.log(f"[运行] 任务开始运行 | 时间: {start_time_str}")
        self.log(f" 标题: {task.get_display_name()}")
        
        self.app.root.after(0, self.update_list)
        self._run_ytdlp_task(task)

        if task.id in self.running_tasks:
            del self.running_tasks[task.id]
            if task not in self.task_queue:
                self.task_queue.append(task)
        self.app.root.after(0, self.update_list)
        self.app.root.after(100, self.start_next_task)

    def _notify_auth_issue(self, diagnostic):
        if not diagnostic or diagnostic.ok:
            return
        self.app.latest_auth_diagnostic = diagnostic
        self.record_runtime_issue(
            diagnostic.summary or "检测到认证问题",
            getattr(diagnostic, "detail", "") or getattr(diagnostic, "action_hint", "") or diagnostic.summary,
            level="ERROR" if diagnostic.is_auth_related else "WARN",
        )
        self.log(f"[错误] {diagnostic.summary}", "ERROR" if diagnostic.is_auth_related else "WARN")
        if diagnostic.action_hint:
            self.log(f"[提示] {diagnostic.action_hint}", "ERROR" if diagnostic.is_auth_related else "WARN")
        if diagnostic.is_auth_related:
            self.app.root.after(0, lambda diag=diagnostic: self.app.notify_cookies_error(diag))
            if hasattr(self.app, 'top_bar'):
                self.app.root.after(0, self.app.top_bar.refresh_auth_status)

    def _run_ytdlp_task(self, task):
        """执行 yt-dlp 下载链路。"""
        if task.profile.custom_filename:
            task.final_title = task.profile.custom_filename
            self.log(f"[完成] 使用自定义文件名: {task.final_title}")
        elif not task.final_title and not task.stop_flag:
            self.log(f"[获取] 正在获取标题: [{task.id}]")
            try:
                title_result = self.app.metadata_service.fetch_title(task.url)
                if title_result["used_cookies"]:
                    task.needs_cookies = True
                    self.log("[完成] 已使用 cookies 成功获取标题")
                elif title_result["returncode"] != 0:
                    self.log("[警告] 标题获取失败，将记录诊断信息并继续进入下载阶段", "WARN")

                diagnostic = title_result.get("auth_diagnostic")
                if diagnostic and not diagnostic.ok:
                    if getattr(diagnostic, "is_auth_related", False):
                        self._notify_auth_issue(diagnostic)
                    elif getattr(diagnostic, "summary", ""):
                        self.log(f"[警告] {diagnostic.summary}", "WARN")
                        if getattr(diagnostic, "action_hint", ""):
                            self.log(f"[提示] {diagnostic.action_hint}", "WARN")
                        if getattr(diagnostic, "detail", ""):
                            detail_preview = diagnostic.detail.strip().replace("\r", " ").replace("\n", " ")
                            self.log(f"[诊断] 标题获取诊断: {detail_preview[:180]}")

                if title_result["ok"] and title_result["title"]:
                    task.final_title = title_result["title"]
                    self.log(f"[完成] 标题获取成功: [{task.id}] {task.final_title[:40]}...")
                else:
                    task.final_title = task.get_display_name()
                    error_out = title_result["error_output"]
                    self.log(f"[错误] 获取标题失败 (码:{title_result['returncode']}),输出: {error_out.strip()[:60]}...")
                    if error_out.strip():
                        raw_preview = error_out.strip().replace("\r", " ").replace("\n", " ")
                        self.log(f"[日志] 标题获取原始日志: {raw_preview[:220]}")
            except Exception as exc:
                task.final_title = task.get_display_name()
                self.log(f"[错误] 获取标题异常: {exc},使用默认名称: {task.final_title}")

            self.app.root.after(0, self.update_list)
        
        # 移除重复的 "▶	开始下载" 日志，改为更详细的展示
        if task.needs_cookies:
            self.log("此任务使用 cookies 下载")

        cmd = build_ytdlp_command(
            self.yt_dlp_path,
            self.ffmpeg_path,
            self.cookies_file_path,
            task,
        )
        max_retries = task.profile.retries

        for attempt in range(max_retries + 1):
            if task.stop_flag:
                task.status = TASK_STATUS_STOPPED
                self.log(f"[停止] 任务已停止: [{task.id}]")
                return

            if attempt > 0:
                retry_summary = getattr(task, "latest_error_summary", "")
                if retry_summary:
                    self.log(f"[警告] 上次失败摘要: {retry_summary}", "WARN")
                    self.log(f"[重试] [{task.id}] 第 {attempt}/{max_retries} 次")
                time.sleep(5)
            try:
                error_output_buffer = []
                output_dir = task.resolve_output_dir() if hasattr(task, "resolve_output_dir") else task.save_path
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

                for line in task.process.stdout:
                    if task.stop_flag:
                        task.process.kill()
                        break
                    line = line.strip()
                    if not line:
                        continue

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
                        self.app.root.after(0, self.update_list)

                if task.stop_flag:
                    task.status = TASK_STATUS_STOPPED
                    self.log(f"[停止] 任务已停止: [{task.id}]")
                    return

                return_code = task.process.wait()
                if return_code == 0:
                    task.status = TASK_STATUS_SUCCESS
                    task.end_time = time.time()
                    duration = task.end_time - (task.start_time or task.add_time)
                    end_time_str = time.strftime("%H:%M:%S", time.localtime(task.end_time))
                    self.log(f"[完成] 任务下载完成 | 时间: {end_time_str} | 耗时: {duration:.1f}秒")
                    self.log(f" 标题: {task.get_display_name()}")
                    self._save_to_history(task)
                    self.log("-" * 40)
                    return

                if attempt == max_retries:
                    task.status = TASK_STATUS_FAILED
                    task.end_time = time.time()
                    duration = task.end_time - (task.start_time or task.add_time)
                    end_time_str = time.strftime("%H:%M:%S", time.localtime(task.end_time))
                    self.log(f"[错误] 任务下载失败 | 时间: {end_time_str} | 耗时: {duration:.1f}秒")
                    self.log(f" 标题: {task.get_display_name()}")
                    
                    failure_summary = ""
                    failure_stage = "download"
                    if error_output_buffer:
                        failure_summary = error_output_buffer[-1][:300]
                        diagnostic = detect_auth_diagnostic("\n".join(error_output_buffer))
                        if not diagnostic.ok:
                            self._notify_auth_issue(diagnostic)
                            failure_summary = diagnostic.summary or failure_summary
                            failure_stage = "auth" if diagnostic.is_auth_related else "network"
                    task.latest_error_summary = failure_summary or f"下载失败，退出码 {return_code}"
                    self.record_runtime_issue(
                        f"任务失败: {task.get_display_name()}",
                        task.latest_error_summary,
                        level="ERROR",
                    )
                    self._save_failed_history(
                        task,
                        failure_stage=failure_stage,
                        failure_summary=failure_summary,
                        return_code=return_code,
                    )
                    self.log("-" * 40)
                    return
            except Exception as exc:
                task.latest_error_summary = str(exc)[:300]
                self.record_runtime_issue(
                    f"任务异常: {task.get_display_name()}",
                    task.latest_error_summary,
                    level="ERROR",
                )
                self.log(f"[错误] 任务异常: [{task.id}] - {exc}")
                if attempt == max_retries:
                    task.status = TASK_STATUS_FAILED
                    self._save_failed_history(
                        task,
                        failure_stage="runtime",
                        failure_summary=str(exc)[:300],
                        return_code=None,
                    )
                    return

    def _save_to_history(self, task):
        """将成功任务写入历史。"""
        try:
            db_saved = self.history_repo.save_task(task)
            archive_path = getattr(task, "archive_output_path", "") or getattr(task, "save_path", "")
            if archive_path:
                self.log(f"归档目录: {archive_path}")
            if db_saved:
                self.log("已保存到历史数据库")
            else:
                self.log("已保存到 JSON 历史备份")
        except Exception as exc:
            self.log(f"保存历史记录失败: {exc}")

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
                self.log("已保存失败记录到历史数据库")
            else:
                self.log("已保存失败记录到 JSON 历史备份")
        except Exception as exc:
            self.log(f"保存失败历史记录失败: {exc}")

    def stop_task(self, task_id):
        """停止指定任务。"""
        if task_id in self.running_tasks:
            task = self.running_tasks[task_id]
            task.stop_flag = True
            if task.process:
                try:
                    pid = task.process.pid
                    subprocess.run(
                        ['taskkill', '/F', '/T', '/PID', str(pid)],
                        capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    try:
                        task.process.wait(timeout=3)
                    except Exception:
                        pass
                except Exception as exc:
                    self.log(f"终止进程时出错: {exc}")
            self.log(f"正在停止任务: [{task.id}]")
            return

    def stop_all(self):
        """停止所有运行中的任务。"""
        for task_id in list(self.running_tasks.keys()):
            self.stop_task(task_id)

    def clear_completed(self):
        """清理已结束任务。"""
        remaining = []
        for task in self.task_queue:
            if task.status in {TASK_STATUS_SUCCESS, TASK_STATUS_FAILED, TASK_STATUS_STOPPED}:
                continue
            remaining.append(task)
        self.task_queue = remaining
        self.update_list()

    def retry_task(self, task_tree):
        """重试选中的失败/停止任务。"""
        selection = task_tree.selection() if task_tree is not None else ()
        if not selection:
            return
        for task_id in selection:
            task = self._find_task(task_id)
            if not task or task.status not in {TASK_STATUS_FAILED, TASK_STATUS_STOPPED}:
                continue
            task.status = TASK_STATUS_WAITING
            task.progress = "0%"
            task.speed = "0 M/s"
            task.stop_flag = False
            if task_id not in self.running_tasks and task not in self.task_queue:
                self.task_queue.append(task)
        self.update_list()
        self.start_next_task()

    def stop_selected(self, task_tree):
        """停止选中的运行任务。"""
        selection = task_tree.selection() if task_tree is not None else ()
        for task_id in selection:
            self.stop_task(task_id)

    def delete_selected(self, task_tree):
        """删除选中的非运行任务。"""
        selection = task_tree.selection() if task_tree is not None else ()
        if not selection:
            return
        remaining = []
        selected_ids = set(selection)
        for task in self.task_queue:
            if task.id in selected_ids and task.status != TASK_STATUS_RUNNING:
                continue
            remaining.append(task)
        self.task_queue = remaining
        self.update_list()

    def _find_task(self, task_id):
        if task_id in self.running_tasks:
            return self.running_tasks[task_id]
        for task in self.task_queue:
            if task.id == task_id:
                return task
        return None

from dataclasses import dataclass, field
import os
import queue
import subprocess
import threading
import time
import uuid

from core.ffmpeg_builder import build_ffmpeg_command

MEDIA_JOB_REMUX = "remux"
MEDIA_JOB_EXTRACT_AUDIO = "extract_audio"
MEDIA_JOB_TRIM = "trim"
MEDIA_JOB_CONCAT = "concat"
MEDIA_JOB_BURN_SUBTITLE = "burn_subtitle"
MEDIA_JOB_SCALE = "scale"
MEDIA_JOB_CROP = "crop"
MEDIA_JOB_ROTATE = "rotate"
MEDIA_JOB_WATERMARK = "watermark"
MEDIA_JOB_LOUDNORM = "loudnorm"

MEDIA_JOB_STATUS_WAITING = "等待中"
MEDIA_JOB_STATUS_RUNNING = "处理中"
MEDIA_JOB_STATUS_SUCCESS = "完成"
MEDIA_JOB_STATUS_FAILED = "失败"
MEDIA_JOB_STATUS_STOPPED = "已停止"


@dataclass
class MediaJobProfile:
    job_type: str
    input_path: str = ""
    output_path: str = ""
    audio_format: str = "mp3"
    start_time: str = ""
    end_time: str = ""
    concat_list_path: str = ""
    subtitle_path: str = ""
    scale_width: str = ""
    scale_height: str = ""
    crop_width: str = ""
    crop_height: str = ""
    crop_x: str = ""
    crop_y: str = ""
    rotate: str = ""
    watermark_path: str = ""
    watermark_pos: str = "bottom-right"
    video_codec: str = ""
    audio_codec: str = ""
    video_bitrate: str = ""
    audio_bitrate: str = ""
    crf: str = ""
    preset: str = ""
    vf_custom: str = ""
    af_custom: str = ""
    extra_args: str = ""
    add_time: float = field(default_factory=lambda: time.time())


@dataclass
class MediaJobRecord:
    profile: MediaJobProfile
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: str = MEDIA_JOB_STATUS_WAITING
    progress: str = "0%"
    speed: str = "-"
    process: object = None
    stop_flag: bool = False
    start_time: float = 0.0
    end_time: float = 0.0
    latest_error_summary: str = ""

    def get_display_name(self):
        job_type = getattr(self.profile, "job_type", "")
        if job_type == MEDIA_JOB_REMUX:
            return "转封装"
        if job_type == MEDIA_JOB_EXTRACT_AUDIO:
            return "音频提取"
        if job_type == MEDIA_JOB_TRIM:
            return "剪辑"
        if job_type == MEDIA_JOB_CONCAT:
            return "拼接"
        if job_type == MEDIA_JOB_BURN_SUBTITLE:
            return "字幕烧录"
        if job_type == MEDIA_JOB_SCALE:
            return "缩放"
        if job_type == MEDIA_JOB_CROP:
            return "裁切"
        if job_type == MEDIA_JOB_ROTATE:
            return "旋转"
        if job_type == MEDIA_JOB_WATERMARK:
            return "水印"
        if job_type == MEDIA_JOB_LOUDNORM:
            return "音量归一化"
        return "媒体任务"

    def resolve_output_dir(self):
        output_path = getattr(self.profile, "output_path", "")
        if not output_path:
            return ""
        return os.path.dirname(output_path)


class MediaJobManager:
    """负责本地媒体任务的调度与执行。"""

    def __init__(self, app, ffmpeg_path, startupinfo=None, max_concurrent=1):
        self.app = app
        self.ffmpeg_path = ffmpeg_path
        self.startupinfo = startupinfo
        self.max_concurrent = max_concurrent
        self.job_queue = []
        self.running_jobs = {}
        self._state_lock = threading.RLock()
        self.log_queue = queue.Queue()
        self.job_tree = None
        self.log_text = None

    def log(self, message, level="INFO"):
        self.log_queue.put((message, level))

    def _safe_after(self, delay_ms, callback, *args):
        root = getattr(self.app, "root", None)
        if not root or not callback:
            return
        try:
            root.after(delay_ms, callback, *args)
        except Exception as exc:
            self.log(f"[警告] 媒体 UI 调度失败: {exc}", "WARN")

    def process_log_queue(self):
        if self.log_text is None:
            self._safe_after(120, self.process_log_queue)
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
            self._safe_after(120, self.process_log_queue)

    def _snapshot_jobs_for_ui(self):
        with self._state_lock:
            return list(self.running_jobs.values()) + list(self.job_queue)

    def update_list(self):
        if self.job_tree is None:
            return
        self.job_tree.delete(*self.job_tree.get_children())
        all_jobs = self._snapshot_jobs_for_ui()
        for job in all_jobs:
            self.job_tree.insert(
                "",
                "end",
                iid=job.id,
                values=(
                    job.id,
                    job.status,
                    job.progress,
                    job.speed,
                    job.get_display_name(),
                ),
            )

    def add_job(self, job):
        with self._state_lock:
            if any(getattr(existing, 'id', None) == job.id for existing in self.job_queue):
                self.log(f"[警告] 已存在同 ID 等待任务，已跳过: [{job.id}]", "WARN")
                return False
            if job.id in self.running_jobs:
                self.log(f"[警告] 任务正在运行中，已跳过: [{job.id}]", "WARN")
                return False
            self.job_queue.append(job)
        self.update_list()
        add_time_str = time.strftime("%H:%M:%S", time.localtime(job.profile.add_time))
        self.log(f"[添加] 媒体任务已入队 | 时间: {add_time_str} | 类型: {job.get_display_name()}", "INFO")
        return True

    def start_next_job(self):
        with self._state_lock:
            if len(self.running_jobs) >= self.max_concurrent:
                return False
            waiting_jobs = [j for j in self.job_queue if j.status == MEDIA_JOB_STATUS_WAITING]
            if not waiting_jobs:
                return False
            job = waiting_jobs[0]
            if job not in self.job_queue:
                return False
            self.job_queue.remove(job)
            self.running_jobs[job.id] = job
        threading.Thread(target=lambda: self.run_job(job), daemon=True).start()
        return True

    def start_all_jobs(self):
        with self._state_lock:
            waiting_count = sum(1 for j in self.job_queue if j.status == MEDIA_JOB_STATUS_WAITING)
        if waiting_count == 0:
            self.log("没有等待中的媒体任务", "INFO")
            return
        self.log(f"[开始] 启动 {waiting_count} 个媒体任务...", "INFO")
        while True:
            with self._state_lock:
                if len(self.running_jobs) >= self.max_concurrent:
                    break
            if not self.start_next_job():
                break

    def run_job(self, job):
        job.status = MEDIA_JOB_STATUS_RUNNING
        job.start_time = time.time()
        start_time_str = time.strftime("%H:%M:%S", time.localtime(job.start_time))
        self.log(f"[运行] 媒体任务开始 | 时间: {start_time_str} | 类型: {job.get_display_name()}", "INFO")
        self._safe_after(0, self.update_list)
        self._run_ffmpeg_job(job)
        with self._state_lock:
            if job.id in self.running_jobs:
                del self.running_jobs[job.id]
                if job not in self.job_queue:
                    self.job_queue.append(job)
        self._safe_after(0, self.update_list)
        self._safe_after(100, self.start_next_job)

    def _cleanup_job_process(self, job, kill_timeout=3):
        proc = getattr(job, "process", None)
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
                        self.log(f"[警告] 等待媒体进程终止超时: {exc}", "WARN")
        except Exception as exc:
            self.log(f"[警告] 媒体进程清理失败: {exc}", "WARN")
        finally:
            try:
                if proc.stdout:
                    proc.stdout.close()
            except Exception as exc:
                self.log(f"[警告] 关闭媒体进程输出流失败: {exc}", "WARN")
            job.process = None

    def _run_ffmpeg_job(self, job):
        try:
            cmd = build_ffmpeg_command(self.ffmpeg_path, job)
        except Exception as exc:
            job.status = MEDIA_JOB_STATUS_FAILED
            job.end_time = time.time()
            job.latest_error_summary = f"命令构建失败: {exc}"
            self.log(f"[错误] 媒体任务命令构建失败: {exc}", "ERROR")
            return

        self.log(f"[摘要] ffmpeg 命令: {' '.join(cmd[:8])}{' ...' if len(cmd) > 8 else ''}", "INFO")

        output_dir = job.resolve_output_dir()
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        try:
            job.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                startupinfo=self.startupinfo,
            )
            error_lines = []
            for line in job.process.stdout:
                if job.stop_flag:
                    job.process.kill()
                    break
                line = line.strip()
                if not line:
                    continue
                if "error" in line.lower() or "invalid" in line.lower():
                    error_lines.append(line)
                if len(error_lines) > 6:
                    error_lines = error_lines[-6:]
            if job.stop_flag:
                job.status = MEDIA_JOB_STATUS_STOPPED
                self.log(f"[停止] 媒体任务已停止: [{job.id}]", "INFO")
                return

            return_code = job.process.wait()
            if return_code == 0:
                job.status = MEDIA_JOB_STATUS_SUCCESS
                job.end_time = time.time()
                duration = job.end_time - (job.start_time or job.profile.add_time)
                end_time_str = time.strftime("%H:%M:%S", time.localtime(job.end_time))
                self.log(f"[完成] 媒体任务完成 | 时间: {end_time_str} | 耗时: {duration:.1f}秒", "INFO")
                return

            job.status = MEDIA_JOB_STATUS_FAILED
            job.end_time = time.time()
            job.latest_error_summary = (error_lines[-1] if error_lines else f"ffmpeg 退出码 {return_code}")
            self.log(f"[错误] 媒体任务失败: {job.latest_error_summary}", "ERROR")
        except Exception as exc:
            job.status = MEDIA_JOB_STATUS_FAILED
            job.end_time = time.time()
            job.latest_error_summary = str(exc)[:300]
            self.log(f"[错误] 媒体任务异常: {exc}", "ERROR")
        finally:
            self._cleanup_job_process(job)

    def stop_job(self, job_id):
        with self._state_lock:
            job = self.running_jobs.get(job_id)
        if not job:
            return
        job.stop_flag = True
        if job.process:
            try:
                pid = job.process.pid
                subprocess.run(
                    ['taskkill', '/F', '/T', '/PID', str(pid)],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=10,
                )
            except Exception as exc:
                self.log(f"终止媒体进程时出错: {exc}", "WARN")
            finally:
                self._cleanup_job_process(job)
        self.log(f"正在停止媒体任务: [{job.id}]", "INFO")
        return

    def stop_selected(self, job_tree):
        selection = job_tree.selection() if job_tree is not None else ()
        for job_id in selection:
            self.stop_job(job_id)

    def delete_selected(self, job_tree):
        selection = job_tree.selection() if job_tree is not None else ()
        if not selection:
            return
        with self._state_lock:
            remaining = []
            selected_ids = set(selection)
            for job in self.job_queue:
                if job.id in selected_ids and job.status != MEDIA_JOB_STATUS_RUNNING:
                    continue
                remaining.append(job)
            self.job_queue = remaining
        self.update_list()

    def clear_completed(self):
        with self._state_lock:
            remaining = []
            for job in self.job_queue:
                if job.status in {MEDIA_JOB_STATUS_SUCCESS, MEDIA_JOB_STATUS_FAILED, MEDIA_JOB_STATUS_STOPPED}:
                    continue
                remaining.append(job)
            self.job_queue = remaining
        self.update_list()

import os
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
import tempfile
import shutil
import tkinter as tk
from tkinter import filedialog, ttk

BROWSER_COOKIES_CHOICES = ("chrome", "edge", "firefox")


def choose_directory(app):
    """选择保存文件夹。"""
    current_path = app.shared_save_dir_var.get()
    folder = filedialog.askdirectory(
        title=app.get_text("bottom_browse"),
        initialdir=current_path,
    )
    if folder:
        app.shared_save_dir_var.set(folder)



def open_save_directory(app):
    """打开当前设置的保存目录。"""
    current_path = app.shared_save_dir_var.get()
    try:
        if os.path.exists(current_path):
            if os.name == 'nt':
                os.startfile(current_path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', current_path])
            else:
                subprocess.Popen(['xdg-open', current_path])
        else:
            app.SilentMessagebox.showwarning(
                app.get_text("common_notice"),
                app.get_text("app_save_dir_missing"),
            )
    except Exception as exc:
        app.SilentMessagebox.showerror(
            app.get_text("common_error"),
            app.get_text("app_open_dir_failed").format(error=exc),
        )



COMPONENT_SOURCES = {
    "yt-dlp": {
        "url": "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe",
        "type": "binary",
        "filename": "yt-dlp.exe",
    },
    "ffmpeg": {
        "url": "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip",
        "type": "zip",
        "filename": "ffmpeg.exe",
        "zip_match": "ffmpeg.exe",
    },
    "deno": {
        "url": "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip",
        "type": "zip",
        "filename": "deno.exe",
        "zip_match": "deno.exe",
    },
}


def _normalize_mb(size_bytes):
    try:
        return float(size_bytes) / 1024 / 1024
    except Exception:
        return 0.0


def _format_progress_text(downloaded, total):
    if total > 0:
        pct = min(100.0, max(0.0, downloaded / total * 100.0))
        return f"{pct:.1f}% ({_normalize_mb(downloaded):.2f}MB/{_normalize_mb(total):.2f}MB)"
    return f"{_normalize_mb(downloaded):.2f}MB"


def _make_progress_dialog(app, title_key, initial_text):
    dialog = tk.Toplevel(app.root)
    dialog.title(app.get_text(title_key))
    dialog.geometry("520x160")
    dialog.configure(bg="#ffffff")
    dialog.transient(app.root)
    dialog.grab_set()

    frame = ttk.Frame(dialog, padding=12)
    frame.pack(fill="both", expand=True)

    label_var = tk.StringVar(value=initial_text)
    label = ttk.Label(frame, textvariable=label_var, wraplength=480)
    label.pack(anchor="w")

    bar = ttk.Progressbar(frame, mode="determinate", length=480)
    bar.pack(pady=(12, 6))

    tip_var = tk.StringVar(value=app.get_text("components_downloading_hint"))
    tip = ttk.Label(frame, textvariable=tip_var, foreground="#666666")
    tip.pack(anchor="w")

    return {
        "dialog": dialog,
        "label_var": label_var,
        "bar": bar,
        "tip_var": tip_var,
    }


def _center_dialog(dialog):
    try:
        dialog.update_idletasks()
        width = dialog.winfo_reqwidth()
        height = dialog.winfo_reqheight()
        sw = dialog.winfo_screenwidth()
        sh = dialog.winfo_screenheight()
        x = max(0, (sw - width) // 2)
        y = max(0, (sh - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
    except Exception:
        pass


def _download_with_progress(url, target_path, progress_cb=None, timeout=20):
    def report(block_count, block_size, total_size):
        downloaded = block_count * block_size
        if progress_cb:
            progress_cb(downloaded, total_size)

    tmp_path = target_path + ".tmp"
    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    urllib.request.urlretrieve(url, tmp_path, reporthook=report)
    os.replace(tmp_path, target_path)
    return target_path


def _extract_zip_member(zip_path, match_name, target_path):
    with zipfile.ZipFile(zip_path, "r") as zf:
        members = zf.namelist()
        candidate = None
        lowered = match_name.lower()
        for name in members:
            if name.lower().endswith(lowered):
                candidate = name
                break
        if not candidate:
            raise RuntimeError(f"zip_missing:{match_name}")
        with zf.open(candidate) as src, open(target_path + ".tmp", "wb") as dst:
            shutil.copyfileobj(src, dst)
        os.replace(target_path + ".tmp", target_path)
    return target_path


def _record_component_update_failure(app, summary_key, err_msg):
    if hasattr(app, 'latest_runtime_issue'):
        app.latest_runtime_issue = {
            "summary": app.get_text(summary_key),
            "detail": err_msg,
            "level": "ERROR",
            "time": __import__('time').strftime("%Y-%m-%d %H:%M:%S"),
        }


def _safe_ui_update(app, progress_ui, text=None, percent=None):
    def apply_update():
        if text is not None:
            progress_ui["label_var"].set(text)
        if percent is not None:
            progress_ui["bar"].configure(value=percent)

    try:
        app.root.after(0, apply_update)
    except Exception:
        pass


def _ensure_component(app, base_dir, name, progress_ui):
    source = COMPONENT_SOURCES.get(name)
    if not source:
        raise RuntimeError(f"unknown_component:{name}")

    url = source["url"]
    kind = source["type"]
    filename = source["filename"]
    target_path = os.path.join(base_dir, filename)

    _safe_ui_update(
        app,
        progress_ui,
        text=app.get_text("components_downloading").format(name=name, url=url),
        percent=0,
    )

    def on_progress(downloaded, total):
        text = app.get_text("components_downloading_progress").format(
            name=name,
            progress=_format_progress_text(downloaded, total),
        )
        percent = min(100.0, downloaded / total * 100.0) if total > 0 else None
        _safe_ui_update(app, progress_ui, text=text, percent=percent)

    if kind == "binary":
        _download_with_progress(url, target_path, progress_cb=on_progress)
        return target_path

    if kind == "zip":
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, f"{name}.zip")
            _download_with_progress(url, zip_path, progress_cb=on_progress)
            match_name = source.get("zip_match") or filename
            _extract_zip_member(zip_path, match_name, target_path)
        return target_path

    raise RuntimeError(f"unknown_component_type:{kind}")


def _refresh_component_paths(app, base_dir):
    try:
        app.components_manager.yt_dlp_path = os.path.join(base_dir, "yt-dlp.exe")
        app.components_manager.ffmpeg_path = os.path.join(base_dir, "ffmpeg.exe")
        app.components_manager.deno_path = os.path.join(base_dir, "deno.exe")
    except Exception:
        pass

    if getattr(app, "metadata_service", None):
        try:
            app.metadata_service.yt_dlp_path = app.components_manager.yt_dlp_path
        except Exception:
            pass
    if getattr(app, "ytdlp_manager", None):
        try:
            app.ytdlp_manager.yt_dlp_path = app.components_manager.yt_dlp_path
            app.ytdlp_manager.ffmpeg_path = app.components_manager.ffmpeg_path
        except Exception:
            pass
    if getattr(app, "media_manager", None):
        try:
            app.media_manager.ffmpeg_path = app.components_manager.ffmpeg_path
        except Exception:
            pass


def _get_component_target_dir(app, fallback_dir):
    configured_dir = (getattr(app, "components_dir", "") or "").strip()
    if configured_dir:
        return os.path.abspath(configured_dir)
    if fallback_dir:
        return os.path.abspath(fallback_dir)
    return os.getcwd()


def update_components(app, base_dir, components=None):
    """更新或下载 yt-dlp/ffmpeg/deno 单文件到程序根目录。"""
    if getattr(app, 'yt_dlp_update_in_progress', False):
        app.main_status_var.set(app.get_text("app_yt_dlp_updating"))
        return

    selected = components or ["yt-dlp", "ffmpeg", "deno"]
    target_dir = _get_component_target_dir(app, base_dir)
    os.makedirs(target_dir, exist_ok=True)
    app.main_status_var.set(app.get_text("components_update_start"))
    app.yt_dlp_update_in_progress = True

    progress_ui = _make_progress_dialog(app, "components_update_title", app.get_text("components_update_start"))
    _center_dialog(progress_ui["dialog"])

    def finish(status_text):
        app.yt_dlp_update_in_progress = False
        app.main_status_var.set(status_text)
        try:
            if progress_ui.get("dialog"):
                progress_ui["dialog"].destroy()
        except Exception:
            pass

    def run_update():
        try:
            for comp in selected:
                _ensure_component(app, target_dir, comp, progress_ui)

            _refresh_component_paths(app, target_dir)

            app.root.after(0, lambda: [
                app.SilentMessagebox.showinfo(
                    app.get_text("common_update_done"),
                    app.get_text("components_update_done"),
                ),
                finish(app.get_text("common_update_done"))
            ])
        except Exception as exc:
            err_msg = str(exc)
            _record_component_update_failure(app, "components_update_failed", err_msg)
            app.root.after(0, lambda msg=err_msg: [
                app.SilentMessagebox.showerror(
                    app.get_text("common_update_failed"),
                    app.get_text("components_update_fail_detail").format(message=msg),
                ),
                finish(app.get_text("common_update_failed"))
            ])

    try:
        threading.Thread(target=run_update, daemon=True).start()
    except Exception as exc:
        app.yt_dlp_update_in_progress = False
        _record_component_update_failure(app, "components_update_failed", str(exc))
        app.SilentMessagebox.showerror(
            app.get_text("common_error"),
            app.get_text("components_update_start_fail").format(error=exc),
        )
        app.main_status_var.set(app.get_text("topbar_runtime_ok"))


def update_yt_dlp(app, yt_dlp_path):
    """兼容旧入口：仅更新 yt-dlp。"""
    base_dir = _get_component_target_dir(
        app,
        os.path.dirname(os.path.abspath(yt_dlp_path)) if yt_dlp_path else os.getcwd(),
    )
    return update_components(app, base_dir, components=["yt-dlp"])



def export_components_diagnostics(app, statuses):
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    default_name = f"components_diagnosis_{timestamp}.json"
    file_path = filedialog.asksaveasfilename(
        title=app.get_text("app_export_diagnosis_title"),
        defaultextension=".json",
        initialfile=default_name,
        filetypes=[("JSON", "*.json")],
    )
    if not file_path:
        return
    try:
        app.components_manager.export_diagnostics(file_path, statuses)
        app.SilentMessagebox.showinfo(
            app.get_text("common_export_done"),
            app.get_text("app_export_diagnosis_done").format(path=file_path),
        )
    except Exception as exc:
        app.SilentMessagebox.showerror(
            app.get_text("common_error"),
            app.get_text("app_export_diagnosis_failed").format(error=exc),
        )



def apply_browser_cookies(app, browser_name: str):
    if not browser_name:
        return False
    normalized = browser_name.strip().lower()
    if normalized not in BROWSER_COOKIES_CHOICES:
        app.SilentMessagebox.showwarning(
            app.get_text("common_notice"),
            app.get_text("app_browser_cookies_invalid"),
        )
        return False
    app.default_cookies_mode = "browser"
    app.default_browser_cookies = normalized
    app.set_ui_state_value("cookies", "mode", value="browser")
    app.set_ui_state_value("cookies", "browser", value=normalized)
    app.save_ui_state()
    for frame in getattr(app, "input_frames", []) or []:
        if getattr(frame, "cookies_mode_var", None):
            frame.cookies_mode_var.set("browser")
        if getattr(frame, "cookies_browser_var", None):
            frame.cookies_browser_var.set(normalized)
    return True


def apply_file_cookies_mode(app):
    app.default_cookies_mode = "file"
    app.default_browser_cookies = ""
    app.set_ui_state_value("cookies", "mode", value="file")
    app.set_ui_state_value("cookies", "browser", value="")
    app.save_ui_state()
    for frame in getattr(app, "input_frames", []) or []:
        if getattr(frame, "cookies_mode_var", None):
            frame.cookies_mode_var.set("file")
    return True


def notify_cookies_error(app, diagnostic=None):
    """提示 cookies 或认证问题，仅提示一次。"""
    if app.cookies_error_notified:
        return

    app.cookies_error_notified = True
    raw_summary = getattr(diagnostic, 'summary', None) or app.get_text("app_cookies_diag_summary")
    raw_action_hint = getattr(diagnostic, 'action_hint', None) or app.get_text("app_cookies_diag_hint_default")
    summary = app.get_text(raw_summary, raw_summary)
    action_hint = app.get_text(raw_action_hint, raw_action_hint)

    app.root.after(500, lambda: app.SilentMessagebox.showwarning(
        app.get_text("app_cookies_diag_warn_title"),
        f"{summary}\n\n{app.get_text('app_cookies_diag_hint_title')}\n{action_hint}",
        parent=app.root
    ))
def repair_po_token(app):
    """手动触发 PO Token 环境修复。"""
    from core.po_token_manager import get_manager
    pot_manager = get_manager()
    
    status, msg = pot_manager.get_status()
    if status == "no_node":
        app.SilentMessagebox.showwarning(
            app.get_text("common_warning"),
            app.get_text("pot_help_node_required")
        )
        # 尝试打开 nodejs 官网
        try:
            import webbrowser
            webbrowser.open("https://nodejs.org/")
        except Exception:
            pass
        return

    pot_manager.repair()
    try:
        app.refresh_pot_status()
    except Exception:
        pass

    # `main_status_var` 是全局主状态，不应被 `PO Token` 专用状态覆盖。
    # 若之前已经残留为 `PO Token: 安装中...`，这里顺手恢复为通用就绪状态。
    try:
        current_main_status = (app.main_status_var.get() or "").strip()
        if "PO Token" in current_main_status:
            app.main_status_var.set(app.get_text("app_main_status_ready"))
    except Exception:
        pass

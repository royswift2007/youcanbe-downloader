import os
import subprocess
import sys
import threading
import urllib.request
from tkinter import filedialog


def choose_directory(app):
    """选择保存文件夹。"""
    current_path = app.shared_save_dir_var.get()
    folder = filedialog.askdirectory(title="选择保存文件夹", initialdir=current_path)
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
            app.SilentMessagebox.showwarning("提示", "保存目录不存在")
    except Exception as exc:
        app.SilentMessagebox.showerror("错误", f"无法打开目录: {exc}")



def update_yt_dlp(app, yt_dlp_path):
    """更新 yt-dlp.exe。"""
    if getattr(app, 'yt_dlp_update_in_progress', False):
        app.main_status_var.set("yt-dlp 更新进行中")
        return

    url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    app.main_status_var.set("正在更新 yt-dlp...")
    app.yt_dlp_update_in_progress = True

    def finish(status_text):
        app.yt_dlp_update_in_progress = False
        app.main_status_var.set(status_text)

    def record_update_failure(err_msg):
        if hasattr(app, 'latest_runtime_issue'):
            app.latest_runtime_issue = {
                "summary": "yt-dlp 更新失败",
                "detail": err_msg,
                "level": "ERROR",
                "time": __import__('time').strftime("%Y-%m-%d %H:%M:%S"),
            }

    def run_update():
        tmp_path = yt_dlp_path + ".tmp"
        backup_path = yt_dlp_path + ".bak"
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            if os.path.exists(backup_path):
                os.remove(backup_path)

            urllib.request.urlretrieve(url, tmp_path)
            verify_proc = subprocess.run(
                [tmp_path, "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                startupinfo=getattr(app, 'startupinfo', None),
            )
            if verify_proc.returncode != 0:
                raise RuntimeError(f"临时文件校验失败: {(verify_proc.stderr or verify_proc.stdout).strip()[:200]}")

            if os.path.exists(yt_dlp_path):
                os.replace(yt_dlp_path, backup_path)
            try:
                os.replace(tmp_path, yt_dlp_path)
            except Exception:
                if os.path.exists(backup_path):
                    os.replace(backup_path, yt_dlp_path)
                raise

            if os.path.exists(backup_path):
                os.remove(backup_path)

            app.root.after(0, lambda: [
                app.SilentMessagebox.showinfo("更新完成", "yt-dlp 已更新到最新版!"),
                finish("就绪")
            ])
        except Exception as exc:
            err_msg = str(exc)
            record_update_failure(err_msg)
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            try:
                if os.path.exists(backup_path) and not os.path.exists(yt_dlp_path):
                    os.replace(backup_path, yt_dlp_path)
            except Exception:
                pass
            app.root.after(0, lambda msg=err_msg: [
                app.SilentMessagebox.showerror("更新失败", f"更新 yt-dlp 失败:{msg}"),
                finish("更新失败")
            ])

    try:
        threading.Thread(target=run_update, daemon=True).start()
    except Exception as exc:
        app.yt_dlp_update_in_progress = False
        record_update_failure(str(exc))
        app.SilentMessagebox.showerror("错误", f"启动更新失败:{exc}")
        app.main_status_var.set("就绪")



def notify_cookies_error(app, diagnostic=None):
    """提示 cookies 或认证问题，仅提示一次。"""
    if app.cookies_error_notified:
        return

    app.cookies_error_notified = True
    summary = getattr(diagnostic, 'summary', None) or "检测到 YouTube cookies 文件可能已失效或当前内容需要登录权限。"
    action_hint = getattr(diagnostic, 'action_hint', None) or (
        "1. 使用浏览器插件重新导出 cookies\n"
        "2. 确保导出的是 www.youtube.com_cookies.txt\n"
        "3. 将文件放在程序同一目录下"
    )

    app.root.after(500, lambda: app.SilentMessagebox.showwarning(
        "[警告] 认证状态警告",
        f"{summary}\n\n建议处理：\n{action_hint}\n\n推荐插件: Get cookies.txt LOCALLY",
        parent=app.root
    ))

import os
import tkinter as tk
from tkinter import ttk

from ui.history_center import HistoryCenterWindow


class AuthStatusWindow:
    """认证状态窗口。"""

    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title("认证状态中心")
        self.window.geometry("760x420")
        self._build()

    def _build(self):
        frame = ttk.Frame(self.window, padding=12)
        frame.pack(fill='both', expand=True)

        cookies_path = self.app.COOKIES_FILE_PATH
        exists = os.path.exists(cookies_path)
        diagnostic = getattr(self.app, 'latest_auth_diagnostic', None)
        cookies_status = getattr(self.app, 'latest_cookies_status', None)

        ttk.Label(frame, text="Cookies 文件路径", font=(self.app.FONT_FAMILY, self.app.FONT_SIZE_TITLE, 'bold')).pack(anchor='w')
        ttk.Label(frame, text=cookies_path or "-", wraplength=700).pack(anchor='w', pady=(4, 10))

        ttk.Label(frame, text=f"文件状态: {'存在' if exists else '不存在'}").pack(anchor='w', pady=(0, 4))
        if cookies_status:
            ttk.Label(frame, text=f"最近校验结果: {getattr(cookies_status, 'last_message', '未检查')}").pack(anchor='w', pady=(0, 4))
            ttk.Label(frame, text=f"最近错误类别: {getattr(cookies_status, 'last_error_category', '无')}").pack(anchor='w', pady=(0, 8))
        else:
            ttk.Label(frame, text="最近校验结果: 未检查").pack(anchor='w', pady=(0, 8))

        ttk.Label(frame, text="建议动作", font=(self.app.FONT_FAMILY, self.app.FONT_SIZE_TITLE, 'bold')).pack(anchor='w', pady=(6, 0))
        action_hint = getattr(diagnostic, 'action_hint', '') if diagnostic else ''
        if not action_hint:
            action_hint = "1. 如访问受限内容，请重新导出浏览器 cookies\n2. 确保文件名为 www.youtube.com_cookies.txt\n3. 将 cookies 文件放在程序同目录下"
        ttk.Label(frame, text=action_hint, justify='left', wraplength=700).pack(anchor='w', pady=(4, 10))

        ttk.Label(frame, text="最近诊断摘要", font=(self.app.FONT_FAMILY, self.app.FONT_SIZE_TITLE, 'bold')).pack(anchor='w', pady=(6, 0))
        summary = getattr(diagnostic, 'summary', '') if diagnostic else ''
        detail = getattr(diagnostic, 'detail', '') if diagnostic else ''
        diagnostic_text = summary or "暂无认证异常"
        if detail:
            diagnostic_text += f"\n\n{detail}"
        text = tk.Text(frame, height=8, wrap='word')
        text.pack(fill='both', expand=True, pady=(4, 10))
        text.insert('1.0', diagnostic_text)
        text.configure(state='disabled')

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill='x')
        ttk.Button(btn_frame, text="关闭", command=self.window.destroy).pack(side='right')


class RuntimeStatusWindow:
    """运行状态窗口。"""

    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title("运行状态中心")
        self.window.geometry("760x460")
        self._build()

    def _build(self):
        frame = ttk.Frame(self.window, padding=12)
        frame.pack(fill='both', expand=True)

        issue = getattr(self.app, 'latest_runtime_issue', None) or {}
        manager = getattr(self.app, 'ytdlp_manager', None)
        waiting_count = len(getattr(manager, 'task_queue', []) or []) if manager else 0
        running_count = len(getattr(manager, 'running_tasks', {}) or {}) if manager else 0
        db_available = bool(getattr(getattr(manager, 'history_repo', None), 'db_available', False)) if manager else False
        db_path = getattr(getattr(manager, 'history_repo', None), 'db_path', '') if manager else ''

        ttk.Label(frame, text="任务运行概览", font=(self.app.FONT_FAMILY, self.app.FONT_SIZE_TITLE, 'bold')).pack(anchor='w')
        ttk.Label(frame, text=f"运行中: {running_count} | 队列中: {waiting_count}").pack(anchor='w', pady=(4, 4))
        ttk.Label(frame, text=f"历史数据库: {'可用' if db_available else '已回退 JSON'}").pack(anchor='w', pady=(0, 4))
        ttk.Label(frame, text=f"数据库路径: {db_path or '-'}", wraplength=700).pack(anchor='w', pady=(0, 10))

        ttk.Label(frame, text="最近运行问题", font=(self.app.FONT_FAMILY, self.app.FONT_SIZE_TITLE, 'bold')).pack(anchor='w')
        summary = issue.get('summary') or '暂无运行异常'
        ttk.Label(frame, text=f"摘要: {summary}", wraplength=700).pack(anchor='w', pady=(4, 4))
        ttk.Label(frame, text=f"级别: {issue.get('level', 'INFO')} | 时间: {issue.get('time', '-')}").pack(anchor='w', pady=(0, 8))

        detail_text = tk.Text(frame, height=10, wrap='word')
        detail_text.pack(fill='both', expand=True, pady=(0, 10))
        detail_text.insert('1.0', issue.get('detail') or '暂无额外详情')
        detail_text.configure(state='disabled')

        action_hint = [
            "建议处理：",
            "1. 若为认证问题，优先检查 cookies 文件状态",
            "2. 若为数据库问题，可先继续使用 JSON 历史后再处理 SQLite 文件",
            "3. 若为下载失败，可查看批量页结果摘要或日志中的最近错误信息",
        ]
        ttk.Label(frame, text="\n".join(action_hint), justify='left', wraplength=700).pack(anchor='w', pady=(0, 10))

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill='x')
        ttk.Button(btn_frame, text="关闭", command=self.window.destroy).pack(side='right')



def load_history(app, mode):
    """加载指定模式的历史记录到应用状态。"""
    file_path = app.HISTORY_FILES.get(mode)
    if not file_path or not os.path.exists(file_path):
        app.current_history_data = app.ytdlp_manager.history_repo.load()
        app.current_history_mode = mode
        return
    try:
        app.current_history_data = app.ytdlp_manager.history_repo.load()
        app.current_history_mode = mode
    except Exception:
        app.current_history_data = []
        app.current_history_mode = mode



def show_history(app):
    """显示当前历史中心窗口。"""
    HistoryCenterWindow(app, app.current_history_data, app.current_history_mode)



def show_auth_status(app):
    """显示认证状态中心窗口。"""
    AuthStatusWindow(app)



def show_runtime_status(app):
    """显示运行状态中心窗口。"""
    RuntimeStatusWindow(app)



def clear_all_history(app, mode):
    """清空指定模式的全部历史记录。"""
    try:
        app.ytdlp_manager.history_repo.clear()
        app.current_history_data = []
    except Exception:
        pass

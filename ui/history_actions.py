import os
import time
import tkinter as tk
from tkinter import ttk

from ui.history_center import HistoryCenterWindow


class AuthStatusWindow:
    """认证状态窗口。"""

    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title(self.app.get_text("auth_window_title"))
        self.window.geometry("760x680")
        self._build()

    def _translate_text(self, value, legacy_key_map=None):
        text = (value or "").strip()
        if not text:
            return ""

        translated = self.app.get_text(text)
        if translated != text:
            return translated

        legacy_key = (legacy_key_map or {}).get(text)
        if legacy_key:
            return self.app.get_text(legacy_key)
        return text

    def _translate_auth_message(self, value):
        return self._translate_text(
            value,
            legacy_key_map={
                "Cookies 文件存在": "app_cookies_exists",
                "cookies 文件存在": "app_cookies_exists",
                "未找到 cookies 文件": "app_cookies_missing_optional",
                "未检测到本地 Cookies 文件 (选填)": "app_cookies_missing_optional",
            },
        )

    def _build(self):
        frame = ttk.Frame(self.window, padding=12)
        frame.pack(fill='both', expand=True)

        cookies_path = self.app.COOKIES_FILE_PATH
        exists = os.path.exists(cookies_path)
        diagnostic = getattr(self.app, 'latest_auth_diagnostic', None)
        cookies_status = getattr(self.app, 'latest_cookies_status', None)
        browser_name = getattr(self.app, 'default_browser_cookies', '')
        browser_mode = getattr(self.app, 'default_cookies_mode', 'file')
        from core.po_token_manager import get_manager as _get_pot_manager
        pot_detail = _get_pot_manager().get_status_detail()

        ttk.Label(frame, text=self.app.get_text("auth_overview"), font=(self.app.FONT_FAMILY, self.app.FONT_SIZE_TITLE, 'bold')).pack(anchor='w')
        ttk.Label(
            frame,
            text=self.app.get_text("auth_cookies_mode").format(mode=browser_mode, browser=browser_name or '-'),
        ).pack(anchor='w', pady=(4, 8))
        ttk.Label(frame, text=self.app.get_text("auth_cookies_path_title"), font=(self.app.FONT_FAMILY, self.app.FONT_SIZE_TITLE, 'bold')).pack(anchor='w')
        ttk.Label(frame, text=cookies_path or "-", wraplength=700).pack(anchor='w', pady=(4, 10))

        status_label = self.app.get_text("auth_file_exists") if exists else self.app.get_text("auth_file_missing")
        ttk.Label(frame, text=self.app.get_text("auth_file_status").format(status=status_label)).pack(anchor='w', pady=(0, 4))
        if cookies_status:
            last_message = getattr(cookies_status, 'last_message', self.app.get_text("auth_last_check_none"))
            last_message = self._translate_auth_message(last_message) or self.app.get_text("auth_last_check_none")
            last_category = getattr(cookies_status, 'last_error_category', self.app.get_text("auth_last_error_none"))
            if last_category == "none":
                last_category = self.app.get_text("auth_last_error_none")
            ttk.Label(frame, text=self.app.get_text("auth_last_check").format(result=last_message)).pack(anchor='w', pady=(0, 4))
            ttk.Label(frame, text=self.app.get_text("auth_last_error").format(category=last_category)).pack(anchor='w', pady=(0, 8))
        else:
            ttk.Label(frame, text=self.app.get_text("auth_last_check").format(result=self.app.get_text("auth_last_check_none"))).pack(anchor='w', pady=(0, 8))

        pot_status = pot_detail.get('status') or '-'
        pot_message = self._translate_text(
            pot_detail.get('message') or '-',
            legacy_key_map={
                "未启用": "pot_msg_disabled",
                "PO Token 工具未随当前版本提供，已自动禁用": "pot_msg_disabled",
            },
        ) or '-'
        if pot_status == "未启用":
            pot_status = self.app.get_text("pot_status_disabled").replace("{icon}", "").strip()
        ttk.Label(frame, text=self.app.get_text("auth_pot_title"), font=(self.app.FONT_FAMILY, self.app.FONT_SIZE_TITLE, 'bold')).pack(anchor='w', pady=(6, 0))
        ttk.Label(frame, text=self.app.get_text("auth_pot_status").format(status=pot_status, message=pot_message)).pack(anchor='w', pady=(4, 0))
        last_updated = pot_detail.get('last_updated_at')
        last_updated_text = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_updated)) if last_updated else '-'
        ttk.Label(frame, text=self.app.get_text("auth_pot_last_update").format(time=last_updated_text)).pack(anchor='w', pady=(0, 4))
        ttk.Label(frame, text=self.app.get_text("auth_pot_last_error").format(reason=pot_detail.get('last_error') or '-')).pack(anchor='w', pady=(0, 8))

        ttk.Label(frame, text=self.app.get_text("auth_action_hint_title"), font=(self.app.FONT_FAMILY, self.app.FONT_SIZE_TITLE, 'bold')).pack(anchor='w', pady=(6, 0))
        action_hint = getattr(diagnostic, 'action_hint', '') if diagnostic else ''
        action_hint = self._translate_text(action_hint)
        if not action_hint:
            action_hint = self.app.get_text("auth_action_hint_default")
        ttk.Label(frame, text=action_hint, justify='left', wraplength=700).pack(anchor='w', pady=(4, 10))

        ttk.Label(frame, text=self.app.get_text("auth_diag_summary_title"), font=(self.app.FONT_FAMILY, self.app.FONT_SIZE_TITLE, 'bold')).pack(anchor='w', pady=(6, 0))
        summary = self._translate_text(getattr(diagnostic, 'summary', '') if diagnostic else '')
        detail = self._translate_text(getattr(diagnostic, 'detail', '') if diagnostic else '')
        diagnostic_text = summary or self.app.get_text("auth_diag_none")
        if detail:
            diagnostic_text += f"\n\n{detail}"
        text = tk.Text(frame, height=8, wrap='word')
        text.pack(fill='both', expand=True, pady=(4, 10))
        text.insert('1.0', diagnostic_text)
        text.configure(state='disabled')

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill='x')
        ttk.Button(btn_frame, text=self.app.get_text("common_close"), command=self.window.destroy).pack(side='right')


class RuntimeStatusWindow:
    """运行状态窗口。"""

    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title(self.app.get_text("runtime_window_title"))
        self.window.geometry("760x510")
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

        ttk.Label(frame, text=self.app.get_text("runtime_overview_title"), font=(self.app.FONT_FAMILY, self.app.FONT_SIZE_TITLE, 'bold')).pack(anchor='w')
        ttk.Label(frame, text=self.app.get_text("runtime_overview_counts").format(running=running_count, waiting=waiting_count)).pack(anchor='w', pady=(4, 4))
        db_status = self.app.get_text("runtime_db_available") if db_available else self.app.get_text("runtime_db_fallback")
        ttk.Label(frame, text=self.app.get_text("runtime_db_status").format(status=db_status)).pack(anchor='w', pady=(0, 4))
        ttk.Label(frame, text=self.app.get_text("runtime_db_path").format(path=db_path or '-'), wraplength=700).pack(anchor='w', pady=(0, 10))

        ttk.Label(frame, text=self.app.get_text("runtime_issue_title"), font=(self.app.FONT_FAMILY, self.app.FONT_SIZE_TITLE, 'bold')).pack(anchor='w')
        summary = issue.get('summary') or self.app.get_text("runtime_issue_none")
        detail = issue.get('detail') or self.app.get_text("runtime_issue_detail_none")
        if summary == self.app.get_text("app_main_status_ready") or summary in {"就绪", "Ready"}:
            summary = self.app.get_text("app_main_status_ready")
        if detail == self.app.get_text("app_main_status_ready") or detail in {"就绪", "Ready"}:
            detail = self.app.get_text("app_main_status_ready")
        ttk.Label(frame, text=self.app.get_text("runtime_issue_summary").format(summary=summary), wraplength=700).pack(anchor='w', pady=(4, 4))
        ttk.Label(frame, text=self.app.get_text("runtime_issue_level_time").format(level=issue.get('level', 'INFO'), time=issue.get('time', '-'))).pack(anchor='w', pady=(0, 8))

        detail_text = tk.Text(frame, height=10, wrap='word')
        detail_text.pack(fill='both', expand=True, pady=(0, 10))
        detail_text.insert('1.0', detail)
        detail_text.configure(state='disabled')

        ttk.Label(frame, text=self.app.get_text("runtime_action_hint"), justify='left', wraplength=700).pack(anchor='w', pady=(0, 10))

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill='x')
        ttk.Button(btn_frame, text=self.app.get_text("common_close"), command=self.window.destroy).pack(side='right')



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

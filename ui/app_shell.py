import os
from tkinter import ttk
import tkinter as tk
from core.po_token_manager import get_manager as _get_pot_manager, STATUS_READY, STATUS_NO_NODE, STATUS_OLD_NODE, STATUS_INSTALLING, STATUS_DISABLED, STATUS_ERROR


class TopBar(ttk.Frame):
    """应用顶部工具栏。"""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._trace_ids = []
        self.pack(fill='x', padx=10, pady=(5, 0))
        self._build()

    def _build(self):
        # 创建一个右对齐的容器
        container = ttk.Frame(self)
        container.pack(side='right')

        # 1. 状态标签 (PACK 从左往右在容器内，但整个容器在右边)
        def add_separator(pad_r=8):
            # 自定义短垂直分割线，颜色使用浅灰
            tk.Frame(container, width=1, height=12, bg="#e0e0e0").pack(side='left', padx=(8, pad_r))

        ttk.Label(
            container,
            textvariable=self.app.main_status_var,
            font=(self.app.FONT_FAMILY, self.app.FONT_SIZE_NORMAL),
        ).pack(side='left', padx=(0, 0))

        add_separator(8)

        self.auth_status_var = ttk.Label(
            container,
            textvariable=self.app.auth_status_var,
        )
        self.auth_status_var.pack(side='left', padx=(0, 0))

        add_separator(8)

        self.runtime_status_var = ttk.Label(
            container,
            textvariable=self.app.runtime_status_var,
        )
        self.runtime_status_var.pack(side='left', padx=(0, 0))

        add_separator(8)

        self._pot_status_label = ttk.Label(container, textvariable=self.app.pot_status_var)
        self._pot_status_label.pack(side='left', padx=(0, 12))
        _get_pot_manager().on_status_change(lambda code, msg: self.after(0, self.app.refresh_pot_status))

        ttk.Checkbutton(
            container,
            text=self.app.get_text("topbar_clipboard_watch"),
            variable=self.app.clipboard_watch_var,
        ).pack(side='left', padx=(4, 0))
        ttk.Checkbutton(
            container,
            text=self.app.get_text("topbar_auto_parse"),
            variable=self.app.clipboard_auto_parse_var,
        ).pack(side='left', padx=(4, 12))

        ttk.Label(container, text=f"{self.app.get_text('topbar_cookies')}:").pack(side='left', padx=(4, 4))
        self.cookies_mode_combo = ttk.Combobox(
            container,
            textvariable=self.app.cookies_mode_var,
            state="readonly",
            width=8,
            values=("file", "browser"),
        )
        self.cookies_mode_combo.pack(side='left', padx=(0, 4))
        self.cookies_browser_combo = ttk.Combobox(
            container,
            textvariable=self.app.cookies_browser_var,
            state="readonly",
            width=10,
            values=("chrome", "edge", "firefox"),
        )
        self.cookies_browser_combo.pack(side='left', padx=(0, 8))

        def sync_browser_state(*_args):
            mode = (self.app.cookies_mode_var.get() or "").strip()
            if mode == "browser":
                self.cookies_browser_combo.configure(state="readonly")
            else:
                self.cookies_browser_combo.configure(state="disabled")

        sync_browser_state()
        self._add_trace(self.app.cookies_mode_var, 'write', lambda *_args: self.after(0, sync_browser_state))

        ttk.Label(container, text=f"{self.app.get_text('topbar_language')}:").pack(side='left', padx=(4, 4))
        lang_values = ("zh", "en")
        lang_display = {
            "zh": self.app.get_text("lang_zh"),
            "en": self.app.get_text("lang_en"),
        }
        display_to_code = {label: code for code, label in lang_display.items()}
        initial_label = lang_display.get(self.app.current_lang, self.app.current_lang)
        self.lang_var = tk.StringVar(value=initial_label)
        self.lang_combo = ttk.Combobox(
            container,
            textvariable=self.lang_var,
            state="readonly",
            width=8,
            values=[lang_display[v] for v in lang_values],
        )
        self.lang_combo.pack(side='left', padx=(0, 8))

        def sync_lang_from_display(*_args):
            selected = self.lang_var.get()
            code = display_to_code.get(selected)
            if code:
                self.app.set_language(code)

        self.lang_combo.bind("<<ComboboxSelected>>", lambda _evt: sync_lang_from_display())

        # 2. 功能按钮
        ttk.Button(
            container,
            text=self.app.get_text("topbar_auth"),
            command=self.app.show_auth_status,
            style="Small.TButton",
        ).pack(side='left', padx=(8, 0))

        ttk.Button(
            container,
            text=self.app.get_text("topbar_history"),
            command=lambda: self.app.show_history_window('ytdlp'),
            style="Small.TButton",
        ).pack(side='left', padx=0)

        ttk.Button(
            container,
            text=self.app.get_text("topbar_components"),
            command=self.app.show_components_center,
            style="Small.TButton",
        ).pack(side='left', padx=0)

        ttk.Button(
            container,
            text=self.app.get_text("topbar_runtime"),
            command=self.app.show_runtime_status,
            style="Small.TButton",
        ).pack(side='left', padx=0)

        ttk.Button(
            container,
            text=self.app.get_text("topbar_usage"),
            command=self.app.show_usage_introduction,
            style="Small.TButton",
        ).pack(side='left', padx=0)

    def _build_auth_text(self):
        status = getattr(self.app, 'latest_cookies_status', None)
        diagnostic = getattr(self.app, 'latest_auth_diagnostic', None)
        cookies_path = getattr(self.app, 'COOKIES_FILE_PATH', '')
        exists = status.exists if status else (os.path.exists(cookies_path) if cookies_path else False)
        mode = (getattr(self.app, 'default_cookies_mode', 'file') or 'file').strip()
        browser = (getattr(self.app, 'default_browser_cookies', '') or '').strip()

        if diagnostic and not diagnostic.ok:
            summary = self.app.get_text(getattr(diagnostic, 'summary', '') or '', getattr(diagnostic, 'summary', '') or '')
            return self.app.get_text("topbar_auth_error").format(summary=summary)
        if mode == "browser":
            return self.app.get_text("topbar_auth_browser").format(browser=browser or "-")
        if exists:
            return self.app.get_text("topbar_auth_file_configured")
        if status and getattr(status, 'last_message', ''):
            message = self.app.get_text(getattr(status, 'last_message', '') or '', getattr(status, 'last_message', '') or '')
            return self.app.get_text("topbar_auth_last_message").format(message=message)
        return self.app.get_text("topbar_auth_unconfigured")

    def _build_runtime_text(self):
        issue = getattr(self.app, 'latest_runtime_issue', None) or {}
        summary = (issue.get('summary') or '').strip()
        if summary:
            return self.app.get_text("topbar_runtime_issue").format(summary=summary)
        return self.app.get_text("topbar_runtime_ok")

    def _build_pot_text(self):
        code, msg = _get_pot_manager().get_status()
        icons = {
            "unknown": "⚪", "no_node": "🔴", "old_node": "🔴",
            "installing": "🟡", "ready": "🟢", "error": "🔴", "disabled": "⚪",
        }
        icon = icons.get(code, "⚪")
        if code == "ready":
            return self.app.get_text("pot_status_ready").format(icon=icon)
        if code == "no_node":
            return self.app.get_text("pot_status_no_node").format(icon=icon)
        if code == "old_node":
            return self.app.get_text("pot_status_old_node").format(icon=icon)
        if code == "installing":
            return self.app.get_text("pot_status_installing").format(icon=icon)
        if code == "error":
            return self.app.get_text("pot_status_error").format(icon=icon)
        return self.app.get_text("pot_status_checking").format(icon=icon)

    def _refresh_pot_status(self):
        if hasattr(self, '_pot_status_label'):
            self._pot_status_label.configure(text=self._build_pot_text())

    def refresh_auth_status(self):
        self.auth_status_var.configure(text=self._build_auth_text())

    def refresh_runtime_status(self):
        if hasattr(self, 'runtime_status_var'):
            self.runtime_status_var.configure(text=self._build_runtime_text())

    def _add_trace(self, variable, mode, callback):
        tid = variable.trace_add(mode, callback)
        self._trace_ids.append((variable, tid))
        return tid

    def destroy(self):
        # Remove all tracked traces to prevent callbacks from firing after widgets are destroyed
        for variable, tid in getattr(self, "_trace_ids", []):
            try:
                variable.trace_remove("write", tid)
            except Exception:
                pass
        super().destroy()


class BottomBar(ttk.Frame):
    """应用底部保存路径栏。"""

    def __init__(self, parent, app):
        super().__init__(parent, padding=(10, 5))
        self.app = app
        self.pack(side='bottom', fill='x', padx=10, pady=(0, 10))
        self._build()

    def _build(self):
        self.columnconfigure(1, weight=1)

        ttk.Label(
            self,
            text=f"{self.app.get_text('bottom_current_dir')}:",
            font=(self.app.FONT_FAMILY, self.app.FONT_SIZE_NORMAL),
        ).grid(row=0, column=0, padx=(0, 6), sticky="w")

        path_entry = ttk.Entry(
            self,
            textvariable=self.app.shared_save_dir_var,
            state='readonly',
        )
        path_entry.grid(row=0, column=1, padx=5, sticky="ew")

        ttk.Button(
            self,
            text=self.app.get_text("bottom_browse"),
            command=self.app.choose_directory,
        ).grid(row=0, column=2, padx=5, sticky="e")

        ttk.Button(
            self,
            text=self.app.get_text("bottom_open_dir"),
            command=self.app.open_save_directory,
        ).grid(row=0, column=3, padx=(5, 0), sticky="e")

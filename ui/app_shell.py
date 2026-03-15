import os
from tkinter import ttk
import tkinter as tk
from core.po_token_manager import get_manager as _get_pot_manager, STATUS_READY, STATUS_NO_NODE, STATUS_OLD_NODE, STATUS_INSTALLING, STATUS_DISABLED, STATUS_ERROR


class TopBar(ttk.Frame):
    """应用顶部工具栏。"""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
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
            text=self._build_auth_text(),
        )
        self.auth_status_var.pack(side='left', padx=(0, 0))

        add_separator(8)

        self.runtime_status_var = ttk.Label(
            container,
            text=self._build_runtime_text(),
        )
        self.runtime_status_var.pack(side='left', padx=(0, 0))

        add_separator(8)

        self._pot_status_label = ttk.Label(container, text=self._build_pot_text())
        self._pot_status_label.pack(side='left', padx=(0, 16))
        _get_pot_manager().on_status_change(lambda code, msg: self.after(0, self._refresh_pot_status))

        # 2. 功能按钮
        ttk.Button(
            container,
            text="🔐 认证状态",
            command=self.app.show_auth_status,
            style="Small.TButton",
        ).pack(side='left', padx=(8, 0))

        ttk.Button(
            container,
            text="📜 历史记录",
            command=lambda: self.app.show_history_window('ytdlp'),
            style="Small.TButton",
        ).pack(side='left', padx=0)

        ttk.Button(
            container,
            text="🩺 运行状态",
            command=self.app.show_runtime_status,
            style="Small.TButton",
        ).pack(side='left', padx=0)

        ttk.Button(
            container,
            text="🔄 更新yt-dlp",
            command=self.app.update_yt_dlp,
            style="Small.TButton",
        ).pack(side='left', padx=0)

        ttk.Button(
            container,
            text="📜 使用介绍",
            command=self.app.show_usage_introduction,
            style="Small.TButton",
        ).pack(side='left', padx=0)

    def _build_auth_text(self):
        status = getattr(self.app, 'latest_cookies_status', None)
        diagnostic = getattr(self.app, 'latest_auth_diagnostic', None)
        cookies_path = getattr(self.app, 'COOKIES_FILE_PATH', '')
        exists = os.path.exists(cookies_path) if cookies_path else False

        if diagnostic and not diagnostic.ok:
            return f"认证异常: {diagnostic.summary}"
        if status and getattr(status, 'last_message', ''):
            return f"认证状态: {status.last_message}"
        if exists:
            return "cookies 正常"
        return "未配置 cookies"

    def _build_runtime_text(self):
        issue = getattr(self.app, 'latest_runtime_issue', None) or {}
        summary = (issue.get('summary') or '').strip()
        if summary:
            return f"运行状态: {summary}"
        return "运行状态: 正常"

    def _build_pot_text(self):
        code, msg = _get_pot_manager().get_status()
        icons = {
            "unknown": "⚪", "no_node": "🔴", "old_node": "🔴",
            "installing": "🟡", "ready": "🟢", "error": "🔴", "disabled": "⚪",
        }
        icon = icons.get(code, "⚪")
        if code == "ready":
            return f"{icon} PO Token: 就绪"
        if code == "no_node":
            return f"{icon} PO Token: 需安装 Node.js"
        if code == "old_node":
            return f"{icon} PO Token: Node 版本过低"
        if code == "installing":
            return f"{icon} PO Token: 安装中…"
        if code == "error":
            return f"{icon} PO Token: 初始化失败"
        return f"{icon} PO Token: 检测中…"

    def _refresh_pot_status(self):
        if hasattr(self, '_pot_status_label'):
            self._pot_status_label.configure(text=self._build_pot_text())

    def refresh_auth_status(self):
        self.auth_status_var.configure(text=self._build_auth_text())

    def refresh_runtime_status(self):
        if hasattr(self, 'runtime_status_var'):
            self.runtime_status_var.configure(text=self._build_runtime_text())


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
            text="当前目录:",
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
            text="浏览/设置",
            command=self.app.choose_directory,
        ).grid(row=0, column=2, padx=5, sticky="e")

        ttk.Button(
            self,
            text="📁 打开目录",
            command=self.app.open_save_directory,
        ).grid(row=0, column=3, padx=(5, 0), sticky="e")

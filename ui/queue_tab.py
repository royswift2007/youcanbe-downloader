import tkinter as tk
from tkinter import ttk


class QueueTab(ttk.Frame):
    """独立的下载队列与日志标签页。"""

    def __init__(self, parent, app, manager):
        super().__init__(parent)
        self.app = app
        self.manager = manager
        parent.add(self, text='下载队列')
        self._build_layout()

    def _get_pane_state(self):
        return self.app.get_ui_state_value('panes', 'queue_tab', default={})

    def _save_pane_state(self):
        if not getattr(self, 'container_pane', None):
            return
        try:
            sash_y = self.container_pane.sashpos(0)
            total_width = max(1, self.container_pane.winfo_width())
            total_height = max(1, self.container_pane.winfo_height())
        except Exception:
            return
        self.app.set_ui_state_value(
            'panes',
            'queue_tab',
            value={
                'sash_y': int(sash_y),
                'width': int(total_width),
                'height': int(total_height),
            },
        )
        self.app.save_ui_state()

    def _restore_pane_state(self):
        pane_state = self._get_pane_state()
        if not isinstance(pane_state, dict):
            return
        sash_y = pane_state.get('sash_y')
        if sash_y is None:
            return
        try:
            total_height = max(1, self.container_pane.winfo_height())
            if total_height <= 1:
                self.after(120, self._restore_pane_state)
                return
            max_sash = max(120, total_height - 180)
            restored_sash = max(120, min(int(sash_y), max_sash))
            self.container_pane.sashpos(0, restored_sash)
        except Exception:
            pass

    def _on_pane_released(self, _event=None):
        self._save_pane_state()

    def _on_pane_configure(self, _event=None):
        if getattr(self, '_pane_restore_done', False):
            return
        self._pane_restore_done = True
        self.after(80, self._restore_pane_state)

    def _build_layout(self):
        container = ttk.PanedWindow(self, orient='vertical')
        container.pack(fill='both', expand=True, padx=10, pady=(5, 10))
        self.container_pane = container
        self._pane_restore_done = False
        self.after(80, self._restore_pane_state)
        self.container_pane.bind("<ButtonRelease-1>", self._on_pane_released)
        self.container_pane.bind("<Configure>", self._on_pane_configure)

        queue_frame = ttk.LabelFrame(container, text="   下载队列", padding="5")
        log_frame = ttk.LabelFrame(container, text="   实时日志", padding="5")
        container.add(queue_frame, weight=3)
        container.add(log_frame, weight=2)

        cols = ("id", "status", "progress", "speed", "name", "type")
        task_tree = ttk.Treeview(
            queue_frame,
            columns=cols,
            show="headings",
            selectmode="extended",
            height=14,
            takefocus=False,
        )

        task_tree.heading("id", text="    ID", anchor="w")
        task_tree.heading("status", text="状态", anchor="w")
        task_tree.heading("progress", text="进度", anchor="w")
        task_tree.heading("speed", text="速度", anchor="w")
        task_tree.heading("name", text="文件名", anchor="w")
        task_tree.heading("type", text="类型", anchor="w")

        task_tree.column("id", width=90, minwidth=70, anchor="w")
        task_tree.column("status", width=110, minwidth=90, anchor="w")
        task_tree.column("progress", width=110, minwidth=90, anchor="w")
        task_tree.column("speed", width=120, minwidth=90, anchor="w")
        task_tree.column("name", width=520, minwidth=220, anchor="w")
        task_tree.column("type", width=100, minwidth=70, anchor="w")

        queue_vsb = ttk.Scrollbar(queue_frame, orient="vertical", command=task_tree.yview)
        queue_hsb = ttk.Scrollbar(queue_frame, orient="horizontal", command=task_tree.xview)
        task_tree.configure(yscrollcommand=queue_vsb.set, xscrollcommand=queue_hsb.set)

        task_tree.grid(row=0, column=0, sticky='nsew')
        queue_vsb.grid(row=0, column=1, sticky='ns')
        queue_hsb.grid(row=1, column=0, sticky='ew')
        queue_frame.grid_rowconfigure(0, weight=1)
        queue_frame.grid_columnconfigure(0, weight=1)

        btn_frame = ttk.Frame(queue_frame)
        btn_frame.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(8, 0))
        ttk.Button(btn_frame, text="▶ 开始全部", command=self.manager.start_all_tasks, style="Success.TButton").pack(side='left', padx=2)
        ttk.Button(btn_frame, text="↻ 重试选中", command=lambda: self.manager.retry_task(task_tree), style="Small.TButton").pack(side='left', padx=2)
        ttk.Button(btn_frame, text="⏹ 停止选中", command=lambda: self.manager.stop_selected(task_tree), style="Small.TButton").pack(side='left', padx=2)
        ttk.Button(btn_frame, text="❌ 停止全部", command=self.manager.stop_all, style="Danger.TButton").pack(side='left', padx=2)
        ttk.Button(btn_frame, text="🗑 删除选中", command=lambda: self.manager.delete_selected(task_tree), style="Small.TButton").pack(side='left', padx=2)
        ttk.Button(btn_frame, text="🧹 清除完成", command=self.manager.clear_completed, style="Small.TButton").pack(side='left', padx=2)
        ttk.Button(btn_frame, text="📜 历史记录", command=lambda: self.app.show_history_window(self.manager.mode), style="Small.TButton").pack(side='right', padx=2)

        font_family = getattr(self.app, 'FONT_FAMILY', 'Microsoft YaHei')
        font_size = getattr(self.app, 'FONT_SIZE_NORMAL', 10)
        log_font_size = max(8, font_size - 1)
        log_text = tk.Text(
            log_frame,
            height=16,
            bg='#ffffff',
            fg='#333333',
            insertbackground='#333333',
            relief='flat',
            wrap='word',
            font=(font_family, log_font_size),
            padx=8,
            pady=8,
            tabs=(30, "left"),
        )
        log_scrollbar = ttk.Scrollbar(log_frame, command=log_text.yview)
        log_text.config(yscrollcommand=log_scrollbar.set)
        log_text.pack(side='left', fill='both', expand=True)
        log_scrollbar.pack(side='right', fill='y')

        log_text.tag_config("ERROR", foreground="#d32f2f")
        log_text.tag_config("SUCCESS", foreground="#2e7d32")
        log_text.tag_config("INFO", foreground="#1565c0")
        log_text.tag_config("WARN", foreground="#e65100")
        log_text.tag_config("WARNING", foreground="#e65100")

        self.manager.task_tree = task_tree
        self.manager.log_text = log_text

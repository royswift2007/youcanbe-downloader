import tkinter as tk
from tkinter import ttk


class HistoryPage(ttk.Frame):
    """历史记录页。"""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._history_mode = "ytdlp"
        parent.add(self, text=self.app.get_text("tab_history"))
        self._build_layout()

    def _build_layout(self):
        wrap = ttk.Frame(self, style="Card.TFrame", padding=12)
        wrap.pack(fill="both", expand=True, padx=12, pady=12)

        title = ttk.Label(
            wrap,
            text=self.app.get_text("topbar_history"),
            style="Card.TLabel",
            font=(self.app.FONT_FAMILY, self.app.FONT_SIZE_TITLE, "bold"),
        )
        title.pack(anchor="w")

        text_frame = ttk.Frame(wrap, style="Card.TFrame")
        text_frame.pack(fill="both", expand=True, pady=(8, 10))

        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.text = tk.Text(text_frame, wrap="word", yscrollcommand=scrollbar.set)
        self.text.pack(expand=True, fill="both", side=tk.LEFT)
        scrollbar.config(command=self.text.yview)

        btn_frame = ttk.Frame(wrap)
        btn_frame.pack(fill="x")

        ttk.Button(
            btn_frame,
            text=self.app.get_text("components_refresh"),
            command=self.refresh,
            style="Small.TButton",
        ).pack(side="left")
        ttk.Button(
            btn_frame,
            text=self.app.get_text("history_btn_clear"),
            command=self._on_clear_all,
            style="Small.TButton",
        ).pack(side="left", padx=(8, 0))

        self.refresh()

    def refresh(self):
        try:
            self.app.load_history(self._history_mode)
        except Exception:
            pass
        history_data = self.app.current_history_data or []

        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if not history_data:
            self.text.insert("end", self.app.get_text("history_empty"))
        else:
            for item in history_data:
                title = item.get('title', 'N/A')
                url = item.get('url', 'N/A')
                path = item.get('path', 'N/A')
                time_str = item.get('time', 'N/A')
                profile = item.get('profile') or item.get('kwargs', {})
                task_type = item.get('type') or item.get('task_type') or 'youtube'
                source_platform = item.get('source_platform') or item.get('source') or ''

                detail_str = f"{self.app.get_text('history_label_title')}: {title}\n"
                detail_str += f"{self.app.get_text('history_label_type')}: {task_type}\n"
                if source_platform:
                    detail_str += f"{self.app.get_text('history_label_source')}: {source_platform}\n"
                detail_str += f"{self.app.get_text('history_label_url')}: {url}\n"
                detail_str += f"{self.app.get_text('history_label_path')}: {path}\n"
                detail_str += f"{self.app.get_text('history_label_time')}: {time_str}\n"
                detail_str += f"{self.app.get_text('history_label_format')}: {profile.get('format', self.app.get_text('history_default'))}\n"
                detail_str += f"{self.app.get_text('history_label_sub_lang')}: {profile.get('sub_lang', self.app.get_text('history_none'))}\n"
                detail_str += f"{self.app.get_text('history_label_retries')}: {profile.get('retries', 3)}\n"
                custom_filename = profile.get('custom_filename', '')
                if custom_filename:
                    detail_str += f"{self.app.get_text('history_label_custom_filename')}: {custom_filename}\n"
                detail_str += "=" * 60 + "\n\n"
                self.text.insert("end", detail_str)
        self.text.configure(state="disabled")

    def _on_clear_all(self):
        if not self.app.current_history_data:
            return
        self.app.clear_all_history(self._history_mode)
        self.refresh()

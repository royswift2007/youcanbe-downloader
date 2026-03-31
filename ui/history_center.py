import tkinter as tk
from tkinter import ttk


class HistoryCenterWindow:
    """下载历史中心窗口。"""

    def __init__(self, app, history_data, history_mode):
        self.app = app
        self.history_data = history_data or []
        self.history_mode = history_mode
        self.window = tk.Toplevel(app.root)
        self.window.title(self.app.get_text("history_window_title"))
        self.window.geometry("800x600")
        self._build()

    def _build(self):
        text_frame = ttk.Frame(self.window)
        text_frame.pack(fill='both', expand=True, padx=10, pady=10)

        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        text = tk.Text(text_frame, wrap="word", yscrollcommand=scrollbar.set)
        text.pack(expand=True, fill="both", side=tk.LEFT)
        scrollbar.config(command=text.yview)

        if not self.history_data:
            text.insert("end", self.app.get_text("history_empty"))
        else:
            for item in self.history_data:
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
                text.insert("end", detail_str)

        btn_frame = ttk.Frame(self.window)
        btn_frame.pack(fill='x', padx=10, pady=(0, 10))

        def on_clear_all():
            if not self.history_data:
                return
            self.app.clear_all_history(self.history_mode)
            self.window.destroy()

        ttk.Button(btn_frame, text=self.app.get_text("history_btn_clear"), command=on_clear_all).pack(side='left', padx=5)
        ttk.Button(btn_frame, text=self.app.get_text("common_close"), command=self.window.destroy).pack(side='right', padx=5)

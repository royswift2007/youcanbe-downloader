import tkinter as tk
from tkinter import ttk


class HistoryCenterWindow:
    """下载历史中心窗口。"""

    def __init__(self, app, history_data, history_mode):
        self.app = app
        self.history_data = history_data or []
        self.history_mode = history_mode
        self.window = tk.Toplevel(app.root)
        self.window.title("下载历史记录 - 详细信息")
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
            text.insert("end", "暂无历史记录")
        else:
            for item in self.history_data:
                title = item.get('title', 'N/A')
                url = item.get('url', 'N/A')
                path = item.get('path', 'N/A')
                time_str = item.get('time', 'N/A')
                profile = item.get('profile') or item.get('kwargs', {})

                detail_str = f"任务标题: {title}\n"
                detail_str += "下载类型: YouTube\n"
                detail_str += f"URL: {url}\n"
                detail_str += f"保存路径: {path}\n"
                detail_str += f"完成时间: {time_str}\n"
                detail_str += f"下载格式: {profile.get('format', '默认')}\n"
                detail_str += f"字幕语言: {profile.get('sub_lang', '无')}\n"
                detail_str += f"重试次数: {profile.get('retries', 3)}\n"
                custom_filename = profile.get('custom_filename', '')
                if custom_filename:
                    detail_str += f"自定义文件名: {custom_filename}\n"
                detail_str += "=" * 60 + "\n\n"
                text.insert("end", detail_str)

        btn_frame = ttk.Frame(self.window)
        btn_frame.pack(fill='x', padx=10, pady=(0, 10))

        def on_clear_all():
            if not self.history_data:
                return
            self.app.clear_all_history(self.history_mode)
            self.window.destroy()

        ttk.Button(btn_frame, text="🗑 清空全部历史", command=on_clear_all).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="关闭", command=self.window.destroy).pack(side='right', padx=5)

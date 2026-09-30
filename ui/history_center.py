import tkinter as tk
from tkinter import ttk


PAGE_SIZE = 100


def _format_item(app, item):
    title = item.get('title', 'N/A')
    url = item.get('url', 'N/A')
    path = item.get('path', 'N/A')
    time_str = item.get('time', 'N/A')
    profile = item.get('profile') or item.get('kwargs', {})
    task_type = item.get('type') or item.get('task_type') or 'youtube'
    source_platform = item.get('source_platform') or item.get('source') or ''

    detail_str = f"{app.get_text('history_label_title')}: {title}\n"
    detail_str += f"{app.get_text('history_label_type')}: {task_type}\n"
    if source_platform:
        detail_str += f"{app.get_text('history_label_source')}: {source_platform}\n"
    detail_str += f"{app.get_text('history_label_url')}: {url}\n"
    detail_str += f"{app.get_text('history_label_path')}: {path}\n"
    detail_str += f"{app.get_text('history_label_time')}: {time_str}\n"
    detail_str += f"{app.get_text('history_label_format')}: {profile.get('format', app.get_text('history_default'))}\n"
    detail_str += f"{app.get_text('history_label_sub_lang')}: {profile.get('sub_lang', app.get_text('history_none'))}\n"
    detail_str += f"{app.get_text('history_label_retries')}: {profile.get('retries', 3)}\n"
    custom_filename = profile.get('custom_filename', '')
    if custom_filename:
        detail_str += f"{app.get_text('history_label_custom_filename')}: {custom_filename}\n"
    detail_str += "=" * 60 + "\n\n"
    return detail_str


class HistoryCenterWindow:
    """下载历史中心窗口：提供搜索与分页，按需渲染当前页。"""

    def __init__(self, app, history_data, history_mode):
        self.app = app
        self.history_data = history_data or []
        self.history_mode = history_mode
        self._page = 0
        self._query = ""
        self.window = tk.Toplevel(app.root)
        self.window.title(self.app.get_text("history_window_title"))
        self.window.geometry("800x600")
        self._build()

    def _filtered_items(self):
        query = self._query.strip().lower()
        if not query:
            return list(self.history_data)
        result = []
        for item in self.history_data:
            title = str(item.get('title') or '').lower()
            url = str(item.get('url') or '').lower()
            if query in title or query in url:
                result.append(item)
        return result

    def _page_count(self, items):
        if not items:
            return 1
        return (len(items) + PAGE_SIZE - 1) // PAGE_SIZE

    def _build(self):
        container = ttk.Frame(self.window)
        container.pack(fill='both', expand=True, padx=10, pady=10)

        # 顶部搜索栏
        search_bar = ttk.Frame(container)
        search_bar.pack(fill='x', pady=(0, 8))

        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_bar, textvariable=self.search_var)
        self.search_entry.pack(side='left', fill='x', expand=True, padx=(0, 6))
        self.search_entry.bind('<Return>', lambda _e: self._apply_search())
        ttk.Button(
            search_bar,
            text=self.app.get_text("history_search"),
            command=self._apply_search,
            style="Small.TButton",
        ).pack(side='left')

        # 文本显示区
        text_frame = ttk.Frame(container)
        text_frame.pack(fill='both', expand=True)

        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.text = tk.Text(text_frame, wrap="word", yscrollcommand=scrollbar.set)
        self.text.pack(expand=True, fill="both", side=tk.LEFT)
        scrollbar.config(command=self.text.yview)

        # 底部分页 + 操作
        pager = ttk.Frame(container)
        pager.pack(fill='x', pady=(8, 0))

        self.page_info_label = ttk.Label(pager, text="")
        self.page_info_label.pack(side='left')

        ttk.Button(
            pager,
            text=self.app.get_text("history_prev"),
            command=self._prev_page,
            style="Small.TButton",
        ).pack(side='right')
        ttk.Button(
            pager,
            text=self.app.get_text("history_next"),
            command=self._next_page,
            style="Small.TButton",
        ).pack(side='right', padx=(0, 6))

        btn_frame = ttk.Frame(self.window)
        btn_frame.pack(fill='x', padx=10, pady=(0, 10))

        def on_clear_all():
            if not self.history_data:
                return
            self.app.clear_all_history(self.history_mode)
            self.window.destroy()

        ttk.Button(btn_frame, text=self.app.get_text("history_btn_clear"), command=on_clear_all).pack(side='left', padx=5)
        ttk.Button(btn_frame, text=self.app.get_text("common_close"), command=self.window.destroy).pack(side='right', padx=5)

        self._render()

    def _apply_search(self):
        self._query = self.search_var.get()
        self._page = 0
        self._render()

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self._render()

    def _next_page(self):
        items = self._filtered_items()
        total_pages = self._page_count(items)
        if self._page < total_pages - 1:
            self._page += 1
            self._render()

    def _render(self):
        items = self._filtered_items()
        total_pages = self._page_count(items)
        if self._page >= total_pages:
            self._page = max(0, total_pages - 1)

        start = self._page * PAGE_SIZE
        end = start + PAGE_SIZE
        page_items = items[start:end]

        self.text.configure(state="normal")
        self.text.delete("1.0", "end")

        if not items:
            self.text.insert("end", self.app.get_text("history_empty"))
        elif not page_items:
            self.text.insert("end", self.app.get_text("history_no_result"))
        else:
            for item in page_items:
                self.text.insert("end", _format_item(self.app, item))

        self.text.configure(state="disabled")

        self.page_info_label.configure(
            text=self.app.get_text("history_page_info").format(
                page=self._page + 1,
                total=total_pages,
                count=len(items),
            )
        )

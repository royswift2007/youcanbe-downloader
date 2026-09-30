import tkinter as tk
from tkinter import ttk

from ui.history_center import PAGE_SIZE, _format_item


class HistoryPage(ttk.Frame):
    """历史记录页。"""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._history_mode = "ytdlp"
        self._query = ""
        self._page = 0
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

        search_bar = ttk.Frame(wrap, style="Card.TFrame")
        search_bar.pack(fill="x", pady=(8, 0))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_bar, textvariable=self.search_var)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.search_entry.bind('<Return>', lambda _e: self._apply_search())
        ttk.Button(
            search_bar,
            text=self.app.get_text("history_search"),
            command=self._apply_search,
            style="Small.TButton",
        ).pack(side="left")

        text_frame = ttk.Frame(wrap, style="Card.TFrame")
        text_frame.pack(fill="both", expand=True, pady=(8, 10))

        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.text = tk.Text(text_frame, wrap="word", yscrollcommand=scrollbar.set)
        self.text.pack(expand=True, fill="both", side=tk.LEFT)
        scrollbar.config(command=self.text.yview)

        pager = ttk.Frame(wrap)
        pager.pack(fill="x", pady=(0, 4))
        self.page_info_label = ttk.Label(pager, text="")
        self.page_info_label.pack(side="left")
        ttk.Button(
            pager,
            text=self.app.get_text("history_prev"),
            command=self._prev_page,
            style="Small.TButton",
        ).pack(side="right")
        ttk.Button(
            pager,
            text=self.app.get_text("history_next"),
            command=self._next_page,
            style="Small.TButton",
        ).pack(side="right", padx=(0, 6))

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

    def _filtered_items(self):
        history_data = self.app.current_history_data or []
        query = self._query.strip().lower()
        if not query:
            return list(history_data)
        result = []
        for item in history_data:
            title = str(item.get('title') or '').lower()
            url = str(item.get('url') or '').lower()
            if query in title or query in url:
                result.append(item)
        return result

    def _page_count(self, items):
        if not items:
            return 1
        return (len(items) + PAGE_SIZE - 1) // PAGE_SIZE

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

    def refresh(self):
        try:
            self.app.load_history(self._history_mode)
        except Exception:
            pass
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

    def _on_clear_all(self):
        if not self.app.current_history_data:
            return
        self.app.clear_all_history(self._history_mode)
        self._page = 0
        self._query = ""
        self.search_var.set("")
        self.refresh()

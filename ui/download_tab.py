import tkinter as tk
from tkinter import ttk


class DownloadTab(ttk.Frame):
    """标准下载页容器：仅承载输入区与跳转入口。"""

    def __init__(self, parent, app, title, manager, input_frame_class):
        super().__init__(parent)
        self.app = app
        self.manager = manager
        self.input_frame_class = input_frame_class
        parent.add(self, text=title)
        self._build_layout()

    def _build_layout(self):
        container = ttk.Frame(self)
        container.pack(fill='both', expand=True, padx=8, pady=(2, 4))
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)
        container.grid_columnconfigure(1, weight=0)

        canvas = tk.Canvas(container, highlightthickness=0, borderwidth=0)
        canvas.grid(row=0, column=0, sticky='nsew', padx=(0, 6))

        y_scroll = ttk.Scrollbar(container, orient='vertical', command=canvas.yview)
        y_scroll.grid(row=0, column=1, sticky='ns')
        canvas.configure(yscrollcommand=y_scroll.set)

        scroll_frame = ttk.Frame(canvas)
        canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor='nw')

        def _sync_scroll_region(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _sync_canvas_width(event):
            canvas.itemconfigure(canvas_window, width=event.width)

        scroll_frame.bind("<Configure>", _sync_scroll_region)
        canvas.bind("<Configure>", _sync_canvas_width)

        input_frame = self.input_frame_class(scroll_frame, self.manager, self.app)
        input_frame.pack(fill='both', expand=True, pady=(0, 0))
        if hasattr(self.app, 'register_input_frame'):
            self.app.register_input_frame(input_frame)

        self.manager.input_frame = input_frame

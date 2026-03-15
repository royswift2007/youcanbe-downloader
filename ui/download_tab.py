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
        container.pack(fill='both', expand=True, padx=10, pady=(5, 10))
        container.grid_rowconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=0)
        container.grid_columnconfigure(0, weight=1)

        input_frame = self.input_frame_class(container, self.manager, self.app)
        input_frame.grid(row=0, column=0, sticky='nsew', pady=(0, 6))
        if hasattr(self.app, 'register_input_frame'):
            self.app.register_input_frame(input_frame)

        self.manager.input_frame = input_frame

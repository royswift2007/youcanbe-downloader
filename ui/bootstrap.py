import os
import tkinter as tk
from tkinter import ttk


DEBUG_STARTUP_LOG = os.path.join(os.getcwd(), "startup_debug.log")


def debug_startup(message):
    try:
        with open(DEBUG_STARTUP_LOG, "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception:
        pass


def setup_styles(ui_colors, font_family, font_size_normal):
    """配置 ttk 样式。"""
    style = ttk.Style()

    try:
        style.theme_use('alt')
    except Exception:
        pass

    style.configure(
        ".",
        background=ui_colors["bg_main"],
        foreground=ui_colors["text_primary"],
        font=(font_family, font_size_normal),
    )

    style.configure("TFrame", background=ui_colors["bg_main"], borderwidth=0)
    style.configure(
        "TLabel",
        background=ui_colors["bg_main"],
        foreground=ui_colors["text_primary"],
        borderwidth=0,
    )

    style.configure(
        "TLabelframe",
        background=ui_colors["bg_main"],
        foreground=ui_colors["text_primary"],
        relief="flat",
        borderwidth=0,
    )
    style.configure(
        "TLabelframe.Label",
        background=ui_colors["bg_main"],
        foreground=ui_colors["primary"],
        font=(font_family, font_size_normal - 2, 'bold'),
        borderwidth=0,
    )

    style.configure("Card.TFrame", background=ui_colors["bg_secondary"], relief="flat", borderwidth=0)
    style.configure("Card.TLabel", background=ui_colors["bg_secondary"], borderwidth=0)
    
    style.configure(
        "CardHeader.TLabel",
        background=ui_colors["bg_secondary"],
        foreground=ui_colors["primary"],
        font=(font_family, font_size_normal, 'bold'),
        borderwidth=0,
    )

    style.configure("Divider.TFrame", background="#f0f2f5", height=1)

    style.configure(
        "TButton",
        padding=(15, 8),
        relief="flat",
        borderwidth=0,
        font=(font_family, font_size_normal, 'bold'),
        focuscolor=ui_colors["bg_main"],
    )
    style.map(
        "TButton",
        background=[('active', '#e6f7ff'), ('pressed', '#bae7ff')],
        foreground=[('active', ui_colors["primary"])],
    )

    style.configure("Primary.TButton", background=ui_colors["primary"], foreground="white")
    style.map(
        "Primary.TButton",
        background=[('active', '#40a9ff'), ('pressed', '#096dd9')],
        foreground=[('active', 'white')],
    )

    style.configure("Success.TButton", background=ui_colors["success"], foreground="white")
    style.map(
        "Success.TButton",
        background=[('active', '#73d13d'), ('pressed', '#389e0d')],
        foreground=[('active', 'white')],
    )

    style.configure(
        "Danger.TButton",
        padding=(12, 8),
        font=(font_family, font_size_normal, 'bold'),
        background=ui_colors["danger"],
        foreground="white",
    )
    style.map("Danger.TButton", background=[('active', '#ff7875'), ('pressed', '#cf1322')])

    style.configure(
        "Small.TButton",
        padding=(8, 6),
        font=(font_family, font_size_normal - 1),
        background=ui_colors["bg_secondary"],
    )
    style.map(
        "Small.TButton",
        background=[('active', '#e6f7ff'), ('pressed', '#bae7ff')],
        foreground=[('active', ui_colors["primary"])],
    )

    style.configure(
        "Tiny.TButton",
        padding=(2, 0),
        font=(font_family, font_size_normal - 2),
        background=ui_colors["bg_secondary"],
    )
    style.map(
        "Tiny.TButton",
        background=[('active', '#e6f7ff'), ('pressed', '#bae7ff')],
        foreground=[('active', ui_colors["primary"])],
    )

    style.configure(
        "Info.Small.TButton",
        padding=(12, 8),
        font=(font_family, font_size_normal, 'bold'),
        background="#436EEE",
        foreground="white",
    )
    style.map(
        "Info.Small.TButton",
        background=[('active', '#1874CD'), ('pressed', '#006d75')],
        foreground=[('active', 'white')],
    )

    style.configure(
        "Warning.Small.TButton",
        padding=(12, 8),
        font=(font_family, font_size_normal, 'bold'),
        background="#ff7a45",
        foreground="white",
    )
    style.map(
        "Warning.Small.TButton",
        background=[('active', '#ff9c6e'), ('pressed', '#d4380d')],
        foreground=[('active', 'white')],
    )

    style.configure(
        "TEntry",
        padding=5,
        relief="solid",
        borderwidth=1,
        bordercolor="#e5e5e5",
        highlightthickness=0,
        fieldbackground="white",
    )
    style.map(
        "TEntry",
        bordercolor=[('focus', '#e5e5e5')],
        lightcolor=[('focus', '#e5e5e5')],
        darkcolor=[('focus', '#e5e5e5')],
        relief=[('focus', 'solid')],
        borderwidth=[('focus', 1)],
    )

    style.configure(
        "TSpinbox",
        padding=5,
        arrowcolor="#999999",
        arrowsize=10,
        bordercolor="#e5e5e5",
        lightcolor="#e5e5e5",
        darkcolor="#e5e5e5",
        relief="solid",
        borderwidth=1,
        fieldbackground="white",
    )
    style.map(
        "TSpinbox",
        bordercolor=[('focus', '#e5e5e5')],
        lightcolor=[('focus', '#e5e5e5')],
        darkcolor=[('focus', '#e5e5e5')],
        relief=[('focus', 'solid')],
        borderwidth=[('focus', 1)],
    )


    style.configure(
        "TCombobox",
        padding=5,
        relief="solid",
        borderwidth=1,
        bordercolor="#e5e5e5",
        arrowcolor=ui_colors["text_secondary"],
    )
    style.map(
        "TCombobox",
        bordercolor=[('focus', '#e5e5e5')],
        lightcolor=[('focus', '#e5e5e5')],
        darkcolor=[('focus', '#e5e5e5')],
        fieldbackground=[('readonly', 'white')],
    )

    style.configure(
        "TSpinbox",
        padding=(8, 6),
        arrowsize=18,
        relief="solid",
        borderwidth=1,
        bordercolor="#e5e5e5",
        font=(font_family, font_size_normal + 3),
        arrowcolor=ui_colors["text_secondary"],
    )
    style.map(
        "TSpinbox",
        bordercolor=[('focus', '#e5e5e5')],
        lightcolor=[('focus', '#e5e5e5')],
        darkcolor=[('focus', '#e5e5e5')],
        fieldbackground=[('readonly', 'white')],
    )

    style.configure(
        "Treeview",
        background="white",
        fieldbackground="white",
        foreground=ui_colors["text_primary"],
        font=(font_family, font_size_normal),
        rowheight=28,
        borderwidth=1,
        bordercolor=ui_colors["border"],
        lightcolor=ui_colors["border"],
        darkcolor=ui_colors["border"],
        relief="solid",
        highlightthickness=0,
    )
    style.layout("Treeview", [('Treeview.treearea', {'sticky': 'nswe'})])
    style.map(
        "Treeview",
        background=[('selected', '#e3f2fd')],
        foreground=[('selected', ui_colors["text_primary"])],
        font=[('selected', (font_family, font_size_normal, 'bold'))],
    )
    style.configure(
        "Treeview.Heading",
        background="#fafafa",
        foreground=ui_colors["text_secondary"],
        font=(font_family, font_size_normal, 'bold'),
        relief="flat",
        borderwidth=0,
    )

    style.configure(
        "TScrollbar",
        background="#f0f0f0",
        troughcolor=ui_colors["bg_main"],
        borderwidth=0,
        relief="flat",
        arrowcolor="#cccccc",
    )
    style.map("TScrollbar", background=[('active', '#e0e0e0'), ('pressed', '#d0d0d0')])

    style.configure(
        "TNotebook",
        background=ui_colors["bg_main"],
        tabmargins=[10, 10, 0, 0],
        borderwidth=0,
        relief="flat",
    )
    style.configure(
        "TNotebook.Tab",
        padding=[20, 10],
        font=(font_family, font_size_normal, 'bold'),
        background=ui_colors["bg_main"],
        foreground=ui_colors["text_secondary"],
        borderwidth=0,
        relief="flat",
        focuscolor=ui_colors["bg_main"],
    )
    style.map(
        "TNotebook.Tab",
        background=[('selected', '#E9E7EF')],
        foreground=[('selected', ui_colors["primary"])],
        expand=[('selected', [0, 0, 0, 0])],
    )

    style.configure(
        "TLabelframe.Label",
        background=ui_colors["bg_main"],
        foreground=ui_colors["primary"],
        font=(font_family, font_size_normal - 2, 'bold'),
        borderwidth=0,
    )


def run_app(app_class):
    debug_startup('main entry')
    root = tk.Tk()
    debug_startup('tk root created')
    app_class(root)
    debug_startup('app created')
    root.mainloop()
    debug_startup('mainloop exited')


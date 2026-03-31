import os
from tkinter import ttk
import tkinter as tk

from core.po_token_manager import get_manager
from ui.app_actions import export_components_diagnostics, update_components, repair_po_token


class ComponentsCenterWindow:
    """组件中心窗口。"""

    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title(self.app.get_text("components_title"))
        self.window.geometry("760x520") # 增加高度以容纳新卡片
        self._pot_indicator_label = None
        self._pot_hint_label = None
        self._pot_help_label = None
        self.window.protocol("WM_DELETE_WINDOW", self._close)

        def _handle_pot_status_change(_code, _msg):
            try:
                if self.window.winfo_exists():
                    self.window.after(0, self._refresh_pot_status_card)
            except Exception:
                pass

        get_manager().on_status_change(_handle_pot_status_change)
        self._build()

    def _build(self):
        frame = ttk.Frame(self.window, padding=12)
        frame.pack(fill='both', expand=True)

        ttk.Label(
            frame,
            text=self.app.get_text("components_title"),
            font=(self.app.FONT_FAMILY, self.app.FONT_SIZE_TITLE, 'bold'),
        ).pack(anchor='w')
        ttk.Label(
            frame,
            text=self.app.get_text("components_subtitle"),
            foreground="#666666",
        ).pack(anchor='w', pady=(4, 10))

        # 增加滚动功能，以防卡片过多
        canvas_f = ttk.Frame(frame)
        canvas_f.pack(fill='both', expand=True)
        
        canvas = tk.Canvas(canvas_f, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_f, orient="vertical", command=canvas.yview)
        self.status_frame = ttk.Frame(canvas)
        
        self.status_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.status_frame, anchor="nw", width=710)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._render_statuses()

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill='x', pady=(10, 0))
        ttk.Button(
            btn_row,
            text=self.app.get_text("components_refresh"),
            command=self._render_statuses,
            style="Small.TButton",
        ).pack(side='left')
        ttk.Button(
            btn_row,
            text=self.app.get_text("components_update_ytdlp"),
            command=lambda: update_components(self.app, self.app.base_path),
            style="Small.TButton",
        ).pack(side='left', padx=(8, 0))
        ttk.Button(
            btn_row,
            text=self.app.get_text("components_export"),
            command=self._export_diagnostics,
            style="Small.TButton",
        ).pack(side='left', padx=(8, 0))
        ttk.Button(
            btn_row,
            text=self.app.get_text("components_close"),
            command=self._close,
            style="Small.TButton",
        ).pack(side='right')

    def _render_statuses(self):
        for child in self.status_frame.winfo_children():
            child.destroy()

        # 1. 基础组件
        statuses = [
            self.app.components_manager.check_yt_dlp(),
            self.app.components_manager.check_ffmpeg(),
            self.app.components_manager.check_deno(),
        ]
        self._latest_statuses = statuses

        for idx, status in enumerate(statuses):
            card = ttk.Frame(self.status_frame, style="Card.TFrame", padding=6)
            card.pack(fill='x', pady=(0 if idx == 0 else 6, 0))
            status_text = self.app.get_text("components_ok") if status.ok else self.app.get_text("components_bad")
            title = f"{status.name} | {status_text}"
            ttk.Label(
                card,
                text=title,
                style="Card.TLabel",
                font=(self.app.FONT_FAMILY, self.app.FONT_SIZE_NORMAL, 'bold'),
            ).pack(anchor='w')
            ttk.Label(
                card,
                text=f"{self.app.get_text('components_path')}: {status.path or '-'}",
                style="Card.TLabel",
                wraplength=680,
            ).pack(anchor='w', pady=(2, 0))
            ttk.Label(
                card,
                text=f"{self.app.get_text('components_version')}: {status.version or '-'}",
                style="Card.TLabel",
            ).pack(anchor='w')
            if status.message:
                ttk.Label(
                    card,
                    text=f"{self.app.get_text('components_hint')}: {status.message}",
                    style="Card.TLabel",
                    foreground="#e65100",
                ).pack(anchor='w')
            if not status.ok:
                ttk.Label(
                    card,
                    text=self.app.get_text("components_suggest"),
                    style="Card.TLabel",
                    foreground="#d32f2f",
                ).pack(anchor='w')

        # 2. PO Token 模块
        pot_card = ttk.Frame(self.status_frame, style="Card.TFrame", padding=6)
        pot_card.pack(fill='x', pady=(10, 0))

        title_f = ttk.Frame(pot_card, style="Card.TFrame")
        title_f.pack(fill='x')

        ttk.Label(
            title_f,
            text=self.app.get_text("components_pot_title"),
            style="Card.TLabel",
            font=(self.app.FONT_FAMILY, self.app.FONT_SIZE_NORMAL, 'bold'),
        ).pack(side='left')

        self._pot_indicator_label = ttk.Label(
            title_f,
            text="",
            style="Card.TLabel",
            foreground="#52c41a",
        )
        self._pot_indicator_label.pack(side='left')

        self._pot_hint_label = ttk.Label(
            pot_card,
            text="",
            style="Card.TLabel",
            wraplength=680,
        )
        self._pot_hint_label.pack(anchor='w', pady=(2, 4))

        ttk.Button(
            pot_card,
            text=self.app.get_text("components_pot_btn_install"),
            command=lambda: repair_po_token(self.app),
            style="Small.TButton"
        ).pack(anchor='w')

        self._pot_help_label = ttk.Label(
            pot_card,
            text="",
            style="Card.TLabel",
            foreground="#d32f2f",
            wraplength=680,
        )
        self._refresh_pot_status_card()

    def _refresh_pot_status_card(self):
        try:
            if not self.window.winfo_exists():
                return
            if not self._pot_hint_label or not self._pot_hint_label.winfo_exists():
                return

            pot_status, pot_msg = get_manager().get_status()
            translated_msg = self.app.get_text(pot_msg) if pot_msg else ""

            if self._pot_indicator_label and self._pot_indicator_label.winfo_exists():
                self._pot_indicator_label.configure(text=" [Ready]" if pot_status == "ready" else "")

            hint_color = "#666666" if pot_status == "ready" else "#d32f2f"
            self._pot_hint_label.configure(
                text=f"{self.app.get_text('components_hint')}: {translated_msg}",
                foreground=hint_color,
            )

            if not self._pot_help_label or not self._pot_help_label.winfo_exists():
                return

            if pot_status == "no_node":
                self._pot_help_label.configure(text=self.app.get_text("pot_help_node_required"))
                if not self._pot_help_label.winfo_manager():
                    self._pot_help_label.pack(anchor='w', pady=(8, 0))
            else:
                if self._pot_help_label.winfo_manager():
                    self._pot_help_label.pack_forget()
        except Exception:
            pass

    def _close(self):
        if self.window.winfo_exists():
            self.window.destroy()

    def _export_diagnostics(self):
        export_components_diagnostics(self.app, getattr(self, "_latest_statuses", []))

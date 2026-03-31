import os
import tkinter as tk
from tkinter import ttk

from core.po_token_manager import get_manager as _get_pot_manager


class SettingsPage(ttk.Frame):
    """Application-level settings and status page."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        # Initialize attributes that are accessed by other methods or updated later
        self.main_status_label = None
        self.auth_status_label = None
        self.runtime_status_label = None
        self.pot_status_label = None
        self.cookies_mode_combo = None
        self.cookies_browser_combo = None
        self.lang_var = tk.StringVar()
        self.lang_combo = None
        self._display_to_code = {}
        self.download_retry_spinbox = None
        self.download_concurrent_spinbox = None
        self.download_speed_limit_spinbox = None
        self._trace_ids = []

        parent.add(self, text=self.app.get_text("tab_settings"))
        self._build_layout()

    def _create_card(self, parent, title, icon=""):
        card = ttk.Frame(parent, style="Card.TFrame", padding=12) # Reduced
        header_row = ttk.Frame(card, style="Card.TFrame")
        header_row.pack(fill="x", pady=(0, 6))

        if icon:
            ttk.Label(header_row, text=icon, style="CardHeader.TLabel").pack(side="left")
            ttk.Label(header_row, text=title, style="CardHeader.TLabel").pack(side="left", padx=(4, 0))
        else:
            ttk.Label(header_row, text=title, style="CardHeader.TLabel").pack(side="left")

        # Divider
        ttk.Frame(card, style="Divider.TFrame", height=1).pack(fill="x", pady=(0, 10))

        content = ttk.Frame(card, style="Card.TFrame")
        content.pack(fill="both", expand=True)
        return card, content

    def _create_stepper(self, parent, variable, minimum, maximum, width=5):
        wrapper = ttk.Frame(parent, style="Card.TFrame")

        def _step(delta):
            raw_value = variable.get().strip() if hasattr(variable, "get") else ""
            try:
                current = int(raw_value)
            except (TypeError, ValueError):
                current = minimum
            next_value = max(minimum, min(maximum, current + delta))
            variable.set(str(next_value))

        value_entry = ttk.Entry(wrapper, textvariable=variable, width=width, justify="center")
        value_entry.pack(side="left", fill="y", padx=(0, 4))
        
        btn_frame = tk.Frame(wrapper, bg="#d9d9d9", bd=1)
        btn_frame.pack(side="left", fill="y")
        
        inner_frame = tk.Frame(btn_frame, bg="white")
        inner_frame.pack(expand=True, fill="both")
        
        lbl_up = tk.Label(inner_frame, text=" + ", bg="white", fg="#666", font=("Arial", 7), width=2, pady=0, bd=0, cursor="hand2")
        lbl_up.pack(side="top", fill="both", expand=True)
        lbl_up.bind("<Button-1>", lambda e: _step(1))
        
        sep = tk.Frame(inner_frame, bg="#f0f0f0", height=1)
        sep.pack(side="top", fill="x")
        
        lbl_down = tk.Label(inner_frame, text=" - ", bg="white", fg="#666", font=("Arial", 7), width=2, pady=0, bd=0, cursor="hand2")
        lbl_down.pack(side="top", fill="both", expand=True)
        lbl_down.bind("<Button-1>", lambda e: _step(-1))
        
        def on_enter(lbl): lbl.config(bg="#f5f5f5")
        def on_leave(lbl): lbl.config(bg="white")
        lbl_up.bind("<Enter>", lambda e: on_enter(lbl_up))
        lbl_up.bind("<Leave>", lambda e: on_leave(lbl_up))
        lbl_down.bind("<Enter>", lambda e: on_enter(lbl_down))
        lbl_down.bind("<Leave>", lambda e: on_leave(lbl_down))

        return wrapper

    def _on_download_retry_changed(self, *_args):
        raw_value = self.app.download_retry_var.get().strip()
        if not raw_value:
            return
        try:
            retry = int(raw_value)
        except ValueError:
            return
        if retry < 0:
            return
        self.app.set_ui_state_value("downloads", "retry", value=retry)
        self.app.save_ui_state()

    def _on_download_concurrent_changed(self, *_args):
        raw_value = self.app.download_concurrent_var.get().strip()
        if not raw_value:
            return
        try:
            concurrent = int(raw_value)
        except ValueError:
            return
        if concurrent < 1:
            return
        self.app.ytdlp_manager.max_concurrent = concurrent
        self.app.set_ui_state_value("downloads", "concurrent", value=concurrent)
        self.app.save_ui_state()
        self.app.ytdlp_manager.start_next_task()

    def _on_download_speed_limit_changed(self, *_args):
        raw_value = self.app.download_speed_limit_var.get().strip()
        if not raw_value:
            return
        try:
            speed_limit = int(raw_value)
        except ValueError:
            return
        if speed_limit < 0:
            return
        self.app.set_ui_state_value("downloads", "speed_limit", value=speed_limit)
        self.app.save_ui_state()

    def _build_layout(self):
        # Main wrap with padding from window edges
        container = ttk.Frame(self, padding=12)
        container.pack(fill="both", expand=True)

        # 1. Status Card (Full Width)
        status_card, status_content = self._create_card(container, self.app.get_text("settings_status"), icon="📊")
        status_card.pack(fill="x", pady=(0, 12))

        # Status Grid
        status_grid = ttk.Frame(status_content, style="Card.TFrame")
        status_grid.pack(fill="x")

        # Use helper for status items to add a "dot" indicator
        def add_status_item(parent, row, col, text_var_or_val, is_var=True):
            frame = ttk.Frame(parent, style="Card.TFrame")
            frame.grid(row=row, column=col, sticky="w", padx=(0, 25), pady=2)
            ttk.Label(frame, text="●", foreground="#52c41a", style="Card.TLabel").pack(side="left", padx=(0, 4))
            if is_var:
                lbl = ttk.Label(frame, textvariable=text_var_or_val, style="Card.TLabel")
                lbl.pack(side="left")
                return lbl
            else:
                lbl = ttk.Label(frame, text=text_var_or_val, style="Card.TLabel")
                lbl.pack(side="left")
                return lbl

        if (self.app.main_status_var.get() or "").strip() == "就绪":
            self.app.main_status_var.set(self.app.get_text("app_main_status_ready"))
        self.main_status_label = add_status_item(status_grid, 0, 0, self.app.main_status_var)
        self.auth_status_label = add_status_item(status_grid, 0, 1, self.app.auth_status_var, is_var=True)
        self.runtime_status_label = add_status_item(status_grid, 1, 0, self.app.runtime_status_var, is_var=True)
        self.pot_status_label = add_status_item(status_grid, 1, 1, self.app.pot_status_var, is_var=True)
        status_grid.columnconfigure(2, weight=1)

        _get_pot_manager().on_status_change(lambda _code, _msg: self.after(0, lambda: self._refresh_pot_status()))

        # 2. Clipboard / Auto-Parse Card
        clipboard_card, clipboard_content = self._create_card(container, self.app.get_text("topbar_clipboard_watch"), icon="📋")
        clipboard_card.pack(fill="x", pady=(0, 12))

        clipboard_row = ttk.Frame(clipboard_content, style="Card.TFrame")
        clipboard_row.pack(fill="x")

        ttk.Checkbutton(
            clipboard_row,
            text=self.app.get_text("topbar_clipboard_watch"),
            variable=self.app.clipboard_watch_var,
        ).pack(side="left", padx=(0, 18))

        ttk.Checkbutton(
            clipboard_row,
            text=self.app.get_text("topbar_auto_parse"),
            variable=self.app.clipboard_auto_parse_var,
        ).pack(side="left")

        # 3. Download Settings Card (Horizontal Layout)
        download_card, download_content = self._create_card(container, self.app.get_text("settings_downloads"), icon="📥")
        download_card.pack(fill="x", pady=(0, 12))

        inner_downloads = ttk.Frame(download_content, style="Card.TFrame")
        inner_downloads.pack(fill="x")

        # Retry
        retry_group = ttk.Frame(inner_downloads, style="Card.TFrame")
        retry_group.pack(side="left")
        ttk.Label(retry_group, text=self.app.get_text('batch_settings_retry'), style="Card.TLabel").pack(side="left", padx=(0, 6))
        self.download_retry_spinbox = self._create_stepper(retry_group, self.app.download_retry_var, 0, 10)
        self.download_retry_spinbox.pack(side="left")

        # Concurrent
        conc_group = ttk.Frame(inner_downloads, style="Card.TFrame")
        conc_group.pack(side="left", padx=(25, 0))
        ttk.Label(conc_group, text=self.app.get_text('batch_settings_concurrency'), style="Card.TLabel").pack(side="left", padx=(0, 6))
        self.download_concurrent_spinbox = self._create_stepper(conc_group, self.app.download_concurrent_var, 1, 10)
        self.download_concurrent_spinbox.pack(side="left")

        # Speed Limit
        speed_group = ttk.Frame(inner_downloads, style="Card.TFrame")
        speed_group.pack(side="left", padx=(25, 0))
        ttk.Label(speed_group, text=self.app.get_text('batch_settings_speed_limit'), style="Card.TLabel").pack(side="left", padx=(0, 6))
        self.download_speed_limit_spinbox = self._create_stepper(speed_group, self.app.download_speed_limit_var, 0, 100)
        self.download_speed_limit_spinbox.pack(side="left")
        ttk.Label(speed_group, text=self.app.get_text('batch_settings_speed_unlimited'), style="Card.TLabel", foreground="#999").pack(side="left", padx=(8, 0))

        # 4. Page Settings Card
        controls_card, controls_content = self._create_card(container, self.app.get_text("settings_controls"), icon="⚙️")
        controls_card.pack(fill="x", pady=(0, 12))

        # Layout for controls
        inner_controls = ttk.Frame(controls_content, style="Card.TFrame")
        inner_controls.pack(fill="x")
        inner_controls.columnconfigure(1, weight=1)

        label_width = 10
        ttk.Label(inner_controls, text=self.app.get_text('topbar_cookies'), style="Card.TLabel", width=label_width).grid(row=0, column=0, sticky="w", pady=2)
        cookie_frame = ttk.Frame(inner_controls, style="Card.TFrame")
        cookie_frame.grid(row=0, column=1, sticky="w", pady=2)

        self.cookies_mode_combo = ttk.Combobox(
            cookie_frame,
            textvariable=self.app.cookies_mode_var,
            state="readonly",
            width=10,
            values=("file", "browser"),
        )
        self.cookies_mode_combo.pack(side="left")
        self.cookies_browser_combo = ttk.Combobox(
            cookie_frame,
            textvariable=self.app.cookies_browser_var,
            state="readonly",
            width=12,
            values=("chrome", "edge", "firefox"),
        )
        self.cookies_browser_combo.pack(side="left", padx=(8, 0))

        ttk.Label(inner_controls, text=self.app.get_text('topbar_language'), style="Card.TLabel", width=label_width).grid(row=1, column=0, sticky="w", pady=2)
        lang_values = ("zh", "en")
        lang_display = {
            "zh": self.app.get_text("lang_zh"),
            "en": self.app.get_text("lang_en"),
        }
        self._display_to_code = {label: code for code, label in lang_display.items()}
        self.lang_var = tk.StringVar(value=lang_display.get(self.app.current_lang, self.app.current_lang))
        self.lang_combo = ttk.Combobox(
            inner_controls,
            textvariable=self.lang_var,
            state="readonly",
            width=10,
            values=[lang_display[v] for v in lang_values],
        )
        self.lang_combo.grid(row=1, column=1, sticky="w", pady=2)
        self.lang_combo.bind("<<ComboboxSelected>>", lambda _evt: self._sync_lang_from_display())

        # 3. Quick Access Card
        actions_card, actions_content = self._create_card(container, self.app.get_text("settings_actions"), icon="⚡")
        actions_card.pack(fill="x")

        # Buttons in a single row with consistent spacing
        btn_frame = ttk.Frame(actions_content, style="Card.TFrame")
        btn_frame.pack(fill="x")

        actions = [
            (self.app.get_text("topbar_auth"), self.app.show_auth_status),
            (self.app.get_text("topbar_history"), lambda: self.app.show_history_window("ytdlp")),
            (self.app.get_text("topbar_components"), self.app.show_components_center),
            (self.app.get_text("topbar_runtime"), self.app.show_runtime_status),
            (self.app.get_text("topbar_usage"), self.app.show_usage_introduction),
        ]

        for i, (text, cmd) in enumerate(actions):
            ttk.Button(btn_frame, text=text, command=cmd, style="Small.TButton").pack(side="left", padx=(0, 12))

        # Traces and initial sync
        self._add_trace(self.app.download_retry_var, "write", self._on_download_retry_changed)
        self._add_trace(self.app.download_concurrent_var, "write", self._on_download_concurrent_changed)
        self._add_trace(self.app.download_speed_limit_var, "write", self._on_download_speed_limit_changed)
        self._add_trace(self.app.cookies_mode_var, "write", lambda *_args: self.after(0, lambda: self._sync_browser_state()))

        self._sync_browser_state()

    def _sync_lang_from_display(self):
        code = self._display_to_code.get(self.lang_var.get())
        if code:
            self.app.set_language(code)

    def _sync_browser_state(self):
        if not self.winfo_exists() or not hasattr(self, "cookies_browser_combo"):
            return
        if not self.cookies_browser_combo.winfo_exists():
            return
        mode = (self.app.cookies_mode_var.get() or "").strip()
        self.cookies_browser_combo.configure(state="readonly" if mode == "browser" else "disabled")

    def _refresh_pot_status(self):
        if self.winfo_exists():
            self.app.refresh_pot_status()

    def refresh_auth_status(self):
        self.app.refresh_auth_status()

    def refresh_runtime_status(self):
        self.app.refresh_runtime_status()

    def _add_trace(self, variable, mode, callback):
        tid = variable.trace_add(mode, callback)
        self._trace_ids.append((variable, tid))
        return tid

    def destroy(self):
        # Remove all tracked traces to prevent callbacks from firing after widgets are destroyed
        for variable, tid in getattr(self, "_trace_ids", []):
            try:
                variable.trace_remove("write", tid)
            except Exception:
                pass
        super().destroy()

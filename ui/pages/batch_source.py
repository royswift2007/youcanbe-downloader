import threading
import tkinter as tk
from tkinter import ttk

from core.manual_format_policy import (
    ManualBatchPolicy,
    ManualPresetSpec,
    build_manual_rule_hint,
    build_ytdlp_format_expr,
    has_manual_preset_constraints,
    manual_policy_from_dict,
    manual_policy_to_dict,
    validate_manual_batch_policy,
)
from core.youtube_models import BATCH_SOURCE_CHANNEL, BATCH_SOURCE_PLAYLIST, BATCH_SOURCE_UPLOADS
from ui.input_validators import AUDIO_OUTPUT_FORMATS, VIDEO_OUTPUT_FORMATS, build_profile_from_input, validate_advanced_args, validate_custom_filename, validate_download_sections, validate_output_format_compatibility, validate_proxy_url


class BatchSourceInputFrame(ttk.LabelFrame):
    """YouTube 批量来源页：支持播放列表与频道条目预览。"""

    def __init__(self, parent, manager, app):
        super().__init__(parent, text="", padding="12")
        self.manager = manager
        self.app = app
        self.shared_save_dir_var = app.shared_save_dir_var
        self.video_output_formats = VIDEO_OUTPUT_FORMATS + ("webm",)
        self.manual_policy_dict = None
        self.manual_enabled_var = tk.BooleanVar(value=False)
        self._manual_sample_formats = []
        self._manual_sample_source_url = ""
        self._manual_sample_stale = False
        self._manual_fetch_in_progress = False
        self._manual_window = None
        self._manual_window_state = None
        self.batch_result = None
        self.batch_entries = []
        self.batch_row_map = {}
        self._fetch_in_progress = False
        self._enqueue_in_progress = False
        self._trace_ids = []
        self._create_widgets()

    def _create_widgets(self):
        font_family = self.app.FONT_FAMILY
        font_size_title = self.app.FONT_SIZE_TITLE
        font_size_normal = self.app.FONT_SIZE_NORMAL

        url_frame = ttk.Frame(self)
        url_frame.pack(fill='x', pady=(0, 6))
        ttk.Label(url_frame, text=self.app.get_text("batch_url_label"), font=(font_family, font_size_title, 'bold')).pack(anchor='w')
        self.url_entry = tk.Text(url_frame, height=2, width=65, wrap='word', font=(font_family, font_size_normal))
        self.url_entry.pack(fill='x', pady=(5, 0))
        ttk.Label(
            url_frame,
            text=self.app.get_text("batch_url_hint"),
            font=(font_family, 8),
            foreground="#888888",
        ).pack(anchor='w', pady=(2, 0))

        source_card = ttk.Frame(self, style="Card.TFrame", padding=(8, 4))
        source_card.pack(fill='x', pady=(5, 2))
        header_row = ttk.Frame(source_card, style="Card.TFrame")
        header_row.pack(fill='x')
        ttk.Label(header_row, text=self.app.get_text("batch_source_summary"), style="Card.TLabel", font=(font_family, font_size_normal - 1, 'bold')).pack(side='left')
        self.source_title_var = tk.StringVar(value=self.app.get_text("batch_source_unparsed"))
        ttk.Label(header_row, textvariable=self.source_title_var, style="Card.TLabel", font=(font_family, font_size_normal, 'bold')).pack(side='left', padx=(8, 0))
        meta_row = ttk.Frame(source_card, style="Card.TFrame")
        meta_row.pack(fill='x')
        self.source_meta_var = tk.StringVar(value=self.app.get_text("batch_source_meta_default"))
        ttk.Label(meta_row, textvariable=self.source_meta_var, style="Card.TLabel").pack(side='left')
        self.source_stats_var = tk.StringVar(value=self.app.get_text("batch_source_stats_default"))
        ttk.Label(meta_row, textvariable=self.source_stats_var, style="Card.TLabel").pack(side='left', padx=(16, 0))

        action_row = ttk.Frame(self, style="Card.TFrame")
        action_row.pack(fill='x', pady=(0, 6))
        self.fetch_button = tk.Button(
            action_row,
            text=self.app.get_text("batch_fetch_entries"),
            command=self.fetch_batch_entries,
            relief='flat',
            bd=0,
            highlightthickness=0,
            padx=12,
            pady=8,
            font=(font_family, font_size_normal, 'bold'),
            bg="#436EEE",
            fg="white",
            activebackground="#1874CD",
            activeforeground="white",
            disabledforeground="#d9e6ff",
            cursor="hand2",
        )
        self.fetch_button.pack(side='left', padx=(0, 5))
        ttk.Button(action_row, text=self.app.get_text("batch_select_all"), command=self.select_all_entries).pack(side='left', padx=5)
        ttk.Button(action_row, text=self.app.get_text("batch_select_none"), command=self.clear_all_entries).pack(side='left', padx=5)
        ttk.Button(action_row, text=self.app.get_text("batch_keep_available"), command=self.keep_available_entries_selected).pack(side='left', padx=5)
        self.enqueue_button = ttk.Button(action_row, text=self.app.get_text("batch_enqueue_selected"), command=self.add_selected_tasks, style="Primary.TButton")
        self.enqueue_button.pack(side='right', padx=5)

        filter_row = ttk.Frame(self, style="Card.TFrame")
        filter_row.pack(fill='x', pady=(0, 6))
        ttk.Label(filter_row, text=self.app.get_text("batch_filter_source_type"), style="Card.TLabel").pack(side='left')
        self.source_type_var = tk.StringVar(value="auto")
        source_type_combo = ttk.Combobox(filter_row, textvariable=self.source_type_var, state="readonly", width=14)
        source_type_combo.configure(values=("auto", "playlist", "channel"))
        source_type_combo.pack(side='left', padx=(8, 18))
        self.hide_unavailable_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(filter_row, text=self.app.get_text("batch_filter_hide_unavailable"), variable=self.hide_unavailable_var, command=self.refresh_entry_table).pack(side='left')
        self.only_shorts_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(filter_row, text=self.app.get_text("batch_filter_only_shorts"), variable=self.only_shorts_var, command=self.refresh_entry_table).pack(side='left', padx=(8, 0))
        self.filter_summary_var = tk.StringVar(value=self.app.get_text("batch_filter_summary_empty"))
        ttk.Label(filter_row, textvariable=self.filter_summary_var, style="Card.TLabel").pack(side='right')

        result_card = ttk.Frame(self, style="Card.TFrame", padding=(8, 4))
        result_card.pack(fill='x', pady=(0, 4))
        result_row = ttk.Frame(result_card, style="Card.TFrame")
        result_row.pack(fill='x')
        ttk.Label(result_row, text=self.app.get_text("batch_result_title"), style="Card.TLabel", font=(font_family, font_size_normal - 1, 'bold')).pack(side='left')
        self.batch_result_summary_var = tk.StringVar(value=self.app.get_text("batch_result_default"))
        ttk.Label(result_row, textvariable=self.batch_result_summary_var, style="Card.TLabel", font=(font_family, font_size_normal, 'bold')).pack(side='left', padx=(8, 0))
        self.batch_result_error_var = tk.StringVar(value=self.app.get_text("batch_result_error_default"))
        ttk.Label(result_row, textvariable=self.batch_result_error_var, style="Card.TLabel").pack(side='left', padx=(16, 0))

        content_pane = ttk.PanedWindow(self, orient='vertical')
        content_pane.pack(fill='both', expand=True, pady=5)

        table_card = ttk.Frame(content_pane, style="Card.TFrame", padding=5)
        options_card = ttk.Frame(content_pane, style="Card.TFrame", padding=5)
        content_pane.add(table_card, weight=3)
        content_pane.add(options_card, weight=2)
        self.content_pane = content_pane
        self._pane_state_key = "batch_source"
        self.after(80, self._restore_pane_state)
        self.content_pane.bind("<ButtonRelease-1>", self._on_pane_released)
        self.content_pane.bind("<Configure>", self._on_pane_configure)

        columns = ("selected", "index", "title", "channel", "duration", "views", "upload_date", "availability", "shorts", "url")
        self.entry_tree = ttk.Treeview(table_card, columns=columns, show='headings', height=7)
        headings = {
            "selected": self.app.get_text("batch_table_selected"),
            "index": self.app.get_text("batch_table_index"),
            "title": self.app.get_text("batch_table_title"),
            "channel": self.app.get_text("batch_table_channel"),
            "duration": self.app.get_text("batch_table_duration"),
            "views": self.app.get_text("batch_table_views"),
            "upload_date": self.app.get_text("batch_table_upload_date"),
            "availability": self.app.get_text("batch_table_availability"),
            "shorts": self.app.get_text("batch_table_shorts"),
            "url": self.app.get_text("batch_table_url"),
        }
        for name, title in headings.items():
            self.entry_tree.heading(name, text=title, anchor='w')
            width = 90
            if name in {"title", "url"}:
                width = 260
            elif name == "channel":
                width = 150
            self.entry_tree.column(name, width=width, anchor='w', stretch=True)
        tree_scroll_y = ttk.Scrollbar(table_card, orient='vertical', command=self.entry_tree.yview)
        tree_scroll_x = ttk.Scrollbar(table_card, orient='horizontal', command=self.entry_tree.xview)
        self.entry_tree.configure(yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)
        self.entry_tree.grid(row=0, column=0, sticky='nsew')
        tree_scroll_y.grid(row=0, column=1, sticky='ns')
        tree_scroll_x.grid(row=1, column=0, sticky='ew')
        table_card.grid_rowconfigure(0, weight=1)
        table_card.grid_columnconfigure(0, weight=1)
        self.entry_tree.bind("<Double-1>", self._toggle_selected_entry)

        preset_row = ttk.Frame(options_card, style="Card.TFrame")
        preset_row.pack(fill='x', pady=(0, 5))
        ttk.Label(preset_row, text=self.app.get_text("batch_preset"), style="Card.TLabel").pack(side='left')
        self.preset_var = tk.StringVar(value="best_compat")
        preset_options = [
            ("best_quality", self.app.get_text("batch_preset_best_quality")),
            ("best_compat", self.app.get_text("batch_preset_best_compat")),
            ("max_1080p", self.app.get_text("batch_preset_max_1080p")),
            ("max_4k", self.app.get_text("batch_preset_max_4k")),
            ("audio_only", self.app.get_text("batch_preset_audio_only")),
            ("min_size", self.app.get_text("batch_preset_min_size")),
        ]
        for idx, (preset_key, preset_label) in enumerate(preset_options):
            ttk.Radiobutton(
                preset_row,
                text=preset_label,
                value=preset_key,
                variable=self.preset_var,
                command=self._update_batch_summary,
            ).pack(side='left', padx=(10 if idx == 0 else 6, 0))
        ttk.Checkbutton(
            preset_row,
            text=self.app.get_text("batch_manual_enable"),
            variable=self.manual_enabled_var,
            command=self._update_batch_summary,
        ).pack(side='left', padx=(12, 0))
        ttk.Button(
            preset_row,
            text=self.app.get_text("batch_manual_config"),
            command=self.open_manual_format_window,
        ).pack(side='left', padx=(8, 0))

        output_row = ttk.Frame(options_card, style="Card.TFrame")
        output_row.pack(fill='x', pady=(0, 5))
        ttk.Label(output_row, text=self.app.get_text("batch_output_format"), style="Card.TLabel").pack(side='left')
        self.output_format_var = tk.StringVar(value="mp4")
        self.output_format_combo = ttk.Combobox(output_row, textvariable=self.output_format_var, state="readonly", width=10)
        self.output_format_combo.configure(values=self.video_output_formats)
        self.output_format_combo.pack(side='left', padx=(10, 16))
        self.output_format_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_batch_summary())

        ttk.Label(output_row, text=self.app.get_text("batch_audio_quality"), style="Card.TLabel").pack(side='left')
        self.audio_quality_var = tk.StringVar(value="192")
        self.audio_quality_combo = ttk.Combobox(output_row, textvariable=self.audio_quality_var, state="readonly", width=8)
        self.audio_quality_combo.configure(values=("128", "192", "256", "320"))
        self.audio_quality_combo.pack(side='left', padx=(10, 16))
        self.audio_quality_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_batch_summary())

        ttk.Label(output_row, text=self.app.get_text("batch_custom_prefix"), style="Card.TLabel").pack(side='left')
        self.custom_filename_var = tk.StringVar()
        self.filename_entry = ttk.Entry(output_row, textvariable=self.custom_filename_var, width=26)
        self.filename_entry.pack(side='left', padx=(10, 0), fill='x', expand=True)
        self._add_trace(self.custom_filename_var, 'write', lambda *_args: self._update_batch_summary())

        sections_row = ttk.Frame(options_card, style="Card.TFrame")
        sections_row.pack(fill='x', pady=(0, 5))
        ttk.Label(sections_row, text=self.app.get_text("batch_sections"), style="Card.TLabel").pack(side='left')
        self.download_sections_var = tk.StringVar()
        ttk.Entry(sections_row, textvariable=self.download_sections_var, width=18).pack(side='left', padx=(10, 6))
        ttk.Label(sections_row, text=self.app.get_text("batch_sections_format"), style="Card.TLabel").pack(side='left')
        ttk.Label(sections_row, text=self.app.get_text("batch_sections_example"), style="Card.TLabel", foreground="#888888", font=(font_family, 8)).pack(side='left', padx=(6, 0))

        postprocess_row = ttk.Frame(options_card, style="Card.TFrame")
        postprocess_row.pack(fill='x', pady=(0, 5))
        ttk.Label(postprocess_row, text=self.app.get_text("batch_postprocess"), style="Card.TLabel").pack(side='left')
        self.embed_thumbnail_var = tk.BooleanVar(value=True)
        self.embed_metadata_var = tk.BooleanVar(value=True)
        self.write_thumbnail_var = tk.BooleanVar(value=False)
        self.write_info_json_var = tk.BooleanVar(value=False)
        self.write_description_var = tk.BooleanVar(value=False)
        self.write_chapters_var = tk.BooleanVar(value=False)
        self.h264_compat_var = tk.BooleanVar(value=False)
        self.keep_video_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(postprocess_row, text=self.app.get_text("batch_post_embed_thumbnail"), variable=self.embed_thumbnail_var, command=self._update_batch_summary).pack(side='left', padx=(10, 0))
        ttk.Checkbutton(postprocess_row, text=self.app.get_text("batch_post_embed_metadata"), variable=self.embed_metadata_var, command=self._update_batch_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text=self.app.get_text("batch_post_write_thumbnail"), variable=self.write_thumbnail_var, command=self._update_batch_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text=self.app.get_text("batch_post_write_info_json"), variable=self.write_info_json_var, command=self._update_batch_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text=self.app.get_text("batch_post_write_desc"), variable=self.write_description_var, command=self._update_batch_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text=self.app.get_text("batch_post_write_chapters"), variable=self.write_chapters_var, command=self._update_batch_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text=self.app.get_text("batch_post_h264"), variable=self.h264_compat_var, command=self._update_batch_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text=self.app.get_text("batch_post_keep_video"), variable=self.keep_video_var, command=self._update_batch_summary).pack(side='left', padx=(8, 0))
        self.sponsorblock_enabled_var = tk.BooleanVar(value=False)
        self.sponsorblock_categories_var = tk.StringVar(value="sponsor")
        ttk.Checkbutton(postprocess_row, text=self.app.get_text("batch_post_sponsorblock"), variable=self.sponsorblock_enabled_var, command=self._update_batch_summary).pack(side='left', padx=(8, 0))
        ttk.Entry(postprocess_row, textvariable=self.sponsorblock_categories_var, width=16).pack(side='left', padx=(6, 0))
        initial_use_po_token = bool(self.app.use_po_token_var.get()) if getattr(self.app, "use_po_token_var", None) else bool(getattr(self.app, "default_use_po_token", False))
        self.use_po_token_var = tk.BooleanVar(value=initial_use_po_token)
        ttk.Checkbutton(postprocess_row, text=self.app.get_text("batch_post_use_po_token"), variable=self.use_po_token_var, command=self._update_batch_summary).pack(side='left', padx=(8, 0))

        self.retry_var = self.app.download_retry_var
        self.concurrent_var = self.app.download_concurrent_var
        self.speedlimit_var = self.app.download_speed_limit_var

        network_row = ttk.Frame(options_card, style="Card.TFrame")
        network_row.pack(fill='x', pady=(0, 5))
        ttk.Label(network_row, text=self.app.get_text("batch_network"), style="Card.TLabel").pack(side='left')
        ttk.Label(network_row, text=self.app.get_text("batch_proxy"), style="Card.TLabel").pack(side='left', padx=(10, 0))
        self.proxy_url_var = tk.StringVar()
        ttk.Entry(network_row, textvariable=self.proxy_url_var, width=22).pack(side='left', padx=(4, 10))
        ttk.Label(network_row, text=self.app.get_text("batch_cookies"), style="Card.TLabel").pack(side='left')
        self.cookies_mode_var = tk.StringVar(value="file")
        ttk.Combobox(network_row, textvariable=self.cookies_mode_var, state="readonly", width=8, values=("file", "browser")).pack(side='left', padx=(4, 6))
        self.cookies_browser_var = tk.StringVar()
        self.cookies_browser_combo = ttk.Combobox(
            network_row,
            textvariable=self.cookies_browser_var,
            state="readonly",
            width=12,
            values=("chrome", "edge", "firefox"),
        )
        self.cookies_browser_combo.pack(side='left', padx=(0, 6))
        ttk.Label(network_row, text=self.app.get_text("batch_browser_hint"), style="Card.TLabel", foreground="#888888", font=(font_family, 8)).pack(side='left', padx=(6, 10))
        ttk.Label(network_row, text=self.app.get_text("batch_advanced_args"), style="Card.TLabel").pack(side='left')
        self.advanced_args_var = tk.StringVar()
        ttk.Entry(network_row, textvariable=self.advanced_args_var, width=18).pack(side='left', padx=(4, 0))

        def sync_browser_state(*_args):
            mode = (self.cookies_mode_var.get() or "").strip()
            if mode == "browser":
                self.cookies_browser_combo.configure(state="readonly")
            else:
                self.cookies_browser_combo.configure(state="disabled")

        sync_browser_state()
        self._add_trace(self.cookies_mode_var, 'write', lambda *_args: sync_browser_state())

        subtitle_row = ttk.Frame(options_card, style="Card.TFrame")
        subtitle_row.pack(fill='x', pady=(0, 5))
        ttk.Label(subtitle_row, text=self.app.get_text("batch_subtitle"), style="Card.TLabel").pack(side='left')
        self.subtitle_mode_var = tk.StringVar(value="none")
        ttk.Combobox(
            subtitle_row,
            textvariable=self.subtitle_mode_var,
            state="readonly",
            width=10,
            values=("none", "manual", "auto", "both"),
        ).pack(side='left', padx=(10, 6))
        ttk.Label(subtitle_row, text=self.app.get_text("batch_subtitle_lang"), style="Card.TLabel").pack(side='left')
        self.subtitle_langs_var = tk.StringVar()
        ttk.Entry(subtitle_row, textvariable=self.subtitle_langs_var, width=16).pack(side='left', padx=(4, 8))
        ttk.Label(subtitle_row, text=self.app.get_text("batch_subtitle_format"), style="Card.TLabel").pack(side='left')
        self.subtitle_format_var = tk.StringVar()
        ttk.Entry(subtitle_row, textvariable=self.subtitle_format_var, width=10).pack(side='left', padx=(4, 8))
        self.write_subs_var = tk.BooleanVar(value=True)
        self.embed_subs_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(subtitle_row, text=self.app.get_text("batch_subtitle_write"), variable=self.write_subs_var, command=self._update_batch_summary).pack(side='left', padx=(6, 0))
        ttk.Checkbutton(subtitle_row, text=self.app.get_text("batch_subtitle_embed"), variable=self.embed_subs_var, command=self._update_batch_summary).pack(side='left', padx=(6, 0))
        ttk.Label(subtitle_row, text=self.app.get_text("batch_subtitle_hint"), style="Card.TLabel", foreground="#888888", font=(font_family, 8)).pack(side='left', padx=(6, 0))

        throttle_row = ttk.Frame(options_card, style="Card.TFrame")
        throttle_row.pack(fill='x', pady=(0, 5))
        ttk.Label(throttle_row, text=self.app.get_text("batch_throttle"), style="Card.TLabel").pack(side='left')
        ttk.Label(throttle_row, text=self.app.get_text("batch_throttle_interval"), style="Card.TLabel").pack(side='left', padx=(10, 0))
        self.sleep_interval_var = tk.StringVar(value="5")
        ttk.Spinbox(throttle_row, from_=0, to=60, textvariable=self.sleep_interval_var, width=5).pack(side='left', padx=(4, 12))
        ttk.Label(throttle_row, text=self.app.get_text("batch_throttle_max"), style="Card.TLabel").pack(side='left')
        self.max_sleep_interval_var = tk.StringVar(value="10")
        ttk.Spinbox(throttle_row, from_=0, to=120, textvariable=self.max_sleep_interval_var, width=5).pack(side='left', padx=(4, 12))
        ttk.Label(throttle_row, text=self.app.get_text("batch_throttle_api"), style="Card.TLabel").pack(side='left')
        self.sleep_requests_var = tk.StringVar(value="1")
        ttk.Spinbox(throttle_row, from_=0, to=30, textvariable=self.sleep_requests_var, width=5).pack(side='left', padx=(4, 12))
        ttk.Label(throttle_row, text=self.app.get_text("batch_throttle_retry"), style="Card.TLabel").pack(side='left')
        self.retry_interval_var = tk.StringVar(value="10")
        ttk.Spinbox(throttle_row, from_=0, to=300, textvariable=self.retry_interval_var, width=5).pack(side='left', padx=(4, 0))

        summary_row = ttk.Frame(options_card, style="Card.TFrame")
        summary_row.pack(fill='x')
        ttk.Label(summary_row, text=self.app.get_text("batch_summary"), style="Card.TLabel").pack(side='left')
        self.batch_summary_var = tk.StringVar(value=self.app.get_text("batch_summary_default"))
        ttk.Label(summary_row, textvariable=self.batch_summary_var, style="Card.TLabel").pack(side='left', padx=(10, 0))

        self._pane_restore_done = False
        self._update_batch_summary()

    def _get_pane_key(self):
        return getattr(self, '_pane_state_key', 'batch_source')

    def _get_pane_state(self):
        return self.app.get_ui_state_value('panes', self._get_pane_key(), default={})

    def _save_pane_state(self):
        if not getattr(self, 'content_pane', None):
            return
        try:
            sash_y = self.content_pane.sashpos(0)
            total_width = max(1, self.content_pane.winfo_width())
            total_height = max(1, self.content_pane.winfo_height())
        except Exception:
            return
        self.app.set_ui_state_value(
            'panes',
            self._get_pane_key(),
            value={
                'sash_y': int(sash_y),
                'width': int(total_width),
                'height': int(total_height),
            },
        )
        self.app.save_ui_state()

    def _restore_pane_state(self):
        pane_state = self._get_pane_state()
        if not isinstance(pane_state, dict):
            return
        sash_y = pane_state.get('sash_y')
        if sash_y is None:
            return
        try:
            total_height = max(1, self.content_pane.winfo_height())
            if total_height <= 1:
                self.after(120, self._restore_pane_state)
                return
            max_sash = max(120, total_height - 210)
            restored_sash = max(120, min(int(sash_y), max_sash))
            self.content_pane.sashpos(0, restored_sash)
        except Exception:
            pass

    def _on_pane_released(self, _event=None):
        self._save_pane_state()

    def _on_pane_configure(self, _event=None):
        if getattr(self, '_pane_restore_done', False):
            return
        self._pane_restore_done = True
        self.after(80, self._restore_pane_state)

    def _format_duration(self, seconds):
        total = int(seconds or 0)
        hours, remain = divmod(total, 3600)
        minutes, secs = divmod(remain, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def _format_views(self, count):
        value = int(count or 0)
        return f"{value:,}" if value else self.app.get_text("batch_views_unknown")

    def _source_type_label(self, source_type):
        if source_type == BATCH_SOURCE_PLAYLIST:
            return self.app.get_text("batch_source_type_playlist")
        if source_type in {BATCH_SOURCE_CHANNEL, BATCH_SOURCE_UPLOADS}:
            return self.app.get_text("batch_source_type_channel")
        return self.app.get_text("batch_source_type_unknown")

    def _selected_entries(self):
        return [item for item in self.batch_entries if item.selected and item.available and item.url]

    def _get_source_url(self):
        return self.url_entry.get("1.0", "end-1c").strip()

    def _sync_output_format_by_preset(self):
        preset_key = self.preset_var.get().strip() or "best_compat"
        if preset_key == "audio_only":
            self.output_format_combo.configure(values=AUDIO_OUTPUT_FORMATS)
            if self.output_format_var.get().strip() not in AUDIO_OUTPUT_FORMATS:
                self.output_format_var.set("m4a")
        else:
            self.output_format_combo.configure(values=self.video_output_formats)
            if self.output_format_var.get().strip() not in self.video_output_formats:
                self.output_format_var.set("mp4")
        return preset_key

    def open_manual_format_window(self):
        if self._manual_window and self._manual_window.winfo_exists():
            self._manual_window.lift()
            self._manual_window.focus_force()
            return

        win = tk.Toplevel(self)
        win.title(self.app.get_text("batch_manual_title"))
        win.transient(self.winfo_toplevel())
        win.resizable(False, False)
        self._manual_window = win
        self._manual_fetch_in_progress = False
        self._manual_sample_stale = False
        self.manager.log(self.app.get_text("batch_log_manual_open"), "INFO")
        self._build_manual_window_widgets(win)
        win.protocol("WM_DELETE_WINDOW", self._close_manual_window)
        win.grab_set()

    def _build_manual_window_widgets(self, win):
        existing_policy = None
        if isinstance(self.manual_policy_dict, dict):
            try:
                existing_policy = manual_policy_from_dict(self.manual_policy_dict)
            except Exception:
                existing_policy = None

        sample_url_default = ""
        height_default = ""
        codec_default = ""
        container_default = ""
        audio_default = "default"
        preset2_enabled_default = False
        preset2_height_default = ""
        preset2_codec_default = ""
        preset2_container_default = ""
        preset2_audio_default = "default"
        fallback_enabled_default = False
        if existing_policy:
            sample_url_default = existing_policy.sample_video_url or ""
            height_default = str(existing_policy.preset1.target_height or "")
            codec_default = existing_policy.preset1.video_codec_pref or ""
            container_default = existing_policy.preset1.video_container_pref or ""
            audio_default = existing_policy.preset1.audio_mode or "default"
            fallback_enabled_default = bool(existing_policy.fallback_enabled)
            if existing_policy.preset2:
                preset2_enabled_default = True
                preset2_height_default = str(existing_policy.preset2.target_height or "")
                preset2_codec_default = existing_policy.preset2.video_codec_pref or ""
                preset2_container_default = existing_policy.preset2.video_container_pref or ""
                preset2_audio_default = existing_policy.preset2.audio_mode or "default"

        state = {
            "sample_url_var": tk.StringVar(value=sample_url_default),
            "sample_status_var": tk.StringVar(value=self.app.get_text("batch_manual_sample_idle")),
            "height_var": tk.StringVar(value=height_default),
            "codec_var": tk.StringVar(value=codec_default),
            "container_var": tk.StringVar(value=container_default),
            "audio_mode_var": tk.StringVar(value=audio_default),
            "preset2_enabled_var": tk.BooleanVar(value=preset2_enabled_default),
            "preset2_height_var": tk.StringVar(value=preset2_height_default),
            "preset2_codec_var": tk.StringVar(value=preset2_codec_default),
            "preset2_container_var": tk.StringVar(value=preset2_container_default),
            "preset2_audio_mode_var": tk.StringVar(value=preset2_audio_default),
            "fallback_enabled_var": tk.BooleanVar(value=fallback_enabled_default),
        }
        self._manual_window_state = state
        self._add_trace(state["sample_url_var"], "write", lambda *_args: self._manual_on_sample_url_changed())

        body = ttk.Frame(win, padding=12)
        body.pack(fill='both', expand=True)

        sample_row = ttk.Frame(body)
        sample_row.pack(fill='x', pady=(0, 8))
        ttk.Label(sample_row, text=self.app.get_text("batch_manual_sample_url")).pack(side='left')
        ttk.Entry(sample_row, textvariable=state["sample_url_var"], width=46).pack(side='left', padx=(8, 8), fill='x', expand=True)
        ttk.Button(sample_row, text=self.app.get_text("batch_manual_use_selected"), command=self._manual_pick_sample_from_selection).pack(side='left')
        state["fetch_button"] = ttk.Button(sample_row, text=self.app.get_text("batch_manual_fetch_formats"), command=self._manual_fetch_sample_formats_async)
        state["fetch_button"].pack(side='left', padx=(8, 0))

        ttk.Label(body, textvariable=state["sample_status_var"], foreground="#666666").pack(anchor='w', pady=(0, 8))
        ttk.Label(body, text=self.app.get_text("batch_manual_hint"), foreground="#666666", wraplength=620, justify='left').pack(anchor='w', pady=(0, 10))

        preset_frame = ttk.LabelFrame(body, text=self.app.get_text("batch_manual_preset1"), padding=10)
        preset_frame.pack(fill='x', pady=(0, 10))

        row1 = ttk.Frame(preset_frame)
        row1.pack(fill='x', pady=(0, 8))
        ttk.Label(row1, text=self.app.get_text("batch_manual_height")).pack(side='left')
        state["height_combo"] = ttk.Combobox(row1, textvariable=state["height_var"], state="readonly", width=12)
        state["height_combo"].configure(values=())
        state["height_combo"].pack(side='left', padx=(8, 18))
        ttk.Label(row1, text=self.app.get_text("batch_manual_codec")).pack(side='left')
        state["codec_combo"] = ttk.Combobox(row1, textvariable=state["codec_var"], state="readonly", width=12)
        state["codec_combo"].configure(values=())
        state["codec_combo"].pack(side='left', padx=(8, 18))
        ttk.Label(row1, text=self.app.get_text("batch_manual_container")).pack(side='left')
        state["container_combo"] = ttk.Combobox(row1, textvariable=state["container_var"], state="readonly", width=12)
        state["container_combo"].configure(values=())
        state["container_combo"].pack(side='left', padx=(8, 0))

        row2 = ttk.Frame(preset_frame)
        row2.pack(fill='x')
        ttk.Label(row2, text=self.app.get_text("batch_manual_audio")).pack(side='left')
        ttk.Radiobutton(row2, text=self.app.get_text("batch_manual_audio_default"), value="default", variable=state["audio_mode_var"]).pack(side='left', padx=(8, 8))
        ttk.Radiobutton(row2, text=self.app.get_text("batch_manual_audio_none"), value="no_audio", variable=state["audio_mode_var"]).pack(side='left')

        preset2_frame = ttk.LabelFrame(body, text=self.app.get_text("batch_manual_preset2"), padding=10)
        preset2_frame.pack(fill='x', pady=(0, 10))
        ttk.Checkbutton(
            preset2_frame,
            text=self.app.get_text("batch_manual_preset2_enable"),
            variable=state["preset2_enabled_var"],
            command=self._manual_update_preset2_state,
        ).pack(anchor='w', pady=(0, 8))

        row3 = ttk.Frame(preset2_frame)
        row3.pack(fill='x', pady=(0, 8))
        ttk.Label(row3, text=self.app.get_text("batch_manual_height")).pack(side='left')
        state["preset2_height_combo"] = ttk.Combobox(row3, textvariable=state["preset2_height_var"], state="readonly", width=12)
        state["preset2_height_combo"].configure(values=())
        state["preset2_height_combo"].pack(side='left', padx=(8, 18))
        ttk.Label(row3, text=self.app.get_text("batch_manual_codec")).pack(side='left')
        state["preset2_codec_combo"] = ttk.Combobox(row3, textvariable=state["preset2_codec_var"], state="readonly", width=12)
        state["preset2_codec_combo"].configure(values=())
        state["preset2_codec_combo"].pack(side='left', padx=(8, 18))
        ttk.Label(row3, text=self.app.get_text("batch_manual_container")).pack(side='left')
        state["preset2_container_combo"] = ttk.Combobox(row3, textvariable=state["preset2_container_var"], state="readonly", width=12)
        state["preset2_container_combo"].configure(values=())
        state["preset2_container_combo"].pack(side='left', padx=(8, 0))

        row4 = ttk.Frame(preset2_frame)
        row4.pack(fill='x')
        ttk.Label(row4, text=self.app.get_text("batch_manual_audio")).pack(side='left')
        state["preset2_audio_default_radio"] = ttk.Radiobutton(
            row4,
            text=self.app.get_text("batch_manual_audio_default"),
            value="default",
            variable=state["preset2_audio_mode_var"],
        )
        state["preset2_audio_default_radio"].pack(side='left', padx=(8, 8))
        state["preset2_audio_none_radio"] = ttk.Radiobutton(
            row4,
            text=self.app.get_text("batch_manual_audio_none"),
            value="no_audio",
            variable=state["preset2_audio_mode_var"],
        )
        state["preset2_audio_none_radio"].pack(side='left')

        ttk.Checkbutton(
            body,
            text=self.app.get_text("batch_manual_fallback_enable"),
            variable=state["fallback_enabled_var"],
        ).pack(anchor='w', pady=(0, 4))
        ttk.Label(
            body,
            text=self.app.get_text("batch_manual_fallback_hint"),
            foreground="#666666",
            wraplength=620,
            justify='left',
        ).pack(anchor='w', pady=(0, 10))

        actions = ttk.Frame(body)
        actions.pack(fill='x')
        state["save_button"] = ttk.Button(actions, text=self.app.get_text("batch_manual_save"), command=self._manual_save_policy_from_ui)
        state["save_button"].pack(side='right')
        ttk.Button(actions, text=self.app.get_text("batch_manual_cancel"), command=self._close_manual_window).pack(side='right', padx=(0, 8))

        if self._manual_sample_formats and sample_url_default and sample_url_default == self._manual_sample_source_url:
            state["sample_status_var"].set(
                self.app.get_text("batch_manual_sample_loaded").format(count=len(self._manual_sample_formats))
            )
            self._manual_refresh_preset_options()
        else:
            self._manual_sample_source_url = ""
            self._manual_sample_formats = []
            self._manual_clear_preset_options()
        self._manual_update_preset2_state()

    def _close_manual_window(self):
        if self._manual_window and self._manual_window.winfo_exists():
            self._manual_window.destroy()
        self._manual_window = None
        self._manual_window_state = None
        self._manual_fetch_in_progress = False
        self._manual_sample_stale = False

    def _manual_on_sample_url_changed(self):
        state = self._manual_window_state or {}
        sample_url_var = state.get("sample_url_var")
        status_var = state.get("sample_status_var")
        if not sample_url_var or not status_var:
            return

        sample_url = sample_url_var.get().strip()
        if not sample_url:
            status_var.set(self.app.get_text("batch_manual_sample_idle"))
            self._manual_sample_formats = []
            self._manual_sample_source_url = ""
            self._manual_sample_stale = False
            self._manual_clear_preset_options()
            return

        if sample_url != self._manual_sample_source_url:
            self._manual_sample_formats = []
            self._manual_sample_source_url = ""
            self._manual_sample_stale = True
            status_var.set(self.app.get_text("batch_manual_sample_stale"))
            self._manual_clear_preset_options()

    def _manual_clear_preset_options(self):
        state = self._manual_window_state or {}
        if not state:
            return
        any_label = self.app.get_text("batch_manual_any")
        for combo_key, var_key in (
            ("height_combo", "height_var"),
            ("codec_combo", "codec_var"),
            ("container_combo", "container_var"),
            ("preset2_height_combo", "preset2_height_var"),
            ("preset2_codec_combo", "preset2_codec_var"),
            ("preset2_container_combo", "preset2_container_var"),
        ):
            combo = state.get(combo_key)
            var = state.get(var_key)
            if combo:
                combo.configure(values=(any_label,))
            if var:
                var.set(any_label)
        if state.get("preset2_audio_mode_var"):
            state["preset2_audio_mode_var"].set("default")
        self._manual_update_preset2_state()

    def _manual_update_preset2_state(self):
        state = self._manual_window_state or {}
        if not state:
            return
        enabled = bool(state.get("preset2_enabled_var") and state["preset2_enabled_var"].get())
        widget_state = "readonly" if enabled else "disabled"
        for combo_key in ("preset2_height_combo", "preset2_codec_combo", "preset2_container_combo"):
            combo = state.get(combo_key)
            if combo:
                combo.configure(state=widget_state)
        radio_state = "normal" if enabled else "disabled"
        for radio_key in ("preset2_audio_default_radio", "preset2_audio_none_radio"):
            radio = state.get(radio_key)
            if radio:
                radio.configure(state=radio_state)

    def _manual_pick_sample_from_selection(self):
        state = self._manual_window_state or {}
        sample_url_var = state.get("sample_url_var")
        if not sample_url_var:
            return
        selected_entries = self._selected_entries()
        if not selected_entries:
            self.manager.log(self.app.get_text("batch_log_manual_selected_missing"), "WARNING")
            self.app.SilentMessagebox.showwarning(self.app.get_text("common_notice"), self.app.get_text("batch_manual_selected_missing"))
            return
        sample_url_var.set(selected_entries[0].url)
        self.manager.log(self.app.get_text("batch_log_manual_sample_selected").format(url=selected_entries[0].url), "INFO")

    def _manual_fetch_sample_formats_async(self):
        if self._manual_fetch_in_progress:
            self.manager.log(self.app.get_text("batch_log_manual_fetch_busy"), "WARNING")
            return
        state = self._manual_window_state or {}
        sample_url_var = state.get("sample_url_var")
        if not sample_url_var:
            return
        sample_url = sample_url_var.get().strip()
        if not sample_url:
            self.manager.log(self.app.get_text("batch_log_manual_sample_required"), "WARNING")
            self.app.SilentMessagebox.showwarning(self.app.get_text("common_notice"), self.app.get_text("batch_manual_sample_required"))
            return

        fetch_button = state.get("fetch_button")
        save_button = state.get("save_button")
        status_var = state.get("sample_status_var")
        if status_var:
            status_var.set(self.app.get_text("batch_manual_sample_fetching"))
        if fetch_button:
            fetch_button.configure(state="disabled")
        if save_button:
            save_button.configure(state="disabled")
        self._manual_fetch_in_progress = True
        self.manager.log(self.app.get_text("batch_log_manual_fetch_start").format(url=sample_url), "INFO")

        def finish():
            self._manual_fetch_in_progress = False
            current_state = self._manual_window_state or {}
            current_fetch_button = current_state.get("fetch_button")
            current_save_button = current_state.get("save_button")
            if current_fetch_button:
                current_fetch_button.configure(state="normal")
            if current_save_button:
                current_save_button.configure(state="normal")

        def run_fetch():
            try:
                use_po_token = self.use_po_token_var.get() if hasattr(self, "use_po_token_var") else False
                result = self.app.metadata_service.fetch_formats(sample_url, use_po_token=use_po_token)
                if not result.get("ok"):
                    raise RuntimeError(result.get("error_output") or self.app.get_text("batch_manual_fetch_failed"))

                formats = list(result.get("formats") or [])
                if not formats:
                    raise RuntimeError(self.app.get_text("batch_manual_sample_empty"))

                def apply_success():
                    self._manual_sample_formats = formats
                    self._manual_sample_source_url = sample_url
                    self._manual_sample_stale = False
                    if self._manual_window_state and self._manual_window_state.get("sample_status_var"):
                        self._manual_window_state["sample_status_var"].set(
                            self.app.get_text("batch_manual_sample_loaded").format(count=len(formats))
                        )
                    self.manager.log(
                        self.app.get_text("batch_log_manual_fetch_success").format(url=sample_url, count=len(formats)),
                        "INFO",
                    )
                    self._manual_refresh_preset_options()
                    finish()

                self.app.root.after(0, apply_success)
            except Exception as exc:
                message = str(exc)

                def apply_error(msg=message):
                    if self._manual_window_state and self._manual_window_state.get("sample_status_var"):
                        self._manual_window_state["sample_status_var"].set(
                            self.app.get_text("batch_manual_sample_failed").format(message=msg[:120])
                        )
                    self.manager.log(self.app.get_text("batch_log_manual_fetch_failed").format(message=msg), "ERROR")
                    finish()

                self.app.root.after(0, apply_error)

        threading.Thread(target=run_fetch, daemon=True).start()

    def _manual_refresh_preset_options(self):
        state = self._manual_window_state or {}
        if not state:
            return

        heights = []
        codecs = []
        containers = []
        seen_heights = set()
        seen_codecs = set()
        seen_containers = set()

        for item in self._manual_sample_formats:
            if item.get("is_audio_only"):
                continue
            height = int(item.get("height") or 0)
            if height > 0 and height not in seen_heights:
                seen_heights.add(height)
                heights.append(str(height))

            container = (item.get("ext") or "").strip().lower()
            if container in {"mp4", "webm"} and container not in seen_containers:
                seen_containers.add(container)
                containers.append(container)

            codec = self._normalize_manual_vcodec(item.get("vcodec") or "")
            if codec and codec not in seen_codecs:
                seen_codecs.add(codec)
                codecs.append(codec)

        heights.sort(key=lambda value: int(value), reverse=True)
        codec_order = ["h264", "av1", "vp9"]
        codecs.sort(key=lambda value: codec_order.index(value))
        containers.sort(key=lambda value: (0 if value == "mp4" else 1, value))

        any_label = self.app.get_text("batch_manual_any")
        height_values = tuple([any_label] + heights)
        codec_values = tuple([any_label] + codecs)
        container_values = tuple([any_label] + containers)

        state["height_combo"].configure(values=height_values)
        state["codec_combo"].configure(values=codec_values)
        state["container_combo"].configure(values=container_values)
        state["preset2_height_combo"].configure(values=height_values)
        state["preset2_codec_combo"].configure(values=codec_values)
        state["preset2_container_combo"].configure(values=container_values)

        for var_key, values in (
            ("height_var", height_values),
            ("codec_var", codec_values),
            ("container_var", container_values),
            ("preset2_height_var", height_values),
            ("preset2_codec_var", codec_values),
            ("preset2_container_var", container_values),
        ):
            if state[var_key].get().strip() not in values:
                state[var_key].set(values[0] if values else "")
        self._manual_update_preset2_state()

    def _normalize_manual_vcodec(self, raw_value):
        text = (raw_value or "").strip().lower()
        if not text or text == "none":
            return None
        if "avc1" in text or "avc3" in text or text.startswith("h264") or "h.264" in text:
            return "h264"
        if "av01" in text or text.startswith("av1"):
            return "av1"
        if "vp09" in text or text.startswith("vp9"):
            return "vp9"
        return None

    def _manual_read_preset_spec_from_ui(self, prefix=""):
        state = self._manual_window_state or {}
        any_label = self.app.get_text("batch_manual_any")

        raw_height = state[f"{prefix}height_var"].get().strip()
        raw_codec = state[f"{prefix}codec_var"].get().strip()
        raw_container = state[f"{prefix}container_var"].get().strip()
        audio_mode = state[f"{prefix}audio_mode_var"].get().strip() or "default"

        return ManualPresetSpec(
            target_height=int(raw_height) if raw_height and raw_height != any_label else None,
            video_codec_pref=raw_codec if raw_codec and raw_codec != any_label else None,
            video_container_pref=raw_container if raw_container and raw_container != any_label else None,
            audio_mode=audio_mode,
        )

    def _manual_save_policy_from_ui(self):
        state = self._manual_window_state or {}
        if not state:
            return
        if self._manual_sample_stale:
            self.manager.log(self.app.get_text("batch_log_manual_sample_refetch"), "WARNING")
            self.app.SilentMessagebox.showwarning(self.app.get_text("common_notice"), self.app.get_text("batch_manual_sample_refetch"))
            return
        if not self._manual_sample_formats:
            self.manager.log(self.app.get_text("batch_log_manual_sample_empty"), "WARNING")
            self.app.SilentMessagebox.showwarning(self.app.get_text("common_notice"), self.app.get_text("batch_manual_sample_empty"))
            return

        sample_url = state["sample_url_var"].get().strip() or None
        if not sample_url:
            self.manager.log(self.app.get_text("batch_log_manual_sample_required"), "WARNING")
            self.app.SilentMessagebox.showwarning(self.app.get_text("common_notice"), self.app.get_text("batch_manual_sample_required"))
            return
        if sample_url != self._manual_sample_source_url:
            self.manager.log(self.app.get_text("batch_log_manual_sample_refetch"), "WARNING")
            self.app.SilentMessagebox.showwarning(self.app.get_text("common_notice"), self.app.get_text("batch_manual_sample_refetch"))
            return

        try:
            preset1 = self._manual_read_preset_spec_from_ui()
            preset2 = None
            if state["preset2_enabled_var"].get():
                preset2 = self._manual_read_preset_spec_from_ui("preset2_")
                if not has_manual_preset_constraints(preset2):
                    raise ValueError(self.app.get_text("batch_manual_preset2_required"))
            policy = ManualBatchPolicy(
                enabled=True,
                sample_video_url=sample_url,
                preset1=preset1,
                preset2=preset2,
                fallback_enabled=state["fallback_enabled_var"].get(),
            )
            validate_manual_batch_policy(policy)
            expr = build_ytdlp_format_expr(policy)
            self.manual_policy_dict = manual_policy_to_dict(policy)
            self.manual_enabled_var.set(True)
            self.manager.log(
                self.app.get_text("batch_log_manual_save_success").format(
                    height=preset1.target_height or self.app.get_text("batch_manual_any"),
                    codec=preset1.video_codec_pref or self.app.get_text("batch_manual_any"),
                    container=preset1.video_container_pref or self.app.get_text("batch_manual_any"),
                    audio=preset1.audio_mode,
                ),
                "INFO",
            )
            self.manager.log(build_manual_rule_hint(policy, expr), "INFO")
            self._update_batch_summary()
            self._close_manual_window()
        except Exception as exc:
            message = str(exc) or self.app.get_text("batch_manual_save_failed")
            self.manager.log(self.app.get_text("batch_log_manual_save_failed").format(message=message), "ERROR")
            self.app.SilentMessagebox.showwarning(self.app.get_text("common_notice"), message)


    def _get_manual_policy_runtime(self):
        if not self.manual_enabled_var.get():
            return None, "", ""
        if not isinstance(self.manual_policy_dict, dict):
            raise ValueError(self.app.get_text("batch_manual_invalid"))

        policy = manual_policy_from_dict(self.manual_policy_dict)
        validate_manual_batch_policy(policy)
        expr = build_ytdlp_format_expr(policy)
        hint = build_manual_rule_hint(policy, expr)
        return policy, expr, hint

    def _apply_manual_policy_to_profile(self, profile, expr):
        profile.format = expr
        profile.preset_key = "manual"

    def _build_batch_summary(self):
        preset_key = self._sync_output_format_by_preset()
        preset_label = preset_key
        output_format = self.output_format_var.get().strip() or ("m4a" if preset_key == "audio_only" else "mp4")
        selected_count = len(self._selected_entries())
        flags = []
        if self.manual_enabled_var.get():
            try:
                policy, expr, _hint = self._get_manual_policy_runtime()
                preset_label = self.app.get_text("batch_preset_manual")
                flags.append(self.app.get_text("batch_flag_manual"))
                if policy and policy.sample_video_url:
                    flags.append(self.app.get_text("batch_flag_manual_sample"))
                if policy and policy.preset2 is not None:
                    flags.append(self.app.get_text("batch_flag_manual_preset2"))
                if policy and policy.fallback_enabled:
                    flags.append(self.app.get_text("batch_flag_manual_fallback"))
                if expr:
                    flags.append(self.app.get_text("batch_flag_manual_expr"))
            except Exception:
                preset_label = self.app.get_text("batch_preset_manual_invalid")
                flags.append(self.app.get_text("batch_flag_manual_invalid"))
        if self.download_sections_var.get().strip():
            flags.append(self.app.get_text("batch_flag_sections"))
        subtitle_mode = self.subtitle_mode_var.get().strip() if hasattr(self, "subtitle_mode_var") else "none"
        if subtitle_mode and subtitle_mode != "none":
            subtitle_langs = self.subtitle_langs_var.get().strip() if hasattr(self, "subtitle_langs_var") else ""
            subtitle_format = self.subtitle_format_var.get().strip() if hasattr(self, "subtitle_format_var") else ""
            sub_flags = [self.app.get_text("batch_subtitle_flag").format(mode=subtitle_mode)]
            if subtitle_langs:
                sub_flags.append(subtitle_langs)
            if subtitle_format:
                sub_flags.append(subtitle_format)
            if getattr(self, "write_subs_var", None) and self.write_subs_var.get():
                sub_flags.append(self.app.get_text("batch_subtitle_external"))
            if getattr(self, "embed_subs_var", None) and self.embed_subs_var.get():
                sub_flags.append(self.app.get_text("batch_subtitle_embed_flag"))
            flags.append(" ".join(sub_flags))
        if self.embed_thumbnail_var.get():
            flags.append(self.app.get_text("batch_flag_thumbnail"))
        if self.embed_metadata_var.get():
            flags.append(self.app.get_text("batch_flag_metadata"))
        if self.sponsorblock_enabled_var.get():
            categories = self.sponsorblock_categories_var.get().strip() or "sponsor"
            flags.append(self.app.get_text("batch_flag_sponsorblock").format(categories=categories))
        if self.write_thumbnail_var.get():
            flags.append(self.app.get_text("batch_flag_thumbnail_file"))
        if self.write_info_json_var.get():
            flags.append(self.app.get_text("batch_flag_info_json"))
        if self.write_description_var.get():
            flags.append(self.app.get_text("batch_flag_desc"))
        if self.write_chapters_var.get():
            flags.append(self.app.get_text("batch_flag_chapters"))
        if self.h264_compat_var.get():
            flags.append(self.app.get_text("batch_flag_h264"))
        if self.keep_video_var.get():
            flags.append(self.app.get_text("batch_flag_keep_video"))
        extras = "/".join(flags) if flags else self.app.get_text("batch_extras_none")
        prefix = self.custom_filename_var.get().strip() or self.app.get_text("batch_prefix_auto")
        return self.app.get_text("batch_summary_template").format(
            selected=selected_count,
            preset=preset_label,
            output=output_format,
            prefix=prefix,
            extras=extras,
        )

    def _update_batch_summary(self):
        self.batch_summary_var.set(self._build_batch_summary())

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

    def _update_source_info(self):
        if not self.batch_result:
            self.source_title_var.set(self.app.get_text("batch_source_unparsed"))
            self.source_meta_var.set(self.app.get_text("batch_source_meta_default"))
            self.source_stats_var.set(self.app.get_text("batch_source_stats_default"))
            return

        source = self.batch_result.source
        available_count = len([item for item in self.batch_entries if item.available])
        self.source_title_var.set(source.get_display_name())
        self.source_meta_var.set(
            self.app.get_text("batch_source_meta_template").format(
                type=self._source_type_label(source.source_type),
                source_id=source.source_id or '-',
                channel=source.channel or source.uploader or '-',
            )
        )
        self.source_stats_var.set(
            self.app.get_text("batch_source_stats_template").format(
                total=len(self.batch_entries),
                available=available_count,
                unavailable=len(self.batch_entries) - available_count,
            )
        )

    def _iter_visible_entries(self):
        entries = list(self.batch_entries)
        if self.hide_unavailable_var.get():
            entries = [item for item in entries if item.available]
        if self.only_shorts_var.get():
            entries = [item for item in entries if item.is_shorts]
        return entries

    def refresh_entry_table(self):
        self.entry_tree.delete(*self.entry_tree.get_children())
        self.batch_row_map = {}
        visible_entries = self._iter_visible_entries()
        for idx, item in enumerate(visible_entries, start=1):
            selected_text = "[√]" if item.selected else ""
            row_id = self.entry_tree.insert(
                "",
                "end",
                values=(
                    selected_text,
                    item.playlist_index or idx,
                    item.get_display_title(),
                    item.channel or "-",
                    self._format_duration(item.duration),
                    self._format_views(item.view_count),
                    item.upload_date or "-",
                    item.availability if item.available else (item.reason_unavailable or self.app.get_text("batch_availability_unavailable")),
                    self.app.get_text("batch_short_yes") if item.is_shorts else self.app.get_text("batch_short_no"),
                    item.url or "-",
                ),
            )
            self.batch_row_map[row_id] = item

        total_count = len(self.batch_entries)
        visible_count = len(visible_entries)
        selected_count = len(self._selected_entries())
        if total_count == 0:
            self.filter_summary_var.set(self.app.get_text("batch_filter_summary_empty"))
        elif visible_count == 0:
            self.filter_summary_var.set(self.app.get_text("batch_filter_summary_none").format(total=total_count))
        else:
            self.filter_summary_var.set(self.app.get_text("batch_filter_summary_some").format(
                visible=visible_count,
                total=total_count,
                selected=selected_count,
            ))
        self._update_source_info()
        self._update_batch_summary()

    def _toggle_selected_entry(self, _event=None):
        selection = self.entry_tree.selection()
        if not selection:
            return
        item = self.batch_row_map.get(selection[0])
        if not item or not item.available:
            return
        item.selected = not item.selected
        self.refresh_entry_table()

    def select_all_entries(self):
        for item in self.batch_entries:
            if item.available:
                item.selected = True
        self.refresh_entry_table()

    def clear_all_entries(self):
        for item in self.batch_entries:
            item.selected = False
        self.refresh_entry_table()

    def keep_available_entries_selected(self):
        for item in self.batch_entries:
            item.selected = bool(item.available)
        self.refresh_entry_table()

    def _build_task_name_prefix(self):
        custom_prefix = self.custom_filename_var.get().strip()
        return custom_prefix if custom_prefix else ""

    def _set_batch_result_feedback(self, summary, error_summary=""):
        self.batch_result_summary_var.set(summary)
        if error_summary:
            self.batch_result_error_var.set(self.app.get_text("batch_result_error").format(error=error_summary))
        else:
            self.batch_result_error_var.set(self.app.get_text("batch_result_error_default"))

    def _set_action_buttons_state(self, *, fetch_enabled=None, enqueue_enabled=None):
        if fetch_enabled is not None and hasattr(self, 'fetch_button'):
            self.fetch_button.configure(state='normal' if fetch_enabled else 'disabled')
        if enqueue_enabled is not None and hasattr(self, 'enqueue_button'):
            self.enqueue_button.configure(state='normal' if enqueue_enabled else 'disabled')

    def add_selected_tasks(self):
        if self._enqueue_in_progress:
            self._set_batch_result_feedback(self.app.get_text("batch_enqueue_in_progress"), self.app.get_text("batch_enqueue_in_progress_hint"))
            self.manager.log(self.app.get_text("batch_log_enqueue_in_progress"), "WARNING")
            return

        selected_entries = self._selected_entries()
        if not selected_entries:
            self._set_batch_result_feedback(self.app.get_text("batch_enqueue_none"), self.app.get_text("batch_enqueue_none_hint"))
            self.manager.log(self.app.get_text("batch_log_enqueue_none"), "WARNING")
            return

        custom_prefix = self._build_task_name_prefix()
        if custom_prefix and not validate_custom_filename(self, custom_prefix):
            return
        if not validate_download_sections(self, self.download_sections_var.get().strip()):
            return
        if not validate_proxy_url(self, self.proxy_url_var.get().strip()):
            return
        if not validate_advanced_args(self, self.advanced_args_var.get().strip()):
            return
        if not validate_output_format_compatibility(self):
            return

        manual_expr = ""
        manual_hint = ""
        if self.manual_enabled_var.get():
            try:
                _policy, manual_expr, manual_hint = self._get_manual_policy_runtime()
            except Exception as exc:
                message = str(exc) or self.app.get_text("batch_manual_invalid")
                self._set_batch_result_feedback(self.app.get_text("batch_enqueue_failed"), message[:120])
                self.manager.log(self.app.get_text("batch_log_manual_invalid").format(message=message), "ERROR")
                return
            if manual_hint:
                self.manager.log(manual_hint, "INFO")

        self._enqueue_in_progress = True
        self._set_action_buttons_state(enqueue_enabled=False)
        try:
            seen_urls = {getattr(task, 'url', '') for task in self.manager.task_queue}
            seen_urls.update(getattr(task, 'url', '') for task in self.manager.running_tasks.values())
            added_count = 0
            skipped_count = 0
            skipped_history_count = 0

            for index, entry in enumerate(selected_entries, start=1):
                if entry.url in seen_urls:
                    skipped_count += 1
                    continue
                if self.manager.history_repo.has_success_record(url=entry.url, video_id=entry.video_id):
                    skipped_history_count += 1
                    continue

                profile = build_profile_from_input(self)
                if custom_prefix:
                    profile.custom_filename = f"{custom_prefix}_{index:03d}_{entry.video_id or 'video'}"
                else:
                    profile.custom_filename = None
                if manual_expr:
                    self._apply_manual_policy_to_profile(profile, manual_expr)

                if self.download_sections_var.get().strip() and not validate_download_sections(self, self.download_sections_var.get().strip()):
                    self.manager.log(self.app.get_text("batch_sections_invalid"), "WARNING")
                    return

                task = self._create_task(entry.url, profile)
                task.final_title = entry.get_display_title()
                task.save_path = self.shared_save_dir_var.get()
                task.source_type = self.batch_result.source.source_type if self.batch_result else "batch"
                task.source_name = (
                    self.batch_result.source.get_display_name()
                    if self.batch_result else self.app.get_text("batch_source_default")
                )
                task.source_id = self.batch_result.source.source_id if self.batch_result else ""
                task.channel_name = entry.channel or (self.batch_result.source.channel if self.batch_result else "")
                task.channel_id = entry.channel_id or (self.batch_result.source.channel_id if self.batch_result else "")
                task.upload_date = entry.upload_date or ""
                task.archive_root = self.shared_save_dir_var.get()
                task.archive_subdir = task.resolve_archive_subdir()
                task.save_path = task.resolve_output_dir()
                if self.batch_result and self.batch_result.used_cookies:
                    task.needs_cookies = True
                self.manager.add_task(task)
                seen_urls.add(entry.url)
                added_count += 1

            result_summary = self.app.get_text("batch_enqueue_summary").format(
                added=added_count,
                skipped_queue=skipped_count,
                skipped_history=skipped_history_count,
            )
            error_summary = ""
            if added_count == 0:
                error_summary = self.app.get_text("batch_enqueue_none_new")
            self._set_batch_result_feedback(result_summary, error_summary)
            self.manager.log(self.app.get_text("batch_log_enqueue_done").format(
                added=added_count,
                skipped_queue=skipped_count,
                skipped_history=skipped_history_count,
            ))
            self._update_batch_summary()
        except Exception as exc:
            message = str(exc)
            self._set_batch_result_feedback(self.app.get_text("batch_enqueue_failed"), message[:120])
            self.manager.record_runtime_issue(self.app.get_text("batch_enqueue_failed"), message, level="ERROR")
            self.manager.log(self.app.get_text("batch_log_enqueue_failed").format(message=message), "ERROR")
        finally:
            self._enqueue_in_progress = False
            self._set_action_buttons_state(enqueue_enabled=True)

    def _create_task(self, url, profile):
        from core.youtube_models import TASK_MODE_YOUTUBE, URL_TYPE_YOUTUBE, YouTubeTaskRecord, detect_url_type

        return YouTubeTaskRecord(
            url=url,
            save_path=self.shared_save_dir_var.get(),
            profile=profile,
            task_type=TASK_MODE_YOUTUBE,
            source_platform=URL_TYPE_YOUTUBE,
            url_type=detect_url_type(url),
        )

    def fetch_batch_entries(self):
        if self._fetch_in_progress:
            self._set_batch_result_feedback(self.app.get_text("batch_fetch_in_progress"), self.app.get_text("batch_fetch_in_progress_hint"))
            self.manager.log(self.app.get_text("batch_log_fetch_in_progress"), "WARNING")
            return

        url = self._get_source_url()
        if not url:
            self.app.root.after(0, lambda: self.app.SilentMessagebox.showwarning(self.app.get_text("common_notice"), self.app.get_text("batch_warn_url_missing")))
            return

        self._fetch_in_progress = True
        self._set_action_buttons_state(fetch_enabled=False)
        self.manager.log(self.app.get_text("batch_log_fetch_start").format(url=url))
        source_type = self.source_type_var.get().strip()

        def run_fetch():
            try:
                use_po_token = self.use_po_token_var.get() if hasattr(self, "use_po_token_var") else False
                if source_type == "playlist":
                    result = self.app.metadata_service.fetch_playlist_entries(url, use_po_token=use_po_token)
                elif source_type == "channel":
                    result = self.app.metadata_service.fetch_channel_entries(url, use_po_token=use_po_token)
                else:
                    if "list=" in url.lower():
                        result = self.app.metadata_service.fetch_playlist_entries(url, use_po_token=use_po_token)
                    else:
                        result = self.app.metadata_service.fetch_channel_entries(url, use_po_token=use_po_token)

                if not result.ok:
                    raise RuntimeError(result.error_output or self.app.get_text("batch_fetch_failed_default"))

                def apply_result():
                    self.batch_result = result
                    self.batch_entries = list(result.entries)
                    self.refresh_entry_table()
                    self._set_batch_result_feedback(
                        self.app.get_text("batch_fetch_success").format(
                            total=len(result.entries),
                            available=len(result.available_entries()),
                        ),
                        ""
                    )
                    self.manager.log(self.app.get_text("batch_log_fetch_done").format(
                        available=len(result.available_entries()),
                    ))
                    self._fetch_in_progress = False
                    self._set_action_buttons_state(fetch_enabled=True)

                self.app.root.after(0, apply_result)
            except Exception as exc:
                err_msg = str(exc)

                def apply_error(msg=err_msg):
                    self._set_batch_result_feedback(self.app.get_text("batch_fetch_failed"), msg[:120])
                    self.manager.record_runtime_issue(self.app.get_text("batch_fetch_failed"), msg, level="ERROR")
                    self.manager.log(self.app.get_text("batch_log_fetch_failed").format(message=msg), "ERROR")
                    self._fetch_in_progress = False
                    self._set_action_buttons_state(fetch_enabled=True)

                self.app.root.after(0, apply_error)

        threading.Thread(target=run_fetch, daemon=True).start()

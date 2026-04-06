import threading
import tkinter as tk
from tkinter import ttk

from core.youtube_models import DOWNLOAD_PRESET_LABELS, TASK_MODE_GENERIC, TASK_MODE_YOUTUBE
from ui.input_validators import (
    prepare_direct_task,
    prepare_generic_task,
    prepare_standard_task,
    sync_output_format_by_preset,
    validate_advanced_args,
    validate_custom_filename,
    validate_download_sections,
    validate_generic_url,
    validate_proxy_url,
    validate_youtube_url,
)
from ui.video_actions import fetch_formats_async, refresh_format_view


class BaseInputFrame(ttk.LabelFrame):
    """用于构建下载输入区域的基类。"""

    def __init__(self, parent, manager, app):
        super().__init__(parent, text="", padding="12")
        self.manager = manager
        self.app = app
        self.shared_save_dir_var = app.shared_save_dir_var
        self.video_output_formats = ("mp4", "mkv", "webm")
        self._trace_ids = []
        self._create_widgets()

    def _create_widgets(self):
        raise NotImplementedError

    def _create_common_buttons(self, add_task_command):
        button_frame = ttk.Frame(self)
        button_frame.pack(fill='x', pady=(6, 0))

        ttk.Button(
            button_frame,
            text=self.app.get_text("single_add_queue"),
            command=add_task_command,
            style="Primary.TButton",
        ).pack(side='left', padx=5)

    def _create_concurrency_spinbox(self, parent, manager, font_family, font_size_normal, default_val=1, grid_row=1, grid_col_start=2, padx=(0, 0)):
        ttk.Label(parent, text=self.app.get_text("single_concurrency"), font=(font_family, font_size_normal - 1)).grid(
            row=grid_row,
            column=grid_col_start,
            sticky='w',
            pady=(5, 0),
            padx=padx,
        )

        var = self.app.download_concurrent_var
        spinbox = ttk.Spinbox(
            parent,
            from_=1,
            to=10,
            textvariable=var,
            width=5,
            font=(font_family, font_size_normal),
            state="readonly",
        )
        spinbox.grid(row=grid_row, column=grid_col_start + 1, sticky='w', padx=5, pady=(5, 0))
        return var

    def _create_speedlimit_spinbox(self, parent, font_family, font_size_normal, default_val=2):
        ttk.Label(parent, text=self.app.get_text("single_speed_limit"), font=(font_family, font_size_normal - 1)).grid(
            row=1,
            column=4,
            sticky='w',
            padx=(15, 0),
            pady=(5, 0),
        )

        var = self.app.download_speed_limit_var
        ttk.Spinbox(
            parent,
            from_=0,
            to=100,
            textvariable=var,
            width=5,
            font=(font_family, font_size_normal),
            state="readonly",
        ).grid(row=1, column=5, sticky='w', padx=5, pady=(5, 0))

        ttk.Label(parent, text=self.app.get_text("single_speed_unlimited"), font=(font_family, 8), foreground="gray").grid(
            row=1,
            column=6,
            sticky='w',
            pady=(5, 0),
        )
        return var

    def _create_retry_spinbox(self, parent, font_family, font_size_normal, default_val=3):
        ttk.Label(parent, text=self.app.get_text("single_retry"), font=(font_family, font_size_normal - 1)).grid(
            row=1,
            column=0,
            sticky='w',
            pady=(5, 0),
        )

        var = tk.IntVar(value=default_val)
        ttk.Spinbox(
            parent,
            from_=0,
            to=10,
            textvariable=var,
            width=5,
            font=(font_family, font_size_normal),
        ).grid(row=1, column=1, sticky='w', padx=5, pady=(5, 0))
        return var


class UnifiedVideoInputFrame(BaseInputFrame):
    """YouTube 专用单视频输入页。"""

    def _create_widgets(self):
        font_family = self.app.FONT_FAMILY
        font_size_title = self.app.FONT_SIZE_TITLE
        font_size_normal = self.app.FONT_SIZE_NORMAL
        silent_messagebox = self.app.SilentMessagebox
        cookies_file_path = self.app.COOKIES_FILE_PATH

        url_frame = ttk.Frame(self)
        url_frame.pack(fill='x', pady=(0, 5))

        mode_row = ttk.Frame(url_frame)
        mode_row.pack(fill='x', pady=(0, 4))
        ttk.Label(mode_row, text=self.app.get_text("single_mode"), font=(font_family, font_size_normal)).pack(side='left')
        self.mode_var = tk.StringVar(value=TASK_MODE_YOUTUBE)
        ttk.Radiobutton(
            mode_row,
            text=self.app.get_text("single_mode_youtube"),
            value=TASK_MODE_YOUTUBE,
            variable=self.mode_var,
            command=self._on_mode_changed,
        ).pack(side='left', padx=(8, 0))
        ttk.Radiobutton(
            mode_row,
            text=self.app.get_text("single_mode_generic"),
            value=TASK_MODE_GENERIC,
            variable=self.mode_var,
            command=self._on_mode_changed,
        ).pack(side='left', padx=(6, 0))

        self.url_label = ttk.Label(url_frame, text=self.app.get_text("single_url_youtube"), font=(font_family, font_size_title, 'bold'))
        self.url_label.pack(anchor='w')
        self.url_var = tk.StringVar()
        self.url_entry = tk.Text(
            url_frame,
            height=2,
            width=65,
            wrap='word',
            font=(font_family, font_size_normal),
        )
        self.url_entry.pack(fill='x', pady=(5, 0))

        def update_url_from_text(*args):
            self.url_var.set(self.url_entry.get("1.0", "end-1c"))

        self.url_entry.bind("<KeyRelease>", update_url_from_text)

        self.url_hint_var = tk.StringVar(value=self.app.get_text("single_url_hint_youtube"))
        ttk.Label(
            url_frame,
            textvariable=self.url_hint_var,
            font=(font_family, 8),
            foreground="#888888",
        ).pack(anchor='w', side='right', pady=(2, 0))

        info_card = ttk.Frame(self, style="Card.TFrame", padding=4)
        info_card.pack(fill='x', pady=2)
        ttk.Label(info_card, text=self.app.get_text("single_info_title"), style="Card.TLabel").pack(anchor='w')
        self.video_title_var = tk.StringVar(value=self.app.get_text("single_info_unparsed"))
        ttk.Label(info_card, textvariable=self.video_title_var, style="Card.TLabel", font=(font_family, font_size_normal, 'bold')).pack(anchor='w', pady=(4, 2))
        self.video_meta_var = tk.StringVar(value=self.app.get_text("single_info_meta_default"))
        ttk.Label(info_card, textvariable=self.video_meta_var, style="Card.TLabel").pack(anchor='w')

        strategy_card = ttk.Frame(self, style="Card.TFrame", padding=2)
        strategy_card.pack(fill='x', pady=2)

        strategy_row = ttk.Frame(strategy_card, style="Card.TFrame")
        strategy_row.pack(fill='x', pady=(0, 8))
        ttk.Label(strategy_row, text=self.app.get_text("single_strategy"), style="Card.TLabel").pack(side='left')
        self.preset_var = tk.StringVar(value="best_compat")
        preset_options = [
            ("best_quality", self.app.get_text("batch_preset_best_quality")),
            ("best_compat", self.app.get_text("batch_preset_best_compat")),
            ("max_1080p", self.app.get_text("batch_preset_max_1080p")),
            ("max_4k", self.app.get_text("batch_preset_max_4k")),
            ("audio_only", self.app.get_text("batch_preset_audio_only")),
            ("min_size", self.app.get_text("batch_preset_min_size")),
            ("keep_original", self.app.get_text("single_post_keep_video")),
            ("hdr_priority", self.app.get_text("batch_preset_hdr_priority")),
            ("high_fps", self.app.get_text("batch_preset_high_fps")),
            ("manual", self.app.get_text("single_strategy_manual")),
        ]
        for idx, (preset_key, preset_label) in enumerate(preset_options):
            ttk.Radiobutton(
                strategy_row,
                text=preset_label,
                value=preset_key,
                variable=self.preset_var,
                command=self._on_preset_changed,
            ).pack(side='left', padx=(10 if idx == 0 else 6, 0))

        output_row = ttk.Frame(strategy_card, style="Card.TFrame")
        output_row.pack(fill='x')
        ttk.Label(output_row, text=self.app.get_text("single_output_format"), style="Card.TLabel").pack(side='left')
        self.output_format_var = tk.StringVar(value="mp4")
        self.output_format_combo = ttk.Combobox(output_row, textvariable=self.output_format_var, state="readonly", width=12)
        self.output_format_combo.pack(side='left', padx=(10, 20))
        ttk.Label(output_row, text=self.app.get_text("single_manual_format"), style="Card.TLabel").pack(side='left')
        self.format_var_combo = tk.StringVar()
        self.selected_format_id_var = tk.StringVar()
        self.selected_format_label_var = tk.StringVar(value=self.app.get_text("single_selected_format_none"))
        ttk.Label(output_row, textvariable=self.selected_format_label_var, style="Card.TLabel").pack(side='left', padx=10, fill='x', expand=True)

        content_wrap = ttk.Frame(self, style="Card.TFrame")
        content_wrap.pack(fill='x', pady=2)

        format_card = ttk.Frame(content_wrap, style="Card.TFrame", padding=2)
        format_card.pack(fill='both', expand=True)

        btn_row = ttk.Frame(format_card, style="Card.TFrame")
        btn_row.pack(fill='x', pady=(0, 2))

        self.fetch_formats_button = tk.Button(
            btn_row,
            text=self.app.get_text("single_fetch_formats"),
            command=self.fetch_formats,
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
        self.fetch_formats_button.pack(side='left', padx=(0, 5))

        ttk.Button(
            btn_row,
            text=self.app.get_text("single_direct_download"),
            command=self.add_direct_task,
            style="Warning.Small.TButton",
        ).pack(side='left', padx=5)
        ttk.Button(
            btn_row,
            text=self.app.get_text("single_add_queue"),
            command=self.add_task,
            style="Primary.Small.TButton",
        ).pack(side='left', padx=5)

        filter_row = ttk.Frame(format_card, style="Card.TFrame")
        filter_row.pack(fill='x', pady=(0, 8))
        ttk.Label(filter_row, text=self.app.get_text("single_filter_title"), style="Card.TLabel").pack(side='left')
        self.filter_mp4_var = tk.BooleanVar(value=False)
        self.filter_with_audio_var = tk.BooleanVar(value=False)
        self.filter_60fps_var = tk.BooleanVar(value=False)
        self.filter_4k_var = tk.BooleanVar(value=False)
        self.filter_audio_only_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(filter_row, text=self.app.get_text("single_filter_mp4"), variable=self.filter_mp4_var, command=self._refresh_filters).pack(side='left', padx=(10, 0))
        ttk.Checkbutton(filter_row, text=self.app.get_text("single_filter_with_audio"), variable=self.filter_with_audio_var, command=self._refresh_filters).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(filter_row, text=self.app.get_text("single_filter_60fps"), variable=self.filter_60fps_var, command=self._refresh_filters).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(filter_row, text=self.app.get_text("single_filter_4k"), variable=self.filter_4k_var, command=self._refresh_filters).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(filter_row, text=self.app.get_text("single_filter_audio_only"), variable=self.filter_audio_only_var, command=self._refresh_filters).pack(side='left', padx=(8, 0))
        ttk.Label(filter_row, text=self.app.get_text("single_filter_sort"), style="Card.TLabel").pack(side='left', padx=(15, 4))
        self.sort_mode_var = tk.StringVar(value="quality_desc")
        self.sort_mode_combo = ttk.Combobox(filter_row, textvariable=self.sort_mode_var, state="readonly", width=14)
        self.sort_mode_combo.configure(values=("quality_desc", "quality_asc", "size_desc", "size_asc"))
        self.sort_mode_combo.pack(side='left')
        self.sort_mode_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_filters())
        self.filter_summary_var = tk.StringVar(value=self.app.get_text("single_format_fetch_hint"))
        ttk.Label(filter_row, textvariable=self.filter_summary_var, style="Card.TLabel").pack(side='right')

        table_wrap = ttk.Frame(format_card, style="Card.TFrame")
        table_wrap.pack(fill='both', expand=True, pady=(0, 6))
        columns = ("format_id", "ext", "resolution", "fps", "vcodec", "acodec", "protocol", "filesize", "dynamic_range", "note")
        self.format_table = ttk.Treeview(table_wrap, columns=columns, show='headings', height=4)
        headings = {
            "format_id": "format_id",
            "ext": "ext",
            "resolution": "resolution",
            "fps": "fps",
            "vcodec": "vcodec",
            "acodec": "acodec",
            "protocol": "protocol",
            "filesize": "filesize",
            "dynamic_range": "dynamic_range",
            "note": "note",
        }
        widths = {
            "format_id": 70,
            "ext": 60,
            "resolution": 110,
            "fps": 60,
            "vcodec": 140,
            "acodec": 120,
            "protocol": 100,
            "filesize": 90,
            "dynamic_range": 90,
            "note": 120,
        }
        for name, title in headings.items():
            self.format_table.heading(name, text=title, anchor='w')
            self.format_table.column(name, width=widths.get(name, 80), anchor='w', stretch=True)
        table_scroll_y = ttk.Scrollbar(table_wrap, orient='vertical', command=self.format_table.yview)
        table_scroll_x = ttk.Scrollbar(table_wrap, orient='horizontal', command=self.format_table.xview)
        self.format_table.configure(yscrollcommand=table_scroll_y.set, xscrollcommand=table_scroll_x.set)
        self.format_table.grid(row=0, column=0, sticky='nsew')
        table_scroll_y.grid(row=0, column=1, sticky='ns')
        table_scroll_x.grid(row=1, column=0, sticky='ew')
        table_wrap.grid_rowconfigure(0, weight=1)
        table_wrap.grid_columnconfigure(0, weight=1)
        self.format_table.bind("<Double-1>", self._on_format_table_double_click)

        self.format_rows = {}
        self.format_table_tip_var = tk.StringVar(value=self.app.get_text("single_format_table_tip"))
        ttk.Label(format_card, textvariable=self.format_table_tip_var, style="Card.TLabel", foreground="#888888").pack(anchor='w', padx=(2, 0))


        options_card = ttk.Frame(content_wrap, style="Card.TFrame", padding=2)
        options_card.pack(fill='x', pady=(2, 0))

        audio_card = ttk.Frame(options_card, style="Card.TFrame")
        audio_card.pack(fill='x', pady=(0, 3))
        ttk.Label(audio_card, text=self.app.get_text("single_audio_export"), style="Card.TLabel").pack(side='left')
        self.audio_quality_var = tk.StringVar(value="192")
        ttk.Label(audio_card, text=self.app.get_text("single_audio_quality"), style="Card.TLabel").pack(side='left', padx=(12, 4))
        self.audio_quality_combo = ttk.Combobox(audio_card, textvariable=self.audio_quality_var, state="readonly", width=8)
        self.audio_quality_combo.configure(values=("128", "192", "256", "320"))
        self.audio_quality_combo.pack(side='left', padx=(0, 12))
        ttk.Label(audio_card, text=self.app.get_text("single_audio_quality_hint"), style="Card.TLabel").pack(side='left')

        file_row = ttk.Frame(options_card, style="Card.TFrame")
        file_row.pack(fill='x', pady=(0, 2))
        ttk.Label(file_row, text=self.app.get_text("single_rename"), style="Card.TLabel").pack(side='left')
        self.custom_filename_var = tk.StringVar()
        filename_entry = tk.Text(file_row, height=1, width=30, wrap='word', font=(font_family, font_size_normal))
        filename_entry.pack(side='left', padx=10, fill='x', expand=True)

        def update_filename_var(*args):
            self.custom_filename_var.set(filename_entry.get("1.0", "end-1c"))
            self._update_filename_preview()

        filename_entry.bind("<KeyRelease>", update_filename_var)
        self.filename_entry_widget = filename_entry

        ttk.Label(
            file_row,
            text=self.app.get_text("single_rename_hint"),
            font=(font_family, 8),
            foreground="#888888",
            style="Card.TLabel",
        ).pack(side='left')

        preview_row = ttk.Frame(options_card, style="Card.TFrame")
        preview_row.pack(fill='x', pady=(0, 2))
        ttk.Label(preview_row, text=self.app.get_text("single_filename_preview"), style="Card.TLabel").pack(side='left')
        self.filename_preview_var = tk.StringVar(value=self.app.get_text("single_filename_default"))
        ttk.Label(preview_row, textvariable=self.filename_preview_var, style="Card.TLabel").pack(side='left', padx=(10, 0))

        network_row = ttk.Frame(options_card, style="Card.TFrame")
        network_row.pack(fill='x', pady=(0, 2))
        ttk.Label(network_row, text=self.app.get_text("single_network"), style="Card.TLabel").pack(side='left')
        ttk.Label(network_row, text=self.app.get_text("single_proxy"), style="Card.TLabel").pack(side='left', padx=(10, 0))
        self.proxy_url_var = tk.StringVar()
        ttk.Entry(network_row, textvariable=self.proxy_url_var, width=22).pack(side='left', padx=(4, 10))
        ttk.Label(network_row, text=self.app.get_text("single_cookies"), style="Card.TLabel").pack(side='left')
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
        ttk.Label(network_row, text=self.app.get_text("single_browser_hint"), style="Card.TLabel", foreground="#888888", font=(font_family, 8)).pack(side='left', padx=(6, 10))
        ttk.Label(network_row, text=self.app.get_text("single_advanced_args"), style="Card.TLabel").pack(side='left')
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

        sections_row = ttk.Frame(options_card, style="Card.TFrame")
        sections_row.pack(fill='x', pady=(0, 2))
        ttk.Label(sections_row, text=self.app.get_text("single_sections"), style="Card.TLabel").pack(side='left')
        self.download_sections_var = tk.StringVar()
        ttk.Entry(sections_row, textvariable=self.download_sections_var, width=18).pack(side='left', padx=(10, 6))
        ttk.Label(sections_row, text=self.app.get_text("single_sections_format"), style="Card.TLabel").pack(side='left')
        ttk.Label(sections_row, text=self.app.get_text("single_sections_example"), style="Card.TLabel", foreground="#888888", font=(font_family, 8)).pack(side='left', padx=(6, 0))

        subtitle_row = ttk.Frame(options_card, style="Card.TFrame")
        subtitle_row.pack(fill='x', pady=(0, 2))
        ttk.Label(subtitle_row, text=self.app.get_text("single_subtitle"), style="Card.TLabel").pack(side='left')
        self.subtitle_mode_var = tk.StringVar(value="none")
        ttk.Combobox(
            subtitle_row,
            textvariable=self.subtitle_mode_var,
            state="readonly",
            width=10,
            values=("none", "manual", "auto", "both"),
        ).pack(side='left', padx=(10, 6))
        ttk.Label(subtitle_row, text=self.app.get_text("single_subtitle_lang"), style="Card.TLabel").pack(side='left')
        self.subtitle_langs_var = tk.StringVar()
        ttk.Entry(subtitle_row, textvariable=self.subtitle_langs_var, width=16).pack(side='left', padx=(4, 8))
        ttk.Label(subtitle_row, text=self.app.get_text("single_subtitle_format"), style="Card.TLabel").pack(side='left')
        self.subtitle_format_var = tk.StringVar()
        ttk.Entry(subtitle_row, textvariable=self.subtitle_format_var, width=10).pack(side='left', padx=(4, 8))
        self.write_subs_var = tk.BooleanVar(value=True)
        self.embed_subs_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(subtitle_row, text=self.app.get_text("single_subtitle_write"), variable=self.write_subs_var, command=self._update_download_summary).pack(side='left', padx=(6, 0))
        ttk.Checkbutton(subtitle_row, text=self.app.get_text("single_subtitle_embed"), variable=self.embed_subs_var, command=self._update_download_summary).pack(side='left', padx=(6, 0))
        ttk.Label(subtitle_row, text=self.app.get_text("single_subtitle_hint"), style="Card.TLabel", foreground="#888888", font=(font_family, 8)).pack(side='left', padx=(6, 0))

        postprocess_row = ttk.Frame(options_card, style="Card.TFrame")
        postprocess_row.pack(fill='x', pady=(0, 2))
        ttk.Label(postprocess_row, text=self.app.get_text("single_postprocess"), style="Card.TLabel").pack(side='left')
        self.embed_thumbnail_var = tk.BooleanVar(value=True)
        self.embed_metadata_var = tk.BooleanVar(value=True)
        self.write_thumbnail_var = tk.BooleanVar(value=False)
        self.write_info_json_var = tk.BooleanVar(value=False)
        self.write_description_var = tk.BooleanVar(value=False)
        self.write_chapters_var = tk.BooleanVar(value=False)
        self.keep_video_var = tk.BooleanVar(value=False)
        self.h264_compat_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(postprocess_row, text=self.app.get_text("single_post_embed_thumbnail"), variable=self.embed_thumbnail_var, command=self._update_download_summary).pack(side='left', padx=(10, 0))
        ttk.Checkbutton(postprocess_row, text=self.app.get_text("single_post_embed_metadata"), variable=self.embed_metadata_var, command=self._update_download_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text=self.app.get_text("single_post_write_thumbnail"), variable=self.write_thumbnail_var, command=self._update_download_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text=self.app.get_text("single_post_write_info"), variable=self.write_info_json_var, command=self._update_download_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text=self.app.get_text("single_post_write_desc"), variable=self.write_description_var, command=self._update_download_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text=self.app.get_text("single_post_write_chapters"), variable=self.write_chapters_var, command=self._update_download_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text=self.app.get_text("single_post_keep_video"), variable=self.keep_video_var, command=self._update_download_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text=self.app.get_text("single_post_h264"), variable=self.h264_compat_var, command=self._update_download_summary).pack(side='left', padx=(8, 0))
        self.sponsorblock_enabled_var = tk.BooleanVar(value=False)
        self.sponsorblock_categories_var = tk.StringVar(value="sponsor")
        ttk.Checkbutton(postprocess_row, text=self.app.get_text("single_post_sponsorblock"), variable=self.sponsorblock_enabled_var, command=self._update_download_summary).pack(side='left', padx=(8, 0))
        ttk.Entry(postprocess_row, textvariable=self.sponsorblock_categories_var, width=16).pack(side='left', padx=(6, 0))
        initial_use_po_token = bool(self.app.use_po_token_var.get()) if getattr(self.app, "use_po_token_var", None) else bool(getattr(self.app, "default_use_po_token", False))
        self.use_po_token_var = tk.BooleanVar(value=initial_use_po_token)
        ttk.Checkbutton(postprocess_row, text=self.app.get_text("single_post_use_po_token"), variable=self.use_po_token_var, command=self._update_download_summary).pack(side='left', padx=(8, 0))

        summary_row = ttk.Frame(options_card, style="Card.TFrame")
        summary_row.pack(fill='x', pady=(0, 2))
        ttk.Label(summary_row, text=self.app.get_text("single_summary"), style="Card.TLabel").pack(side='left')
        self.download_summary_var = tk.StringVar(value=self.app.get_text("single_summary_default"))
        ttk.Label(summary_row, textvariable=self.download_summary_var, style="Card.TLabel").pack(side='left', padx=(10, 0))

        self.retry_var = self.app.download_retry_var
        self.concurrent_var = self.app.download_concurrent_var
        self.speedlimit_var = self.app.download_speed_limit_var

        self._create_common_buttons(self.add_task)

        self.format_fetch_used_cookies = False
        self.detected_url_type = None
        self._silent_messagebox = silent_messagebox
        self._cookies_file_path = cookies_file_path
        self.all_formats = []
        self.current_formats = []
        self._format_fetch_in_progress = False
        self._on_preset_changed()
        self._on_mode_changed(initial=True)
        self._update_filename_preview()
        self._update_download_summary()

    def _apply_mode_metadata_defaults(self):
        mode = self.mode_var.get().strip() if getattr(self, "mode_var", None) else TASK_MODE_YOUTUBE
        if mode == TASK_MODE_GENERIC:
            self.video_title_var.set(self.app.get_text("single_generic_title"))
            self.video_meta_var.set(self.app.get_text("single_generic_meta"))
            if getattr(self, "format_table_tip_var", None):
                self.format_table_tip_var.set(self.app.get_text("single_generic_no_format"))
        else:
            self.video_title_var.set(self.app.get_text("single_info_unparsed"))
            self.video_meta_var.set(self.app.get_text("single_info_meta_default"))
            if getattr(self, "format_table_tip_var", None):
                self.format_table_tip_var.set(self.app.get_text("single_format_table_tip"))

    def _set_format_controls_state(self, enabled):
        if getattr(self, "fetch_formats_button", None):
            self.fetch_formats_button.configure(
                state="normal",
                bg="#436EEE",
                activebackground="#1874CD",
                fg="white",
                activeforeground="white",
                cursor="hand2",
                command=self.fetch_formats if enabled else (lambda: self.app.SilentMessagebox.showwarning(self.app.get_text("common_notice"), self.app.get_text("single_fetch_warn_generic"))),
            )
        if getattr(self, "format_table", None):
            self.format_table.configure(selectmode="browse" if enabled else "none")
            if enabled:
                self.format_table.state(["!disabled"])
            else:
                self.format_table.state(["disabled"])
        if getattr(self, "sort_mode_combo", None):
            self.sort_mode_combo.configure(state="readonly" if enabled else "disabled")
        if getattr(self, "filter_mp4_var", None):
            self.filter_mp4_var.set(False)
        if getattr(self, "filter_with_audio_var", None):
            self.filter_with_audio_var.set(False)
        if getattr(self, "filter_60fps_var", None):
            self.filter_60fps_var.set(False)
        if getattr(self, "filter_4k_var", None):
            self.filter_4k_var.set(False)
        if getattr(self, "filter_audio_only_var", None):
            self.filter_audio_only_var.set(False)
        if getattr(self, "filter_summary_var", None) and not enabled:
            self.filter_summary_var.set(self.app.get_text("single_generic_no_format"))

    def _clear_format_state(self):
        if getattr(self, "format_table", None):
            for child in self.format_table.get_children():
                self.format_table.delete(child)
        if getattr(self, "selected_format_label_var", None):
            self.selected_format_label_var.set(self.app.get_text("single_selected_format_none"))
        self.selected_format_id_var.set("")
        self.format_rows = {}
        self.all_formats = []
        self.current_formats = []
        self.filter_summary_var.set(self.app.get_text("single_filter_summary_empty"))
        self.format_fetch_used_cookies = False

    def _on_mode_changed(self, *_args, initial=False):
        mode = self.mode_var.get().strip() if getattr(self, "mode_var", None) else TASK_MODE_YOUTUBE
        is_youtube = mode == TASK_MODE_YOUTUBE
        if getattr(self, "url_label", None):
            self.url_label.configure(text=self.app.get_text("single_url_youtube") if is_youtube else self.app.get_text("single_url_generic"))
        if getattr(self, "url_hint_var", None):
            self.url_hint_var.set(self.app.get_text("single_url_hint_youtube") if is_youtube else self.app.get_text("single_url_hint_generic"))
        if not is_youtube:
            self._clear_format_state()
        self._set_format_controls_state(is_youtube)
        self._on_preset_changed()
        self._apply_mode_metadata_defaults()
        if not initial:
            self._update_download_summary()

    def _build_filename_preview(self):
        custom_filename = self.custom_filename_var.get().strip()
        output_format = self.output_format_var.get().strip() or "mp4"
        if custom_filename:
            return f"{custom_filename}.{output_format}"
        title = self.video_title_var.get().strip()
        if title and title != self.app.get_text("single_info_unparsed") and title != self.app.get_text("single_generic_title"):
            return self.app.get_text("single_filename_from_title").format(title=title, ext=output_format)
        return self.app.get_text("single_filename_auto").format(ext=output_format)

    def _build_download_summary(self):
        preset_key = self.preset_var.get().strip() or "manual"
        preset_label = self.app.get_text(f"batch_preset_{preset_key}") if preset_key != "manual" else self.app.get_text("single_strategy_manual")
        output_format = self.output_format_var.get().strip() or "mp4"
        selected_format = self.selected_format_id_var.get().strip()
        mode = self.mode_var.get().strip() if getattr(self, "mode_var", None) else TASK_MODE_YOUTUBE
        if preset_key == "manual":
            if mode == TASK_MODE_GENERIC:
                selected_format_text = self.app.get_text("single_format_auto_site")
            else:
                selected_format_text = (self.selected_format_label_var.get().strip() if getattr(self, "selected_format_label_var", None) else selected_format) or self.app.get_text("single_format_manual_missing")
        else:
            selected_format_text = selected_format or self.app.get_text("single_format_auto_strategy")
        flags = []
        if self.download_sections_var.get().strip():
            flags.append(self.app.get_text("single_flag_sections"))
        subtitle_mode = self.subtitle_mode_var.get().strip() if hasattr(self, "subtitle_mode_var") else "none"
        if subtitle_mode and subtitle_mode != "none":
            subtitle_langs = self.subtitle_langs_var.get().strip() if hasattr(self, "subtitle_langs_var") else ""
            subtitle_format = self.subtitle_format_var.get().strip() if hasattr(self, "subtitle_format_var") else ""
            sub_flags = [self.app.get_text("single_subtitle_flag").format(mode=subtitle_mode)]
            if subtitle_langs:
                sub_flags.append(subtitle_langs)
            if subtitle_format:
                sub_flags.append(subtitle_format)
            if getattr(self, "write_subs_var", None) and self.write_subs_var.get():
                sub_flags.append(self.app.get_text("single_subtitle_external"))
            if getattr(self, "embed_subs_var", None) and self.embed_subs_var.get():
                sub_flags.append(self.app.get_text("single_subtitle_embed_flag"))
            flags.append(" ".join(sub_flags))
        if self.embed_thumbnail_var.get():
            flags.append(self.app.get_text("single_flag_thumbnail"))
        if self.embed_metadata_var.get():
            flags.append(self.app.get_text("single_flag_metadata"))
        if self.sponsorblock_enabled_var.get():
            categories = self.sponsorblock_categories_var.get().strip() or "sponsor"
            flags.append(self.app.get_text("single_flag_sponsorblock").format(categories=categories))
        if self.write_thumbnail_var.get():
            flags.append(self.app.get_text("single_flag_thumbnail_file"))
        if self.write_info_json_var.get():
            flags.append(self.app.get_text("single_flag_info_json"))
        if self.write_description_var.get():
            flags.append(self.app.get_text("single_flag_desc"))
        if self.write_chapters_var.get():
            flags.append(self.app.get_text("single_flag_chapters"))
        if self.h264_compat_var.get():
            flags.append(self.app.get_text("single_flag_h264"))
        if self.keep_video_var.get():
            flags.append(self.app.get_text("single_flag_keep_video"))
        extras = " / ".join(flags) if flags else self.app.get_text("single_post_none")
        return self.app.get_text("single_summary_template").format(preset=preset_label, output=output_format, format=selected_format_text, extras=extras)

    def _update_filename_preview(self):
        self.filename_preview_var.set(self._build_filename_preview())
        self._update_download_summary()

    def _update_download_summary(self):
        self.download_summary_var.set(self._build_download_summary())

    def _on_format_table_double_click(self, _event=None):
        selection = self.format_table.selection() if getattr(self, "format_table", None) else ()
        if not selection:
            return
        item_id = selection[0]
        payload = getattr(self, "format_rows", {}).get(item_id)
        if not payload:
            return
        format_id = payload.get("format_id") or ""
        label = payload.get("label") or format_id
        self.selected_format_id_var.set(format_id)
        self.format_var_combo.set(label)
        if getattr(self, "selected_format_label_var", None):
            self.selected_format_label_var.set(label)
        if format_id:
            self.preset_var.set("manual")
            self._on_preset_changed()
            self._update_filename_preview()

    def _refresh_filters(self):
        refresh_format_view(self)
        self._update_download_summary()

    def _on_preset_changed(self):
        sync_output_format_by_preset(self)
        preset_key = self.preset_var.get().strip()
        mode = self.mode_var.get().strip() if getattr(self, "mode_var", None) else TASK_MODE_YOUTUBE
        if getattr(self, "format_table", None):
            if mode == TASK_MODE_GENERIC:
                self.format_table.configure(selectmode="none")
                self.format_table.state(["disabled"])
            else:
                self.format_table.configure(selectmode="browse")
                self.format_table.state(["!disabled"])
        if preset_key != "manual":
            self.selected_format_id_var.set("")
            if getattr(self, "selected_format_label_var", None):
                self.selected_format_label_var.set(self.app.get_text("single_selected_format_none"))
        self._update_filename_preview()


    def _on_format_combo_selected(self, _event=None):
        raw = self.format_var_combo.get().strip() if getattr(self, "format_var_combo", None) else ""
        format_id = raw.split('|', 1)[0].strip() if raw else ""
        self.selected_format_id_var.set(format_id)
        if getattr(self, "selected_format_label_var", None):
            self.selected_format_label_var.set(raw or self.app.get_text("single_selected_format_none"))
        if format_id:
            self.preset_var.set("manual")
            self._on_preset_changed()
            self._update_filename_preview()

    def fetch_formats(self):
        if getattr(self, "mode_var", None) and self.mode_var.get().strip() != TASK_MODE_YOUTUBE:
            self.manager.log(self.app.get_text("single_fetch_warn_generic"), "WARNING")
            self.app.SilentMessagebox.showwarning(self.app.get_text("common_notice"), self.app.get_text("single_fetch_warn_generic"))
            return
        fetch_formats_async(self)

    def add_task(self):
        url = self.url_entry.get("1.0", "end-1c").strip()
        mode = self.mode_var.get().strip() if getattr(self, "mode_var", None) else TASK_MODE_YOUTUBE
        if mode == TASK_MODE_GENERIC:
            if not validate_generic_url(self, url):
                return
            detected = self.detected_url_type or "unknown"
            self.manager.log(self.app.get_text("single_log_url_generic").format(url=url, detected=detected))
        else:
            if not validate_youtube_url(self, url):
                return
            self.manager.log(self.app.get_text("single_log_url_youtube").format(url=url))

        custom_filename = self.custom_filename_var.get().strip()
        if not validate_custom_filename(self, custom_filename):
            return
        if not validate_download_sections(self, self.download_sections_var.get().strip()):
            return
        if not validate_proxy_url(self, self.proxy_url_var.get().strip()):
            return
        if not validate_advanced_args(self, self.advanced_args_var.get().strip()):
            return

        preset_key = self.preset_var.get().strip() or "manual"
        if mode == TASK_MODE_YOUTUBE and preset_key == "manual" and not self.selected_format_id_var.get().strip():
            self.manager.log(self.app.get_text("single_log_manual_missing"), "WARNING")
            return

        if mode == TASK_MODE_GENERIC:
            task = prepare_generic_task(self, url)
        else:
            task = prepare_standard_task(self, url)
        if not task:
            return

        self.manager.add_task(task)
        self._reset_form(clear_formats=True)

    def add_direct_task(self):
        url = self.url_entry.get("1.0", "end-1c").strip()
        mode = self.mode_var.get().strip() if getattr(self, "mode_var", None) else TASK_MODE_YOUTUBE
        if mode == TASK_MODE_GENERIC:
            if not validate_generic_url(self, url):
                return
            detected = self.detected_url_type or "unknown"
            self.manager.log(self.app.get_text("single_log_url_generic_direct").format(url=url, detected=detected))
        else:
            if not validate_youtube_url(self, url):
                return
            self.manager.log(self.app.get_text("single_log_url_youtube_direct").format(url=url))

        custom_filename = self.custom_filename_var.get().strip()
        if not validate_custom_filename(self, custom_filename):
            return
        if not validate_download_sections(self, self.download_sections_var.get().strip()):
            return
        if not validate_proxy_url(self, self.proxy_url_var.get().strip()):
            return
        if not validate_advanced_args(self, self.advanced_args_var.get().strip()):
            return

        preset_key = self.preset_var.get().strip() or "manual"
        if mode == TASK_MODE_YOUTUBE and preset_key == "manual" and not self.selected_format_id_var.get().strip():
            self.manager.log(self.app.get_text("single_log_direct_manual_missing"), "WARNING")
            return

        if mode == TASK_MODE_GENERIC:
            task = prepare_generic_task(self, url)
        else:
            task = prepare_direct_task(self, url)
        if not task:
            self.manager.log(self.app.get_text("single_direct_task_failed"), "ERROR")
            return
        self.manager.add_task(task)
        self._reset_form(clear_formats=False)


    def _reset_form(self, clear_formats):
        self.url_entry.delete("1.0", "end")
        self.custom_filename_var.set("")
        self.filename_entry_widget.delete("1.0", "end")
        if clear_formats:
            self._clear_format_state()
            self._apply_mode_metadata_defaults()
        self._update_filename_preview()

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

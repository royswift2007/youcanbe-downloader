import threading
import tkinter as tk
from tkinter import ttk

from core.youtube_models import BATCH_SOURCE_CHANNEL, BATCH_SOURCE_PLAYLIST, BATCH_SOURCE_UPLOADS
from ui.input_validators import AUDIO_OUTPUT_FORMATS, VIDEO_OUTPUT_FORMATS, build_profile_from_input, validate_advanced_args, validate_custom_filename, validate_download_sections, validate_proxy_url


class BatchSourceInputFrame(ttk.LabelFrame):
    """YouTube 批量来源页：支持播放列表与频道条目预览。"""

    def __init__(self, parent, manager, app):
        super().__init__(parent, text="", padding="12")
        self.manager = manager
        self.app = app
        self.shared_save_dir_var = app.shared_save_dir_var
        self.batch_result = None
        self.batch_entries = []
        self.batch_row_map = {}
        self._fetch_in_progress = False
        self._enqueue_in_progress = False
        self._create_widgets()

    def _create_widgets(self):
        font_family = self.app.FONT_FAMILY
        font_size_title = self.app.FONT_SIZE_TITLE
        font_size_normal = self.app.FONT_SIZE_NORMAL

        url_frame = ttk.Frame(self)
        url_frame.pack(fill='x', pady=(0, 6))
        ttk.Label(url_frame, text="批量 URL:", font=(font_family, font_size_title, 'bold')).pack(anchor='w')
        self.url_entry = tk.Text(url_frame, height=2, width=65, wrap='word', font=(font_family, font_size_normal))
        self.url_entry.pack(fill='x', pady=(5, 0))
        ttk.Label(
            url_frame,
            text="支持播放列表、频道首页、/videos 页面；当前用于条目预览与后续批量入队",
            font=(font_family, 8),
            foreground="#888888",
        ).pack(anchor='w', pady=(2, 0))

        source_card = ttk.Frame(self, style="Card.TFrame", padding=(8, 4))
        source_card.pack(fill='x', pady=(5, 2))
        header_row = ttk.Frame(source_card, style="Card.TFrame")
        header_row.pack(fill='x')
        ttk.Label(header_row, text="批量来源摘要:", style="Card.TLabel", font=(font_family, font_size_normal - 1, 'bold')).pack(side='left')
        self.source_title_var = tk.StringVar(value="尚未解析批量来源")
        ttk.Label(header_row, textvariable=self.source_title_var, style="Card.TLabel", font=(font_family, font_size_normal, 'bold')).pack(side='left', padx=(8, 0))
        meta_row = ttk.Frame(source_card, style="Card.TFrame")
        meta_row.pack(fill='x')
        self.source_meta_var = tk.StringVar(value="类型: - | 来源ID: - | 频道: -")
        ttk.Label(meta_row, textvariable=self.source_meta_var, style="Card.TLabel").pack(side='left')
        self.source_stats_var = tk.StringVar(value="总条目: - | 可用: - | 不可用: -")
        ttk.Label(meta_row, textvariable=self.source_stats_var, style="Card.TLabel").pack(side='left', padx=(16, 0))

        action_row = ttk.Frame(self, style="Card.TFrame")
        action_row.pack(fill='x', pady=(0, 6))
        self.fetch_button = ttk.Button(
            action_row,
            text="解析批量条目",
            command=self.fetch_batch_entries,
            style="Info.Small.TButton",
        )
        self.fetch_button.pack(side='left', padx=(0, 5))
        ttk.Button(action_row, text="全选", command=self.select_all_entries).pack(side='left', padx=5)
        ttk.Button(action_row, text="全不选", command=self.clear_all_entries).pack(side='left', padx=5)
        ttk.Button(action_row, text="仅保留可用", command=self.keep_available_entries_selected).pack(side='left', padx=5)
        self.enqueue_button = ttk.Button(action_row, text="添加选中到队列", command=self.add_selected_tasks, style="Primary.TButton")
        self.enqueue_button.pack(side='right', padx=5)

        filter_row = ttk.Frame(self, style="Card.TFrame")
        filter_row.pack(fill='x', pady=(0, 6))
        ttk.Label(filter_row, text="来源类型:", style="Card.TLabel").pack(side='left')
        self.source_type_var = tk.StringVar(value="auto")
        source_type_combo = ttk.Combobox(filter_row, textvariable=self.source_type_var, state="readonly", width=14)
        source_type_combo.configure(values=("auto", "playlist", "channel"))
        source_type_combo.pack(side='left', padx=(8, 18))
        self.hide_unavailable_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(filter_row, text="隐藏不可用条目", variable=self.hide_unavailable_var, command=self.refresh_entry_table).pack(side='left')
        self.only_shorts_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(filter_row, text="仅 Shorts", variable=self.only_shorts_var, command=self.refresh_entry_table).pack(side='left', padx=(8, 0))
        self.filter_summary_var = tk.StringVar(value="尚未解析批量条目")
        ttk.Label(filter_row, textvariable=self.filter_summary_var, style="Card.TLabel").pack(side='right')

        result_card = ttk.Frame(self, style="Card.TFrame", padding=(8, 4))
        result_card.pack(fill='x', pady=(0, 4))
        result_row = ttk.Frame(result_card, style="Card.TFrame")
        result_row.pack(fill='x')
        ttk.Label(result_row, text="批量处理结果:", style="Card.TLabel", font=(font_family, font_size_normal - 1, 'bold')).pack(side='left')
        self.batch_result_summary_var = tk.StringVar(value="尚无最近一次批量处理结果")
        ttk.Label(result_row, textvariable=self.batch_result_summary_var, style="Card.TLabel", font=(font_family, font_size_normal, 'bold')).pack(side='left', padx=(8, 0))
        self.batch_result_error_var = tk.StringVar(value="最近错误摘要: 无")
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
            "selected": "选择",
            "index": "序号",
            "title": "标题",
            "channel": "频道",
            "duration": "时长",
            "views": "观看",
            "upload_date": "上传日期",
            "availability": "可用性",
            "shorts": "Shorts",
            "url": "URL",
        }
        for name, title in headings.items():
            self.entry_tree.heading(name, text=title)
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
        ttk.Label(preset_row, text="下载策略:", style="Card.TLabel").pack(side='left')
        self.preset_var = tk.StringVar(value="best_compat")
        preset_options = [
            ("best_quality", "最佳画质"),
            ("best_compat", "最佳兼容"),
            ("max_1080p", "最高 1080p"),
            ("max_4k", "最高 4K"),
            ("audio_only", "仅音频"),
            ("min_size", "最小体积"),
        ]
        for idx, (preset_key, preset_label) in enumerate(preset_options):
            ttk.Radiobutton(
                preset_row,
                text=preset_label,
                value=preset_key,
                variable=self.preset_var,
                command=self._update_batch_summary,
            ).pack(side='left', padx=(10 if idx == 0 else 6, 0))

        output_row = ttk.Frame(options_card, style="Card.TFrame")
        output_row.pack(fill='x', pady=(0, 5))
        ttk.Label(output_row, text="输出格式:", style="Card.TLabel").pack(side='left')
        self.output_format_var = tk.StringVar(value="mp4")
        self.output_format_combo = ttk.Combobox(output_row, textvariable=self.output_format_var, state="readonly", width=10)
        self.output_format_combo.configure(values=VIDEO_OUTPUT_FORMATS)
        self.output_format_combo.pack(side='left', padx=(10, 16))
        self.output_format_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_batch_summary())

        ttk.Label(output_row, text="音质(k):", style="Card.TLabel").pack(side='left')
        self.audio_quality_var = tk.StringVar(value="192")
        self.audio_quality_combo = ttk.Combobox(output_row, textvariable=self.audio_quality_var, state="readonly", width=8)
        self.audio_quality_combo.configure(values=("128", "192", "256", "320"))
        self.audio_quality_combo.pack(side='left', padx=(10, 16))
        self.audio_quality_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_batch_summary())

        ttk.Label(output_row, text="自定义前缀:", style="Card.TLabel").pack(side='left')
        self.custom_filename_var = tk.StringVar()
        self.filename_entry = ttk.Entry(output_row, textvariable=self.custom_filename_var, width=26)
        self.filename_entry.pack(side='left', padx=(10, 0), fill='x', expand=True)
        self.custom_filename_var.trace_add('write', lambda *_args: self._update_batch_summary())

        sections_row = ttk.Frame(options_card, style="Card.TFrame")
        sections_row.pack(fill='x', pady=(0, 5))
        ttk.Label(sections_row, text="区段下载:", style="Card.TLabel").pack(side='left')
        self.download_sections_var = tk.StringVar()
        ttk.Entry(sections_row, textvariable=self.download_sections_var, width=18).pack(side='left', padx=(10, 6))
        ttk.Label(sections_row, text="格式: HH:MM:SS-MM:SS", style="Card.TLabel").pack(side='left')
        ttk.Label(sections_row, text="(例: 00:01:00-00:02:30)", style="Card.TLabel", foreground="#888888", font=(font_family, 8)).pack(side='left', padx=(6, 0))

        postprocess_row = ttk.Frame(options_card, style="Card.TFrame")
        postprocess_row.pack(fill='x', pady=(0, 5))
        ttk.Label(postprocess_row, text="后处理:", style="Card.TLabel").pack(side='left')
        self.embed_thumbnail_var = tk.BooleanVar(value=True)
        self.embed_metadata_var = tk.BooleanVar(value=True)
        self.write_thumbnail_var = tk.BooleanVar(value=False)
        self.write_info_json_var = tk.BooleanVar(value=False)
        self.write_description_var = tk.BooleanVar(value=False)
        self.write_chapters_var = tk.BooleanVar(value=False)
        self.h264_compat_var = tk.BooleanVar(value=False)
        self.keep_video_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(postprocess_row, text="嵌入封面", variable=self.embed_thumbnail_var, command=self._update_batch_summary).pack(side='left', padx=(10, 0))
        ttk.Checkbutton(postprocess_row, text="嵌入元数据", variable=self.embed_metadata_var, command=self._update_batch_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text="写入缩略图", variable=self.write_thumbnail_var, command=self._update_batch_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text="写入 JSON", variable=self.write_info_json_var, command=self._update_batch_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text="写入描述", variable=self.write_description_var, command=self._update_batch_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text="章节写入", variable=self.write_chapters_var, command=self._update_batch_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text="H.264 兼容", variable=self.h264_compat_var, command=self._update_batch_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text="保留中间视频", variable=self.keep_video_var, command=self._update_batch_summary).pack(side='left', padx=(8, 0))
        self.sponsorblock_enabled_var = tk.BooleanVar(value=False)
        self.sponsorblock_categories_var = tk.StringVar(value="sponsor")
        ttk.Checkbutton(postprocess_row, text="SponsorBlock", variable=self.sponsorblock_enabled_var, command=self._update_batch_summary).pack(side='left', padx=(8, 0))
        ttk.Entry(postprocess_row, textvariable=self.sponsorblock_categories_var, width=16).pack(side='left', padx=(6, 0))
        self.use_po_token_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(postprocess_row, text="启用 PO Token", variable=self.use_po_token_var, command=self._update_batch_summary).pack(side='left', padx=(8, 0))

        settings_row = ttk.Frame(options_card, style="Card.TFrame")
        settings_row.pack(fill='x', pady=(0, 5))
        ttk.Label(settings_row, text="重试:", style="Card.TLabel").pack(side='left')
        self.retry_var = tk.StringVar(value="3")
        ttk.Spinbox(settings_row, from_=0, to=10, textvariable=self.retry_var, width=5).pack(side='left', padx=(8, 18))
        ttk.Label(settings_row, text="并发数:", style="Card.TLabel").pack(side='left')
        self.concurrent_var = tk.StringVar(value="1")
        concurrent_box = ttk.Spinbox(settings_row, from_=1, to=10, textvariable=self.concurrent_var, width=5)
        concurrent_box.pack(side='left', padx=(8, 18))
        self.concurrent_var.trace_add('write', self._on_concurrent_changed)
        ttk.Label(settings_row, text="限速(MB/s):", style="Card.TLabel").pack(side='left')
        self.speedlimit_var = tk.StringVar(value="2")
        ttk.Spinbox(settings_row, from_=0, to=100, textvariable=self.speedlimit_var, width=5).pack(side='left', padx=(8, 12))
        ttk.Label(settings_row, text="(0=不限)", style="Card.TLabel").pack(side='left')

        network_row = ttk.Frame(options_card, style="Card.TFrame")
        network_row.pack(fill='x', pady=(0, 5))
        ttk.Label(network_row, text="网络设置:", style="Card.TLabel").pack(side='left')
        ttk.Label(network_row, text="代理:", style="Card.TLabel").pack(side='left', padx=(10, 0))
        self.proxy_url_var = tk.StringVar()
        ttk.Entry(network_row, textvariable=self.proxy_url_var, width=22).pack(side='left', padx=(4, 10))
        ttk.Label(network_row, text="Cookies:", style="Card.TLabel").pack(side='left')
        self.cookies_mode_var = tk.StringVar(value="file")
        ttk.Combobox(network_row, textvariable=self.cookies_mode_var, state="readonly", width=8, values=("file", "browser")).pack(side='left', padx=(4, 6))
        self.cookies_browser_var = tk.StringVar()
        ttk.Entry(network_row, textvariable=self.cookies_browser_var, width=16).pack(side='left', padx=(0, 6))
        ttk.Label(network_row, text="高级参数:", style="Card.TLabel").pack(side='left')
        self.advanced_args_var = tk.StringVar()
        ttk.Entry(network_row, textvariable=self.advanced_args_var, width=18).pack(side='left', padx=(4, 0))

        subtitle_row = ttk.Frame(options_card, style="Card.TFrame")
        subtitle_row.pack(fill='x', pady=(0, 5))
        ttk.Label(subtitle_row, text="字幕:", style="Card.TLabel").pack(side='left')
        self.subtitle_mode_var = tk.StringVar(value="none")
        ttk.Combobox(
            subtitle_row,
            textvariable=self.subtitle_mode_var,
            state="readonly",
            width=10,
            values=("none", "manual", "auto", "both"),
        ).pack(side='left', padx=(10, 6))
        ttk.Label(subtitle_row, text="语言:", style="Card.TLabel").pack(side='left')
        self.subtitle_langs_var = tk.StringVar()
        ttk.Entry(subtitle_row, textvariable=self.subtitle_langs_var, width=16).pack(side='left', padx=(4, 8))
        ttk.Label(subtitle_row, text="格式:", style="Card.TLabel").pack(side='left')
        self.subtitle_format_var = tk.StringVar()
        ttk.Entry(subtitle_row, textvariable=self.subtitle_format_var, width=10).pack(side='left', padx=(4, 8))
        self.write_subs_var = tk.BooleanVar(value=True)
        self.embed_subs_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(subtitle_row, text="外挂字幕", variable=self.write_subs_var, command=self._update_batch_summary).pack(side='left', padx=(6, 0))
        ttk.Checkbutton(subtitle_row, text="内嵌字幕", variable=self.embed_subs_var, command=self._update_batch_summary).pack(side='left', padx=(6, 0))
        ttk.Label(subtitle_row, text="(mkv更稳)", style="Card.TLabel", foreground="#888888", font=(font_family, 8)).pack(side='left', padx=(6, 0))

        throttle_row = ttk.Frame(options_card, style="Card.TFrame")
        throttle_row.pack(fill='x', pady=(0, 5))
        ttk.Label(throttle_row, text="防风控:", style="Card.TLabel").pack(side='left')
        ttk.Label(throttle_row, text="请求间隔(s):", style="Card.TLabel").pack(side='left', padx=(10, 0))
        self.sleep_interval_var = tk.StringVar(value="5")
        ttk.Spinbox(throttle_row, from_=0, to=60, textvariable=self.sleep_interval_var, width=5).pack(side='left', padx=(4, 12))
        ttk.Label(throttle_row, text="最大间隔(s):", style="Card.TLabel").pack(side='left')
        self.max_sleep_interval_var = tk.StringVar(value="10")
        ttk.Spinbox(throttle_row, from_=0, to=120, textvariable=self.max_sleep_interval_var, width=5).pack(side='left', padx=(4, 12))
        ttk.Label(throttle_row, text="API间隔(s):", style="Card.TLabel").pack(side='left')
        self.sleep_requests_var = tk.StringVar(value="1")
        ttk.Spinbox(throttle_row, from_=0, to=30, textvariable=self.sleep_requests_var, width=5).pack(side='left', padx=(4, 12))
        ttk.Label(throttle_row, text="重试间隔(s):", style="Card.TLabel").pack(side='left')
        self.retry_interval_var = tk.StringVar(value="10")
        ttk.Spinbox(throttle_row, from_=0, to=300, textvariable=self.retry_interval_var, width=5).pack(side='left', padx=(4, 0))

        summary_row = ttk.Frame(options_card, style="Card.TFrame")
        summary_row.pack(fill='x')
        ttk.Label(summary_row, text="批量摘要:", style="Card.TLabel").pack(side='left')
        self.batch_summary_var = tk.StringVar(value="尚未配置批量下载摘要")
        ttk.Label(summary_row, textvariable=self.batch_summary_var, style="Card.TLabel").pack(side='left', padx=(10, 0))

        self._pane_restore_done = False
        self._on_concurrent_changed()
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
        return f"{value:,}" if value else "未知"

    def _source_type_label(self, source_type):
        if source_type == BATCH_SOURCE_PLAYLIST:
            return "播放列表"
        if source_type in {BATCH_SOURCE_CHANNEL, BATCH_SOURCE_UPLOADS}:
            return "频道"
        return "未知"

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
            self.output_format_combo.configure(values=VIDEO_OUTPUT_FORMATS)
            if self.output_format_var.get().strip() not in VIDEO_OUTPUT_FORMATS:
                self.output_format_var.set("mp4")
        return preset_key

    def _build_batch_summary(self):
        preset_key = self._sync_output_format_by_preset()
        output_format = self.output_format_var.get().strip() or ("m4a" if preset_key == "audio_only" else "mp4")
        selected_count = len(self._selected_entries())
        flags = []
        if self.download_sections_var.get().strip():
            flags.append("区段")
        subtitle_mode = self.subtitle_mode_var.get().strip() if hasattr(self, "subtitle_mode_var") else "none"
        if subtitle_mode and subtitle_mode != "none":
            subtitle_langs = self.subtitle_langs_var.get().strip() if hasattr(self, "subtitle_langs_var") else ""
            subtitle_format = self.subtitle_format_var.get().strip() if hasattr(self, "subtitle_format_var") else ""
            sub_flags = [f"字幕:{subtitle_mode}"]
            if subtitle_langs:
                sub_flags.append(subtitle_langs)
            if subtitle_format:
                sub_flags.append(subtitle_format)
            if getattr(self, "write_subs_var", None) and self.write_subs_var.get():
                sub_flags.append("外挂")
            if getattr(self, "embed_subs_var", None) and self.embed_subs_var.get():
                sub_flags.append("内嵌")
            flags.append(" ".join(sub_flags))
        if self.embed_thumbnail_var.get():
            flags.append("封面")
        if self.embed_metadata_var.get():
            flags.append("元数据")
        if self.sponsorblock_enabled_var.get():
            categories = self.sponsorblock_categories_var.get().strip() or "sponsor"
            flags.append(f"SB:{categories}")
        if self.write_thumbnail_var.get():
            flags.append("缩略图")
        if self.write_info_json_var.get():
            flags.append("JSON")
        if self.write_description_var.get():
            flags.append("描述")
        if self.write_chapters_var.get():
            flags.append("章节")
        if self.h264_compat_var.get():
            flags.append("H.264兼容")
        if self.keep_video_var.get():
            flags.append("保留中间视频")
        extras = "/".join(flags) if flags else "无后处理"
        prefix = self.custom_filename_var.get().strip() or "自动标题"
        return f"已选 {selected_count} 个 | 策略 {preset_key} | 输出 {output_format} | 前缀 {prefix} | 后处理 {extras}"

    def _update_batch_summary(self):
        self.batch_summary_var.set(self._build_batch_summary())

    def _on_concurrent_changed(self, *_args):
        raw_value = self.concurrent_var.get().strip()
        if not raw_value:
            return
        try:
            concurrent = int(raw_value)
        except ValueError:
            return
        if concurrent < 1:
            return
        self.manager.max_concurrent = concurrent
        self.manager.start_next_task()

    def _update_source_info(self):
        if not self.batch_result:
            self.source_title_var.set("尚未解析批量来源")
            self.source_meta_var.set("类型: - | 来源ID: - | 频道: -")
            self.source_stats_var.set("总条目: - | 可用: - | 不可用: -")
            return

        source = self.batch_result.source
        available_count = len([item for item in self.batch_entries if item.available])
        self.source_title_var.set(source.get_display_name())
        self.source_meta_var.set(
            f"类型: {self._source_type_label(source.source_type)} | 来源ID: {source.source_id or '-'} | 频道: {source.channel or source.uploader or '-'}"
        )
        self.source_stats_var.set(
            f"总条目: {len(self.batch_entries)} | 可用: {available_count} | 不可用: {len(self.batch_entries) - available_count}"
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
                    item.availability if item.available else (item.reason_unavailable or "不可用"),
                    "是" if item.is_shorts else "否",
                    item.url or "-",
                ),
            )
            self.batch_row_map[row_id] = item

        total_count = len(self.batch_entries)
        visible_count = len(visible_entries)
        selected_count = len(self._selected_entries())
        if total_count == 0:
            self.filter_summary_var.set("尚未解析批量条目")
        elif visible_count == 0:
            self.filter_summary_var.set(f"筛选后无可见条目（原始 {total_count} 个）")
        else:
            self.filter_summary_var.set(f"已显示 {visible_count} / {total_count} 个条目，已选 {selected_count} 个")
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
        self.batch_result_error_var.set(f"最近错误摘要: {error_summary or '无'}")

    def _set_action_buttons_state(self, *, fetch_enabled=None, enqueue_enabled=None):
        if fetch_enabled is not None and hasattr(self, 'fetch_button'):
            self.fetch_button.configure(state='normal' if fetch_enabled else 'disabled')
        if enqueue_enabled is not None and hasattr(self, 'enqueue_button'):
            self.enqueue_button.configure(state='normal' if enqueue_enabled else 'disabled')

    def add_selected_tasks(self):
        if self._enqueue_in_progress:
            self._set_batch_result_feedback("本次未入队：已有批量入队操作正在执行", "请等待当前批量入队完成后再试")
            self.manager.log("⚠️ 批量入队正在执行中，已忽略重复点击", "WARNING")
            return

        selected_entries = self._selected_entries()
        if not selected_entries:
            self._set_batch_result_feedback("本次未入队：没有已选中的可用条目", "未选择任何可用条目")
            self.manager.log("⚠️ 当前没有已选中的可用条目", "WARNING")
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

                if self.download_sections_var.get().strip() and not validate_download_sections(self, self.download_sections_var.get().strip()):
                    self.manager.log("⚠️ 区段格式无效，已取消本次批量入队", "WARNING")
                    return

                task = self._create_task(entry.url, profile)
                task.final_title = entry.get_display_title()
                task.save_path = self.shared_save_dir_var.get()
                task.source_type = self.batch_result.source.source_type if self.batch_result else "batch"
                task.source_name = self.batch_result.source.get_display_name() if self.batch_result else "批量来源"
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

            result_summary = f"本次批量入队：新增 {added_count} 个，跳过队列重复 {skipped_count} 个，跳过历史重复 {skipped_history_count} 个"
            error_summary = ""
            if added_count == 0:
                error_summary = "没有新的可入队条目"
            self._set_batch_result_feedback(result_summary, error_summary)
            self.manager.log(f"[完成] 批量入队完成：新增 {added_count} 个，跳过队列重复 {skipped_count} 个，跳过历史重复 {skipped_history_count} 个")
            self._update_batch_summary()
        except Exception as exc:
            message = str(exc)
            self._set_batch_result_feedback("本次批量入队失败", message[:120])
            self.manager.record_runtime_issue("批量入队失败", message, level="ERROR")
            self.manager.log(f"❌ 批量入队失败: {message}", "ERROR")
        finally:
            self._enqueue_in_progress = False
            self._set_action_buttons_state(enqueue_enabled=True)

    def _create_task(self, url, profile):
        from core.youtube_models import YouTubeTaskRecord

        return YouTubeTaskRecord(
            url=url,
            save_path=self.shared_save_dir_var.get(),
            profile=profile,
            task_type='youtube',
        )

    def fetch_batch_entries(self):
        if self._fetch_in_progress:
            self._set_batch_result_feedback("最近一次解析未启动：已有解析任务正在执行", "请等待当前批量解析完成后再试")
            self.manager.log("⚠️ 批量来源解析正在执行中，已忽略重复点击", "WARNING")
            return

        url = self._get_source_url()
        if not url:
            self.app.root.after(0, lambda: self.app.SilentMessagebox.showwarning("提示", "请输入批量 URL"))
            return

        self._fetch_in_progress = True
        self._set_action_buttons_state(fetch_enabled=False)
        self.manager.log(f"📚 开始解析批量来源: {url}")
        source_type = self.source_type_var.get().strip()

        def run_fetch():
            try:
                if source_type == "playlist":
                    result = self.app.metadata_service.fetch_playlist_entries(url)
                elif source_type == "channel":
                    result = self.app.metadata_service.fetch_channel_entries(url)
                else:
                    if "list=" in url.lower():
                        result = self.app.metadata_service.fetch_playlist_entries(url)
                    else:
                        result = self.app.metadata_service.fetch_channel_entries(url)

                if not result.ok:
                    raise RuntimeError(result.error_output or "批量条目解析失败")

                def apply_result():
                    self.batch_result = result
                    self.batch_entries = list(result.entries)
                    self.refresh_entry_table()
                    self._set_batch_result_feedback(
                        f"最近一次解析成功：共 {len(result.entries)} 个条目，可用 {len(result.available_entries())} 个",
                        ""
                    )
                    self.manager.log(f"[完成] 批量来源解析完成，可用条目 {len(result.available_entries())} 个")
                    self._fetch_in_progress = False
                    self._set_action_buttons_state(fetch_enabled=True)

                self.app.root.after(0, apply_result)
            except Exception as exc:
                err_msg = str(exc)

                def apply_error(msg=err_msg):
                    self._set_batch_result_feedback("最近一次解析失败", msg[:120])
                    self.manager.record_runtime_issue("批量来源解析失败", msg, level="ERROR")
                    self.manager.log(f"❌ 批量来源解析失败: {msg}", "ERROR")
                    self._fetch_in_progress = False
                    self._set_action_buttons_state(fetch_enabled=True)

                self.app.root.after(0, apply_error)

        threading.Thread(target=run_fetch, daemon=True).start()

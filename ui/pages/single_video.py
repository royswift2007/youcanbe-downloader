import threading
import tkinter as tk
from tkinter import ttk

from core.youtube_models import DOWNLOAD_PRESET_LABELS
from ui.input_validators import (
    prepare_direct_task,
    prepare_standard_task,
    sync_output_format_by_preset,
    validate_advanced_args,
    validate_custom_filename,
    validate_download_sections,
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
        self._create_widgets()

    def _create_widgets(self):
        raise NotImplementedError

    def _create_common_buttons(self, add_task_command):
        button_frame = ttk.Frame(self)
        button_frame.pack(fill='x', pady=(15, 0))

        ttk.Button(
            button_frame,
            text="✚ 添加到队列",
            command=add_task_command,
            style="Primary.TButton",
        ).pack(side='left', padx=5)

    def _create_concurrency_spinbox(self, parent, manager, font_family, font_size_normal, default_val=1, grid_row=1, grid_col_start=2, padx=(0, 0)):
        ttk.Label(parent, text="并发数:", font=(font_family, font_size_normal - 1)).grid(
            row=grid_row,
            column=grid_col_start,
            sticky='w',
            pady=(5, 0),
            padx=padx,
        )

        var = tk.StringVar(value=str(default_val))

        def on_concurrent_change(*args):
            raw_value = var.get().strip()
            if not raw_value:
                return
            try:
                concurrent = int(raw_value)
            except ValueError:
                return
            if concurrent < 1:
                return
            manager.max_concurrent = concurrent
            manager.start_next_task()

        var.trace_add('write', on_concurrent_change)

        spinbox = ttk.Spinbox(
            parent,
            from_=1,
            to=10,
            textvariable=var,
            width=5,
            font=(font_family, font_size_normal),
            command=lambda: setattr(manager, 'max_concurrent', max(1, int(var.get() or default_val))),
        )
        spinbox.grid(row=grid_row, column=grid_col_start + 1, sticky='w', padx=5, pady=(5, 0))
        return var

    def _create_speedlimit_spinbox(self, parent, font_family, font_size_normal, default_val=2):
        ttk.Label(parent, text="限速(MB/s):", font=(font_family, font_size_normal - 1)).grid(
            row=1,
            column=4,
            sticky='w',
            padx=(15, 0),
            pady=(5, 0),
        )

        var = tk.IntVar(value=default_val)
        ttk.Spinbox(
            parent,
            from_=0,
            to=100,
            textvariable=var,
            width=5,
            font=(font_family, font_size_normal),
        ).grid(row=1, column=5, sticky='w', padx=5, pady=(5, 0))

        ttk.Label(parent, text="(0=不限)", font=(font_family, 8), foreground="gray").grid(
            row=1,
            column=6,
            sticky='w',
            pady=(5, 0),
        )
        return var

    def _create_retry_spinbox(self, parent, font_family, font_size_normal, default_val=3):
        ttk.Label(parent, text="重    试: ", font=(font_family, font_size_normal - 1)).grid(
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

        ttk.Label(url_frame, text="视频 URL:", font=(font_family, font_size_title, 'bold')).pack(anchor='w')
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

        ttk.Label(
            url_frame,
            text="仅支持 YouTube / youtu.be 链接",
            font=(font_family, 8),
            foreground="#888888",
        ).pack(anchor='w', side='right', pady=(2, 0))

        info_card = ttk.Frame(self, style="Card.TFrame", padding=4)
        info_card.pack(fill='x', pady=2)
        ttk.Label(info_card, text="视频详情", style="Card.TLabel").pack(anchor='w')
        self.video_title_var = tk.StringVar(value="尚未解析视频")
        ttk.Label(info_card, textvariable=self.video_title_var, style="Card.TLabel", font=(font_family, font_size_normal, 'bold')).pack(anchor='w', pady=(4, 2))
        self.video_meta_var = tk.StringVar(value="ID: - | 频道: - | 时长: - | 观看: - | 上传: - | 语言: -")
        ttk.Label(info_card, textvariable=self.video_meta_var, style="Card.TLabel").pack(anchor='w')

        strategy_card = ttk.Frame(self, style="Card.TFrame", padding=2)
        strategy_card.pack(fill='x', pady=2)

        strategy_row = ttk.Frame(strategy_card, style="Card.TFrame")
        strategy_row.pack(fill='x', pady=(0, 8))
        ttk.Label(strategy_row, text="下载策略:", style="Card.TLabel").pack(side='left')
        self.preset_var = tk.StringVar(value="best_compat")
        preset_options = [
            ("best_quality", DOWNLOAD_PRESET_LABELS["best_quality"]),
            ("best_compat", DOWNLOAD_PRESET_LABELS["best_compat"]),
            ("max_1080p", DOWNLOAD_PRESET_LABELS["max_1080p"]),
            ("max_4k", DOWNLOAD_PRESET_LABELS["max_4k"]),
            ("audio_only", DOWNLOAD_PRESET_LABELS["audio_only"]),
            ("min_size", DOWNLOAD_PRESET_LABELS["min_size"]),
            ("keep_original", DOWNLOAD_PRESET_LABELS["keep_original"]),
            ("hdr_priority", DOWNLOAD_PRESET_LABELS["hdr_priority"]),
            ("high_fps", DOWNLOAD_PRESET_LABELS["high_fps"]),
            ("manual", DOWNLOAD_PRESET_LABELS["manual"]),
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
        ttk.Label(output_row, text="输出格式:", style="Card.TLabel").pack(side='left')
        self.output_format_var = tk.StringVar(value="mp4")
        self.output_format_combo = ttk.Combobox(output_row, textvariable=self.output_format_var, state="readonly", width=12)
        self.output_format_combo.pack(side='left', padx=(10, 20))
        ttk.Label(output_row, text="手动格式:", style="Card.TLabel").pack(side='left')
        self.format_var_combo = tk.StringVar()
        self.selected_format_id_var = tk.StringVar()
        self.format_combo = ttk.Combobox(output_row, textvariable=self.format_var_combo, state="readonly", width=55)
        self.format_combo.pack(side='left', padx=10, fill='x', expand=True)
        self.format_combo.bind("<<ComboboxSelected>>", self._on_format_combo_selected)

        content_wrap = ttk.Frame(self, style="Card.TFrame")
        content_wrap.pack(fill='x', pady=2)

        format_card = ttk.Frame(content_wrap, style="Card.TFrame", padding=2)
        format_card.pack(fill='x')

        btn_row = ttk.Frame(format_card, style="Card.TFrame")
        btn_row.pack(fill='x', pady=(0, 2))

        self.fetch_formats_button = ttk.Button(
            btn_row,
            text="获取分辨率/格式",
            command=self.fetch_formats,
            style="Info.Small.TButton",
        )
        self.fetch_formats_button.pack(side='left', padx=(0, 5))

        ttk.Button(
            btn_row,
            text="直接下载",
            command=self.add_direct_task,
            style="Warning.Small.TButton",
        ).pack(side='left', padx=5)

        filter_row = ttk.Frame(format_card, style="Card.TFrame")
        filter_row.pack(fill='x', pady=(0, 8))
        ttk.Label(filter_row, text="格式筛选:", style="Card.TLabel").pack(side='left')
        self.filter_mp4_var = tk.BooleanVar(value=False)
        self.filter_with_audio_var = tk.BooleanVar(value=False)
        self.filter_60fps_var = tk.BooleanVar(value=False)
        self.filter_4k_var = tk.BooleanVar(value=False)
        self.filter_audio_only_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(filter_row, text="仅 MP4", variable=self.filter_mp4_var, command=self._refresh_filters).pack(side='left', padx=(10, 0))
        ttk.Checkbutton(filter_row, text="仅带音频", variable=self.filter_with_audio_var, command=self._refresh_filters).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(filter_row, text="仅 60fps", variable=self.filter_60fps_var, command=self._refresh_filters).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(filter_row, text="仅 4K+", variable=self.filter_4k_var, command=self._refresh_filters).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(filter_row, text="仅音频轨", variable=self.filter_audio_only_var, command=self._refresh_filters).pack(side='left', padx=(8, 0))
        ttk.Label(filter_row, text="排序:", style="Card.TLabel").pack(side='left', padx=(15, 4))
        self.sort_mode_var = tk.StringVar(value="quality_desc")
        self.sort_mode_combo = ttk.Combobox(filter_row, textvariable=self.sort_mode_var, state="readonly", width=14)
        self.sort_mode_combo.configure(values=("quality_desc", "quality_asc", "size_desc", "size_asc"))
        self.sort_mode_combo.pack(side='left')
        self.sort_mode_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_filters())
        self.filter_summary_var = tk.StringVar(value="尚未获取格式")
        ttk.Label(filter_row, textvariable=self.filter_summary_var, style="Card.TLabel").pack(side='right')

        self.format_rows = {}


        options_card = ttk.Frame(content_wrap, style="Card.TFrame", padding=5)
        options_card.pack(fill='x', pady=(6, 0))

        audio_card = ttk.Frame(options_card, style="Card.TFrame")
        audio_card.pack(fill='x', pady=(0, 6))
        ttk.Label(audio_card, text="音频导出:", style="Card.TLabel").pack(side='left')
        self.audio_quality_var = tk.StringVar(value="192")
        ttk.Label(audio_card, text="音质(k):", style="Card.TLabel").pack(side='left', padx=(12, 4))
        self.audio_quality_combo = ttk.Combobox(audio_card, textvariable=self.audio_quality_var, state="readonly", width=8)
        self.audio_quality_combo.configure(values=("128", "192", "256", "320"))
        self.audio_quality_combo.pack(side='left', padx=(0, 12))
        ttk.Label(audio_card, text="仅在 mp3/opus/wav/flac 转码时生效", style="Card.TLabel").pack(side='left')

        file_row = ttk.Frame(options_card, style="Card.TFrame")
        file_row.pack(fill='x', pady=(0, 5))
        ttk.Label(file_row, text="重命名:", style="Card.TLabel").pack(side='left')
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
            text="(可选 | 留空则自动从网页获取)",
            font=(font_family, 8),
            foreground="#888888",
            style="Card.TLabel",
        ).pack(side='left')

        preview_row = ttk.Frame(options_card, style="Card.TFrame")
        preview_row.pack(fill='x', pady=(0, 6))
        ttk.Label(preview_row, text="命名预览:", style="Card.TLabel").pack(side='left')
        self.filename_preview_var = tk.StringVar(value="未命名（将使用网页标题）")
        ttk.Label(preview_row, textvariable=self.filename_preview_var, style="Card.TLabel").pack(side='left', padx=(10, 0))

        network_row = ttk.Frame(options_card, style="Card.TFrame")
        network_row.pack(fill='x', pady=(0, 6))
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

        sections_row = ttk.Frame(options_card, style="Card.TFrame")
        sections_row.pack(fill='x', pady=(0, 5))
        ttk.Label(sections_row, text="区段下载:", style="Card.TLabel").pack(side='left')
        self.download_sections_var = tk.StringVar()
        ttk.Entry(sections_row, textvariable=self.download_sections_var, width=18).pack(side='left', padx=(10, 6))
        ttk.Label(sections_row, text="格式: HH:MM:SS-MM:SS", style="Card.TLabel").pack(side='left')
        ttk.Label(sections_row, text="(例: 00:01:00-00:02:30)", style="Card.TLabel", foreground="#888888", font=(font_family, 8)).pack(side='left', padx=(6, 0))

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
        ttk.Checkbutton(subtitle_row, text="外挂字幕", variable=self.write_subs_var, command=self._update_download_summary).pack(side='left', padx=(6, 0))
        ttk.Checkbutton(subtitle_row, text="内嵌字幕", variable=self.embed_subs_var, command=self._update_download_summary).pack(side='left', padx=(6, 0))
        ttk.Label(subtitle_row, text="(mkv更稳)", style="Card.TLabel", foreground="#888888", font=(font_family, 8)).pack(side='left', padx=(6, 0))

        postprocess_row = ttk.Frame(options_card, style="Card.TFrame")
        postprocess_row.pack(fill='x', pady=(0, 5))
        ttk.Label(postprocess_row, text="后处理增强:", style="Card.TLabel").pack(side='left')
        self.embed_thumbnail_var = tk.BooleanVar(value=True)
        self.embed_metadata_var = tk.BooleanVar(value=True)
        self.write_thumbnail_var = tk.BooleanVar(value=False)
        self.write_info_json_var = tk.BooleanVar(value=False)
        self.write_description_var = tk.BooleanVar(value=False)
        self.write_chapters_var = tk.BooleanVar(value=False)
        self.keep_video_var = tk.BooleanVar(value=False)
        self.h264_compat_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(postprocess_row, text="嵌入封面", variable=self.embed_thumbnail_var, command=self._update_download_summary).pack(side='left', padx=(10, 0))
        ttk.Checkbutton(postprocess_row, text="嵌入元数据", variable=self.embed_metadata_var, command=self._update_download_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text="写入缩略图文件", variable=self.write_thumbnail_var, command=self._update_download_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text="写入信息 JSON", variable=self.write_info_json_var, command=self._update_download_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text="写入描述", variable=self.write_description_var, command=self._update_download_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text="章节写入", variable=self.write_chapters_var, command=self._update_download_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text="保留中间视频", variable=self.keep_video_var, command=self._update_download_summary).pack(side='left', padx=(8, 0))
        ttk.Checkbutton(postprocess_row, text="H.264 兼容模式", variable=self.h264_compat_var, command=self._update_download_summary).pack(side='left', padx=(8, 0))
        self.sponsorblock_enabled_var = tk.BooleanVar(value=False)
        self.sponsorblock_categories_var = tk.StringVar(value="sponsor")
        ttk.Checkbutton(postprocess_row, text="SponsorBlock", variable=self.sponsorblock_enabled_var, command=self._update_download_summary).pack(side='left', padx=(8, 0))
        ttk.Entry(postprocess_row, textvariable=self.sponsorblock_categories_var, width=16).pack(side='left', padx=(6, 0))
        self.use_po_token_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(postprocess_row, text="启用 PO Token", variable=self.use_po_token_var, command=self._update_download_summary).pack(side='left', padx=(8, 0))

        summary_row = ttk.Frame(options_card, style="Card.TFrame")
        summary_row.pack(fill='x', pady=(0, 5))
        ttk.Label(summary_row, text="下载摘要:", style="Card.TLabel").pack(side='left')
        self.download_summary_var = tk.StringVar(value="尚未配置下载摘要")
        ttk.Label(summary_row, textvariable=self.download_summary_var, style="Card.TLabel").pack(side='left', padx=(10, 0))

        settings_row = ttk.Frame(options_card, style="Card.TFrame")
        settings_row.pack(fill='x')

        self.retry_var = self._create_retry_spinbox(settings_row, font_family, font_size_normal)
        self.concurrent_var = self._create_concurrency_spinbox(settings_row, self.manager, font_family, font_size_normal, padx=(15, 0))
        self.speedlimit_var = self._create_speedlimit_spinbox(settings_row, font_family, font_size_normal)

        self._create_common_buttons(self.add_task)

        self.format_fetch_used_cookies = False
        self.detected_url_type = None
        self._silent_messagebox = silent_messagebox
        self._cookies_file_path = cookies_file_path
        self.all_formats = []
        self.current_formats = []
        self._format_fetch_in_progress = False
        self._on_preset_changed()
        self._update_filename_preview()
        self._update_download_summary()

    def _build_filename_preview(self):
        custom_filename = self.custom_filename_var.get().strip()
        output_format = self.output_format_var.get().strip() or "mp4"
        if custom_filename:
            return f"{custom_filename}.{output_format}"
        title = self.video_title_var.get().strip()
        if title and title != "尚未解析视频":
            return f"{title}.{output_format}"
        return f"未命名.{output_format}（将使用网页标题）"

    def _build_download_summary(self):
        preset_key = self.preset_var.get().strip() or "manual"
        preset_label = DOWNLOAD_PRESET_LABELS.get(preset_key, preset_key)
        output_format = self.output_format_var.get().strip() or "mp4"
        selected_format = self.selected_format_id_var.get().strip()
        if preset_key == "manual":
            selected_format_text = selected_format or "未选择（请先获取格式并选择一项）"
        else:
            selected_format_text = selected_format or "自动按策略选择"
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
            flags.append("缩略图文件")
        if self.write_info_json_var.get():
            flags.append("信息JSON")
        if self.write_description_var.get():
            flags.append("描述文件")
        if self.write_chapters_var.get():
            flags.append("章节")
        if self.h264_compat_var.get():
            flags.append("H.264兼容")
        if self.keep_video_var.get():
            flags.append("保留中间视频")
        extras = " / ".join(flags) if flags else "无附加后处理"
        return f"策略: {preset_label} | 输出: {output_format} | 格式: {selected_format_text} | 后处理: {extras}"

    def _update_filename_preview(self):
        self.filename_preview_var.set(self._build_filename_preview())
        self._update_download_summary()

    def _update_download_summary(self):
        self.download_summary_var.set(self._build_download_summary())

    def _refresh_filters(self):
        refresh_format_view(self)
        self._update_download_summary()

    def _on_preset_changed(self):
        sync_output_format_by_preset(self)
        preset_key = self.preset_var.get().strip()
        manual_state = "readonly" if preset_key == "manual" else "disabled"
        self.format_combo.configure(state=manual_state)
        if preset_key != "manual":
            self.selected_format_id_var.set("")
        self._update_filename_preview()


    def _on_format_combo_selected(self, _event=None):
        raw = self.format_var_combo.get().strip()
        format_id = raw.split('|', 1)[0].strip() if raw else ""
        self.selected_format_id_var.set(format_id)
        if format_id:
            self.preset_var.set("manual")
            self._on_preset_changed()
            self._update_filename_preview()

    def fetch_formats(self):
        fetch_formats_async(self)

    def add_task(self):
        url = self.url_entry.get("1.0", "end-1c").strip()
        if not validate_youtube_url(self, url):
            return
        self.manager.log(f"URL: {url} (类型: YouTube)")

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
        if preset_key == "manual" and not self.selected_format_id_var.get().strip():
            self.manager.log("⚠️ 当前为手动格式模式，请先获取格式并选择一个 format_id", "WARNING")
            return

        task = prepare_standard_task(self, url)
        if not task:
            return

        self.manager.add_task(task)
        self._reset_form(clear_formats=True)

    def add_direct_task(self):
        url = self.url_entry.get("1.0", "end-1c").strip()
        if not validate_youtube_url(self, url):
            return
        self.manager.log(f"URL: {url} (类型: YouTube) [直接下载模式]")

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
        if preset_key == "manual" and not self.selected_format_id_var.get().strip():
            self.manager.log("⚠️ 直接下载模式下，手动格式仍需先获取格式并选择一个 format_id", "WARNING")
            return

        task = prepare_direct_task(self, url)
        if not task:
            self.manager.log("❌ 直接下载任务创建失败，请检查当前格式与输出配置", "ERROR")
            return
        self.manager.add_task(task)
        self._reset_form(clear_formats=False)


    def _reset_form(self, clear_formats):
        self.url_entry.delete("1.0", "end")
        self.custom_filename_var.set("")
        self.filename_entry_widget.delete("1.0", "end")
        if clear_formats:
            self.format_combo.set('')
            self.format_combo['values'] = []
            self.selected_format_id_var.set("")
            self.format_rows = {}
            self.all_formats = []
            self.current_formats = []
            self.filter_summary_var.set("尚未获取格式")
            self.video_title_var.set("尚未解析视频")
            self.video_meta_var.set("ID: - | 频道: - | 时长: - | 观看: - | 上传: - | 语言: -")
            self.format_fetch_used_cookies = False
        self._update_filename_preview()

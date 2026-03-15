import re
import shlex

from core.youtube_models import DOWNLOAD_PRESET_FORMATS, P1080_FMT, YouTubeDownloadProfile, YouTubeTaskRecord


INVALID_FILENAME_CHARS = r'\/:*?"<>|'
AUDIO_OUTPUT_FORMATS = ("m4a", "mp3", "opus", "wav", "flac")
VIDEO_OUTPUT_FORMATS = ("mp4", "mkv")
TIME_RANGE_SEPARATOR = "-"
ADVANCED_ARG_CONFLICTS = {
    "-f",
    "--format",
    "-o",
    "--output",
    "--cookies",
    "--cookies-from-browser",
    "--proxy",
    "--download-sections",
    "--sponsorblock-remove",
    "--sponsorblock-mark",
    "--sponsorblock",
    "--extractor-args",
    "--ffmpeg-location",
}

_TIME_CODE_RE = re.compile(r"^(?:\d{1,2}:)?\d{1,2}:\d{2}$")


def _get_selected_preset_key(frame):
    return getattr(frame, "preset_var", None).get().strip() if getattr(frame, "preset_var", None) else "manual"


def _show_input_warning(frame, message):
    frame.manager.log(f"⚠️ 输入值无效，已回退默认值: {message}", "WARN")
    frame.app.SilentMessagebox.showwarning("提示", message)


def _is_time_code(value):
    return bool(_TIME_CODE_RE.match(value or ""))


def _normalize_download_sections(value):
    raw = (value or "").strip()
    if not raw:
        return ""

    if TIME_RANGE_SEPARATOR not in raw:
        return ""

    start, end = [part.strip() for part in raw.split(TIME_RANGE_SEPARATOR, 1)]
    if not start or not end:
        return ""
    if not _is_time_code(start) or not _is_time_code(end):
        return ""
    return f"*{start}-{end}"


def _extract_advanced_flags(advanced_args):
    if not advanced_args:
        return []
    try:
        tokens = shlex.split(advanced_args)
    except ValueError:
        tokens = advanced_args.split()
    flags = []
    for token in tokens:
        if not token.startswith("-"):
            continue
        flag = token.split("=", 1)[0]
        flags.append(flag)
    return flags


def _coerce_int_input(frame, var_name, default, minimum=None, maximum=None, label="数值"):
    variable = getattr(frame, var_name, None)
    if variable is None:
        return default

    raw_value = str(variable.get()).strip()
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        variable.set(default)
        _show_input_warning(frame, f"{label}输入无效，已自动恢复为 {default}")
        return default

    if minimum is not None and value < minimum:
        variable.set(default)
        _show_input_warning(frame, f"{label}不能小于 {minimum}，已自动恢复为 {default}")
        return default

    if maximum is not None and value > maximum:
        variable.set(default)
        _show_input_warning(frame, f"{label}不能大于 {maximum}，已自动恢复为 {default}")
        return default

    return value


def build_profile_from_input(frame):
    """根据输入页控件状态构建下载配置。"""
    format_widget = getattr(frame, "format_var_combo", None)
    format_value = format_widget.get().strip() if format_widget else ""
    format_value = format_value or P1080_FMT
    custom_filename = frame.custom_filename_var.get().strip()
    retries = _coerce_int_input(frame, "retry_var", 3, minimum=0, maximum=10, label="重试次数")
    retry_interval = _coerce_int_input(frame, "retry_interval_var", 0, minimum=0, maximum=300, label="重试间隔")
    sleep_interval = _coerce_int_input(frame, "sleep_interval_var", 0, minimum=0, maximum=60, label="请求间隔")
    max_sleep_interval = _coerce_int_input(frame, "max_sleep_interval_var", 0, minimum=0, maximum=120, label="最大请求间隔")
    sleep_requests = _coerce_int_input(frame, "sleep_requests_var", 0, minimum=0, maximum=30, label="API请求间隔")
    speed_limit = _coerce_int_input(frame, "speedlimit_var", 0, minimum=0, maximum=100, label="限速")
    concurrent = _coerce_int_input(frame, "concurrent_var", 1, minimum=1, maximum=10, label="并发数")
    preset_key = _get_selected_preset_key(frame)
    output_format = getattr(frame, "output_format_var", None).get().strip() if getattr(frame, "output_format_var", None) else "mp4"
    audio_quality = getattr(frame, "audio_quality_var", None).get().strip() if getattr(frame, "audio_quality_var", None) else "192"
    embed_thumbnail = bool(getattr(frame, "embed_thumbnail_var", None).get()) if getattr(frame, "embed_thumbnail_var", None) else True
    embed_metadata = bool(getattr(frame, "embed_metadata_var", None).get()) if getattr(frame, "embed_metadata_var", None) else True
    write_thumbnail = bool(getattr(frame, "write_thumbnail_var", None).get()) if getattr(frame, "write_thumbnail_var", None) else False
    write_info_json = bool(getattr(frame, "write_info_json_var", None).get()) if getattr(frame, "write_info_json_var", None) else False
    write_description = bool(getattr(frame, "write_description_var", None).get()) if getattr(frame, "write_description_var", None) else False
    write_chapters = bool(getattr(frame, "write_chapters_var", None).get()) if getattr(frame, "write_chapters_var", None) else False
    keep_video = bool(getattr(frame, "keep_video_var", None).get()) if getattr(frame, "keep_video_var", None) else False
    h264_compat = bool(getattr(frame, "h264_compat_var", None).get()) if getattr(frame, "h264_compat_var", None) else False
    use_po_token = bool(getattr(frame, "use_po_token_var", None).get()) if getattr(frame, "use_po_token_var", None) else False
    raw_download_sections = getattr(frame, "download_sections_var", None).get().strip() if getattr(frame, "download_sections_var", None) else ""
    download_sections = _normalize_download_sections(raw_download_sections)
    if raw_download_sections and not download_sections:
        _show_input_warning(frame, "区段格式无效，请使用 HH:MM:SS-MM:SS 或 MM:SS-MM:SS")
        download_sections = ""
    sponsorblock_enabled = bool(getattr(frame, "sponsorblock_enabled_var", None).get()) if getattr(frame, "sponsorblock_enabled_var", None) else False
    sponsorblock_categories = getattr(frame, "sponsorblock_categories_var", None).get().strip() if getattr(frame, "sponsorblock_categories_var", None) else ""
    proxy_url = getattr(frame, "proxy_url_var", None).get().strip() if getattr(frame, "proxy_url_var", None) else ""
    advanced_args = getattr(frame, "advanced_args_var", None).get().strip() if getattr(frame, "advanced_args_var", None) else ""
    cookies_mode = getattr(frame, "cookies_mode_var", None).get().strip() if getattr(frame, "cookies_mode_var", None) else "file"
    cookies_browser = getattr(frame, "cookies_browser_var", None).get().strip() if getattr(frame, "cookies_browser_var", None) else ""
    subtitle_mode = getattr(frame, "subtitle_mode_var", None).get().strip() if getattr(frame, "subtitle_mode_var", None) else "none"
    subtitle_langs = getattr(frame, "subtitle_langs_var", None).get().strip() if getattr(frame, "subtitle_langs_var", None) else ""
    subtitle_format = getattr(frame, "subtitle_format_var", None).get().strip() if getattr(frame, "subtitle_format_var", None) else ""
    embed_subs = bool(getattr(frame, "embed_subs_var", None).get()) if getattr(frame, "embed_subs_var", None) else False
    write_subs = bool(getattr(frame, "write_subs_var", None).get()) if getattr(frame, "write_subs_var", None) else True

    if cookies_mode == "browser" and not cookies_browser:
        _show_input_warning(frame, "已选择 browser cookies，但未填写浏览器名称")
        cookies_mode = "file"
    if sponsorblock_enabled and not sponsorblock_categories:
        sponsorblock_categories = "sponsor"

    frame.manager.max_concurrent = concurrent

    return YouTubeDownloadProfile(
        format=format_value,
        subtitle_mode=subtitle_mode or "none",
        subtitle_langs=subtitle_langs,
        subtitle_format=subtitle_format,
        embed_subs=embed_subs,
        write_subs=write_subs,
        retries=retries,
        retry_interval=retry_interval,
        sleep_interval=sleep_interval,
        max_sleep_interval=max_sleep_interval,
        sleep_requests=sleep_requests,
        speed_limit=speed_limit,
        custom_filename=custom_filename,
        preset_key=preset_key or "manual",
        merge_output_format=output_format or "mp4",
        audio_quality=audio_quality or "192",
        embed_thumbnail=embed_thumbnail,
        embed_metadata=embed_metadata,
        write_thumbnail=write_thumbnail,
        write_info_json=write_info_json,
        write_description=write_description,
        write_chapters=write_chapters,
        keep_video=keep_video,
        h264_compat=h264_compat,
        use_po_token=use_po_token,
        download_sections=download_sections,
        sponsorblock_enabled=sponsorblock_enabled,
        sponsorblock_categories=sponsorblock_categories,
        proxy_url=proxy_url,
        advanced_args=advanced_args,
        cookies_mode=cookies_mode,
        cookies_browser=cookies_browser,
    )


def validate_proxy_url(frame, proxy_url):
    if not proxy_url:
        return True
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", proxy_url):
        _show_input_warning(frame, "代理格式无效，请包含协议头，例如 http:// 或 socks5://")
        return False
    return True


def validate_advanced_args(frame, advanced_args):
    if not advanced_args:
        return True
    flags = _extract_advanced_flags(advanced_args)
    conflicts = [flag for flag in flags if flag in ADVANCED_ARG_CONFLICTS]
    if conflicts:
        _show_input_warning(frame, f"高级参数包含冲突项: {', '.join(conflicts)}")
        return False
    return True


def validate_youtube_url(frame, url):
    """校验输入链接是否为可支持的 YouTube 链接。"""
    detected = detect_youtube_url(frame, url)
    if detected is None:
        frame.app.SilentMessagebox.showwarning("提示", "请输入 YouTube URL")
        return False
    if detected != 'youtube':
        frame.app.SilentMessagebox.showwarning("提示", "当前版本仅支持 YouTube 链接")
        return False
    return True


def detect_youtube_url(frame, url):
    """检测并记录当前输入链接的类型。"""
    normalized_url = (url or '').strip()
    if not normalized_url:
        frame.detected_url_type = None
        return None

    detected = frame.app.detect_video_url_type(normalized_url)
    frame.detected_url_type = detected
    return detected


def validate_custom_filename(frame, custom_filename):
    """校验自定义文件名是否包含非法字符。"""
    if not custom_filename:
        return True

    if any(char in custom_filename for char in INVALID_FILENAME_CHARS):
        frame.manager.log(f"❌ 添加任务失败: 文件名包含非法字符 {INVALID_FILENAME_CHARS}", "ERROR")
        frame.app.SilentMessagebox.showerror("错误", f"文件名不能包含以下字符:\n{INVALID_FILENAME_CHARS}")
        return False

    frame.manager.log(f"[完成] 将使用自定义文件名: {custom_filename}")
    return True


def create_task_record(frame, url, profile, task_type='youtube'):
    """创建任务记录对象。"""
    return YouTubeTaskRecord(
        url=url,
        save_path=frame.shared_save_dir_var.get(),
        profile=profile,
        task_type=task_type,
    )


def get_selected_format_id(frame):
    """返回当前选中的格式 ID。"""
    selected = getattr(frame, "selected_format_id_var", None)
    if selected:
        format_id = selected.get().strip()
        if format_id:
            return format_id

    fmt_choice = frame.format_var_combo.get().strip()
    if not fmt_choice:
        frame.app.SilentMessagebox.showwarning("提示", "请先获取并选择格式")
        return None
    return fmt_choice.split('|', 1)[0].strip()


def get_selected_preset_format(frame):
    preset_key = _get_selected_preset_key(frame)
    if preset_key and preset_key != "manual":
        return DOWNLOAD_PRESET_FORMATS.get(preset_key)
    return None


def get_selected_output_format(frame, preset_key):
    raw_value = getattr(frame, "output_format_var", None).get().strip() if getattr(frame, "output_format_var", None) else "mp4"
    if preset_key == "audio_only":
        return raw_value if raw_value in AUDIO_OUTPUT_FORMATS else "m4a"
    return raw_value if raw_value in VIDEO_OUTPUT_FORMATS else "mp4"


def sync_output_format_by_preset(frame):
    preset_key = _get_selected_preset_key(frame)
    if not getattr(frame, "output_format_var", None):
        return preset_key

    if preset_key == "audio_only":
        frame.output_format_combo.configure(values=AUDIO_OUTPUT_FORMATS)
        if frame.output_format_var.get().strip() not in AUDIO_OUTPUT_FORMATS:
            frame.output_format_var.set("m4a")
    else:
        frame.output_format_combo.configure(values=VIDEO_OUTPUT_FORMATS)
        if frame.output_format_var.get().strip() not in VIDEO_OUTPUT_FORMATS:
            frame.output_format_var.set("mp4")
    return preset_key


def validate_download_sections(frame, raw_value):
    if not raw_value:
        return True
    normalized = _normalize_download_sections(raw_value)
    if not normalized:
        _show_input_warning(frame, "区段格式无效，请使用 HH:MM:SS-MM:SS 或 MM:SS-MM:SS")
        return False
    return True


def apply_task_save_path(frame, task):
    """为任务写入当前保存目录。"""
    task.save_path = frame.shared_save_dir_var.get()
    return task


def apply_task_cookies_requirement(frame, task):
    """根据格式获取阶段的状态为任务标记 cookies 需求。"""
    if frame.format_fetch_used_cookies:
        task.needs_cookies = True
        frame.manager.log("[信息] 此任务将使用cookies下载")
    return task


def validate_format_fetch_request(frame, url):
    """校验“获取格式”请求是否满足基本条件。"""
    normalized_url = (url or '').strip()
    if not normalized_url:
        frame.app.root.after(0, lambda: frame.app.SilentMessagebox.showwarning("提示", "请输入 YouTube URL"))
        return None

    detected = detect_youtube_url(frame, normalized_url)
    if detected != 'youtube':
        frame.app.root.after(0, lambda: frame.app.SilentMessagebox.showwarning("提示", "当前版本仅支持 YouTube 链接"))
        return None

    return normalized_url


def prepare_standard_task(frame, url):
    """构建标准格式下载任务。"""
    preset_key = sync_output_format_by_preset(frame)
    preset_format = get_selected_preset_format(frame)
    profile = build_profile_from_input(frame)
    profile.preset_key = preset_key or "manual"
    profile.merge_output_format = get_selected_output_format(frame, profile.preset_key)

    if preset_format:
        profile.format = preset_format
    else:
        format_id = get_selected_format_id(frame)
        if not format_id:
            return None
        profile.format = f"{format_id}+bestaudio[ext=m4a]"

    task = create_task_record(frame, url, profile)
    apply_task_save_path(frame, task)
    apply_task_cookies_requirement(frame, task)
    return task


def prepare_direct_task(frame, url):
    """构建直接下载任务。"""
    preset_key = sync_output_format_by_preset(frame)
    profile = build_profile_from_input(frame)
    profile.preset_key = preset_key or "manual"
    preset_format = get_selected_preset_format(frame)
    if preset_format:
        profile.format = preset_format
    else:
        format_id = get_selected_format_id(frame)
        if not format_id:
            return None
        profile.format = f"{format_id}+bestaudio[ext=m4a]"
    profile.merge_output_format = get_selected_output_format(frame, profile.preset_key)
    task = create_task_record(frame, url, profile)
    apply_task_save_path(frame, task)
    apply_task_cookies_requirement(frame, task)
    return task

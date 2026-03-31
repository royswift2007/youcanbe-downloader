import os

from core.advanced_args_policy import parse_and_validate_advanced_args
from core.cookies_args import build_cookies_args
from core.youtube_models import AUDIO_FMT
from core.po_token_manager import get_manager as _get_pot_manager


def build_ytdlp_command(yt_dlp_path, ffmpeg_path, cookies_file_path, task):
    output_dir = task.resolve_output_dir() if hasattr(task, "resolve_output_dir") else task.save_path
    custom_name = task.profile.custom_filename
    if custom_name:
        output_template = os.path.join(output_dir, f"{custom_name}.%(ext)s")
    else:
        output_template = os.path.join(output_dir, "%(title)s.%(ext)s")

    cmd = [yt_dlp_path]

    socket_timeout = getattr(task.profile, "socket_timeout", 0) or 0
    if socket_timeout > 0:
        cmd.extend(["--socket-timeout", str(socket_timeout)])

    cookies_mode = (getattr(task.profile, "cookies_mode", "file") or "file").strip().lower()
    cookies_browser = (getattr(task.profile, "cookies_browser", "") or "").strip().lower()
    cookies_args = build_cookies_args(cookies_mode, cookies_browser, cookies_file_path)
    if cookies_mode == "browser":
        cmd.extend(cookies_args)
    elif task.needs_cookies and cookies_args:
        cmd.extend(cookies_args)

    fmt = task.profile.format
    sub_lang = task.profile.sub_lang
    subtitle_mode = getattr(task.profile, "subtitle_mode", "none") or "none"
    subtitle_langs = getattr(task.profile, "subtitle_langs", "") or ""
    subtitle_format = getattr(task.profile, "subtitle_format", "") or ""
    embed_subs = bool(getattr(task.profile, "embed_subs", False))
    write_subs = bool(getattr(task.profile, "write_subs", True))
    speed_limit = task.profile.speed_limit
    merge_output_format = getattr(task.profile, "merge_output_format", "mp4") or "mp4"
    audio_quality = getattr(task.profile, "audio_quality", "192") or "192"
    embed_thumbnail = bool(getattr(task.profile, "embed_thumbnail", True))
    embed_metadata = bool(getattr(task.profile, "embed_metadata", True))
    write_thumbnail = bool(getattr(task.profile, "write_thumbnail", False))
    write_info_json = bool(getattr(task.profile, "write_info_json", False))
    write_description = bool(getattr(task.profile, "write_description", False))
    write_chapters = bool(getattr(task.profile, "write_chapters", False))
    keep_video = bool(getattr(task.profile, "keep_video", False))
    h264_compat = bool(getattr(task.profile, "h264_compat", False))
    download_sections = getattr(task.profile, "download_sections", "") or ""
    sponsorblock_enabled = bool(getattr(task.profile, "sponsorblock_enabled", False))
    sponsorblock_categories = getattr(task.profile, "sponsorblock_categories", "") or ""
    proxy_url = getattr(task.profile, "proxy_url", "") or ""
    advanced_args = getattr(task.profile, "advanced_args", "") or ""
    preset_key = getattr(task.profile, "preset_key", "") or ""
    is_audio_download = preset_key == "audio_only" or fmt == AUDIO_FMT

    if fmt:
        cmd.extend(["-f", fmt])

    cmd.extend([
        "-o", output_template,
        "--ffmpeg-location", ffmpeg_path,
        "--newline"
    ])

    if is_audio_download:
        audio_format = merge_output_format if merge_output_format in {"m4a", "mp3", "opus", "wav", "flac"} else "m4a"
        cmd.extend(["-x", "--audio-format", audio_format, "--audio-quality", audio_quality])
        if keep_video:
            cmd.append("--keep-video")
    else:
        if merge_output_format == "webm" and h264_compat:
            raise ValueError("webm output does not support H.264 compatibility transcoding")
        cmd.extend(["--merge-output-format", merge_output_format])
        if merge_output_format == "mkv":
            cmd.append("--remux-video")
            cmd.append("mkv")

    if embed_metadata:
        cmd.append("--embed-metadata")
    if embed_thumbnail:
        cmd.append("--embed-thumbnail")
        # mkv + embedded subtitles + embedded thumbnail is unstable on some ffmpeg/muxer stacks.
        if merge_output_format == "mkv" and embed_subs:
            cmd.extend(["--convert-thumbnails", "png"])
    if write_thumbnail:
        cmd.append("--write-thumbnail")
    if write_info_json:
        cmd.append("--write-info-json")
    if write_description:
        cmd.append("--write-description")
    if write_chapters:
        cmd.append("--embed-chapters")

    if h264_compat and not is_audio_download:
        cmd.extend(["--recode-video", "mp4", "--postprocessor-args", "ffmpeg:-c:v libx264 -c:a aac"])

    if speed_limit > 0:
        cmd.extend(["-r", f"{speed_limit}M"])

    retry_interval = getattr(task.profile, "retry_interval", 0)
    sleep_interval = getattr(task.profile, "sleep_interval", 0)
    max_sleep_interval = getattr(task.profile, "max_sleep_interval", 0)
    sleep_requests = getattr(task.profile, "sleep_requests", 0)
    if retry_interval > 0:
        cmd.extend(["--retry-sleep", f"http:{retry_interval}"])
    if sleep_interval > 0:
        cmd.extend(["--sleep-interval", str(sleep_interval)])
    if max_sleep_interval > 0:
        cmd.extend(["--max-sleep-interval", str(max_sleep_interval)])
    if sleep_requests > 0:
        cmd.extend(["--sleep-requests", str(sleep_requests)])

    resolved_subtitle_mode = subtitle_mode
    resolved_sub_langs = subtitle_langs
    resolved_embed_subs = embed_subs
    resolved_write_subs = write_subs

    if resolved_subtitle_mode == "none" and sub_lang:
        resolved_subtitle_mode = "manual"
        if not resolved_sub_langs:
            resolved_sub_langs = sub_lang
        if resolved_embed_subs is False:
            resolved_embed_subs = True

    if resolved_subtitle_mode in {"manual", "both"}:
        cmd.append("--write-subs")
    if resolved_subtitle_mode in {"auto", "both"}:
        cmd.append("--write-auto-subs")

    if resolved_subtitle_mode != "none" and resolved_sub_langs:
        cmd.extend(["--sub-langs", resolved_sub_langs])

    if resolved_subtitle_mode != "none" and subtitle_format:
        cmd.extend(["--sub-format", subtitle_format])

    if resolved_subtitle_mode != "none":
        if resolved_embed_subs:
            cmd.append("--embed-subs")

    if download_sections:
        cmd.extend(["--download-sections", download_sections])

    if sponsorblock_enabled:
        categories = sponsorblock_categories.strip() or "sponsor"
        cmd.extend(["--sponsorblock-remove", categories])

    if proxy_url:
        cmd.extend(["--proxy", proxy_url])

    if advanced_args:
        advanced_tokens, error_message = parse_and_validate_advanced_args(advanced_args)
        if error_message:
            raise ValueError(f"高级参数无效: {error_message}")
        cmd.extend(advanced_tokens)

    # PO Token 注入（方案 B）
    use_po_token = bool(getattr(task.profile, "use_po_token", False))
    if use_po_token:
        pot_manager = _get_pot_manager()
        token_data = pot_manager.get_token()
        if token_data:
            visitor_data = token_data.get("visitor_data", "")
            po_token = token_data.get("po_token", "")
            if visitor_data and po_token:
                cmd.extend([
                    "--extractor-args",
                    f"youtube:player_client=web,po_token=visitor_data={visitor_data},po_token={po_token}"
                ])

    cmd.append(task.url)
    return cmd

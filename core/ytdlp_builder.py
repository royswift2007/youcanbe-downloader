import os

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

    if task.needs_cookies and os.path.exists(cookies_file_path):
        cmd.extend(["--cookies", cookies_file_path])

    fmt = task.profile.format
    sub_lang = task.profile.sub_lang
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

    if fmt:
        cmd.extend(["-f", fmt])

    cmd.extend([
        "-o", output_template,
        "--ffmpeg-location", ffmpeg_path,
        "--newline"
    ])

    if fmt == AUDIO_FMT:
        audio_format = merge_output_format if merge_output_format in {"m4a", "mp3", "opus", "wav", "flac"} else "m4a"
        if audio_format == "m4a":
            cmd.extend(["--merge-output-format", "m4a"])
        else:
            cmd.extend(["-x", "--audio-format", audio_format, "--audio-quality", audio_quality])
        if keep_video:
            cmd.append("--keep-video")
    else:
        cmd.extend(["--merge-output-format", merge_output_format])
        if merge_output_format == "mkv":
            cmd.append("--remux-video")
            cmd.append("mkv")

    if embed_metadata:
        cmd.append("--embed-metadata")
    if embed_thumbnail:
        cmd.append("--embed-thumbnail")
    if write_thumbnail:
        cmd.append("--write-thumbnail")
    if write_info_json:
        cmd.append("--write-info-json")
    if write_description:
        cmd.append("--write-description")
    if write_chapters:
        cmd.append("--embed-chapters")

    if h264_compat and fmt != AUDIO_FMT:
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

    if sub_lang:
        cmd.extend(["--write-subs", "--sub-lang", sub_lang, "--embed-subs"])

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

import os

from core.ffmpeg_args_policy import parse_and_validate_ffmpeg_extra_args

# Keep job type constants local to avoid circular imports with core.media_jobs.
MEDIA_JOB_REMUX = "remux"
MEDIA_JOB_EXTRACT_AUDIO = "extract_audio"
MEDIA_JOB_TRIM = "trim"
MEDIA_JOB_CONCAT = "concat"
MEDIA_JOB_BURN_SUBTITLE = "burn_subtitle"
MEDIA_JOB_SCALE = "scale"
MEDIA_JOB_CROP = "crop"
MEDIA_JOB_ROTATE = "rotate"
MEDIA_JOB_WATERMARK = "watermark"
MEDIA_JOB_LOUDNORM = "loudnorm"


_AUDIO_CODEC_MAP = {
    "mp3": "libmp3lame",
    "m4a": "aac",
    "wav": "pcm_s16le",
    "flac": "flac",
    "opus": "libopus",
}

_VIDEO_CODEC_MAP = {
    "h264": "libx264",
    "h265": "libx265",
    "hevc": "libx265",
    "vp9": "libvpx-vp9",
    "av1": "libaom-av1",
    "copy": "copy",
}


def _normalize_path(path_value):
    return os.path.abspath(path_value) if path_value else ""


def _sanitize_int(value):
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return text if text.isdigit() else ""


def _sanitize_float(value):
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        float(text)
    except ValueError:
        return ""
    return text


def _build_scale_filter(width, height):
    w = _sanitize_int(width)
    h = _sanitize_int(height)
    if not w and not h:
        return ""
    return f"scale={w or -1}:{h or -1}"


def _build_crop_filter(width, height, x, y):
    w = _sanitize_int(width)
    h = _sanitize_int(height)
    if not w or not h:
        return ""
    x_val = _sanitize_int(x) or 0
    y_val = _sanitize_int(y) or 0
    return f"crop={w}:{h}:{x_val}:{y_val}"


def _build_rotate_filter(rotate_value):
    value = (rotate_value or "").strip()
    if value in {"90", "180", "270"}:
        if value == "90":
            return "transpose=1"
        if value == "180":
            return "transpose=1,transpose=1"
        if value == "270":
            return "transpose=2"
    return ""


def _build_watermark_filter(position):
    pos = (position or "").strip()
    mapping = {
        "top-left": "10:10",
        "top-right": "main_w-overlay_w-10:10",
        "bottom-left": "10:main_h-overlay_h-10",
        "bottom-right": "main_w-overlay_w-10:main_h-overlay_h-10",
        "center": "(main_w-overlay_w)/2:(main_h-overlay_h)/2",
    }
    return mapping.get(pos, "main_w-overlay_w-10:main_h-overlay_h-10")


def _merge_filter_chain(*items):
    tokens = [item for item in items if item]
    return ",".join(tokens)


def _build_encoding_args(profile):
    args = []
    video_codec = (getattr(profile, "video_codec", "") or "").strip().lower()
    audio_codec = (getattr(profile, "audio_codec", "") or "").strip().lower()
    video_bitrate = (getattr(profile, "video_bitrate", "") or "").strip()
    audio_bitrate = (getattr(profile, "audio_bitrate", "") or "").strip()
    crf = (getattr(profile, "crf", "") or "").strip()
    preset = (getattr(profile, "preset", "") or "").strip()

    if video_codec:
        codec_value = _VIDEO_CODEC_MAP.get(video_codec, video_codec)
        args.extend(["-c:v", codec_value])
    if audio_codec:
        codec_value = _AUDIO_CODEC_MAP.get(audio_codec, audio_codec)
        args.extend(["-c:a", codec_value])
    if video_bitrate:
        args.extend(["-b:v", video_bitrate])
    if audio_bitrate:
        args.extend(["-b:a", audio_bitrate])
    if crf:
        args.extend(["-crf", crf])
    if preset:
        args.extend(["-preset", preset])
    return args



def _needs_reencode(profile):
    return bool(_build_encoding_args(profile))


def _build_extra_args(extra_args):
    tokens, error_message = parse_and_validate_ffmpeg_extra_args(extra_args)
    if error_message:
        raise ValueError(f"ffmpeg 高级参数无效: {error_message}")
    return tokens


def _build_custom_filters(profile):
    vf_custom = (getattr(profile, "vf_custom", "") or "").strip()
    af_custom = (getattr(profile, "af_custom", "") or "").strip()
    vf_args = ["-vf", vf_custom] if vf_custom else []
    af_args = ["-af", af_custom] if af_custom else []
    return vf_args, af_args


def _build_subtitle_filter(subtitle_path):
    normalized = (subtitle_path or "").replace("\\", "/")
    escaped = normalized.replace(":", "\\:").replace("'", "\\'")
    return f"subtitles='{escaped}'"


def build_ffmpeg_command(ffmpeg_path, job):
    profile = getattr(job, "profile", job)
    job_type = getattr(profile, "job_type", "") or getattr(job, "job_type", "")

    input_path = _normalize_path(getattr(profile, "input_path", ""))
    output_path = _normalize_path(getattr(profile, "output_path", ""))

    if not ffmpeg_path:
        raise ValueError("ffmpeg_path 不能为空")
    if not job_type:
        raise ValueError("未指定媒体任务类型")

    if job_type in {
        MEDIA_JOB_REMUX,
        MEDIA_JOB_EXTRACT_AUDIO,
        MEDIA_JOB_TRIM,
        MEDIA_JOB_BURN_SUBTITLE,
        MEDIA_JOB_SCALE,
        MEDIA_JOB_CROP,
        MEDIA_JOB_ROTATE,
        MEDIA_JOB_WATERMARK,
        MEDIA_JOB_LOUDNORM,
    }:
        if not input_path:
            raise ValueError("输入文件路径不能为空")
    if job_type != MEDIA_JOB_CONCAT and not output_path:
        raise ValueError("输出文件路径不能为空")

    if job_type == MEDIA_JOB_REMUX:
        cmd = [
            ffmpeg_path,
            "-y",
            "-i",
            input_path,
        ]
        if _needs_reencode(profile):
            cmd.extend(_build_encoding_args(profile))
        else:
            cmd.extend(["-c", "copy"])
        cmd.extend(_build_extra_args(getattr(profile, "extra_args", "")))
        cmd.append(output_path)
        return cmd

    if job_type == MEDIA_JOB_EXTRACT_AUDIO:
        audio_format = (getattr(profile, "audio_format", "mp3") or "mp3").lower()
        audio_codec = _AUDIO_CODEC_MAP.get(audio_format, "aac")
        cmd = [
            ffmpeg_path,
            "-y",
            "-i",
            input_path,
            "-vn",
            "-c:a",
            audio_codec,
        ]
        cmd.extend(_build_encoding_args(profile))
        cmd.extend(_build_extra_args(getattr(profile, "extra_args", "")))
        cmd.append(output_path)
        return cmd

    if job_type == MEDIA_JOB_TRIM:
        start_time = (getattr(profile, "start_time", "") or "").strip()
        end_time = (getattr(profile, "end_time", "") or "").strip()
        if not start_time:
            raise ValueError("剪辑起始时间不能为空")
        cmd = [
            ffmpeg_path,
            "-y",
        ]
        if start_time:
            cmd.extend(["-ss", start_time])
        cmd.extend(["-i", input_path])
        if end_time:
            cmd.extend(["-to", end_time])
        if _needs_reencode(profile):
            cmd.extend(_build_encoding_args(profile))
        else:
            cmd.extend(["-c", "copy"])
        cmd.extend(_build_extra_args(getattr(profile, "extra_args", "")))
        cmd.append(output_path)
        return cmd

    if job_type == MEDIA_JOB_CONCAT:
        list_path = _normalize_path(getattr(profile, "concat_list_path", ""))
        if not list_path:
            raise ValueError("拼接任务缺少列表文件")
        cmd = [
            ffmpeg_path,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_path,
        ]
        if _needs_reencode(profile):
            cmd.extend(_build_encoding_args(profile))
        else:
            cmd.extend(["-c", "copy"])
        cmd.extend(_build_extra_args(getattr(profile, "extra_args", "")))
        cmd.append(output_path)
        return cmd

    if job_type == MEDIA_JOB_BURN_SUBTITLE:
        subtitle_path = _normalize_path(getattr(profile, "subtitle_path", ""))
        if not subtitle_path:
            raise ValueError("字幕文件路径不能为空")
        filter_arg = _build_subtitle_filter(subtitle_path)
        cmd = [
            ffmpeg_path,
            "-y",
            "-i",
            input_path,
            "-vf",
            filter_arg,
        ]
        cmd.extend(_build_encoding_args(profile) or ["-c:v", "libx264", "-c:a", "aac"])
        cmd.append(output_path)
        cmd.extend(_build_extra_args(getattr(profile, "extra_args", "")))
        return cmd

    if job_type == MEDIA_JOB_SCALE:
        filter_arg = _build_scale_filter(getattr(profile, "scale_width", ""), getattr(profile, "scale_height", ""))
        if not filter_arg:
            raise ValueError("缩放参数不能为空")
        vf_custom, af_custom = _build_custom_filters(profile)
        merged_filter = _merge_filter_chain(filter_arg, (vf_custom[1] if vf_custom else ""))
        cmd = [ffmpeg_path, "-y", "-i", input_path]
        if merged_filter:
            cmd.extend(["-vf", merged_filter])
        if af_custom:
            cmd.extend(af_custom)
        cmd.extend(_build_encoding_args(profile))
        cmd.append(output_path)
        cmd.extend(_build_extra_args(getattr(profile, "extra_args", "")))
        return cmd

    if job_type == MEDIA_JOB_CROP:
        filter_arg = _build_crop_filter(
            getattr(profile, "crop_width", ""),
            getattr(profile, "crop_height", ""),
            getattr(profile, "crop_x", ""),
            getattr(profile, "crop_y", ""),
        )
        if not filter_arg:
            raise ValueError("裁切参数不能为空")
        vf_custom, af_custom = _build_custom_filters(profile)
        merged_filter = _merge_filter_chain(filter_arg, (vf_custom[1] if vf_custom else ""))
        cmd = [ffmpeg_path, "-y", "-i", input_path]
        if merged_filter:
            cmd.extend(["-vf", merged_filter])
        if af_custom:
            cmd.extend(af_custom)
        cmd.extend(_build_encoding_args(profile))
        cmd.append(output_path)
        cmd.extend(_build_extra_args(getattr(profile, "extra_args", "")))
        return cmd

    if job_type == MEDIA_JOB_ROTATE:
        filter_arg = _build_rotate_filter(getattr(profile, "rotate", ""))
        if not filter_arg:
            raise ValueError("旋转参数不能为空")
        vf_custom, af_custom = _build_custom_filters(profile)
        merged_filter = _merge_filter_chain(filter_arg, (vf_custom[1] if vf_custom else ""))
        cmd = [ffmpeg_path, "-y", "-i", input_path]
        if merged_filter:
            cmd.extend(["-vf", merged_filter])
        if af_custom:
            cmd.extend(af_custom)
        cmd.extend(_build_encoding_args(profile))
        cmd.append(output_path)
        cmd.extend(_build_extra_args(getattr(profile, "extra_args", "")))
        return cmd

    if job_type == MEDIA_JOB_WATERMARK:
        watermark_path = _normalize_path(getattr(profile, "watermark_path", ""))
        if not watermark_path:
            raise ValueError("水印文件路径不能为空")
        overlay = _build_watermark_filter(getattr(profile, "watermark_pos", ""))
        vf_custom, af_custom = _build_custom_filters(profile)
        filter_chain = f"overlay={overlay}"
        if vf_custom:
            filter_chain = f"{filter_chain},{vf_custom[1]}"
        cmd = [
            ffmpeg_path,
            "-y",
            "-i",
            input_path,
            "-i",
            watermark_path,
            "-filter_complex",
            filter_chain,
        ]
        if af_custom:
            cmd.extend(af_custom)
        cmd.extend(_build_encoding_args(profile) or ["-c:v", "libx264", "-c:a", "aac"])
        cmd.append(output_path)
        cmd.extend(_build_extra_args(getattr(profile, "extra_args", "")))
        return cmd

    if job_type == MEDIA_JOB_LOUDNORM:
        vf_custom, af_custom = _build_custom_filters(profile)
        af_chain = "loudnorm"
        if af_custom:
            af_chain = f"{af_chain},{af_custom[1]}"
        cmd = [
            ffmpeg_path,
            "-y",
            "-i",
            input_path,
            "-af",
            af_chain,
        ]
        if vf_custom:
            cmd.extend(vf_custom)
        cmd.extend(_build_encoding_args(profile) or ["-c:a", "aac"])
        cmd.append(output_path)
        cmd.extend(_build_extra_args(getattr(profile, "extra_args", "")))
        return cmd

    raise ValueError(f"未知媒体任务类型: {job_type}")

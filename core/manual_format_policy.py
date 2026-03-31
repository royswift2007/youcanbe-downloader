from dataclasses import asdict, dataclass, field
from typing import Optional


SUPPORTED_VIDEO_CODECS = ("h264", "av1", "vp9")
SUPPORTED_VIDEO_CONTAINERS = ("mp4", "webm")
SUPPORTED_AUDIO_MODES = ("default", "no_audio", "select")
DEFAULT_CODEC_RANK = ["h264", "av1", "vp9"]


@dataclass
class ManualPresetSpec:
    target_height: Optional[int] = None
    video_codec_pref: Optional[str] = None
    video_container_pref: Optional[str] = None
    audio_mode: str = "default"
    audio_ext: Optional[str] = None
    audio_quality_kbps: Optional[int] = None


@dataclass
class ManualBatchPolicy:
    enabled: bool = False
    sample_video_url: Optional[str] = None
    preset1: ManualPresetSpec = field(default_factory=ManualPresetSpec)
    preset2: Optional[ManualPresetSpec] = None
    fallback_enabled: bool = False
    codec_rank: list[str] = field(default_factory=lambda: list(DEFAULT_CODEC_RANK))
    ignore_fps: bool = True


def manual_policy_to_dict(policy: ManualBatchPolicy) -> dict:
    if not isinstance(policy, ManualBatchPolicy):
        raise TypeError("policy must be a ManualBatchPolicy instance")
    return asdict(policy)


def manual_policy_from_dict(data: dict) -> ManualBatchPolicy:
    if not isinstance(data, dict):
        raise TypeError("data must be a dict")

    preset1_data = data.get("preset1") or {}
    preset2_data = data.get("preset2")
    return ManualBatchPolicy(
        enabled=bool(data.get("enabled", False)),
        sample_video_url=_strip_optional_text(data.get("sample_video_url")),
        preset1=_preset_from_dict(preset1_data),
        preset2=_preset_from_dict(preset2_data) if isinstance(preset2_data, dict) else None,
        fallback_enabled=bool(data.get("fallback_enabled", False)),
        codec_rank=_normalize_codec_rank(data.get("codec_rank")),
        ignore_fps=bool(data.get("ignore_fps", True)),
    )


def validate_manual_preset_spec(preset: ManualPresetSpec) -> None:
    if not isinstance(preset, ManualPresetSpec):
        raise TypeError("preset must be a ManualPresetSpec instance")

    if preset.target_height is not None:
        if not isinstance(preset.target_height, int):
            raise ValueError("target_height must be an integer")
        if preset.target_height <= 0:
            raise ValueError("target_height must be greater than 0")

    if preset.video_codec_pref is not None and preset.video_codec_pref not in SUPPORTED_VIDEO_CODECS:
        raise ValueError(f"unsupported video codec preference: {preset.video_codec_pref}")

    if preset.video_container_pref is not None and preset.video_container_pref not in SUPPORTED_VIDEO_CONTAINERS:
        raise ValueError(f"unsupported video container preference: {preset.video_container_pref}")

    if preset.audio_mode not in SUPPORTED_AUDIO_MODES:
        raise ValueError(f"unsupported audio mode: {preset.audio_mode}")

    if preset.audio_mode == "select":
        raise ValueError("audio select is not implemented in V1")

    if preset.audio_quality_kbps is not None:
        if not isinstance(preset.audio_quality_kbps, int):
            raise ValueError("audio_quality_kbps must be an integer")
        if preset.audio_quality_kbps <= 0:
            raise ValueError("audio_quality_kbps must be greater than 0")

    if not has_manual_preset_constraints(preset):
        raise ValueError("preset must specify at least one video constraint")


def validate_manual_batch_policy(policy: ManualBatchPolicy) -> None:
    if not isinstance(policy, ManualBatchPolicy):
        raise TypeError("policy must be a ManualBatchPolicy instance")
    if not policy.enabled:
        raise ValueError("manual batch policy is disabled")
    if not policy.ignore_fps:
        raise ValueError("ignore_fps must remain enabled in V1")
    policy.codec_rank = _normalize_codec_rank(policy.codec_rank)
    validate_manual_preset_spec(policy.preset1)
    if policy.preset2 is not None:
        validate_manual_preset_spec(policy.preset2)


def _strip_optional_text(value) -> Optional[str]:
    text = str(value).strip() if value is not None else ""
    return text or None


def _preset_from_dict(data: dict) -> ManualPresetSpec:
    if not isinstance(data, dict):
        raise TypeError("preset data must be a dict")
    return ManualPresetSpec(
        target_height=_normalize_optional_int(data.get("target_height")),
        video_codec_pref=_strip_optional_text(data.get("video_codec_pref")),
        video_container_pref=_strip_optional_text(data.get("video_container_pref") or data.get("container_ext")),
        audio_mode=_strip_optional_text(data.get("audio_mode")) or "default",
        audio_ext=_strip_optional_text(data.get("audio_ext")),
        audio_quality_kbps=_normalize_optional_int(data.get("audio_quality_kbps")),
    )


def _normalize_optional_int(value) -> Optional[int]:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError("boolean is not a valid integer value")
    return int(value)


def _normalize_codec_rank(codec_rank) -> list[str]:
    if not codec_rank:
        return list(DEFAULT_CODEC_RANK)

    normalized = []
    seen = set()
    for item in codec_rank:
        codec = _strip_optional_text(item)
        if not codec:
            continue
        if codec not in SUPPORTED_VIDEO_CODECS:
            raise ValueError(f"unsupported codec in codec_rank: {codec}")
        if codec not in seen:
            seen.add(codec)
            normalized.append(codec)

    for codec in DEFAULT_CODEC_RANK:
        if codec not in seen:
            normalized.append(codec)
    return normalized


def _vcodec_filter_token(codec: str) -> Optional[str]:
    mapping = {
        "h264": "vcodec*=avc1",
        "av1": "vcodec*=av01",
        "vp9": "vcodec*=vp09",
    }
    return mapping.get((codec or "").strip().lower())


def build_video_expr(height: Optional[int], ext: Optional[str], codec: Optional[str]) -> str:
    expr = "bestvideo"
    if height is not None:
        if not isinstance(height, int) or height <= 0:
            raise ValueError("height must be a positive integer")
        expr += f"[height={height}]"
    if ext:
        normalized_ext = ext.strip().lower()
        if normalized_ext not in SUPPORTED_VIDEO_CONTAINERS:
            raise ValueError(f"unsupported video container: {normalized_ext}")
        expr += f"[ext={normalized_ext}]"
    if codec:
        token = _vcodec_filter_token(codec.strip().lower())
        if not token:
            raise ValueError(f"unsupported video codec: {codec}")
        expr += f"[{token}]"
    return expr


def build_audio_expr(preset: ManualPresetSpec) -> str:
    validate_manual_preset_spec(preset)
    if preset.audio_mode == "no_audio":
        return ""
    if preset.audio_mode == "default":
        return "+bestaudio"
    raise ValueError("audio select is not implemented in V1")


def build_expr_for_preset_strict(preset: ManualPresetSpec, codec_rank: list[str]) -> str:
    validate_manual_preset_spec(preset)
    normalized_rank = _normalize_codec_rank(codec_rank)
    audio_expr = build_audio_expr(preset)
    codec_candidates = _build_codec_candidates(preset.video_codec_pref, normalized_rank)
    segments = []
    for codec in codec_candidates:
        segments.append(
            f"{build_video_expr(preset.target_height, preset.video_container_pref, codec)}{audio_expr}"
        )
    return "/".join(segments)


def build_expr_for_fallback(preset: ManualPresetSpec, codec_rank: list[str]) -> str:
    validate_manual_preset_spec(preset)
    normalized_rank = _normalize_codec_rank(codec_rank)
    audio_expr = build_audio_expr(preset)
    segments = []
    if preset.target_height is not None:
        for operator in ("=", ">", "<"):
            segments.extend(
                _build_video_segments(
                    target_height=preset.target_height,
                    height_operator=operator,
                    ext=preset.video_container_pref,
                    preferred_codec=preset.video_codec_pref,
                    codec_rank=normalized_rank,
                    audio_expr=audio_expr,
                )
            )
    else:
        segments.extend(
            _build_video_segments(
                target_height=None,
                height_operator=None,
                ext=preset.video_container_pref,
                preferred_codec=preset.video_codec_pref,
                codec_rank=normalized_rank,
                audio_expr=audio_expr,
            )
        )
    segments.append(_build_terminal_fallback_expr(audio_expr))
    return "/".join(_unique_segments(segments))


def build_ytdlp_format_expr(policy: ManualBatchPolicy) -> str:
    validate_manual_batch_policy(policy)
    expr_parts = [build_expr_for_preset_strict(policy.preset1, policy.codec_rank)]
    if policy.preset2 is not None:
        expr_parts.append(build_expr_for_preset_strict(policy.preset2, policy.codec_rank))
    if policy.fallback_enabled:
        expr_parts.append(build_expr_for_fallback(policy.preset2 or policy.preset1, policy.codec_rank))
    expr_segments = []
    for part in expr_parts:
        if not part:
            continue
        expr_segments.extend(part.split("/"))
    expr = "/".join(_unique_segments(expr_segments))
    if not expr:
        raise ValueError("manual format expression is empty")
    return expr


def build_manual_rule_hint(policy: ManualBatchPolicy, expr: str) -> str:
    validate_manual_batch_policy(policy)
    if not expr:
        raise ValueError("expr must not be empty")

    preset = policy.preset1
    parts = [
        "manual batch format active",
        f"sample={policy.sample_video_url or 'none'}",
        f"preset1={_preset_hint(preset)}",
        f"fallback={'enabled' if policy.fallback_enabled else 'disabled'}",
        f"expr={expr}",
        "note=batch matching is rule-based; actual selection is determined by yt-dlp",
    ]
    if policy.preset2 is not None:
        parts.insert(3, f"preset2={_preset_hint(policy.preset2)}")
    return " | ".join(parts)


def has_manual_preset_constraints(preset: ManualPresetSpec) -> bool:
    if not isinstance(preset, ManualPresetSpec):
        return False
    return any(
        (
            preset.target_height is not None,
            preset.video_codec_pref is not None,
            preset.video_container_pref is not None,
        )
    )


def _preset_hint(preset: ManualPresetSpec) -> str:
    return ",".join(
        [
            f"height={preset.target_height or 'any'}",
            f"codec={preset.video_codec_pref or 'any'}",
            f"container={preset.video_container_pref or 'any'}",
            f"audio={preset.audio_mode}",
        ]
    )


def _build_codec_candidates(preferred_codec: Optional[str], codec_rank: list[str]) -> list[Optional[str]]:
    if not preferred_codec:
        return [None]

    normalized_pref = preferred_codec.strip().lower()
    if normalized_pref not in SUPPORTED_VIDEO_CODECS:
        raise ValueError(f"unsupported video codec preference: {preferred_codec}")

    ordered = [normalized_pref]
    for codec in codec_rank:
        if codec != normalized_pref:
            ordered.append(codec)
    ordered.append(None)
    return ordered


def _build_video_expr_with_height_filter(
    target_height: Optional[int],
    height_operator: Optional[str],
    ext: Optional[str],
    codec: Optional[str],
) -> str:
    expr = "bestvideo"
    if target_height is not None:
        if not isinstance(target_height, int) or target_height <= 0:
            raise ValueError("target_height must be a positive integer")
        operator = height_operator or "="
        if operator not in ("=", ">", "<"):
            raise ValueError(f"unsupported height operator: {operator}")
        expr += f"[height{operator}{target_height}]"
    if ext:
        normalized_ext = ext.strip().lower()
        if normalized_ext not in SUPPORTED_VIDEO_CONTAINERS:
            raise ValueError(f"unsupported video container: {normalized_ext}")
        expr += f"[ext={normalized_ext}]"
    if codec:
        token = _vcodec_filter_token(codec.strip().lower())
        if not token:
            raise ValueError(f"unsupported video codec: {codec}")
        expr += f"[{token}]"
    return expr


def _build_video_segments(
    target_height: Optional[int],
    height_operator: Optional[str],
    ext: Optional[str],
    preferred_codec: Optional[str],
    codec_rank: list[str],
    audio_expr: str,
) -> list[str]:
    segments = []
    for codec in _build_codec_candidates(preferred_codec, codec_rank):
        segments.append(
            f"{_build_video_expr_with_height_filter(target_height, height_operator, ext, codec)}{audio_expr}"
        )
    return segments


def _build_terminal_fallback_expr(audio_expr: str) -> str:
    if audio_expr:
        return f"bestvideo{audio_expr}/best"
    return "bestvideo"


def _unique_segments(segments: list[str]) -> list[str]:
    result = []
    seen = set()
    for segment in segments:
        if not segment or segment in seen:
            continue
        seen.add(segment)
        result.append(segment)
    return result

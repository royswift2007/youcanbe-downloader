import shlex


# Disallow overriding options controlled by app-level profile fields.
DISALLOWED_ADVANCED_FLAGS = {
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

# Whitelist of supported advanced args and whether they require a value.
# value_mode: "none" | "required"
ALLOWED_ADVANCED_FLAGS = {
    "--no-part": "none",
    "--no-continue": "none",
    "--force-overwrites": "none",
    "--ignore-errors": "none",
    "--abort-on-error": "none",
    "--force-ipv4": "none",
    "--no-check-certificate": "none",
    "--concurrent-fragments": "required",
    "-N": "required",
    "--fragment-retries": "required",
    "--extractor-retries": "required",
    "--file-access-retries": "required",
    "--socket-timeout": "required",
    "--http-chunk-size": "required",
    "--downloader": "required",
    "--downloader-args": "required",
    "--compat-options": "required",
}


def parse_and_validate_advanced_args(raw_args):
    text = (raw_args or "").strip()
    if not text:
        return [], ""

    try:
        tokens = shlex.split(text)
    except ValueError as exc:
        return [], f"参数解析失败: {exc}"

    parsed = []
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        if not token.startswith("-"):
            return [], f"仅允许参数，不允许独立值: {token}"

        if "=" in token:
            flag, inline_value = token.split("=", 1)
        else:
            flag, inline_value = token, None

        if flag in DISALLOWED_ADVANCED_FLAGS:
            return [], f"包含受限参数: {flag}"
        if flag not in ALLOWED_ADVANCED_FLAGS:
            return [], f"不支持的高级参数: {flag}"

        value_mode = ALLOWED_ADVANCED_FLAGS[flag]
        if value_mode == "none":
            if inline_value is not None and inline_value != "":
                return [], f"参数 {flag} 不接受值"
            parsed.append(token)
            idx += 1
            continue

        # required value
        if inline_value is not None:
            if inline_value == "":
                return [], f"参数 {flag} 需要值"
            parsed.append(token)
            idx += 1
            continue

        if idx + 1 >= len(tokens):
            return [], f"参数 {flag} 缺少值"
        next_token = tokens[idx + 1]
        if next_token.startswith("-"):
            return [], f"参数 {flag} 缺少值"
        parsed.extend([token, next_token])
        idx += 2

    return parsed, ""


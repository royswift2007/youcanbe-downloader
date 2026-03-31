import shlex


DISALLOWED_FFMPEG_FLAGS = {
    "-i",
    "-y",
    "-n",
    "-filter_complex",
    "-vf",
    "-af",
    "-map",
    "-c",
    "-c:v",
    "-c:a",
    "-f",
    "-ss",
    "-to",
}

ALLOWED_FFMPEG_FLAGS = {
    "-metadata": "required",
    "-movflags": "required",
    "-shortest": "none",
    "-threads": "required",
}


def parse_and_validate_ffmpeg_extra_args(raw_args):
    raw = (raw_args or "").strip()
    if not raw:
        return [], ""

    try:
        tokens = shlex.split(raw)
    except ValueError as exc:
        return [], f"参数解析失败: {exc}"

    validated = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith("-"):
            return [], f"不允许的位置参数: {token}"
        if token in DISALLOWED_FFMPEG_FLAGS:
            return [], f"禁止参数: {token}"
        if token not in ALLOWED_FFMPEG_FLAGS:
            return [], f"未允许的参数: {token}"

        validated.append(token)
        rule = ALLOWED_FFMPEG_FLAGS[token]
        if rule == "required":
            if index + 1 >= len(tokens):
                return [], f"参数缺少取值: {token}"
            value = tokens[index + 1]
            if value.startswith("-"):
                return [], f"参数缺少取值: {token}"
            validated.append(value)
            index += 2
            continue

        index += 1

    return validated, ""

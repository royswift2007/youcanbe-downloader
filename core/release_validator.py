import os


REQUIRED_BINARIES = {
    "yt-dlp": ("yt-dlp.exe", "yt-dlp"),
    "ffmpeg": ("ffmpeg.exe", "ffmpeg"),
    "deno": ("deno.exe", "deno"),
}

REQUIRED_DATA_FILES = (
    "usage_intro.md",
    "usage_intro_en.md",
)


def validate_release_bundle(bundle_root, only_binaries=False):
    root = os.path.abspath(bundle_root or ".")
    missing = []

    checked = []
    for logical_name, candidates in REQUIRED_BINARIES.items():
        checked.extend(candidates)
        if not any(os.path.exists(os.path.join(root, candidate)) for candidate in candidates):
            missing.append(logical_name)

    if not only_binaries:
        for relative_path in REQUIRED_DATA_FILES:
            checked.append(relative_path)
            candidate = os.path.join(root, relative_path)
            if not os.path.exists(candidate):
                missing.append(relative_path)

    return {
        "ok": not missing,
        "root": root,
        "missing": missing,
        "checked": checked,
    }

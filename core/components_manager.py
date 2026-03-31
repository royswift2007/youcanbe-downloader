import json
import os
import re
import shutil
import subprocess
import time


MIN_YTDLP_VERSION = "2024.10.22"
MIN_FFMPEG_PREFIX = "ffmpeg version"
MIN_DENO_VERSION = "1.39"


def _parse_numeric_version_parts(version_text):
    text = (version_text or "").strip().lower()
    if not text:
        return ()
    match = re.search(r"(\d+(?:\.\d+)+)", text)
    if not match:
        return ()
    parts = []
    for item in match.group(1).split("."):
        try:
            parts.append(int(item))
        except ValueError:
            return ()
    return tuple(parts)


def _is_version_at_least(version_text, minimum_text):
    current = _parse_numeric_version_parts(version_text)
    minimum = _parse_numeric_version_parts(minimum_text)
    if not current or not minimum:
        return False
    width = max(len(current), len(minimum))
    current = current + (0,) * (width - len(current))
    minimum = minimum + (0,) * (width - len(minimum))
    return current >= minimum


class ComponentStatus:
    def __init__(self, name, path="", version="", ok=False, message=""):
        self.name = name
        self.path = path
        self.version = version
        self.ok = ok
        self.message = message
        self.checked_at = time.strftime("%Y-%m-%d %H:%M:%S")


class ComponentsManager:
    def __init__(self, yt_dlp_path, ffmpeg_path, deno_path="", text_getter=None):
        self.yt_dlp_path = yt_dlp_path
        self.ffmpeg_path = ffmpeg_path
        self.deno_path = deno_path
        self._text_getter = text_getter

    def _t(self, key, fallback=""):
        if callable(self._text_getter):
            try:
                return self._text_getter(key, fallback)
            except Exception:
                pass
        return fallback or key

    def _run_version(self, cmd, timeout=6):
        import sys
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace", startupinfo=startupinfo)
            if result.returncode != 0:
                return "", False, (result.stderr or result.stdout or "").strip()
            return (result.stdout or "").strip(), True, ""
        except FileNotFoundError:
            return "", False, "not_found"
        except Exception as exc:
            return "", False, str(exc)

    def check_yt_dlp(self):
        path = self.yt_dlp_path
        version, ok, message = self._run_version([path, "--version"], timeout=6)
        if ok and version:
            if not _parse_numeric_version_parts(version):
                ok = False
                message = self._t(
                    "components_version_invalid",
                    "{name} version output invalid",
                ).format(name="yt-dlp")
            elif not _is_version_at_least(version, MIN_YTDLP_VERSION):
                ok = False
                message = self._t(
                    "components_version_too_old",
                    "{name} version too old (min: {min})",
                ).format(name="yt-dlp", min=MIN_YTDLP_VERSION)
        if not ok:
            if not path:
                message = self._t("components_missing_ytdlp", "未配置 yt-dlp 路径")
            elif message == "not_found":
                message = self._t("components_binary_missing", "{name} executable not found").format(name="yt-dlp")
        return ComponentStatus("yt-dlp", path=path, version=version, ok=ok, message=message)

    def check_ffmpeg(self):
        path = self.ffmpeg_path
        version_text, ok, message = self._run_version([path, "-version"], timeout=6)
        version = version_text.splitlines()[0] if version_text else ""
        if ok and version and not version.lower().startswith(MIN_FFMPEG_PREFIX):
            ok = False
            message = self._t(
                "components_version_invalid",
                "{name} version output invalid",
            ).format(name="ffmpeg")
        if not ok:
            if not path:
                message = self._t("components_missing_ffmpeg", "未配置 ffmpeg 路径")
            elif message == "not_found":
                message = self._t("components_binary_missing", "{name} executable not found").format(name="ffmpeg")
        return ComponentStatus("ffmpeg", path=path, version=version, ok=ok, message=message)

    def check_deno(self):
        path = self.deno_path or shutil.which("deno") or shutil.which("deno.exe") or "deno"
        version_text, ok, message = self._run_version([path, "--version"], timeout=6)
        version = version_text.splitlines()[0] if version_text else ""
        if ok and version_text:
            first_line = version_text.splitlines()[0]
            parsed = first_line.replace("deno ", "").strip()
            if not _parse_numeric_version_parts(parsed):
                ok = False
                message = self._t(
                    "components_version_invalid",
                    "{name} version output invalid",
                ).format(name="deno")
            elif not _is_version_at_least(parsed, MIN_DENO_VERSION):
                ok = False
                message = self._t(
                    "components_version_too_old",
                    "{name} version too old (min: {min})",
                ).format(name="deno", min=MIN_DENO_VERSION)
        if not ok and message == "not_found":
            message = self._t("components_binary_missing", "{name} executable not found").format(name="deno")
        return ComponentStatus("deno", path=path, version=version, ok=ok, message=message)

    def export_diagnostics(self, output_path, statuses):
        payload = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "components": [
                {
                    "name": item.name,
                    "path": item.path,
                    "version": item.version,
                    "ok": item.ok,
                    "message": item.message,
                    "checked_at": item.checked_at,
                }
                for item in statuses
            ],
        }
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return output_path

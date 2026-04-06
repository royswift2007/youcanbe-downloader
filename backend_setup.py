import argparse
import configparser
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from dataclasses import dataclass, field

from core.components_manager import (
    MIN_DENO_VERSION,
    MIN_FFMPEG_PREFIX,
    MIN_YTDLP_VERSION,
    _is_version_at_least,
    _parse_numeric_version_parts,
)

COMPONENT_SOURCES = {
    "yt-dlp": {
        "url": "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe",
        "type": "binary",
        "filename": "yt-dlp.exe",
    },
    "ffmpeg": {
        "url": "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip",
        "type": "zip",
        "filename": "ffmpeg.exe",
        "zip_match": "ffmpeg.exe",
    },
    "deno": {
        "url": "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip",
        "type": "zip",
        "filename": "deno.exe",
        "zip_match": "deno.exe",
    },
}

COMPONENT_ORDER = tuple(COMPONENT_SOURCES.keys())
EXIT_SUCCESS = 0
EXIT_COMPONENT_FAILURE = 1
EXIT_ARGS_ERROR = 2
EXIT_DIR_ERROR = 3
EXIT_FATAL_ERROR = 4
DEFAULT_RETRY_DELAY_SECONDS = 2.0
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
FILE_REPLACE_RETRY_DELAY_SECONDS = 0.05
FILE_REPLACE_MAX_ATTEMPTS = 20
COMPONENT_METADATA_FILENAME = ".ycb_component_versions.json"
HTTP_HEADERS = {
    "User-Agent": "YCB-Installer/0.1.1",
    "Accept": "*/*",
}


class InstallerError(RuntimeError):
    pass


class ArgsError(InstallerError):
    pass


class DirectoryError(InstallerError):
    pass


class ConsoleLogger:
    def __init__(self, log_file: str = ""):
        self.log_file = os.path.abspath(log_file) if log_file else ""
        if self.log_file:
            parent = os.path.dirname(self.log_file)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(self.log_file, "w", encoding="utf-8") as f:
                f.write("")

    def log(self, message: str):
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        print(line, flush=True)
        if self.log_file:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")


class _CaseConfigParser(configparser.ConfigParser):
    def optionxform(self, optionstr):
        return optionstr


def replace_file_with_retry(temp_path: str, absolute_path: str):
    last_error = None
    for attempt in range(1, FILE_REPLACE_MAX_ATTEMPTS + 1):
        try:
            os.replace(temp_path, absolute_path)
            return
        except OSError as exc:
            last_error = exc
            winerror = getattr(exc, "winerror", 0)
            retryable = isinstance(exc, PermissionError) or winerror in {5, 32}
            if (not retryable) or attempt >= FILE_REPLACE_MAX_ATTEMPTS:
                raise
            time.sleep(FILE_REPLACE_RETRY_DELAY_SECONDS)

    if last_error is not None:
        raise last_error


class IniWriter:
    @staticmethod
    def write(path: str, section: str, values: dict):
        if not path:
            return
        absolute_path = os.path.abspath(path)
        parent = os.path.dirname(absolute_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        parser = _CaseConfigParser()
        parser[section] = {key: str(value) for key, value in values.items()}
        temp_path = absolute_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            parser.write(f)
        replace_file_with_retry(temp_path, absolute_path)


class TextWriter:
    @staticmethod
    def write(path: str, text: str):
        if not path:
            return
        absolute_path = os.path.abspath(path)
        parent = os.path.dirname(absolute_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        temp_path = absolute_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(text)
        replace_file_with_retry(temp_path, absolute_path)


class ProgressReporter:
    def __init__(self, progress_file: str, total_components: int):
        self.progress_file = progress_file
        self.total_components = max(0, total_components)

    def update(
        self,
        component: str,
        phase: str,
        message: str,
        component_index: int = 0,
        component_progress: int = 0,
        attempt: int = 0,
        max_attempts: int = 0,
        current_bytes: int = 0,
        total_bytes: int = 0,
    ):
        component_progress = max(0, min(100, int(component_progress)))
        if self.total_components > 0 and component_index > 0:
            overall_raw = ((component_index - 1) * 100 + component_progress) / self.total_components
            overall_progress = max(0, min(100, int(overall_raw)))
        elif self.total_components == 0:
            overall_progress = 100 if phase in {"finished", "skipped_all"} else 0
        else:
            overall_progress = 0

        IniWriter.write(
            self.progress_file,
            "progress",
            {
                "component": component,
                "phase": phase,
                "message": message,
                "component_index": component_index,
                "component_total": self.total_components,
                "component_progress": component_progress,
                "overall_progress": overall_progress,
                "attempt": attempt,
                "max_attempts": max_attempts,
                "current_bytes": current_bytes,
                "total_bytes": total_bytes,
                "updated_at": int(time.time()),
            },
        )


@dataclass
class InstallResults:
    requested: list[str] = field(default_factory=list)
    installed: list[str] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    not_selected: list[str] = field(default_factory=list)
    manual_install: list[str] = field(default_factory=list)
    exit_code: int = EXIT_SUCCESS
    message: str = ""

    def finalize(self):
        ordered = []
        seen = set()
        for name in list(self.failed) + list(self.not_selected):
            if name not in seen:
                ordered.append(name)
                seen.add(name)
        self.manual_install = ordered

    @staticmethod
    def _csv(values: list[str]) -> str:
        return ",".join(values)

    def to_ini_dict(self) -> dict:
        return {
            "requested": self._csv(self.requested),
            "installed": self._csv(self.installed),
            "skipped_existing": self._csv(self.skipped_existing),
            "failed": self._csv(self.failed),
            "not_selected": self._csv(self.not_selected),
            "manual_install": self._csv(self.manual_install),
            "exit_code": self.exit_code,
            "message": self.message,
        }


def normalize_component_name(value: str) -> str:
    name = (value or "").strip().lower()
    aliases = {
        "yt-dlp.exe": "yt-dlp",
        "ytdlp": "yt-dlp",
        "yt_dlp": "yt-dlp",
        "ffmpeg.exe": "ffmpeg",
        "deno.exe": "deno",
    }
    return aliases.get(name, name)


def parse_components_argument(raw_value: str | None) -> list[str]:
    if raw_value is None:
        return list(COMPONENT_ORDER)

    text = raw_value.strip()
    if not text:
        return []

    if text.lower() == "all":
        return list(COMPONENT_ORDER)

    selected = []
    seen = set()
    for item in text.split(","):
        normalized = normalize_component_name(item)
        if not normalized:
            continue
        if normalized not in COMPONENT_SOURCES:
            raise ArgsError(f"Unknown component: {item}")
        if normalized not in seen:
            selected.append(normalized)
            seen.add(normalized)
    return selected


def ensure_directory_writable(target_dir: str):
    absolute_dir = os.path.abspath(target_dir)
    os.makedirs(absolute_dir, exist_ok=True)
    probe_path = os.path.join(absolute_dir, ".ycb_installer_write_test")
    try:
        with open(probe_path, "w", encoding="utf-8") as f:
            f.write("ok")
    except OSError as exc:
        raise DirectoryError(f"Target directory is not writable: {absolute_dir} ({exc})") from exc
    finally:
        try:
            if os.path.exists(probe_path):
                os.remove(probe_path)
        except OSError:
            pass


def validate_installed_file(path: str):
    if not os.path.isfile(path):
        raise InstallerError(f"Installed file missing: {path}")
    if os.path.getsize(path) <= 0:
        raise InstallerError(f"Installed file is empty: {path}")


def build_hidden_startupinfo():
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
    return startupinfo


def run_version_command(cmd: list[str], timeout: int = 6) -> tuple[str, bool, str]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            startupinfo=build_hidden_startupinfo(),
        )
        if result.returncode != 0:
            return "", False, (result.stderr or result.stdout or "").strip()
        return (result.stdout or "").strip(), True, ""
    except FileNotFoundError:
        return "", False, "not_found"
    except Exception as exc:
        return "", False, str(exc)


def get_component_metadata_path(target_dir: str) -> str:
    return os.path.join(os.path.abspath(target_dir), COMPONENT_METADATA_FILENAME)


def load_component_metadata(target_dir: str) -> dict:
    metadata_path = get_component_metadata_path(target_dir)
    if not os.path.isfile(metadata_path):
        return {}
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_component_metadata(
    target_dir: str,
    component_name: str,
    version_text: str,
    component_path: str,
    release_hint: str = "",
    compare_version: str = "",
):
    metadata = load_component_metadata(target_dir)
    metadata[component_name] = {
        "version": version_text or "",
        "compare_version": compare_version or "",
        "path": os.path.abspath(component_path) if component_path else "",
        "release_hint": release_hint or "",
        "recorded_at": int(time.time()),
    }
    TextWriter.write(get_component_metadata_path(target_dir), json.dumps(metadata, ensure_ascii=False, indent=2))


def parse_latest_version_from_url(component_name: str, final_url: str) -> str:
    text = final_url or ""
    if component_name == "yt-dlp":
        match = re.search(r"/download/([^/]+)/yt-dlp\.exe", text, re.IGNORECASE)
        return match.group(1).strip() if match else ""
    if component_name == "deno":
        match = re.search(r"/download/([^/]+)/deno-[^/]+\.zip", text, re.IGNORECASE)
        if not match:
            return ""
        return match.group(1).strip().lstrip("v")
    if component_name == "ffmpeg":
        match = re.search(r"/download/([^/]+)/ffmpeg-master-latest-win64-gpl\.zip", text, re.IGNORECASE)
        return match.group(1).strip() if match else ""
    return ""


def resolve_latest_component_hint(name: str, timeout: int, logger: ConsoleLogger) -> dict:
    source = COMPONENT_SOURCES[name]
    request = urllib.request.Request(source["url"], headers=HTTP_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=max(5, min(timeout, 20))) as response:
            final_url = response.geturl() or source["url"]
        version_hint = parse_latest_version_from_url(name, final_url)
        if version_hint:
            logger.log(f"[Info] Latest {name} target version hint: {version_hint}")
        else:
            logger.log(f"[Info] Latest {name} target URL resolved: {final_url}")
        return {
            "version": version_hint,
            "url": final_url,
        }
    except Exception as exc:
        logger.log(f"[Warn] Failed to resolve latest {name} version hint: {exc}")
        return {
            "version": "",
            "url": source["url"],
        }


def detect_component_version(name: str, path: str, timeout: int = 6) -> dict:
    absolute_path = os.path.abspath(path) if path else ""
    if not absolute_path:
        return {
            "path": "",
            "version": "",
            "compare_version": "",
            "compatible": False,
            "message": "missing_path",
        }

    if name == "yt-dlp":
        output, ok, message = run_version_command([absolute_path, "--version"], timeout=timeout)
        version = output.strip()
        compatible = bool(ok and version and _parse_numeric_version_parts(version) and _is_version_at_least(version, MIN_YTDLP_VERSION))
        return {
            "path": absolute_path,
            "version": version,
            "compare_version": version,
            "compatible": compatible,
            "message": "" if compatible else message or "version_not_compatible",
        }

    if name == "ffmpeg":
        output, ok, message = run_version_command([absolute_path, "-version"], timeout=timeout)
        version = output.splitlines()[0].strip() if output else ""
        compatible = bool(ok and version and version.lower().startswith(MIN_FFMPEG_PREFIX))
        compare_version = ""
        match = re.search(r"ffmpeg version\s+([^\s]+)", version, re.IGNORECASE)
        if match:
            compare_version = match.group(1).strip()
        return {
            "path": absolute_path,
            "version": version,
            "compare_version": compare_version,
            "compatible": compatible,
            "message": "" if compatible else message or "version_not_compatible",
        }

    if name == "deno":
        output, ok, message = run_version_command([absolute_path, "--version"], timeout=timeout)
        first_line = output.splitlines()[0].strip() if output else ""
        compare_version = first_line.replace("deno ", "").strip()
        compatible = bool(ok and compare_version and _parse_numeric_version_parts(compare_version) and _is_version_at_least(compare_version, MIN_DENO_VERSION))
        return {
            "path": absolute_path,
            "version": first_line,
            "compare_version": compare_version,
            "compatible": compatible,
            "message": "" if compatible else message or "version_not_compatible",
        }

    return {
        "path": absolute_path,
        "version": "",
        "compare_version": "",
        "compatible": False,
        "message": "unknown_component",
    }


def find_existing_component_paths(name: str, target_dir: str) -> list[str]:
    source = COMPONENT_SOURCES[name]
    candidates = []
    seen = set()

    def add_candidate(candidate: str | None):
        if not candidate:
            return
        absolute_candidate = os.path.abspath(candidate)
        key = absolute_candidate.lower()
        if key in seen:
            return
        seen.add(key)
        candidates.append(absolute_candidate)

    # Only reuse components that already exist in the target app directory.
    # System-wide PATH matches must not suppress installer downloads.
    add_candidate(os.path.join(os.path.abspath(target_dir), source["filename"]))
    return candidates


def find_reusable_existing_component(name: str, target_dir: str, timeout: int, logger: ConsoleLogger) -> dict | None:
    target_dir = os.path.abspath(target_dir)
    target_path = os.path.join(target_dir, COMPONENT_SOURCES[name]["filename"])
    latest_hint = resolve_latest_component_hint(name, timeout, logger)
    metadata = load_component_metadata(target_dir)
    recorded_value = metadata.get(name)
    recorded = recorded_value if isinstance(recorded_value, dict) else {}

    for candidate in find_existing_component_paths(name, target_dir):
        probe = detect_component_version(name, candidate, timeout=min(timeout, 10))
        if not probe["compatible"]:
            continue

        display_version = probe["version"] or probe["compare_version"] or "unknown"
        release_hint = latest_hint.get("version", "")

        if name in {"yt-dlp", "deno"}:
            local_compare = probe["compare_version"]
            if release_hint and local_compare and _is_version_at_least(local_compare, release_hint):
                return {
                    "path": candidate,
                    "version": probe["version"],
                    "compare_version": local_compare,
                    "release_hint": release_hint,
                    "message": f"Using existing {name} {display_version} from {candidate}",
                }
            if not release_hint:
                return {
                    "path": candidate,
                    "version": probe["version"],
                    "compare_version": local_compare,
                    "release_hint": recorded.get("release_hint", "") if os.path.abspath(candidate) == target_path else "",
                    "message": f"Using existing compatible {name} {display_version} from {candidate}",
                }
            continue

        if name == "ffmpeg":
            if os.path.abspath(candidate) == target_path and release_hint and recorded.get("release_hint") == release_hint:
                return {
                    "path": candidate,
                    "version": probe["version"],
                    "compare_version": probe["compare_version"],
                    "release_hint": release_hint,
                    "message": f"Using existing ffmpeg release {release_hint} from {candidate}",
                }
            if not release_hint and os.path.abspath(candidate) == target_path and recorded.get("version") == probe["version"]:
                return {
                    "path": candidate,
                    "version": probe["version"],
                    "compare_version": probe["compare_version"],
                    "release_hint": recorded.get("release_hint", ""),
                    "message": f"Using existing recorded ffmpeg from {candidate}",
                }
            return {
                "path": candidate,
                "version": probe["version"],
                "compare_version": probe["compare_version"],
                "release_hint": recorded.get("release_hint", "") if os.path.abspath(candidate) == target_path else "",
                "message": f"Using existing compatible ffmpeg {display_version} from {candidate}",
            }

    return None


def format_bytes(size: int) -> str:
    if size <= 0:
        return "0B"
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)}{unit}"
            return f"{value:.1f}{unit}"
        value /= 1024.0
    return f"{int(size)}B"


def download_file(url: str, target_path: str, timeout: int, progress_callback=None):
    request = urllib.request.Request(url, headers=HTTP_HEADERS)
    temp_path = target_path + ".tmp"
    if os.path.exists(temp_path):
        os.remove(temp_path)

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, open(temp_path, "wb") as out_file:
            total_size = int(response.headers.get("Content-Length", "0") or "0")
            downloaded = 0
            while True:
                chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                out_file.write(chunk)
                downloaded += len(chunk)
                if callable(progress_callback):
                    progress_callback(downloaded, total_size)
        if os.path.exists(target_path):
            os.remove(target_path)
        replace_file_with_retry(temp_path, target_path)
    except Exception:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass
        raise


def extract_zip_member(zip_path: str, match_name: str, target_path: str):
    with zipfile.ZipFile(zip_path, "r") as zf:
        members = zf.namelist()
        lowered = match_name.lower()
        candidate = ""
        for name in members:
            if name.lower().endswith(lowered):
                candidate = name
                break
        if not candidate:
            raise InstallerError(f"Could not find {match_name} in zip archive")

        temp_path = target_path + ".tmp"
        with zf.open(candidate) as src, open(temp_path, "wb") as dst:
            shutil.copyfileobj(src, dst)
        if os.path.exists(target_path):
            os.remove(target_path)
        replace_file_with_retry(temp_path, target_path)


def install_component(
    name: str,
    component_index: int,
    total_components: int,
    target_dir: str,
    retry_count: int,
    timeout: int,
    skip_existing: bool,
    progress: ProgressReporter,
    logger: ConsoleLogger,
) -> tuple[str, str]:
    source = COMPONENT_SOURCES[name]
    target_path = os.path.join(target_dir, source["filename"])
    max_attempts = max(1, retry_count)

    if skip_existing:
        reusable = find_reusable_existing_component(name, target_dir, timeout, logger)
        if reusable:
            progress.update(
                component=name,
                phase="skipped_existing",
                message=reusable["message"],
                component_index=component_index,
                component_progress=100,
                attempt=1,
                max_attempts=max_attempts,
            )
            logger.log(f"[*] {reusable['message']}; skipping download.")
            if os.path.abspath(reusable["path"]) == os.path.abspath(target_path):
                save_component_metadata(
                    target_dir=target_dir,
                    component_name=name,
                    version_text=reusable.get("version", ""),
                    component_path=reusable["path"],
                    release_hint=reusable.get("release_hint", ""),
                    compare_version=reusable.get("compare_version", ""),
                )
            return "skipped_existing", reusable["message"]

    latest_hint = {"version": "", "url": source["url"]}
    if skip_existing:
        latest_hint = resolve_latest_component_hint(name, timeout, logger)

    for attempt in range(1, max_attempts + 1):
        try:
            progress.update(
                component=name,
                phase="prepare",
                message=f"Preparing {name}",
                component_index=component_index,
                component_progress=0,
                attempt=attempt,
                max_attempts=max_attempts,
            )
            logger.log(f"[Step] Installing {name} (attempt {attempt}/{max_attempts})")

            if source["type"] == "binary":
                def on_progress(downloaded: int, total: int):
                    percent = int(downloaded * 100 / total) if total > 0 else 0
                    progress.update(
                        component=name,
                        phase="download",
                        message=f"Downloading {name}: {format_bytes(downloaded)}/{format_bytes(total)}",
                        component_index=component_index,
                        component_progress=min(90, percent),
                        attempt=attempt,
                        max_attempts=max_attempts,
                        current_bytes=downloaded,
                        total_bytes=total,
                    )

                download_file(source["url"], target_path, timeout=timeout, progress_callback=on_progress)
            else:
                with tempfile.TemporaryDirectory() as temp_dir:
                    zip_path = os.path.join(temp_dir, f"{name}.zip")

                    def on_progress(downloaded: int, total: int):
                        percent = int(downloaded * 100 / total) if total > 0 else 0
                        progress.update(
                            component=name,
                            phase="download",
                            message=f"Downloading {name}: {format_bytes(downloaded)}/{format_bytes(total)}",
                            component_index=component_index,
                            component_progress=min(70, percent),
                            attempt=attempt,
                            max_attempts=max_attempts,
                            current_bytes=downloaded,
                            total_bytes=total,
                        )

                    download_file(source["url"], zip_path, timeout=timeout, progress_callback=on_progress)
                    progress.update(
                        component=name,
                        phase="extract",
                        message=f"Extracting {name}",
                        component_index=component_index,
                        component_progress=85,
                        attempt=attempt,
                        max_attempts=max_attempts,
                    )
                    extract_zip_member(zip_path, source.get("zip_match") or source["filename"], target_path)

            progress.update(
                component=name,
                phase="verify",
                message=f"Verifying {name}",
                component_index=component_index,
                component_progress=95,
                attempt=attempt,
                max_attempts=max_attempts,
            )
            validate_installed_file(target_path)

            detected = detect_component_version(name, target_path, timeout=min(timeout, 10))
            save_component_metadata(
                target_dir=target_dir,
                component_name=name,
                version_text=detected.get("version", ""),
                component_path=target_path,
                release_hint=latest_hint.get("version", ""),
                compare_version=detected.get("compare_version", ""),
            )
            progress.update(
                component=name,
                phase="done",
                message=f"Installed {name}",
                component_index=component_index,
                component_progress=100,
                attempt=attempt,
                max_attempts=max_attempts,
            )
            logger.log(f"[Done] Installed {name} -> {target_path}")
            return "installed", detected.get("version", "")
        except Exception as exc:
            error_message = str(exc)
            logger.log(f"[Error] {name} installation failed on attempt {attempt}/{max_attempts}: {error_message}")
            if attempt < max_attempts:
                progress.update(
                    component=name,
                    phase="retry",
                    message=f"Retrying {name} ({attempt + 1}/{max_attempts})",
                    component_index=component_index,
                    component_progress=0,
                    attempt=attempt + 1,
                    max_attempts=max_attempts,
                )
                time.sleep(DEFAULT_RETRY_DELAY_SECONDS)
                continue

            progress.update(
                component=name,
                phase="error",
                message=f"Failed to install {name}: {error_message}",
                component_index=component_index,
                component_progress=100,
                attempt=attempt,
                max_attempts=max_attempts,
            )
            return "failed", error_message

    return "failed", "Unknown failure"


def write_missing_components_file(path: str, component_names: list[str]):
    if not path:
        return
    lines = [COMPONENT_SOURCES[name]["filename"] for name in component_names]
    TextWriter.write(path, "\n".join(lines))


def run_installation(args) -> int:
    logger = ConsoleLogger(args.log_file)
    progress = ProgressReporter(args.progress_file, 0)
    results = InstallResults()

    try:
        selected_components = parse_components_argument(args.components)
        results.requested = list(selected_components)
        results.not_selected = [name for name in COMPONENT_ORDER if name not in selected_components]
        results.finalize()

        progress = ProgressReporter(args.progress_file, len(selected_components))
        logger.log(f"YCB backend component installer started. target={os.path.abspath(args.dir)}")
        logger.log(f"Selected components: {', '.join(selected_components) if selected_components else '(none)'}")

        ensure_directory_writable(args.dir)

        if not selected_components:
            results.message = "No optional components selected."
            results.exit_code = EXIT_SUCCESS
            progress.update(
                component="(none)",
                phase="skipped_all",
                message="No optional components selected.",
                component_index=0,
                component_progress=100,
            )
            return results.exit_code

        installed_any = False
        for index, name in enumerate(selected_components, start=1):
            status, detail = install_component(
                name=name,
                component_index=index,
                total_components=len(selected_components),
                target_dir=os.path.abspath(args.dir),
                retry_count=args.retry,
                timeout=args.timeout,
                skip_existing=args.skip_existing,
                progress=progress,
                logger=logger,
            )
            if status == "installed":
                installed_any = True
                results.installed.append(name)
            elif status == "skipped_existing":
                results.skipped_existing.append(name)
            else:
                results.failed.append(name)
                logger.log(f"[Result] {name} failed after retry: {detail}")

        results.finalize()
        if results.failed:
            results.exit_code = EXIT_COMPONENT_FAILURE
            results.message = "Some selected components failed to install."
            progress.update(
                component=results.failed[-1],
                phase="finished",
                message=results.message,
                component_index=len(selected_components),
                component_progress=100,
            )
        else:
            results.exit_code = EXIT_SUCCESS
            if results.skipped_existing and not results.installed:
                results.message = "Selected components already satisfied locally; download skipped."
            elif results.skipped_existing:
                results.message = "Selected components installed; compatible local components were skipped."
            else:
                results.message = "Selected components installed successfully."
            final_component = selected_components[-1] if selected_components else "(none)"
            progress.update(
                component=final_component,
                phase="finished",
                message=results.message,
                component_index=len(selected_components),
                component_progress=100,
            )

        if not installed_any and results.skipped_existing:
            logger.log("[*] No new download required; selected components already existed with compatible versions.")

        return results.exit_code
    except ArgsError as exc:
        results.exit_code = EXIT_ARGS_ERROR
        results.message = str(exc)
        logger.log(f"[Fatal] {results.message}")
        progress.update(component="(args)", phase="error", message=results.message, component_progress=100)
        return results.exit_code
    except DirectoryError as exc:
        results.exit_code = EXIT_DIR_ERROR
        results.message = str(exc)
        logger.log(f"[Fatal] {results.message}")
        progress.update(component="(dir)", phase="error", message=results.message, component_progress=100)
        return results.exit_code
    except Exception as exc:
        results.exit_code = EXIT_FATAL_ERROR
        results.message = str(exc)
        logger.log(f"[Fatal] Unexpected error: {results.message}")
        progress.update(component="(fatal)", phase="error", message=results.message, component_progress=100)
        return results.exit_code
    finally:
        results.finalize()
        IniWriter.write(args.result_file, "result", results.to_ini_dict())
        write_missing_components_file(args.missing_components_file, results.manual_install)
        logger.log(
            "Installer finished with exit_code={code}; installed={installed}; skipped_existing={skipped}; failed={failed}; manual_install={manual}".format(
                code=results.exit_code,
                installed=",".join(results.installed) or "(none)",
                skipped=",".join(results.skipped_existing) or "(none)",
                failed=",".join(results.failed) or "(none)",
                manual=",".join(results.manual_install) or "(none)",
            )
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install optional YCB backend components.")
    parser.add_argument("--dir", default=".", help="Target directory for components")
    parser.add_argument(
        "--components",
        default=None,
        help="Comma-separated components to install. Omit for all, use empty string for none.",
    )
    parser.add_argument("--retry", type=int, default=3, help="Retry count for each component")
    parser.add_argument("--timeout", type=int, default=300, help="Per-download timeout in seconds")
    parser.add_argument("--skip-existing", action="store_true", help="Skip existing compatible component files")
    parser.add_argument("--progress-file", default="", help="INI file used to report installation progress")
    parser.add_argument("--result-file", default="", help="INI file used to report installation result summary")
    parser.add_argument(
        "--missing-components-file",
        default="",
        help="Text file that lists components requiring manual installation",
    )
    parser.add_argument("--log-file", default="", help="Optional log file path")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.retry < 1:
        raise SystemExit(EXIT_ARGS_ERROR)
    if args.timeout < 1:
        raise SystemExit(EXIT_ARGS_ERROR)
    return run_installation(args)


if __name__ == "__main__":
    raise SystemExit(main())

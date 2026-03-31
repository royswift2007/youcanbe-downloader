import json
import os
import shutil
import subprocess
import sys
import time


def resolve_deno_path(deno_path=None):
    if deno_path:
        return deno_path
    return shutil.which("deno") or shutil.which("deno.exe") or "deno"


def run_deno_script(deno_path, script_path, payload, timeout=6):
    started_at = time.time()
    resolved_deno = resolve_deno_path(deno_path)
    resolved_script = os.path.abspath(script_path) if script_path else ""
    if not resolved_script or not os.path.exists(resolved_script):
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": "script_not_found",
            "duration": time.time() - started_at,
        }

    ext = os.path.splitext(resolved_script)[1].lower()
    cmd = None
    engine_error = ""
    if ext == ".py":
        cmd = [sys.executable, resolved_script]
    elif ext in {".js", ".mjs", ".cjs"}:
        node_path = shutil.which("node") or shutil.which("node.exe")
        if node_path:
            cmd = [node_path, resolved_script]
        else:
            cmd = [
                resolved_deno,
                "run",
                "--allow-read",
                "--allow-env",
                resolved_script,
            ]
    else:
        cmd = [
            resolved_deno,
            "run",
            "--allow-read",
            "--allow-env",
            resolved_script,
        ]
    input_payload = json.dumps(payload or {}, ensure_ascii=False)
    try:
        proc = subprocess.run(
            cmd,
            input=input_payload,
            text=True,
            capture_output=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout or "",
            "stderr": proc.stderr or "",
            "duration": time.time() - started_at,
        }
    except FileNotFoundError:
        if ext == ".py":
            engine_error = "python_not_found"
        elif ext in {".js", ".mjs", ".cjs"}:
            engine_error = "script_engine_not_found"
        else:
            engine_error = "deno_not_found"
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": engine_error,
            "duration": time.time() - started_at,
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": "timeout",
            "duration": time.time() - started_at,
        }
    except Exception as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": f"runtime_error: {exc}",
            "duration": time.time() - started_at,
        }

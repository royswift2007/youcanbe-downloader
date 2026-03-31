import os
import time
from collections import deque


class LogFileSink:
    def __init__(self, file_path, max_bytes=5 * 1024 * 1024, backup_count=3):
        self.file_path = file_path
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self._buffer = deque()

    def write(self, message, level="INFO", timestamp=None):
        if message is None:
            return
        ts = timestamp or time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] [{level}] {message}\n"
        self._buffer.append(line)

    def flush(self):
        if not self._buffer:
            return
        self._rotate_if_needed()
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        with open(self.file_path, "a", encoding="utf-8") as f:
            while self._buffer:
                f.write(self._buffer.popleft())

    def _rotate_if_needed(self):
        if not os.path.exists(self.file_path):
            return
        try:
            size = os.path.getsize(self.file_path)
        except OSError:
            return
        if size < self.max_bytes:
            return
        for i in range(self.backup_count, 0, -1):
            src = f"{self.file_path}.{i}" if i > 1 else self.file_path
            dst = f"{self.file_path}.{i + 1}"
            if i == self.backup_count:
                if os.path.exists(dst):
                    try:
                        os.remove(dst)
                    except OSError:
                        pass
            if os.path.exists(src):
                try:
                    os.replace(src, dst)
                except OSError:
                    pass

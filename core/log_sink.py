import os
import threading
import time
from collections import deque


class LogFileSink:
    def __init__(self, file_path, max_bytes=5 * 1024 * 1024, backup_count=3):
        self.file_path = file_path
        self.max_bytes = max_bytes
        self.backup_count = max(0, int(backup_count))
        self._buffer = deque()
        self._lock = threading.Lock()

    def write(self, message, level="INFO", timestamp=None):
        if message is None:
            return
        ts = timestamp or time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] [{level}] {message}\n"
        self._buffer.append(line)

    def flush(self):
        if not self._buffer:
            return
        with self._lock:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            # 写入前先轮转，写完后再次检查，超限时循环轮转直到满足；
            # 对于关闭时极少见的“单次写入仍超限”场景，最多补一次轮转即可。
            self._rotate_if_needed()
            with open(self.file_path, "a", encoding="utf-8") as f:
                while self._buffer:
                    f.write(self._buffer.popleft())
            self._rotate_if_needed()

    def _current_size(self):
        try:
            return os.path.getsize(self.file_path)
        except OSError:
            return 0

    def _rotate_if_needed(self):
        if self.backup_count <= 0:
            return
        if not os.path.exists(self.file_path):
            return
        if self._current_size() < self.max_bytes:
            return
        self._rotate_backups()

    def _rotate_backups(self):
        # backup_count=N 恰好保留 N 个备份（不含当前文件）：
        # 删除最旧的 .N 备份，再将 .i 顺次右移为 .i+1，最后当前文件 -> .1。
        try:
            oldest = f"{self.file_path}.{self.backup_count}"
            if os.path.exists(oldest):
                try:
                    os.remove(oldest)
                except OSError:
                    pass
            for i in range(self.backup_count - 1, 0, -1):
                src = f"{self.file_path}.{i}"
                dst = f"{self.file_path}.{i + 1}"
                if os.path.exists(src):
                    try:
                        os.replace(src, dst)
                    except OSError:
                        pass
            if os.path.exists(self.file_path):
                try:
                    os.replace(self.file_path, f"{self.file_path}.1")
                except OSError:
                    pass
        except OSError:
            pass

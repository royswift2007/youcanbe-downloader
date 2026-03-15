"""
core/po_token_manager.py

管理 YouTube PO Token 的自动生成与缓存。
依赖本地安装的 Node.js (>= v18) 和 tools/po_token/ 目录中的 JS 脚本。
失败时静默降级，不影响正常下载流程。
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time

logger = logging.getLogger(__name__)

_TOOLS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools", "po_token")
_SCRIPT_PATH = os.path.join(_TOOLS_DIR, "generate_token.js")
_TOKEN_TTL = 3600  # Token 有效期 1 小时

# 单例全局状态
STATUS_UNKNOWN = "unknown"
STATUS_NO_NODE = "no_node"
STATUS_OLD_NODE = "old_node"
STATUS_INSTALLING = "installing"
STATUS_READY = "ready"
STATUS_ERROR = "error"
STATUS_DISABLED = "disabled"


class PoTokenManager:
    """
    负责 PO Token 的生命周期管理：
    - 检测 Node.js 是否可用及版本
    - 首次使用时自动运行 npm install
    - 生成并缓存 Token（1 小时有效）
    - 所有失败均静默降级，返回 None
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._cached_token: dict | None = None
        self._cached_at: float = 0.0
        self._status: str = STATUS_UNKNOWN
        self._status_message: str = ""
        self._status_callbacks: list = []
        self._node_path: str = self._find_node_path()
        self._repair_in_progress: bool = False

    @staticmethod
    def _find_node_path() -> str:
        """查找 node 可执行文件路径，优先 PATH，兜底 Windows 常见安装位置。"""
        import shutil
        found = shutil.which("node")
        if found:
            return found
        if sys.platform == "win32":
            candidates = [
                r"C:\Program Files\nodejs\node.exe",
                r"C:\Program Files (x86)\nodejs\node.exe",
                os.path.join(os.environ.get("APPDATA", ""), r"nvm\current\node.exe"),
                os.path.join(os.environ.get("ProgramFiles", ""), r"nodejs\node.exe"),
            ]
            for path in candidates:
                if os.path.isfile(path):
                    return path
        return "node"  # 最终兜底，让系统自行查找

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def initialize_async(self):
        """启动时在后台线程检测环境，不阻塞主线程。"""
        t = threading.Thread(target=self._initialize, daemon=True)
        t.start()

    def get_status(self) -> tuple[str, str]:
        """返回 (status_code, status_message)"""
        return self._status, self._status_message

    def is_ready(self) -> bool:
        return self._status == STATUS_READY

    def on_status_change(self, callback):
        """注册状态变更回调，callback(status_code, message)"""
        self._status_callbacks.append(callback)

    def get_token(self) -> dict | None:
        """
        返回 {"visitor_data": "...", "po_token": "..."} 或 None。
        缓存 1 小时内直接复用，过期后重新生成。
        生成失败时自动修复一次（重新 npm install），再次失败则更新顶栏状态。
        """
        if not self.is_ready():
            return None

        with self._lock:
            if self._cached_token and (time.time() - self._cached_at) < _TOKEN_TTL:
                logger.debug("PO Token: 使用缓存")
                return self._cached_token

        token = self._generate_token()
        if token:
            with self._lock:
                self._cached_token = token
                self._cached_at = time.time()
            return token

        # 生成失败 → 后台触发修复（只修复一次，不阻塞当前下载）
        if not self._repair_in_progress:
            t = threading.Thread(target=self._repair_and_retry, daemon=True)
            t.start()
        return None

    def invalidate_cache(self):
        """手动使缓存失效（例如 IP 变化后调用）。"""
        with self._lock:
            self._cached_token = None
            self._cached_at = 0.0

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _set_status(self, code: str, message: str):
        self._status = code
        self._status_message = message
        logger.info(f"PO Token 状态: [{code}] {message}")
        for cb in self._status_callbacks:
            try:
                cb(code, message)
            except Exception:
                pass

    def _initialize(self):
        """后台初始化：检测 node → 确保依赖 → 置为 ready。"""
        self._set_status(STATUS_UNKNOWN, "正在检测 Node.js 环境…")

        # 1. 检测 node
        node_version = self._detect_node()
        if node_version is None:
            self._set_status(STATUS_NO_NODE, "未检测到 Node.js，请安装 v18 或更高版本")
            return
        if node_version < 18:
            self._set_status(STATUS_OLD_NODE, f"Node.js 版本过低 (v{node_version})，需要 v18+")
            return

        # 2. 确保 npm 依赖已安装
        if not self._ensure_deps():
            self._set_status(STATUS_ERROR, "npm install 失败，请检查网络连接")
            return

        # 3. 准备就绪，做一次预热生成
        self._set_status(STATUS_READY, f"就绪 (Node.js v{node_version})")

    def _detect_node(self) -> int | None:
        """返回 Node.js 主版本号，或 None（未安装）。"""
        try:
            result = subprocess.run(
                [self._node_path, "--version"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                return None
            # v20.11.0 → 20
            version_str = result.stdout.strip().lstrip("v")
            major = int(version_str.split(".")[0])
            return major
        except (FileNotFoundError, ValueError, subprocess.TimeoutExpired):
            return None

    def _ensure_deps(self) -> bool:
        """如果 node_modules 不存在则运行 npm install。"""
        node_modules = os.path.join(_TOOLS_DIR, "node_modules")
        if os.path.isdir(node_modules):
            return True
        return self._run_npm_install()

    def _run_npm_install(self) -> bool:
        """执行 npm install，Windows 使用 npm.cmd。"""
        self._set_status(STATUS_INSTALLING, "正在安装依赖（npm install）…")
        npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
        try:
            result = subprocess.run(
                [npm_cmd, "install"],
                cwd=_TOOLS_DIR,
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                logger.error(f"npm install 失败: {result.stderr}")
                return False
            logger.info("npm install 完成")
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.error(f"npm install 异常: {e}")
            return False

    def _repair_and_retry(self):
        """Token 生成失败后：删除 node_modules 重新安装，再试一次。"""
        self._repair_in_progress = True
        try:
            logger.warning("PO Token 生成失败，尝试重新安装依赖…")
            self._set_status(STATUS_INSTALLING, "Token 失败，正在重新安装依赖…")

            # 删除旧的 node_modules
            node_modules = os.path.join(_TOOLS_DIR, "node_modules")
            if os.path.isdir(node_modules):
                import shutil
                shutil.rmtree(node_modules, ignore_errors=True)

            # 重新安装
            if not self._run_npm_install():
                msg = "npm 重装失败，PO Token 不可用，请检查网络或手动运行 npm install"
                logger.error(msg)
                self._set_status(STATUS_ERROR, msg)
                return

            # 再次尝试生成
            self._set_status(STATUS_READY, "重装完成，正在生成 Token…")
            token = self._generate_token()
            if token:
                with self._lock:
                    self._cached_token = token
                    self._cached_at = time.time()
                logger.info("PO Token 修复后生成成功")
                self._set_status(STATUS_READY, "就绪（修复后）")
            else:
                msg = "重装后 Token 生成仍失败，请检查网络或更新 Node.js"
                logger.error(msg)
                self._set_status(STATUS_ERROR, msg)
        finally:
            self._repair_in_progress = False

    def _generate_token(self) -> dict | None:
        """调用 Node.js 脚本生成 Token。"""
        if not os.path.exists(_SCRIPT_PATH):
            logger.warning(f"Token 脚本不存在: {_SCRIPT_PATH}")
            return None
        try:
            result = subprocess.run(
                [self._node_path, _SCRIPT_PATH],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                logger.warning(f"Token 生成失败: {result.stderr.strip()}")
                return None
            data = json.loads(result.stdout.strip())
            if "visitor_data" in data and "po_token" in data:
                logger.info("PO Token 生成成功")
                return data
            logger.warning(f"Token 响应格式异常: {result.stdout.strip()}")
            return None
        except (json.JSONDecodeError, subprocess.TimeoutExpired, OSError) as e:
            logger.warning(f"Token 生成异常: {e}")
            return None


# 全局单例
_manager: PoTokenManager | None = None


def get_manager() -> PoTokenManager:
    global _manager
    if _manager is None:
        _manager = PoTokenManager()
    return _manager

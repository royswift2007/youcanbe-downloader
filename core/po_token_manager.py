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

import sys

# 获取基础目录（支持 PyInstaller）
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    _BASE_DIR = getattr(sys, '_MEIPASS')
else:
    _BASE_DIR = os.path.dirname(os.path.dirname(__file__))

_TOOLS_DIR = os.path.join(_BASE_DIR, "tools", "po_token")
_SCRIPT_PATH = os.path.join(_TOOLS_DIR, "generate_token.js")
_TOKEN_TTL = 3600  # Token 有效期 1 小时

# 当 tools/po_token 目录不存在时，说明当前版本未包含 PO Token 工具，需静默降级
_TOOLS_AVAILABLE = os.path.isdir(_TOOLS_DIR)

# 单例全局状态
STATUS_UNKNOWN = "unknown"
STATUS_NO_NODE = "no_node"
STATUS_OLD_NODE = "old_node"
STATUS_INSTALLING = "installing"
STATUS_READY = "ready"
STATUS_ERROR = "error"
STATUS_DISABLED = "disabled"
STATUS_RETRY_WAIT = "retry_wait"


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
        self._repair_attempts: int = 0
        self._next_repair_at: float = 0.0
        self._last_updated_at: float = 0.0
        self._last_error: str = ""
        
        # Windows 静默启动配置，防止 cmd 窗口闪烁
        if sys.platform == "win32":
            self._startupinfo = subprocess.STARTUPINFO()
            self._startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            self._startupinfo.wShowWindow = subprocess.SW_HIDE
        else:
            self._startupinfo = None

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

    def get_status_detail(self) -> dict:
        return {
            "status": self._status,
            "message": self._status_message,
            "last_updated_at": self._last_updated_at,
            "last_error": self._last_error,
            "repair_in_progress": self._repair_in_progress,
            "repair_attempts": self._repair_attempts,
            "next_repair_at": self._next_repair_at,
        }

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
            self._store_token(token)
            return token

        # 生成失败 → 后台触发修复（只修复一次，不阻塞当前下载）
        self._schedule_repair_after_failure()
        return None

    def repair(self):
        """手动触发安装/修复过程，不强制立即生成 Token。"""
        with self._lock:
            if self._repair_in_progress:
                return
            self._repair_in_progress = True
            self._repair_attempts = 0
            self._next_repair_at = 0.0
            self._last_error = ""
        self._set_status(STATUS_INSTALLING, "pot_msg_installing")
        self._start_repair_thread(verify_token=False)

    def invalidate_cache(self):
        """手动使缓存失效（例如 IP 变化后调用）。"""
        with self._lock:
            self._cached_token = None
            self._cached_at = 0.0

    def _store_token(self, token: dict):
        with self._lock:
            self._cached_token = token
            self._cached_at = time.time()
            self._last_updated_at = self._cached_at
            self._last_error = ""
            self._repair_attempts = 0
            self._next_repair_at = 0.0

    def _next_backoff_seconds(self) -> int:
        step = max(1, self._repair_attempts)
        return min(300, 30 * step)

    def _start_repair_thread(self, verify_token: bool):
        t = threading.Thread(
            target=self._repair_and_retry,
            kwargs={"verify_token": verify_token},
            daemon=True,
        )
        t.start()

    def _schedule_repair_after_failure(self):
        now = time.time()
        with self._lock:
            if self._repair_in_progress:
                return
            if self._next_repair_at and now < self._next_repair_at:
                should_wait = True
            else:
                should_wait = False
                self._repair_in_progress = True
                self._repair_attempts += 1
        if should_wait:
            self._set_status(STATUS_RETRY_WAIT, "pot_msg_retry_wait")
            return
        self._set_status(STATUS_INSTALLING, "pot_msg_repairing")
        self._start_repair_thread(verify_token=True)

    def _set_retry_wait(self, message: str):
        delay = self._next_backoff_seconds()
        now = time.time()
        with self._lock:
            self._next_repair_at = now + delay
            self._last_updated_at = now
            self._last_error = message
        self._set_status(STATUS_RETRY_WAIT, message)

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _set_status(self, code: str, message: str):
        now = time.time()
        with self._lock:
            self._status = code
            self._status_message = message
            self._last_updated_at = now
            if code == STATUS_ERROR:
                self._last_error = message
            elif code == STATUS_READY:
                self._last_error = ""
                self._next_repair_at = 0.0
        logger.info(f"PO Token 状态: [{code}] {message}")
        for cb in self._status_callbacks:
            try:
                cb(code, message)
            except Exception:
                pass

    def _initialize(self):
        """后台初始化：检测 node → 确保依赖 → 置为 ready。"""
        try:
            self._set_status(STATUS_UNKNOWN, "pot_msg_checking")

            # 0. 工具目录缺失时静默降级，避免 subprocess cwd 指向不存在目录导致 WinError 267
            if not _TOOLS_AVAILABLE:
                self._set_status(STATUS_DISABLED, "pot_msg_disabled")
                return

            # 1. 检测 node
            node_version = self._detect_node()
            if node_version is None:
                self._set_status(STATUS_NO_NODE, "pot_msg_no_node")
                return
            if node_version < 18:
                self._set_status(STATUS_OLD_NODE, "pot_msg_old_node")
                return

            # 2. 确保 npm 依赖已安装
            if not self._ensure_deps():
                self._set_status(STATUS_ERROR, "pot_msg_npm_fail")
                return

            # 3. 准备就绪
            self._set_status(STATUS_READY, "pot_msg_ready")
        except Exception as e:
            logger.error(f"PO Token 初始化崩溃: {e}", exc_info=True)
            self._set_status(STATUS_ERROR, f"初始化异常: {str(e)}")

    def _detect_node(self) -> int | None:
        """返回 Node.js 主版本号，或 None（未安装）。"""
        try:
            result = subprocess.run(
                [self._node_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                startupinfo=self._startupinfo,
            )
            if result.returncode != 0:
                return None
            # v20.11.0 → 20
            version_str = result.stdout.strip().lstrip("v")
            major = int(version_str.split(".")[0])
            return major
        except (FileNotFoundError, ValueError, subprocess.TimeoutExpired, OSError, Exception):
            return None

    def _ensure_deps(self) -> bool:
        """如果 node_modules 不存在则运行 npm install。"""
        node_modules = os.path.join(_TOOLS_DIR, "node_modules")
        if os.path.isdir(node_modules):
            return True
        return self._run_npm_install()

    def _run_npm_install(self) -> bool:
        """执行 npm install，Windows 使用 npm.cmd。"""
        self._set_status(STATUS_INSTALLING, "pot_msg_installing")
        import shutil
        npm_cmd = shutil.which("npm.cmd") or shutil.which("npm") or ("npm.cmd" if sys.platform == "win32" else "npm")
        try:
            result = subprocess.run(
                [npm_cmd, "install"],
                cwd=_TOOLS_DIR,
                capture_output=True,
                text=True,
                timeout=120,
                startupinfo=self._startupinfo,
            )
            if result.returncode != 0:
                logger.error(f"npm install 失败: {result.stderr}")
                return False
            
            logger.info("npm install 完成，同步资源文件中…")
            self._sync_vendor_files()
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.error(f"npm install 异常: {e}")
            return False

    def _repair_and_retry(self, verify_token: bool = True):
        """删除 node_modules 后重新安装；自动修复时再额外校验 Token 生成。"""
        try:
            if verify_token:
                logger.warning("PO Token 生成失败，尝试重新安装依赖…")
                self._set_status(STATUS_INSTALLING, "pot_msg_repairing")
            else:
                logger.info("PO Token 手动安装/修复开始…")
                self._set_status(STATUS_INSTALLING, "pot_msg_installing")

            # 删除旧的 node_modules
            node_modules = os.path.join(_TOOLS_DIR, "node_modules")
            if os.path.isdir(node_modules):
                import shutil
                shutil.rmtree(node_modules, ignore_errors=True)

            # 重新安装
            if not self._run_npm_install():
                msg = "pot_msg_repair_fail"
                logger.error(msg)
                if verify_token:
                    self._set_retry_wait(msg)
                else:
                    self._set_status(STATUS_ERROR, msg)
                return

            # 应用针对 NPM 模块的修复补丁和代理逻辑
            self._sync_vendor_files()

            if not verify_token:
                self.invalidate_cache()
                logger.info("PO Token 手动安装/修复完成")
                self._set_status(STATUS_READY, "pot_msg_ready_repaired")
                return

            # 自动修复时才进一步验证 Token 生成
            self._set_status(STATUS_INSTALLING, "pot_msg_repair_generating")
            token = self._generate_token()
            if token:
                self._store_token(token)
                logger.info("PO Token 修复后生成成功")
                self._set_status(STATUS_READY, "pot_msg_ready_repaired")
            else:
                msg = "pot_msg_repair_final_fail"
                logger.error(msg)
                self._set_retry_wait(msg)
        finally:
            with self._lock:
                self._repair_in_progress = False

    def _sync_vendor_files(self):
        """将 node_modules/youtube-po-token-generator 中的 vendor 和 lib 同步到 tools/po_token/ 以修复其内部 Bug。"""
        try:
            import shutil
            src_root = os.path.join(_TOOLS_DIR, "node_modules", "youtube-po-token-generator")
            if not os.path.isdir(src_root):
                return
                
            for folder in ["vendor", "lib"]:
                src = os.path.join(src_root, folder)
                dst = os.path.join(_TOOLS_DIR, folder)
                if os.path.isdir(src):
                    # 如果目标已存在且不是目录，先删除 (防御性)
                    if os.path.exists(dst) and not os.path.isdir(dst):
                        os.remove(dst)
                    # 复制整个文件夹（如果已存在则覆盖）
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                    logger.info(f"PO Token: 已同步 {folder} 发至工具根目录")
                    
            # ------ 补丁：给 npm 工具注入系统代理支持 ------
            task_js = os.path.join(src_root, "lib", "task.js")
            if os.path.isfile(task_js):
                with open(task_js, "r", encoding="utf-8") as f:
                    content = f.read()
                if "proxy: process.env.HTTPS_" not in content:
                    content = content.replace("pretendToBeVisual: true,", "pretendToBeVisual: true,\n            proxy: process.env.HTTPS_PROXY || process.env.HTTP_PROXY || process.env.https_proxy || process.env.http_proxy || undefined,")
                    with open(task_js, "w", encoding="utf-8") as f:
                        f.write(content)
                        
            utils_js = os.path.join(src_root, "lib", "utils.js")
            if os.path.isfile(utils_js):
                with open(utils_js, "r", encoding="utf-8") as f:
                    content = f.read()
                if "https-proxy-agent" not in content and "https.get(url" in content:
                    patch = """
  let options = { headers };
  const proxyUrl = process.env.HTTPS_PROXY || process.env.HTTP_PROXY || process.env.https_proxy || process.env.http_proxy;
  if (proxyUrl) {
    try {
      const { HttpsProxyAgent } = require("https-proxy-agent");
      options.agent = new HttpsProxyAgent(proxyUrl);
    } catch(e) {}
  }
  const req = https.get(url, options, (res) => {"""
                    content = content.replace("https.get(url, { headers }, (res) => {", patch.strip())
                    with open(utils_js, "w", encoding="utf-8") as f:
                        f.write(content)

        except Exception as e:
            logger.error(f"PO Token 资源同步异常: {e}")

    def _extract_node_error(self, result: subprocess.CompletedProcess) -> str:
        streams = []
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        if stderr:
            streams.append(stderr)
        if stdout:
            streams.append(stdout)

        for stream in streams:
            for line in reversed(stream.splitlines()):
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict) and payload.get("success") is False:
                    return json.dumps(payload, ensure_ascii=False)

        combined = "\n".join(streams).strip()
        return combined

    def _generate_token(self) -> dict | None:
        """调用 Node.js 脚本生成 Token。"""
        if not os.path.exists(_SCRIPT_PATH):
            logger.warning(f"Token 脚本不存在: {_SCRIPT_PATH}")
            return None
            
        env = os.environ.copy()

        try:
            result = subprocess.run(
                [self._node_path, _SCRIPT_PATH],
                cwd=_TOOLS_DIR,
                capture_output=True,
                text=True,
                timeout=75,
                startupinfo=self._startupinfo,
                env=env,
            )
            if result.returncode != 0:
                error_detail = self._extract_node_error(result)
                logger.warning(f"Token 生成失败: {error_detail}")
                self._last_error = error_detail
                return None
            data = json.loads(result.stdout.strip())
            if "visitor_data" in data and "po_token" in data:
                logger.info("PO Token 生成成功")
                return data
            logger.warning(f"Token 响应格式异常: {result.stdout.strip()}")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"Token 响应解析异常: {e}")
            self._last_error = f"Token 响应解析异常: {e}"
            return None
        except subprocess.TimeoutExpired as e:
            logger.warning(f"Token 生成超时: {e}")
            self._last_error = f"Token 生成超时: {e}"
            return None
        except OSError as e:
            logger.warning(f"Token 生成异常: {e}")
            self._last_error = f"Token 生成异常: {e}"
            return None


# 全局单例
_manager: PoTokenManager | None = None


def get_manager() -> PoTokenManager:
    global _manager
    if _manager is None:
        _manager = PoTokenManager()
    return _manager

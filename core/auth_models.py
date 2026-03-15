from dataclasses import dataclass, field
from typing import List, Optional
import time

AUTH_LEVEL_INFO = "info"
AUTH_LEVEL_WARNING = "warning"
AUTH_LEVEL_ERROR = "error"

AUTH_STATUS_OK = "ok"
AUTH_STATUS_MISSING = "missing"
AUTH_STATUS_WARNING = "warning"
AUTH_STATUS_ERROR = "error"
AUTH_STATUS_UNKNOWN = "unknown"

AUTH_REASON_NONE = "none"
AUTH_REASON_LOGIN_REQUIRED = "login_required"
AUTH_REASON_AGE_RESTRICTED = "age_restricted"
AUTH_REASON_PRIVATE_VIDEO = "private_video"
AUTH_REASON_MEMBERS_ONLY = "members_only"
AUTH_REASON_PAYMENT_REQUIRED = "payment_required"
AUTH_REASON_FORBIDDEN = "forbidden"
AUTH_REASON_JS_CHALLENGE = "js_challenge"
AUTH_REASON_BOT_CHECK = "bot_check"
AUTH_REASON_NETWORK = "network"
AUTH_REASON_UNKNOWN = "unknown"


@dataclass
class AuthDiagnostic:
    ok: bool = False
    category: str = AUTH_REASON_NONE
    level: str = AUTH_LEVEL_INFO
    summary: str = "未检测到认证问题"
    detail: str = ""
    action_hint: str = ""
    is_auth_related: bool = False
    raw_output: str = ""


@dataclass
class CookiesStatus:
    file_path: str
    exists: bool = False
    status: str = AUTH_STATUS_UNKNOWN
    last_checked_at: float = 0.0
    last_success_at: float = 0.0
    last_error_at: float = 0.0
    last_error_category: str = AUTH_REASON_NONE
    last_message: str = "未检查"
    last_action_hint: str = ""
    last_used_cookies: bool = False
    diagnostics: List[AuthDiagnostic] = field(default_factory=list)

    def update_from_diagnostic(self, diagnostic: AuthDiagnostic, used_cookies: bool = False):
        self.exists = bool(self.file_path)
        self.last_checked_at = time.time()
        self.last_used_cookies = used_cookies
        self.diagnostics.append(diagnostic)
        self.diagnostics = self.diagnostics[-10:]
        self.last_message = diagnostic.summary
        self.last_action_hint = diagnostic.action_hint

        if diagnostic.ok:
            self.status = AUTH_STATUS_OK
            self.last_success_at = self.last_checked_at
            self.last_error_category = AUTH_REASON_NONE
            return

        self.last_error_at = self.last_checked_at
        self.last_error_category = diagnostic.category
        if not self.exists:
            self.status = AUTH_STATUS_MISSING
        elif diagnostic.level == AUTH_LEVEL_ERROR:
            self.status = AUTH_STATUS_ERROR
        else:
            self.status = AUTH_STATUS_WARNING


import os

file_path = r'c:\Users\qinghua\Documents\youcanbe downloader\core\youtube_metadata.py'

replacements = {
    'summary="未检测到认证问题"': 'summary="auth_summary_ok"',
    'summary="标题获取成功"': 'summary="auth_summary_ok"',
    'summary="格式获取成功"': 'summary="auth_summary_ok"',
    'summary="标题/元数据获取失败，原因暂未识别"': 'summary="auth_summary_unknown"',
    'action_hint="建议优先启用 Browser Cookies（Chrome/Edge/Firefox），或重新导出已登录账号的 cookies 文件后重试。"': 'action_hint="auth_action_age_restricted"',
    'action_hint="请确认当前账号具备访问权限，并使用 Browser Cookies 或更新 cookies 文件。"': 'action_hint="auth_action_private_video"',
    'action_hint="请确认当前账号具备会员权限，并使用 Browser Cookies 或更新 cookies 文件。"': 'action_hint="auth_action_members_only"',
    'action_hint="请确认当前账号已购买对应内容，并使用已登录账号的 cookies。"': 'action_hint="auth_action_payment_required"',
    'action_hint="建议启用 Browser Cookies；如继续使用文件模式，请重新导出 `www.youtube.com_cookies.txt`。"': 'action_hint="auth_action_login_required"',
    'action_hint="建议检查 cookies 与代理设置；可尝试启用 Browser Cookies 或 PO Token；若内容本身不可用则无法通过重试解决。"': 'action_hint="auth_action_forbidden"',
    'action_hint="这通常不是 cookies 本身失效，可优先检查 `yt-dlp.exe` 版本与当前网络环境。"': 'action_hint="auth_action_js_challenge"',
    'action_hint="建议稍后重试，必要时更换网络环境，并使用有效 cookies。"': 'action_hint="auth_action_bot_check"',
    'action_hint="请先检查网络连通性、代理配置与 TLS/SSL 环境，再判断是否需要重新导出 cookies。"': 'action_hint="auth_action_network"',
    'action_hint="请直接查看后续“标题获取原始日志”内容，优先判断是否为链接失效、网络异常、yt-dlp 版本问题或站点风控。"': 'action_hint="auth_action_unknown"',
    '"检测到年龄限制内容"': '"auth_summary_age_restricted"',
    '"检测到私有视频或不可公开访问内容"': '"auth_summary_private_video"',
    '"检测到会员专属内容"': '"auth_summary_members_only"',
    '"检测到付费内容"': '"auth_summary_payment_required"',
    '"检测到需要登录后才能访问"': '"auth_summary_login_required"',
    '"检测到访问受限、地区限制或资源不可用问题"': '"auth_summary_forbidden"',
    '"检测到 YouTube JS Challenge / 提取器环境问题"': '"auth_summary_js_challenge"',
    '"检测到机器人校验或异常流量限制"': '"auth_summary_bot_check"',
    '"检测到网络连接或代理环境问题"': '"auth_summary_network"',
    'return "未知"': 'return ""',
    'message = "URL 非法，已阻止解析"': 'message = "metadata_url_invalid"',
    'message = "URL 不能为空"': 'message = "metadata_url_empty"',
    'f"JSON 解析失败: {exc}"': 'f"metadata_json_parse_failed: {exc}"',
}

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

for old, new in replacements.items():
    content = content.replace(old, new)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("done")

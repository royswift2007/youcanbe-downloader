import os

BROWSER_COOKIES_CHOICES = ("chrome", "edge", "firefox")


def build_cookies_args(cookies_mode, cookies_browser, cookies_path):
    mode = (cookies_mode or "file").strip().lower()
    browser = (cookies_browser or "").strip().lower()
    if mode == "browser" and browser in BROWSER_COOKIES_CHOICES:
        return ["--cookies-from-browser", browser]
    if cookies_path and os.path.exists(cookies_path):
        return ["--cookies", cookies_path]
    return []

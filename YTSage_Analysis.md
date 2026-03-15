# YTSage 功能及实现方法技术分析报告

YTSage 是一个基于 **Python (PySide6)** 和 **yt-dlp** 开发的现代化桌面视频下载工具。其核心架构遵循：**PySide6 (GUI) + yt-dlp (下载引擎) + FFmpeg (后处理)**。

---

## 1. 核心下载功能

| 功能项目 | 实现方法 (Implementation Logic) |
| :--- | :--- |
| **多质量视频下载** | 调用 `yt-dlp --list-formats` 获取包含所有流信息的 JSON 字典。根据用户选择，构建参数如 `-f "bestvideo[height<=1080]+bestaudio/best"` 传给下载进程。 |
| **智能音视频合并** | 利用 `yt-dlp` 的自动检测逻辑。只要系统环境变量中有 `ffmpeg`，`yt-dlp` 会在下载完视频流和音频流后自动执行封装命令进行合并。 |
| **音频提取** | 调用 `yt-dlp` 的后处理器。传递参数 `--extract-audio --audio-format [mp3/flac/...] --audio-quality 0`，由 FFmpeg 完成转码。 |
| **视频裁剪下载** | 向 `yt-dlp` 传递 `--download-sections "*00:01:00-00:02:00"`。对于支持的协议（如 HLS）可实现直接下载片段，否则通过下载后调用 `ffmpeg` 剪辑。 |
| **通用模式 (Generic Mode)** | 依赖 `yt-dlp` 内置的数千个 Extractor（提取器）。程序只需将 URL 传给 `YoutubeDL` 类，利用其正则匹配机制自动识别目标网站。 |
| **批量/列表处理** | 使用 `yt-dlp --flat-playlist --dump-single-json` 获取索引。解析 JSON 后在 UI 生成列表供勾选，最后通过循环任务队列依次执行。 |
| **断点续传与速度限制** | 续传通过 `yt-dlp` 默认生成的 `.part` 文件偏移量实现；限速则是向命令注入 `--limit-rate` 参数来控制 socket 吞吐量。 |

---

## 2. 字幕与增强处理

| 功能项目 | 实现方法 (Implementation Logic) |
| :--- | :--- |
| **字幕抓取** | 传递参数 `--write-subs`（上载字幕）或 `--write-auto-subs`（AI 生成字幕）。 |
| **多语言过滤** | 使用参数 `--sub-langs "en.*,zh-Hans"`。通过正则表达式或关键字匹配用户在设置界面选择的语言代码。 |
| **字幕合并/内嵌** | 调用 FFmpeg 后处理器。添加参数 `--embed-subs`，FFmpeg 将字幕文件作为新轨道封装进 MKV/MP4 容器中。 |
| **SponsorBlock 集成** | 调用 `yt-dlp` 内置的第三方 API 接口，传递 `--sponsorblock-remove all`。程序根据云端时间戳自动剔除广告片段。 |
| **章节嵌入** | 传递参数 `--embed-chapters`。从视频元数据提取时间戳信息，利用 `ffmpeg` 的元数据写入功能注入文件。 |

---

## 3. 元数据与附件功能

| 功能项目 | 实现方法 (Implementation Logic) |
| :--- | :--- |
| **封面保存** | 传递参数 `--write-thumbnail`，`yt-dlp` 会下载最高清的图片并重命名为与视频一致的文件名。 |
| **描述文件保存** | 传递参数 `--write-description`，将视频简介抓取并保存为同名的 `.txt` 或 `.description` 文件。 |
| **元数据展示** | 在粘贴链接后异步运行 `yt-dlp --dump-json --skip-download`。获取 JSON 后通过 `Qt Signals` 更新 UI 上的播放量、时长等数据。 |
| **自定义命名** | 利用 `yt-dlp` 的输出模版系统。传递参数如 `-o "%(title)s - %(uploader)s.%(ext)s"`。 |

---

## 4. 高级控制与网络

| 功能项目 | 实现方法 (Implementation Logic) |
| :--- | :--- |
| **Cookie 导入** | 传递参数 `--cookies-from-browser [browser_name]`。`yt-dlp` 会自动定位浏览器本地 SQLite 数据库并读取 Session。 |
| **代理支持** | 通过 Python 设置 `os.environ['HTTPS_PROXY']` 或向 `yt-dlp` 传递 `--proxy` 参数。 |
| **自定义参数** | 在构建最终命令行字符串时，将用户在 UI 文本框输入的额外参数直接拼接在命令末尾。 |
| **强制格式转换** | 使用后处理器参数 `--recode-video mp4`。下载完成后由 `yt-dlp` 调用 `ffmpeg` 进行全片重编码。 |

---

## 5. 系统与维护工具

| 功能项目 | 实现方法 (Implementation Logic) |
| :--- | :--- |
| **跨平台支持** | 使用 `PyInstaller` 或 `Nuitka` 将 Python 环境、PySide6 库及二进制 FFmpeg 打包。 |
| **组件更新程序** | 通过 Python `requests` 访问 GitHub API 获取最新版本号。若有更新，则下载新版二进制文件并覆盖旧文件。 |
| **剪贴板监听** | 利用 PySide6 的 `QClipboard.dataChanged` 信号。匹配到符合 URL 正则的字符串时触发自动填充逻辑。 |
| **多语言界面** | 使用 **Qt Linguist** 系统。通过 `self.tr()` 标记字符串，加载 `.qm` 翻译包实现动态切换。 |

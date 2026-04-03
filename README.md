# YCB (YouCanBe Downloader)

A desktop YouTube downloader and local media toolkit built on `yt-dlp` + `ffmpeg` + (optional) `deno`. It provides single-video downloads, batch downloads (playlist/channel), a download queue, history viewer, media tools, component center, authentication center, runtime status center, and hook extensions.

> PO Token depends on local `Node.js v18+`. If you only use normal downloads, Cookies, or Browser Cookies, Node.js is not required.

- **UI language**: Chinese / English
- **Run modes**: source (Python) or with bundled components
- **Platform**: Windows (this repo ships `.exe` components)

> 中文版说明: [`README_zh.md`](README_zh.md)

> [!IMPORTANT]
> On first launch, go to **Settings → Components** and click **Component Update (yt-dlp/ffmpeg/deno)** first.
> The app depends on these components for downloading and media processing. If they are not present yet, update them before use.

---

## ✨ Features

- **Single video**: YouTube + Generic URL download
- **Batch**: playlists / channels with bulk selection
- **Batch manual policy**: sample-based rules with preset1 / preset2 / final fallback
- **Download presets**: best quality / best compatibility / max 1080p / max 4K / audio only / smallest size / HDR / high FPS / manual format
- **Format table & filters**: parse and filter YouTube formats
- **Queue management**: start all / start / retry / stop / delete / clear completed
- **History**: view / refresh / clear
- **Media tools**: remux, extract audio, trim, concat, burn subtitles, scale, crop, rotate, watermark, loudnorm
- **Auth center**: Cookies / Browser Cookies / PO Token
- **Component center**: yt-dlp / ffmpeg / deno version checks
- **Runtime center**: queue stats / DB status / error summaries
- **Hook extensions**: custom script hooks (see `core/hooks.py`)

---

## 📦 Run

### Option A: Run from source (for developers)

1. Install Python 3.10+ (3.10/3.11 recommended)
2. Install deps:

```bash
pip install -r requirements.txt
```

3. Run:

```bash
python YCB.pyw
```

> On Windows, `YCB.pyw` runs without a console window.

### Option B: Run with bundled components (for users)

Ensure these are placed next to the app:

- `yt-dlp.exe`
- `ffmpeg.exe`
- `deno.exe` (optional)

The app auto-detects and loads them.

---

## 🧭 Core Workflows

### 1) Single video (YouTube / Generic)

1. Select mode:
   - **YouTube**: YouTube-only, includes format parsing
   - **Generic**: any http/https URL, no format list
2. Paste URL
3. Choose action:
   - **Get formats** (YouTube only)
   - **Direct download** (auto preset; audio-only can now start directly with the audio preset)
   - **Add to queue**
4. Start from Queue tab

### 2) Batch (Playlist / Channel)

1. Paste URL → fetch entries
2. Filter/select items
3. Set preset and output options
   - Video output now supports `mp4 / mkv / webm`
   - You can enable **Manual Settings** and build batch rules from a sample video
4. Add to queue → start

---

## ⚙️ Settings Highlights

- **Clipboard watcher**: auto detect YouTube URLs
- **Auto parse**: auto fetch formats after detection
- **Cookies mode**: `file` / `browser`
- **Browser Cookies**: Chrome / Edge / Firefox
- **Language**: Chinese / English

Quick entries: Auth status / History / Components / Runtime / Usage

---

## 🎯 Download Presets

| Preset | Description | yt-dlp format |
|------|------|----------------|
| Best quality | highest video+audio | `bestvideo*+bestaudio/best` |
| Best compatibility | 1080p MP4 max | `bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]` |
| Max 1080p | capped at 1080p | `bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]` |
| Max 4K | capped at 4K | `bestvideo[height<=2160]+bestaudio/best[height<=2160]` |
| Audio only | audio-only | `bestaudio[ext=m4a]/bestaudio` |
| Smallest size | smaller downloads | `best[height<=480]/worst` |
| Keep original | keep original codecs | `bestvideo+bestaudio/best` |
| HDR priority | HDR formats first | `bestvideo[dynamic_range=HDR]+bestaudio/best` |
| High FPS | prefer 50fps+ | `bestvideo[fps>=50]+bestaudio/best` |
| Manual format | pick a format ID | from format table |

### Batch Manual Policy

- Entry: **Enable Manual** + **Manual Settings** on the batch page
- You can fetch formats from one sample video first, then apply rule-based matching to the full batch
- Current support:
  - Preset 1
  - Preset 2 (optional)
  - Final fallback chain (optional)
- Current rule dimensions:
  - Height
  - Codec preference: `h264 / av1 / vp9`
  - Video stream container preference: `mp4 / webm`
  - Audio mode: `default / no_audio`
- Fallback order:
  - same height
  - higher available
  - lower available
  - finally `bestvideo/best`
- Detailed usage notes:
  - Scope: this applies to the batch page for playlist/channel downloads only. It does not replace the single-video page's direct manual `format_id` selection flow.
  - Sample URL: used to inspect one representative video's formats so the rule UI can be built. It does not copy one fixed `format_id` to every task.
  - Use Selected Sample: fills the sample URL from the current batch selection, but you still need to click **Fetch Formats**.
  - Fetch Formats: required before saving; it refreshes the available height / codec / container options. If the sample URL changes, the old format cache becomes invalid immediately.
  - Preset 1: the required first-layer rule. At least one video constraint must be set; leaving height, codec, and container all as `Any` is invalid.
  - Preset 2: optional second-layer rule that is tried only after preset1 misses. In practice it should usually be looser than preset1.
  - Final fallback chain: optional last-resort rule. If preset2 is enabled, the fallback expands from preset2; otherwise it expands from preset1.
  - Height: target video height for the rule layer. With fallback enabled, the resolver tries same height first, then higher, then lower.
  - Codec preference: `h264 / av1 / vp9`. This is a preference order, not a strict one-codec lock. The preferred codec is tried first, then other supported codecs.
  - Video stream container preference: `mp4 / webm`. This is the source video stream preference, not the batch page's final output container.
  - Audio mode: `default` appends `+bestaudio`; `no_audio` keeps the rule video-only.
  - Important distinction: the batch page's top-level output format controls the final packaging target, while manual policy container preference controls which source video streams are preferred during selection.
  - Recommended setup: put the ideal target in preset1, the more tolerant target in preset2, and enable the final fallback chain when playlist/channel items vary a lot.
  - Current limits: advanced audio selection by bitrate/extension is not exposed yet, and the exact final `format_id` is only known at runtime from the yt-dlp logs.

---

## 📑 Subtitles & Post-processing

- **Subtitle modes**: `none` / `manual` / `auto` / `both`
- **Subtitle formats**: `srt` / `vtt` / `ass`
- **Post-processing**: embed cover, metadata, description, chapters, H.264 compat, SponsorBlock, PO Token

---

## 🧰 Media Tools

| Type | Description |
|------|-------------|
| remux | container remux (no re-encode) |
| extract_audio | extract audio |
| trim | clip by time range |
| concat | concat multiple files |
| burn_subtitle | burn subtitles into video |
| scale | scale |
| crop | crop |
| rotate | rotate |
| watermark | watermark |
| loudnorm | loudness normalization |

---

## 🔐 Authentication & Security

- **Cookies file**: default `www.youtube.com_cookies.txt` (Netscape format)
- **Browser Cookies**: Chrome / Edge / Firefox
- **PO Token**: requires Node.js (>=16 recommended)

---

## 🧩 Components

- **yt-dlp**: version check / one-click update
- **ffmpeg**: version check
- **deno**: version check

---

## 🧾 License

This project uses **GPLv3 + Commons Clause** (non-commercial). See [`LICENSE`](LICENSE).

---

## 📌 Notes

- Queue refresh now tries to preserve the current selection; selected rows keep the same light-blue background and use bold text.
- The old queue button label `Retry Selected` is now `Start / Retry`.
- For the full parameter list and detailed guidance, see [`usage_intro_en.md`](usage_intro_en.md) (this README is a compact version).
- If you distribute binaries, ship the source and license file together.

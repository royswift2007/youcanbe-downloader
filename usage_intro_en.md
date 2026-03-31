# YouTube Downloader: In-Depth User Guide and Feature Manual

This application is built on `yt-dlp` + `ffmpeg` + optional `deno`. It supports single-video downloads, batch downloads (playlists/channels), download queue management, history viewing, media tools, a components center, an authentication status center, a runtime status center, Hook extensions, and more. This manual reflects the current code implementation and explains default values, valid ranges, and usage methods item by item.

> [!IMPORTANT]
> Before first use or on first launch, go to **Settings -> Components Center** and click **Component Update (yt-dlp/ffmpeg/deno)**.
> The program depends on these components for downloading and processing. If they are not available locally yet, update them before using the app.

---

## 0. Installation and Running Permissions

> [!CAUTION]
> If you install the program in system-protected directories such as **`C:\Program Files`** or **`C:\Program Files (x86)`**:
> 1. **Permission Requirements**: The program needs to generate logs (`logs/`), save download history (`download_history_ytdlp.json`), and store configuration files (`window_pos.json`) during operation. Normal read/write access to these files is essential for stability.
> 2. **Auto-Authorization**: When using the official `.exe` installer, the setup process automatically grants the necessary read/write permissions to the installation directory.
> 3. **Manual Migration**: If you manually extract the program from a ZIP file or move the installation folder later, ensure the current user has **Full Control** over the folder. Otherwise, you may encounter "Access is denied" errors or find that settings/history are not saved.

---

## 1. Core Workflow

### 1.0 Feature Overview

The current version already covers the following major functional areas:

| No. | Feature Description |
|-----|---------------------|
| 1 | **Single Video Download**: Supports both YouTube and Generic modes, with auto strategy, manual format selection, direct download, queueing, subtitles, post-processing, proxy, Cookies, section download, and more. |
| 2 | **Batch Download**: Supports playlist/channel entry parsing, entry filtering, unified batch parameters, batch manual strategy, and batch queueing. |
| 3 | **Download Queue**: Supports task queueing, start/retry, stop selected, stop all, delete selected, clear completed, and real-time logs. |
| 4 | **History**: Supports viewing summaries of completed/failed tasks, with manual refresh and clear actions. |
| 5 | **Authentication Status Center**: View Cookies file status, Browser Cookies, PO Token status, recent authentication diagnostics, and suggested actions. |
| 6 | **Runtime Status Center**: View current task overview, history database status, and recent runtime issue summaries/details. |
| 7 | **Components Center**: View the status, path, and version of `yt-dlp / ffmpeg / deno`, and run one-click updates or export diagnostics. |
| 8 | **Media Tools**: Run local media processing tasks such as audio extraction, trimming, concatenation, subtitle burn-in, scaling, cropping, rotation, watermarking, loudness normalization, and more. |
| 9 | **Global Settings**: Manage language, clipboard watch, auto-parse, Cookies mode, save directory, concurrency, speed limits, retries, and other global parameters. |
| 10 | **Extension Capabilities**: Supports Hooks, runtime diagnostics, log highlighting, advanced-argument allowlist control, failed-task summaries, and more. |

> If this is your first time using the app, it is recommended to learn it in this order: **component preparation -> settings check -> single-task validation -> batch usage -> media tools**.

### Single-Video Download Flow (YouTube / Generic)

1. **Choose a mode**:
   - **YouTube mode**: Only supports YouTube links and allows fetching the format list and manual format selection.
   - **Generic mode**: Supports any valid `http/https` link with a domain, but does not provide a YouTube-style format list.

2. **Enter a URL**:
   - Supported YouTube URL examples:
     - `https://www.youtube.com/watch?v=xxxxx`
     - `https://youtu.be/xxxxx`
     - `https://www.youtube.com/embed/xxxxx`
   - Generic mode supports any `http/https` URL that includes a valid domain.

3. **Fetch video information**:
   - **Fetch Resolutions / Formats**: Available only in YouTube mode. Parses all supported formats/combinations for the video and displays them in a table for filtering and manual selection.
   - **Direct Download**: Downloads immediately without manual format selection, using the selected download strategy.

4. **Add to queue**:
   - Click **Add to Queue** to send the task into the download queue and wait for manual start or batch start.

5. **Start downloading**:
   - On the **Download Queue** page, click **Start All**, or select one task and use **Start / Retry**.

**Updates in this version**
- The **Audio Only** preset can now be started directly through **Direct Download** without requiring manual audio format selection first.
- The single-video **Audio Only** path now follows the audio-extraction workflow so audio tasks are no longer mistakenly sent through the video-merge flow.

---

### Batch Download Flow (Playlist / Channel)

1. **Enter a URL and fetch entries**:
   - Paste a playlist or channel URL, then click **Fetch Entries**.

2. **Filter and select**:
   - Supports **Select All / Clear All / Keep Available Only**.
   - Supports **Hide Unavailable / Shorts Only**.

3. **Set batch download parameters**:
   - Apply a unified download strategy, output format, subtitles/post-processing, concurrency/speed limits, throttling, proxy, and more.

4. **Add selected tasks**:
   - Click **Add Selected Tasks** to send them to the download queue.

**Updates in this version**
- The batch page now supports `mp4 / mkv / webm` as video output formats.
- The batch page now includes **Enable Manual** and **Manual Settings**, which can generate rule-based `-f` expressions for the entire batch based on the actual formats of a sample video.
- The batch manual strategy supports Preset 1, Preset 2, and an optional **Final Fallback Chain**.

---

## 2. Basic Settings and Performance Tuning (Global Settings Page)

### Settings Page

#### 2.1 Page Settings (Toggles)

| Feature | Default | Description | How to Use |
|--------|---------|-------------|------------|
| Clipboard Watch | Off | Polls the clipboard and auto-fills the input box when a YouTube link is detected | Enable the toggle in the settings page or top area |
| Auto Parse | Off | Automatically runs **Fetch Resolutions / Formats** after clipboard watch is triggered (YouTube mode only) | After enabling it, copying a YouTube URL will auto-parse it |

#### 2.2 Cookies Mode

| Parameter | Default | Range | Description | How to Use |
|----------|---------|-------|-------------|------------|
| Cookies Mode | `file` | `file` / `browser` | `file` uses a local Cookies file; `browser` reads Cookies directly from the browser | Select it in the settings page or top area |
| Browser Cookies Browser | Empty | `chrome` / `edge` / `firefox` | Takes effect only when Cookies mode is `browser` | After selecting a browser, the setting is synchronized to each download page |

> Note: If the mode is `browser` but no browser is selected, it falls back to `file`.

#### 2.3 Language Switching

| Parameter | Default | Range | Description | How to Use |
|----------|---------|-------|-------------|------------|
| Language | Chinese | `Chinese` / `English` | Switching language rebuilds the UI without requiring a restart | Select it on the settings page |

#### 2.4 Quick Access

| Entry | Function | Description |
|------|----------|-------------|
| Auth Status | Open the Authentication Status Center | View Cookies/PO Token status and suggested actions |
| History | Open the history window | Show the history list in text form |
| Components Center | Open the Components Center | View `yt-dlp / ffmpeg / deno` versions and status |
| Runtime Status | Open the Runtime Status Center | View task queue status, database status, and recent runtime issues |
| Guide | Open this manual | Displays the content of this file |

**Additional Notes**
- These entries are essentially status/instruction helper windows and are ideal for inspection, troubleshooting, and review outside the main workflow.
- If the program launches but you do not know where the problem is, the recommended inspection order is usually: `Components Center -> Authentication Status Center -> Runtime Status Center -> Download Queue Logs`.
- **History** and **Guide** are more view-oriented windows, while **Auth Status / Runtime Status / Components Center** are more diagnostic-oriented.
- The entries in the top area and the settings page point to the same type of functionality; they simply offer different access points.

> On first launch, the program directory may not yet contain `yt-dlp.exe / ffmpeg.exe / deno.exe`.
> Please go to **Settings -> Components Center** and click **Component Update (yt-dlp/ffmpeg/deno)**. The program will download and install them automatically into the root directory, and progress will be shown during the download.

#### 2.5 Storage and Performance

| Parameter | Default | Range | Description |
|----------|---------|-------|-------------|
| Save Path | `~/Downloads` | User-selected | Default directory where downloaded files are saved |
| Retries | `3` | `0 - 10` | Automatically retries when the network is unstable; `0` means no retries |
| Concurrency | `2` | `1 - 10` | `2 - 4` is recommended; values that are too high may increase the chance of site anti-abuse triggers |
| Speed Limit (MB/s) | `2` | `0 - 100` | Per-task speed limit; `0` means unlimited |

**Additional Notes**
- The settings page values for concurrency, retries, and speed limit are used as initialization values for each download page. The single-video page and batch page can still adjust them separately.
- The save path affects the default output directory of download tasks, the displayed paths in history, and the behavior of the **Open Directory** button.
- If tasks are already running, changing these parameters usually affects only newly created tasks. Whether queued tasks pick up new values immediately depends on the configuration saved when each task was enqueued.
- For YouTube, higher concurrency and more aggressive throttling adjustments are more likely to trigger anti-abuse checks. Prioritize success rate over blindly increasing speed.

---

## 3. Single-Video Page Parameters (YouTube / Generic)

### 3.1 Mode and URL

| Parameter | Default | Range | Description |
|----------|---------|-------|-------------|
| Mode | `youtube` | `youtube` / `generic` | YouTube mode can fetch formats; Generic mode is for general downloading |
| Video URL | Empty | Valid URL | YouTube mode supports only `youtube.com` / `youtu.be` links; Generic supports any `http/https` URL |

**Buttons and Actions**:
- **Fetch Resolutions / Formats**: Available only in YouTube mode; parses the format table.
- **Direct Download**: Starts downloading directly according to the selected strategy.
- **Add to Queue**: Adds the task to the download queue for later unified start.

**Additional Notes**
- The URL input box on the single-video page is currently two lines high, which makes it easier to paste long URLs, parameterized URLs, or temporarily organized multi-line content.
- In YouTube mode, if the link is not from a standard YouTube domain, the UI will directly block format fetching and queueing.
- In Generic mode, **Fetch Resolutions / Formats** is disabled because generic sites usually cannot provide a stable unified format table.
- When clipboard watch and auto-parse are enabled, copying a YouTube link can automatically fill this area and reduce manual paste steps.

### 3.2 Video Info Card

| Field | Description |
|------|-------------|
| Title | Displays the video title after parsing |
| Metadata | ID / Channel / Duration / Views / Upload / Language |

**Additional Notes**
- In YouTube mode, clicking **Fetch Resolutions / Formats** usually refreshes the title and metadata here first, then updates the format table below.
- If this area still shows **Video not parsed yet** or placeholder metadata, the link has not successfully completed metadata retrieval.
- Once a title has been successfully fetched, and if you did not manually fill in **Rename**, queued tasks will prefer the parsed video title here instead of a simple preset-based name.
- In Generic mode, this section mainly acts as a title placeholder and status feedback area. The completeness of information depends on whether the target site supports metadata parsing.

### 3.3 Download Strategy (Presets)

| Preset | Description | Actual Format (`yt-dlp`) |
|------|-------------|--------------------------|
| Best Quality | Highest available video and audio quality combination | `bestvideo*+bestaudio/best` |
| Best Compatibility | Strongest compatibility (up to 1080p MP4) | `bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]` |
| Max 1080p | Limits the highest resolution to 1080p | `bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]` |
| Max 4K | Limits the highest resolution to 4K | `bestvideo[height<=2160]+bestaudio/best[height<=2160]` |
| Audio Only | Downloads audio only | `bestaudio[ext=m4a]/bestaudio` |
| Minimum Size | Smaller output size | `best[height<=480]/worst` |
| Keep Original Codec | Preserve the original codec combination | `bestvideo+bestaudio/best` |
| HDR First | Prioritize HDR | `bestvideo[dynamic_range=HDR]+bestaudio/best` |
| High Frame Rate First | Prioritize 50fps+ | `bestvideo[fps>=50]+bestaudio/best` |
| Manually Select Format | Manually choose a format ID | Determined by table selection / double-click |

**Updates in this version**
- The **Audio Only** preset can now be used directly in the **Direct Download** path and no longer requires manual format selection first.

### 3.4 Output Format and Manual Format

| Parameter | Default | Range | Description |
|----------|---------|-------|-------------|
| Output Format | `mp4` | `mp4` / `mkv` / `m4a` / `mp3` / `opus` / `wav` / `flac` | Changes with the strategy; audio strategies use audio formats |
| Manual Format | Not selected | From the format table | Takes effect only when **Manually Select Format** is used or after double-clicking a format row |

**Additional Notes**
- Common output formats for video-oriented presets are `mp4 / mkv`.
- Common output formats for the **Audio Only** preset are `m4a / mp3 / opus / wav / flac`.
- If you manually specify a `format_id` that includes video, the final output is still constrained by the selected streams and post-processing capability.

### 3.5 Format Fetching and Filtering (YouTube Mode Only)

| Filter | Default | Description |
|-------|---------|-------------|
| MP4 Only | Off | Show only `mp4` container formats |
| With Audio Only | Off | Show only formats that contain an audio stream |
| 60fps Only | Off | Show only formats with `fps >= 50` |
| 4K+ Only | Off | Show only formats with resolution `>= 2160p` |
| Audio Tracks Only | Off | Show audio-stream formats only |

| Sort | Default | Range | Description |
|------|---------|-------|-------------|
| Sort Mode | `quality_desc` | `quality_desc` / `quality_asc` / `size_desc` / `size_asc` | Sort by quality or size (only for parsed formats) |

**Format Table Columns**: `format_id` / `ext` / `resolution` / `fps` / `vcodec` / `acodec` / `protocol` / `filesize` / `dynamic_range` / `note`.

**Additional Notes**
- Table headers are currently left-aligned to make it easier to scan different column names quickly.
- The **Fetch Resolutions / Formats** button no longer uses a raised shadow effect, making it look more consistent with other page buttons.
- The format table supports horizontal scrolling, which is useful for viewing longer columns such as `note`, `dynamic_range`, and `protocol`.
- The `note` field often contains combinations like **video only / audio only / with audio / merge required / HDR / fps**, which can be very useful when choosing formats manually.
- If you just want a quick download, you usually do not need manual format selection. Presets should be your first choice.

> Tip: Double-click a row in the format table to quickly select that manual format.

### 3.6 Audio Export / Rename / Preview

| Parameter | Default | Range | Description |
|----------|---------|-------|-------------|
| Audio Quality (k) | `192` | `128` / `192` / `256` / `320` | Effective only when transcoding to `mp3 / opus / wav / flac` |
| Rename | Empty | Text | If left empty, a name is generated automatically from the webpage/title |
| Name Preview | Auto-generated | - | Preview of the final output filename |

**Additional Notes**
- Custom filenames are validated: they cannot contain Windows-forbidden characters and cannot end with a space or a dot.
- **Name Preview** refreshes in real time when the title, output format, or custom filename changes, so you can confirm the final filename before queueing.
- If left empty, the program first tries to use the webpage title. If the title was not fetched successfully either, it falls back to a preset-based default name.
- The audio quality parameter mainly matters when audio transcoding is needed. If you are just downloading the original audio stream, the result is still limited by the source site's original audio track.

### 3.7 Network and Advanced Parameters

| Parameter | Default | Range | Description |
|----------|---------|-------|-------------|
| Proxy | Empty | Any protocol URL | Must include a protocol prefix such as `http://` or `socks5://` |
| Cookies Mode | `file` | `file` / `browser` | Synchronized with global settings |
| Browser Cookies | Empty | `chrome` / `edge` / `firefox` | Effective only in `browser` mode |
| Advanced Arguments | Empty | Allowlisted arguments only | Only safe arguments are allowed; see **Advanced Arguments** section |

**Additional Notes**
- The proxy address must be written as a complete URL. If the protocol prefix is missing, the program will reject it immediately as invalid.
- In `browser` mode, if no browser is selected, the program will try to fall back to a safer default behavior to avoid creating invalid tasks.
- Advanced arguments are not an unrestricted command-line passthrough. They are constrained by an allowlist. Core parameters such as `--format`, `--proxy`, `--cookies`, and `--download-sections` cannot be overridden.
- If you have already set proxy, Cookies, sections, subtitles, or other primary parameters in the page UI, you usually do not need to repeat them through advanced arguments.

### 3.8 Section Download

| Parameter | Default | Range | Description |
|----------|---------|-------|-------------|
| Section Download | Empty | `HH:MM:SS-MM:SS` / `MM:SS-MM:SS` | Example: `00:01:00-00:03:30` |

**Additional Notes**
- This is suitable for downloading only a small part of a long video, such as a livestream segment, a lesson excerpt, or a sample clip.
- If the section format is written incorrectly, the task is blocked before queueing instead of failing later at runtime.
- The current program includes a **section download fallback**: if the site's native section download is unstable, the program may first download the full file and then trim the target segment locally with `ffmpeg`.
- Because of that local trimming fallback, section-download tasks may use more disk space and take more time than normal tasks in some scenarios.

### 3.9 Subtitle Settings

| Parameter | Default | Range | Description |
|----------|---------|-------|-------------|
| Subtitle Mode | `none` | `none` / `manual` / `auto` / `both` | Manual / automatic / both |
| Subtitle Languages | Empty | Determined by `yt-dlp` | Example: `zh,en`; supports multiple languages |
| Subtitle Format | Empty | Determined by `yt-dlp` | Example: `srt` / `vtt` / `ass` |
| Write External Subtitles | On | Toggle | Output separate subtitle files |
| Embed Subtitles | Off | Toggle | Mux subtitles into the video file (`mkv` is more reliable) |

**Additional Notes**
- `manual` usually means regular human-made subtitles, `auto` means auto-generated subtitles, and `both` tries both types.
- Multiple languages are typically separated by commas, for example `zh,en,ja`. Whether they can be matched depends on which subtitle tracks the site actually provides.
- **Write External Subtitles** and **Embed Subtitles** can be enabled at the same time: one keeps separate subtitle files, and the other writes subtitles into the media container.
- **Embed Subtitles** is usually more compatible in an `mkv` container. In `mp4`, stable embedding still depends on the original subtitle format and the `ffmpeg` processing chain.
- If the source video has no subtitles at all, enabling these options will not magically create them; the logs usually tell you that no subtitle tracks are available.

### 3.10 Post-Processing

| Parameter | Default | Description |
|----------|---------|-------------|
| Embed Thumbnail | On | Embed the thumbnail into the video file |
| Embed Metadata | On | Write metadata such as title / author / description |
| Write Thumbnail File | Off | Save the cover image as a separate file |
| Write Info JSON | Off | Save metadata as a JSON file |
| Write Description | Off | Save the description text |
| Write Chapters | Off | Write chapter information |
| Keep Intermediate Video | Off | Do not delete temporary stream files after merging |
| H.264 Compatibility Mode | Off | Force transcoding to H.264 (takes extra time) |
| SponsorBlock | Off | Remove specified segment categories (default is `sponsor`, customizable) |
| Enable PO Token | Off | Inject a PO Token for YouTube (requires Node.js) |

**Additional Notes**
- **Embed Thumbnail** and **Embed Metadata** are enabled by default, which is suitable if you want the final download to be closer to a polished finished file.
- **Keep Intermediate Video** is useful for troubleshooting merge failures, transcode failures, or cases where you want to preserve the original stream files. Leaving it off saves disk space.
- **H.264 Compatibility Mode** introduces a transcoding step, which usually takes longer, uses more CPU, and may produce extra temporary files. Only enable it when device compatibility is important.
- The SponsorBlock field defaults to `sponsor`. You can also enter multiple categories supported by `yt-dlp`, but small-scale testing is recommended first.
- **Enable PO Token** only helps in some YouTube extraction scenarios. It is not required for all videos. If regular public videos download normally, you usually do not need to leave it enabled all the time.

### 3.11 Download Control

| Parameter | Default | Range | Description |
|----------|---------|-------|-------------|
| Retries | `3` | `0 - 10` | `0` means no retries |
| Concurrency | `1` | `1 - 10` | Single-video page concurrency affects queue scheduling |
| Speed Limit (MB/s) | `2` | `0 - 100` | `0` means unlimited (per task) |

**Additional Notes**
- The **Concurrency** setting on the single-video page is not just an internal sub-thread concept for one URL. It affects the download manager's concurrent scheduling limit for queued tasks.
- **Retries** are better suited for network jitter, temporary site errors, or broken connections. If the issue is bad parameters or invalid authentication state, repeated retries usually do not help.
- `Speed Limit = 0` means unlimited, but that does not always mean the highest real efficiency. Disk, network, and site anti-abuse systems may become the next bottlenecks.
- When you have multiple tasks piled up in the queue, it is better to tune concurrency and speed limit together instead of maxing out only one of them.

### 3.12 Recommended Usage Order for the Single-Video Page

If this is your first time using the single-video page, this order is recommended:

1. Confirm whether the current mode is `YouTube` or `Generic`.
2. Paste the URL and first check whether the **Video Info Card** can be parsed normally.
3. If you only need a normal download, choose a preset first instead of jumping straight into manual formats.
4. If you explicitly need a specific resolution or codec, click **Fetch Resolutions / Formats** and narrow the results with filters.
5. Check **Name Preview** and **Download Summary** to confirm that the output format, post-processing, subtitles, and naming are correct.
6. Finally decide whether to use **Direct Download** or **Add to Queue**.

The benefit of this order is that most parameter issues can be exposed before the actual download starts, reducing the chance of discovering configuration mistakes only after queueing.

---

## 4. Batch Page Parameters (Playlist / Channel)

### 4.1 URL / Parsing / Filters and Table

**Buttons and Actions**:
- **Parse Batch Entries**: Parse playlist/channel entries.
- **Select All / Select None / Keep Available Only**: Bulk-select entries.
- **Add Selected to Queue**: Add the checked entries to the download queue.

| Parameter | Default | Range | Description |
|----------|---------|-------|-------------|
| Source Type | `auto` | `auto` / `playlist` / `channel` | Used as a hint for the parsing mode |
| Hide Unavailable | Off | On / Off | Hide entries that cannot be downloaded |
| Shorts Only | Off | On / Off | Show only Shorts |

**Table Columns**: Select / No. / Title / Channel / Duration / Views / Upload Date / Availability / Shorts / URL.

**Additional Notes**
- After parsing succeeds, the top of the batch page also refreshes **Source Title / Source Info / Total Entry Count**, making it easier to confirm whether this is the playlist or channel you actually wanted.
- **Keep Available Only** is useful for quickly removing inaccessible entries from large lists and reducing queue noise later.
- **Shorts Only** is more suitable for organizing short-video materials in bulk. If it is not enabled, Shorts and regular videos are shown together.
- The checked state on the batch page directly determines the range used by **Add Selected Tasks**, so the recommended order is filter first, then check items, then enqueue them together.

### 4.2 Download Strategy and Output

| Parameter | Default | Range | Description |
|----------|---------|-------|-------------|
| Download Strategy | `best_compat` | `best_quality / best_compat / max_1080p / max_4k / audio_only / min_size` | Unified strategy for the whole batch |
| Output Format | `mp4` | `mp4` / `mkv` / `webm` (or `m4a / mp3 / opus / wav / flac` for audio-only strategy) | Changes automatically according to the selected strategy |
| Audio Quality | `192` | `128` / `192` / `256` / `320` | Effective only for audio-only strategy |
| Custom Prefix | Empty | Text | Used as a prefix when generating filenames in batch mode |

**Additional Notes**
- These parameters on the batch page are copied to all currently checked tasks when **Add Selected Tasks** is executed, so it is best to confirm them all before queueing.
- **Audio Quality** is mainly meaningful in audio transcoding scenarios. If the final result is the original audio track, it may not strictly match the bitrate value you entered.
- **Custom Prefix** is useful for adding a shared label to the whole batch, such as a course name, project code, or date batch.
- When the manual batch strategy is enabled, the effective download expression is determined by the manual rules rather than the standard preset selector.
- `webm` output is now supported on the batch page.
- `webm` output and **H.264 Compatibility Mode** should not be enabled together; the UI blocks obviously conflicting combinations from entering the queue.

### 4.3 Batch Manual Strategy

**Entry**
- Check `Enable Manual`
- Click `Manual Settings`

**Basic Flow**
1. Choose a sample video URL, or directly take one sample from the currently selected entries.
2. Click **Fetch Formats** to read the available format set of that sample video.
3. Configure Preset 1.
4. If needed, enable and configure Preset 2.
5. If needed, enable the **Final Fallback Chain**.
6. Save the strategy and then enqueue the batch tasks.

**Currently Supported Rule Dimensions**
- Height
- Codec preference: `h264 / av1 / vp9`
- Video stream container preference: `mp4 / webm`
- Audio mode: `default / no_audio`

**Currently Supported Layers**
- Preset 1
- Preset 2 (optional)
- Final Fallback Chain (optional)

**Final Fallback Chain Order**
1. First try an available format with the same target height.
2. If there is no match, continue trying higher available formats.
3. If there is still no match, continue trying lower available formats.
4. Finally fall back to generic `bestvideo/best`.

**Usage Notes**
- This batch manual strategy is rule matching, not pre-locking every task to one fixed `format_id`.
- The actual hit still depends on the real formats available to `yt-dlp` for that specific video.
- After manual strategy is enabled, the task summary shows the `manual` path instead of the previous preset name.

**Current Limitations**
- Advanced audio filtering is still mainly limited to `default / no_audio`. Finer rules such as audio bitrate or audio format preferences are not yet exposed in the UI.
- The UI does not currently show, item by item in advance, which exact format ID will finally be matched. The real result should be confirmed from runtime download logs.
- If the sample URL changes, you must fetch the sample formats again before saving the strategy.

**Detailed Parameter Notes**

1. `Sample URL`
   - Purpose: Used only to read the available formats of one representative video so you can build rules. It does not mean one video's exact formats are forcibly copied to the entire batch.
   - Recommendation: Choose a sample video that is close to your target batch content, has a relatively complete format set, and plays normally.
   - Effect: After the sample is fetched successfully, the available options for height, codec, and video-stream container in the UI are refreshed based on the sample's real formats.
   - Note: Once the sample URL changes, the previous sample format set becomes invalid immediately, and you must click **Fetch Formats** again.

2. `Use Selected Sample`
   - Purpose: Quickly take one URL from the currently checked/selected batch entries and place it into the sample box.
   - Note: This button only fills in the URL. It does not fetch formats automatically. After filling it in, you still need to click **Fetch Formats**.

3. `Fetch Formats`
   - Purpose: Calls the current sample video, reads its format set, and uses it as the candidate data source for the manual-rule UI.
   - Result: After success, the dropdown lists are updated to the actual heights, codecs, and video-stream containers found in the sample.
   - Failure handling: If the sample video is inaccessible, the network fails, site anti-abuse is triggered, or `yt-dlp` cannot parse it, the manual strategy cannot be saved.

4. `Preset 1`
   - Role: This is the first rule layer and the primary rule after manual strategy is enabled.
   - Required: If **Enable Manual** is checked, Preset 1 must be valid.
   - Validation rule: Preset 1 must specify at least one video condition. In other words, at least one of **height / codec / video-stream container** must be selected; leaving all of them as **Any** cannot be saved.
   - Recommendation: Set Preset 1 to your most desired target spec, for example `1080p + h264 + mp4 + default merged audio`.

5. `Preset 2`
   - Role: The second rule layer. It is used only if Preset 1 does not match.
   - Required or not: Optional. It participates in matching only when **Enable Preset 2** is checked.
   - Validation rule: Once Preset 2 is enabled, it must also contain at least one video condition.
   - Recommendation: Preset 2 should be looser than Preset 1 rather than stricter. A common approach is to lower the target height or relax the codec preference.

6. `Enable Final Fallback Chain`
   - Role: If both Preset 1 and Preset 2 fail to match, append one broader closing rule.
   - Base source: If Preset 2 is enabled, the fallback chain is expanded from Preset 2. Otherwise, it is expanded from Preset 1.
   - Suitable scenario: If your batch source is mixed and different videos vary greatly in their available formats, enabling it is recommended.
   - Boundary of effect: The fallback chain only relaxes the height matching method. It does not switch the preferred video-stream container to a different container.

7. `Height`
   - Meaning: Target video-stream height, commonly `2160 / 1440 / 1080 / 720 / 480`.
   - Behavior in Preset 1 / Preset 2: This is the target-height condition. If set to `1080`, that layer tries `height=1080` first.
   - Behavior in the fallback chain: If the fallback chain is enabled, it further expands using the order **same height -> higher -> lower -> generic `bestvideo/best`**.
   - Set to `Any`: Means that layer does not restrict height.

8. `Codec`
   - Currently supported: `h264 / av1 / vp9`.
   - Semantics: This is a **codec preference**, not an absolute hard restriction.
   - Current implementation: If you choose `vp9`, the rule tries `vp9` first and then other codecs in an internal order, so it behaves more like a priority list than a hard lock.
   - Selection advice:
     - `h264`: Best compatibility, suitable for general devices and post-editing.
     - `vp9`: Common on the `webm` path, suitable if you want to stay closer to newer web-stream specs.
     - `av1`: Usually better in size/quality ratio, but not all videos provide it.

9. `Video Stream Container`
   - Currently supported: `mp4 / webm`.
   - Semantics: This is the **preferred source video-stream container**, not the **final output format** at the top of the batch page.
   - Important difference:
     - This option controls whether `yt-dlp` prefers `mp4` or `webm` video streams when selecting a source stream.
     - The **Output Format** on the main batch page controls the final packaging direction after download, such as `mp4 / mkv / webm`.
   - Recommendation:
     - If compatibility is your priority, `mp4` is usually the better choice.
     - If you want to stay as close as possible to `vp9/webm` web resources, choose `webm`.

10. `Audio`
   - Currently supported: `default merged audio` and `no audio`.
   - `default merged audio`: Adds `+bestaudio` to the video rule for that layer, suitable for normal video downloads.
   - `no audio`: Downloads only the video stream for that layer and does not merge audio.
   - Current limitation: It does not yet support manually specifying an audio extension, audio bitrate, or standalone audio format ID here.

**Rule Matching Order**
- The overall order is always: `Preset 1 -> Preset 2 (if enabled) -> Final Fallback Chain (if enabled)`.
- Inside each preset layer, the codec preference generates an ordered candidate chain rather than a single expression.
- If the final fallback chain is enabled:
  - With a target height: it tries `same height -> higher available -> lower available -> bestvideo/best`.
  - Without a target height: it starts from the current container/codec preference chain and then falls back to `bestvideo/best`.
- Which part is actually matched is still ultimately determined by the real available formats reported by `yt-dlp` for that video at runtime.

**Recommended Configuration Patterns**

1. `General Compatibility`
   - Preset 1: `1080 + h264 + mp4 + default merged audio`
   - Preset 2: `720 + h264 + mp4 + default merged audio`
   - Final Fallback Chain: Enabled
   - Suitable for: Mixed playlists where you want better success rate and compatibility first.

2. `Web Stream First`
   - Batch output format: `webm`
   - Preset 1: `1080 + vp9 + webm + default merged audio`
   - Preset 2: `720 + webm + default merged audio`
   - Final Fallback Chain: Enabled
   - Suitable for: Cases where you want to stay on the `webm / vp9` route as much as possible.

3. `Silent Asset Type`
   - Preset 1: `1080 + mp4 + no audio`
   - Preset 2: `720 + mp4 + no audio`
   - Final Fallback Chain: Enable as needed
   - Suitable for: Asset collection or secondary processing where you only need the picture and do not need the audio track.

**Notes for Saving and Queueing**
- After the manual strategy is saved successfully, the batch-page summary is shown as the `manual` path.
- If **Enable Manual** is checked but no valid strategy is saved, batch queueing is blocked.
- The sample is only a reference source used to build the rules. It does not guarantee that the entire batch has the same formats.
- If your rules are too narrow and you do not enable Preset 2 or the fallback chain, different videos may hit **no available format matched** at runtime.
- `webm` output and **H.264 Compatibility Mode** should not be enabled together. The former prefers the `webm` route, while the latter requires H.264-compatible processing.

### 4.4 Section Download

| Parameter | Default | Range | Description |
|----------|---------|-------|-------------|
| Section Download | Empty | `HH:MM:SS-MM:SS` / `MM:SS-MM:SS` | Example: `00:01:00-00:03:30` |

### 4.5 Subtitles and Post-Processing

Same as the single-video page: subtitle mode / language / format, external / embedded subtitles, thumbnail / metadata / description / chapters, H.264 compatibility mode, SponsorBlock, and PO Token. Default values are also the same as on the single-video page.

**Additional Notes**
- Subtitle and post-processing options here affect all currently selected entries together, so an overly heavy configuration can slow down the whole batch.
- If you are only verifying whether a playlist can download stably, it is recommended to disable complex post-processing at first (such as H.264 transcoding, SponsorBlock, and embedding many subtitles), confirm stability, and then add features step by step.
- For batch tasks with many entries, `Write Info JSON / Description / Thumbnail` will noticeably increase the number of extra files. Enable them when you actually need archival organization.

### 4.6 Network and Advanced Parameters

| Parameter | Default | Range | Description |
|----------|---------|-------|-------------|
| Proxy | Empty | Any protocol URL | Same as the single-video page |
| Cookies Mode | `file` | `file` / `browser` | Synchronized with global settings |
| Browser Cookies | Empty | `chrome` / `edge` / `firefox` | Effective only in `browser` mode |
| Advanced Arguments | Empty | Allowlisted arguments only | Only safe arguments are allowed |

**Additional Notes**
- Once the batch page network parameters are enqueued, they are copied into every batch task, so this area is better for **batch-wide unified parameters** rather than per-item differences.
- If you suspect that the entire batch is affected by the same network environment, it is better to set proxy or Browser Cookies for the whole batch here instead of patching failed tasks one by one later.
- Batch advanced arguments are still controlled by the allowlist. They are suitable for small unified tweaks, not for overriding explicit fields that are already exposed in the main UI.

### 4.7 Subtitles

| Parameter | Default | Range | Description |
|----------|---------|-------|-------------|
| Subtitle Mode | `none` | `none` / `manual` / `auto` / `both` | Manual / automatic / both |
| Subtitle Languages | Empty | Determined by `yt-dlp` | Example: `zh,en`; supports multiple languages |
| Subtitle Format | Empty | Determined by `yt-dlp` | Example: `srt` / `vtt` / `ass` |
| Write External Subtitles | On | Toggle | Output separate subtitle files |
| Embed Subtitles | Off | Toggle | Mux subtitles into the video file (`mkv` is more reliable) |

**Additional Notes**
- The subtitle logic is the same as on the single-video page, but because the target is a whole batch, it is recommended to keep the language field relatively flexible; otherwise you may end up with mixed results where some entries have subtitles and others do not.
- If you plan to archive courses, lectures, or interviews long-term, enabling at least external subtitles is usually recommended for later search and reprocessing.
- If you care more about creating a polished single-file result, you can also enable embedded subtitles, but expect longer muxing and post-processing time.

### 4.8 Throttle

| Parameter | Default | Range | Description |
|----------|---------|-------|-------------|
| Sleep Interval (s) | `5` | `0 - 60` | `--sleep-interval` |
| Max Sleep Interval (s) | `10` | `0 - 120` | `--max-sleep-interval` |
| API Sleep (s) | `1` | `0 - 30` | `--sleep-requests` |
| Retry Sleep (s) | `10` | `0 - 300` | `--retry-sleep http:` |

**Additional Notes**
- Throttle parameters are mainly used to slow down batch request pacing and reduce the chance of hitting site frequency limits.
- If playlist parsing succeeds but batch downloading often ends in `403`, rate limits, or interruptions, it is usually better to moderately increase these intervals first rather than simply increasing retries.
- If your network is already stable and the batch size is small, the default values are usually fine. Over-throttling will noticeably lengthen the total download time.

### 4.9 Download Control

| Parameter | Default | Range | Description |
|----------|---------|-------|-------------|
| Retries | `3` | `0 - 10` | `0` means no retries |
| Concurrency | `1` | `1 - 10` | Batch concurrency |
| Speed Limit (MB/s) | `2` | `0 - 100` | `0` means unlimited |

**Additional Notes**
- For large batch tasks, overall speed is often determined less by the speed of one task and more by the balance among concurrency, throttling, network stability, and site anti-abuse behavior.
- If you are downloading a long playlist, it is recommended to first test the first 5 to 10 entries using a conservative configuration. After confirming that there are no widespread failures, you can then relax concurrency or speed limits appropriately.
- If you are using a proxy or a cross-border network environment, overly high concurrency is more likely to trigger connection failures, interrupted downloads, or timeouts.

---

## 5. Queue Management

**Queue Table Columns**: ID / Status / Progress / Speed / Filename / Type.

| Action | Description |
|-------|-------------|
| Start All | Start all pending download tasks |
| Start / Retry | Start selected waiting tasks, or retry selected failed tasks |
| Stop Selected | Stop the selected tasks |
| Stop All | Stop all running tasks |
| Delete Selected | Delete the selected tasks |
| Clear Completed | Clear completed tasks (success / failed) |
| View History | Open the history window |

**Task Statuses**: Waiting / Downloading / Completed / Failed / Stopped

**Log Area**: Real-time runtime logs for the download queue.

**Bottom Bar**: Current Directory / Browse (Set) / Open Directory.

**Additional Notes**
- Queue task IDs are currently three-digit incremental numbers, starting at `001` and wrapping back to `001` after `999`.
- Filenames shown in the queue prefer this order: `custom filename` -> parsed video title -> preset-generated default name.
- **Stop Selected / Stop All** currently keep the tasks in the queue and mark them as **Stopped**. They do not disappear from the list immediately when stopped.
- `[Summary]` lines in the logs are shown in gray, making them easier to distinguish from regular `INFO / WARN / ERROR` logs.
- The **Start / Retry** button is currently placed first in the queue action area and highlighted in blue. **Stop Selected** is highlighted in orange to reduce accidental misuse.
- **Clear Completed** currently removes finished task items. If you want to keep failed tasks for investigation, check the logs or history first before clearing.

**Updates in this version**
- The old **Retry Selected** button has been renamed to **Start / Retry**.
- The download queue and other lists now try to preserve the current selection during auto-refresh.
- The currently selected row keeps a light-blue background and bold text, making the current target of actions easier to identify.

---

## 6. History

The current implementation is **text list display + refresh + clear**.

| Feature | Description |
|--------|-------------|
| Show History | Displays title, type, source, URL, path, time, format, subtitle language, retries, and custom filename |
| Refresh | Reload history data |
| Clear | Clear all history records |

**Additional Notes**
- History data prefers SQLite first. If database initialization fails, the program automatically falls back to JSON history instead of losing history functionality completely.
- Key summaries of both successful tasks and failed tasks are written to history as much as possible, making it easier to review which parameters were used and why a task failed.
- The history page is currently more oriented toward result viewing than task management, so it is not ideal for large-scale filtering or complex searching.
- If your main goal is to investigate the cause of the most recent failure, it is recommended to review **History + Queue Logs + Runtime Status Center** together for a more complete picture.

> Filter / export / re-download buttons are not provided yet.

---

## 7. Authentication and Security

### 7.1 Cookies File

| Item | Description |
|------|-------------|
| Default Filename | `www.youtube.com_cookies.txt` |
| Storage Path | Program directory by default, or a configured path |
| Purpose | Solves `403`, age restriction, and region restriction issues |

**Usage Method**:
1. Log in to YouTube in your browser.
2. Use an extension to export the Cookies for `www.youtube.com` in Netscape format.
3. Put the file in the program directory or save it to the configured path.

**Additional Notes**
- If the program cannot detect a local Cookies file, it usually will not block normal public-video downloads, but the success rate for restricted content will drop significantly.
- Once Browser Cookies is enabled, a local Cookies file is no longer mandatory.
- The Authentication Status Center shows whether the file exists, the latest check result, the latest error category, and diagnostic suggestions.

### 7.2 Browser Cookies

- Supported browsers: Chrome / Edge / Firefox.
- It becomes effective when you select `browser` and specify the browser name in the settings page or top area.
- Browser Cookies is suitable if you do not want to export a Cookies file manually, or if the Cookies file often expires.

### 7.3 PO Token

- Requires Node.js (recommendation: `>=18`; the program's current status detection and prompts also target a relatively recent Node.js environment).
- The program initializes the token automatically, and the status is displayed in the **Authentication Status Center**.
- When **Enable PO Token** is turned on, the program injects `extractor-args` into `yt-dlp`.
- If the current release package does not include the PO Token tool, the status area will show **Disabled**, which is a normal degradation path rather than a program error.
- For most public videos, the program can still work normally without PO Token. Only when you hit specific anti-abuse or extraction restrictions should you investigate PO Token further.

### 7.4 What to Check in the Authentication Status Center

After opening the **Authentication Status Center**, focus on the following items:

1. `Cookies Mode`: Confirm whether the current path is `file` or `browser`.
2. `Cookies File Path`: Confirm whether the path points to the correct file.
3. `Last Check`: Determine whether the most recent Cookies check succeeded.
4. `Last Error Category`: Identify whether the problem is a missing file, expired login, site anti-abuse, or something else.
5. `PO Token Status`: Confirm whether the current status is `ready / disabled / no_node / error`.
6. `Suggested Actions`: The program gives next-step suggestions based on the latest diagnosis, and those suggestions usually have a higher priority than blind repeated attempts.

---

## 8. Components Center

| Item | Description |
|------|-------------|
| yt-dlp | Shows path / version / status and supports one-click update |
| ffmpeg | Shows path / version / status (no update button) |
| deno | Shows path / version / status (no update button) |
| Export Diagnostics | Exports component diagnostics as JSON |

**Additional Notes**
- The **Update** button in the Components Center is currently a unified update entry that handles `yt-dlp / ffmpeg / deno` together, rather than updating only one of them.
- If you are missing only `yt-dlp` or `ffmpeg`, you can still use the same entry and let the program fill in the missing component automatically.
- `deno` mainly affects Hooks and some extension capabilities. Its absence does not necessarily break normal downloads, but it limits extension scripts.
- Exported diagnostics are useful when investigating issues such as wrong versions, bad paths, or unavailable components.

---

## 9. Runtime Status Center

| Item | Description |
|------|-------------|
| Task Overview | Counts of running tasks and queued tasks |
| History Database | Whether SQLite is available and its path |
| Recent Runtime Issues | Summary and details of the most recent runtime issue |

**Additional Notes**
- The Runtime Status Center is not a real-time line-by-line log window. It is more of a summary panel for recent issues.
- When the program detects issues such as missing components, authentication failures, command-build failures, or database exceptions, the recent issue summary is gathered here.
- If this center shows messages such as **release resources missing** or **history database fell back to JSON**, it usually means the program is running in a degraded mode rather than being completely unusable.
- For troubleshooting, it is recommended to look at the summary here first, then return to the download queue logs to locate the exact trigger time and command context.

---

## 10. Media Tools (Local Processing)

### 10.1 Processing Types

| Type | Description |
|------|-------------|
| remux | Container conversion only (no transcoding) |
| extract_audio | Extract audio |
| trim | Trim a time range |
| concat | Concatenate multiple files |
| burn_subtitle | Burn subtitles into video |
| scale | Scale |
| crop | Crop |
| rotate | Rotate |
| watermark | Add watermark |
| loudnorm | Loudness normalization |

**Additional Notes**
- Media Tools operate on local files and do not depend on video-site parsing.
- These tasks have their own **media task queue** and **media task logs**, separate from the download queue.
- If you only want a simple container conversion (for example `mkv -> mp4` without re-encoding), use `remux` first because it is usually the fastest.
- If you need to control codec, CRF, preset, filter chains, and so on, that is a more advanced `ffmpeg` scenario, so small-scale testing is recommended first.

### 10.2 Parameters and Default Values

| Parameter | Default | Range | Description |
|----------|---------|-------|-------------|
| Input File | Empty | File path | Required (except in concatenate mode) |
| Output File | Empty | File path | Required |
| Audio Format | `mp3` | `mp3` / `m4a` / `wav` / `flac` / `opus` | Audio extraction only |
| Trim Start / End | Empty | `HH:MM:SS` | Trim only |
| Concat List | Empty | `.txt` | Concatenate only |
| Subtitle File | Empty | `.srt/.ass/.vtt` | Burn subtitles only |
| Scale Width / Height | Empty | Numbers | Empty = keep aspect ratio |
| Crop Width / Height / X / Y | Empty | Numbers | Crop parameters |
| Rotation Angle | Empty | `90/180/270` | Rotate only |
| Watermark File | Empty | Image file | Watermark only |
| Watermark Position | `bottom-right` | `top-left` / `top-right` / `bottom-left` / `bottom-right` / `center` | Watermark only |
| Loudness Normalization | - | `loudnorm` | Uses `loudnorm` for loudness standardization |
| Media Info | Not parsed | - | Shows parsed media information |
| Video Codec | Empty | `h264` / `h265` / `vp9` / `av1` / `copy` | Advanced parameter |
| Audio Codec | Empty | `aac` / `mp3` / `opus` / `flac` / `copy` | Advanced parameter |
| CRF | Empty | Determined by `ffmpeg` | Quality control |
| Preset | Empty | Determined by `ffmpeg` | Encoding speed / quality |
| Video Bitrate | Empty | Determined by `ffmpeg` | For example `2000k` |
| Audio Bitrate | Empty | Determined by `ffmpeg` | For example `128k` |
| Custom `-vf` / `-af` | Empty | Determined by `ffmpeg` | Filter passthrough |
| Advanced Arguments | Empty | Determined by `ffmpeg` | Direct passthrough |

**Buttons and Actions**: Add Task / Start All / Clear Completed / Stop Selected / Delete Selected.

**Additional Notes**
- After switching the **Processing Type** at the top of the Media Tools page, the UI automatically shows or hides related parameter rows. Different task types do not share exactly the same inputs.
- For example:
  - `extract_audio` focuses more on audio format;
  - `trim` focuses more on start/end time;
  - `concat` focuses more on the concat list;
  - `burn_subtitle` focuses more on the subtitle file;
  - `watermark` focuses more on the watermark file and position;
  - `loudnorm` focuses more on loudness normalization itself rather than additional input files.
- If a certain task type requires filter chains or re-encoding, the codec, bitrate, CRF, and preset parameters become more important than simply changing the container.
- Media task logs are separate from download logs, which is useful when you need to troubleshoot many local processing jobs independently.

---

## 11. Advanced Argument Allowlist (`yt-dlp`)

Only the following safe arguments are allowed. Others will be rejected.

- No-value arguments:
  - `--no-part`
  - `--no-continue`
  - `--force-overwrites`
  - `--ignore-errors`
  - `--abort-on-error`
  - `--force-ipv4`
  - `--no-check-certificate`

- Arguments that require a value:
  - `--concurrent-fragments` / `-N`
  - `--fragment-retries`
  - `--extractor-retries`
  - `--file-access-retries`
  - `--socket-timeout`
  - `--http-chunk-size`
  - `--downloader`
  - `--downloader-args`
  - `--compat-options`

**Usage Suggestions**
- The best use case here is usually **download-layer fine-tuning parameters**, such as fragment concurrency, timeout values, compatibility options, or downloader selection.
- It is not appropriate to put parameters here that are already managed directly by the main UI, such as format, proxy, Cookies, sections, subtitles, or output path.
- If you are not sure whether a parameter is safe, do not use it at first. It is usually more stable to configure the task through the existing UI toggles and input fields.
- When advanced arguments overlap semantically with the main UI parameters, the program protects the main UI parameters first to avoid unpredictable task behavior caused by being overridden.

**Examples**
- To increase fragment concurrency: try `--concurrent-fragments 4`
- To relax certain compatibility behavior: try `--compat-options no-youtube-unavailable-videos`
- To increase network timeout: try `--socket-timeout 30`

> Note: Options that conflict with internal app parameters will be rejected, such as `--format`, `--proxy`, `--cookies`, and `--download-sections`.

---

## 12. Hook Extensions, Logs, and Diagnostics

### 12.1 Hook Extensions

- The program supports `deno`-based Hook extensions for running extra logic when tasks start, complete, fail, and so on.
- Hooks are better suited for advanced extensions such as automatic archiving, notifications, secondary logging, or post-publish workflow integration. They are not required for normal downloading.
- If the current environment does not have `deno`, or if the release package does not include the related Hook resources, the program will usually degrade to **core functionality available, extension functionality unavailable**.

### 12.2 Log Reading Suggestions

- In download logs:
  - `INFO` is mainly used for normal state transitions;
  - `WARN / WARNING` usually indicates risk or a suggestion to adjust parameters;
  - `ERROR` usually indicates task failure or a key step exception;
  - `[Summary]` lines are generally used to show command, parameter, output-directory, and other overview information.
- Media Tools logs and download-queue logs are separate. When troubleshooting, first confirm which task system you are looking at.
- If you see a large number of repeated retries in the logs, go back and check authentication, proxy, and format strategy first instead of simply increasing the retry count again.

### 12.3 Recommended Troubleshooting Order

1. **Check the Components Center first**: confirm that `yt-dlp / ffmpeg / deno` exist and their versions look correct.
2. **Then check the Authentication Status Center**: confirm that Cookies, Browser Cookies, and PO Token are usable.
3. **Then check the Runtime Status Center**: determine whether the most recent issue belongs to components, authentication, database, or runtime behavior.
4. **Finally check the specific logs**: return to the download queue or Media Tools logs and locate the trigger time, summary, and raw error output.

### 12.4 Relationship Between This Document and Actual Behavior

- This manual is organized according to the current code behavior and is intended to serve as a usage and troubleshooting guide.
- If the UI wording, button position, or default values change slightly in the future, prioritize the program UI, real-time logs, and status-center messages.
- For complex features such as batch manual strategy, section fallback, PO Token, and Hooks, it is strongly recommended to test on a small scale before using them in large batches.

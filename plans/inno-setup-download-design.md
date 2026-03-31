# YCB 安装包版（`PyInstaller + Inno Setup`）打包计划

## 1. 目标

为 [`YCB.pyw`](YCB.pyw) 制作“带安装界面的安装包版” Windows 安装程序，满足以下目标：

1. 主程序版本号定为 `v0.1.0`，安装包版本同步标记为 `YCB v0.1.0`。
2. 主程序先通过 [`PyInstaller`](YCB.spec) 打包为可分发目录。
3. 再通过 `Inno Setup` 生成带安装向导的 `Setup.exe`。
4. 安装向导中向用户展示可选组件：
   - `yt-dlp.exe`
   - `ffmpeg.exe`
   - `deno.exe`
5. 用户可勾选需要的组件；安装程序在安装阶段把这些组件下载到最终安装目录 `{app}`。
6. 如果用户选择了安装组件，安装界面需要显示安装进度；若安装失败，自动重试安装。
7. 如果用户未选择安装组件，则跳过下载，但在安装过程中和安装完成页提醒用户：若要使用完整功能，需要手动安装这些组件。
8. 安装完成后，程序目录中已经包含用户勾选并安装成功的组件，主程序可直接使用。

---

## 2. 现状分析

### 2.1 现有主程序打包基础

当前项目已经具备以下基础：

- [`YCB.spec`](YCB.spec) 已配置主程序打包。
- [`YCB.spec`](YCB.spec) 已额外打包出 [`backend_setup.py`](backend_setup.py) 对应的辅助可执行文件，说明项目已经在尝试“安装时补组件”的路线。
- [`backend_setup.py`](backend_setup.py) 已具备下载 `yt-dlp`、下载并解压 `ffmpeg` / `deno` 的基础逻辑。

### 2.2 现有组件来源

组件来源与程序内组件中心一致，可保持统一：

- `yt-dlp`：[`backend_setup.py`](backend_setup.py:11)
- `ffmpeg`：[`backend_setup.py`](backend_setup.py:16)
- `deno`：[`backend_setup.py`](backend_setup.py:22)

### 2.3 主程序对组件的依赖关系

程序运行时会检测以下组件：

- [`check_yt_dlp()`](core/components_manager.py:84)
- [`check_ffmpeg()`](core/components_manager.py:107)
- [`check_deno()`](core/components_manager.py:124)

因此安装器下载到 `{app}` 目录后，可直接复用现有运行时检测逻辑，无需额外改动主程序的组件发现机制。

---

## 3. 总体方案

采用“两段式打包”：

### 阶段 A：主程序分发目录

使用 [`YCB.spec`](YCB.spec) 生成：

- `dist\YCB\`：主程序目录版
- `dist\backend_setup.exe` 或等效辅助下载器 exe

### 阶段 B：安装包封装

使用 `Inno Setup`：

1. 复制 `dist\YCB\*` 到安装目录 `{app}`。
2. 在安装向导中显示组件勾选页。
3. 根据用户勾选结果，调用组件下载器 exe。
4. 组件下载器将 `yt-dlp.exe`、`ffmpeg.exe`、`deno.exe` 下载或解压到 `{app}`。
5. 最终输出 `YCB-Setup.exe`。

---

## 4. 推荐技术路线

推荐继续走“`Inno Setup` + 独立下载器 exe”路线，而不是纯 `Inno Setup Pascal Script` 下载，原因如下：

1. `ffmpeg` 和 `deno` 是 `zip` 包，下载后还要解压，使用 Python 标准库更稳。
2. GitHub 下载链接可能跳转，Python 处理更简单。
3. 错误处理、重试、日志记录、退出码设计更容易做完整。
4. 当前已有 [`backend_setup.py`](backend_setup.py) 可作为基础，改造成本最低。

---

## 5. 安装包目标体验

### 5.1 用户视角安装流程

1. 运行 `YCB-Setup.exe`
2. 选择安装路径
3. 看到组件勾选页，例如：
   - `[x] 安装 yt-dlp.exe（推荐）`
   - `[x] 安装 ffmpeg.exe（推荐）`
   - `[ ] 安装 deno.exe（可选）`
4. 点击“安装”
5. 安装器先复制主程序，再下载所选组件到 `{app}`
6. 完成安装

### 5.2 默认勾选建议

建议默认勾选：

- `yt-dlp.exe`：默认勾选
- `ffmpeg.exe`：默认勾选
- `deno.exe`：默认不勾选或作为高级可选项

理由：

- `yt-dlp` 和 `ffmpeg` 是核心功能高频依赖。
- `deno` 在当前项目中属于增强能力，不必强制所有用户安装。

### 5.3 进度与提醒体验

如果用户勾选了组件，安装界面应明确展示：

- 当前安装的组件名
- 当前阶段：下载 / 解压 / 校验 / 重试
- 单组件进度百分比
- 总体安装进度
- 当前重试次数，例如 `2/3`

如果用户未勾选全部或部分组件，安装器应在以下位置提醒：

1. “准备安装”说明区，提示未安装组件不会随主程序一起提供。
2. “安装完成”页面，列出未安装的组件名称，并提示用户若要使用完整功能，需要手动安装这些组件。

---

## 6. 目标文件结构

建议整理为以下打包结构：

```text
project/
├─ YCB.pyw
├─ YCB.spec
├─ backend_setup.py
├─ installer/
│  ├─ setup.iss
│  ├─ build_installer.bat
│  └─ README.md
├─ dist/
│  ├─ YCB/
│  └─ backend_setup.exe
└─ plans/
   └─ inno-setup-download-design.md
```

说明：

- [`backend_setup.py`](backend_setup.py) 建议继续保留在项目根目录，方便复用当前 [`YCB.spec`](YCB.spec) 打包逻辑。
- `Inno Setup` 脚本建议后续落在 `installer\setup.iss`，避免根目录继续堆积打包脚本。

---

## 7. 下载器设计计划

## 7.1 角色定位

将 [`backend_setup.py`](backend_setup.py) 明确定位为“安装阶段组件下载器”，由 `Inno Setup` 在复制主程序后调用。

## 7.2 下载器输入参数

建议把下载器改造成如下命令行形式：

```bat
backend_setup.exe --dir "C:\Program Files\YCB" --components yt-dlp,ffmpeg
```

建议支持参数：

- `--dir`：目标安装目录
- `--components`：逗号分隔组件列表
- `--retry`：重试次数，默认 `3`
- `--timeout`：单组件超时秒数，默认 `300`
- `--skip-existing`：若文件已存在则跳过
- `--log-file`：可选，输出安装日志到 `{app}` 或 `{tmp}`

## 7.3 下载器需要补强的能力

当前 [`backend_setup.py`](backend_setup.py) 仅能“全量遍历组件”，后续实现时需要增强：

1. 支持按用户勾选下载指定组件。
2. 为每个组件区分 `download / extract / verify / retry / done` 阶段。
3. 每个组件安装失败后自动重试，默认 `3` 次。
4. 为 `ffmpeg` / `deno` 解压结果做校验。
5. 将安装进度写入进度文件，供 `Inno Setup` 页面轮询显示。
6. 记录详细日志，便于安装失败时排查。
7. 可选支持“已存在文件则跳过”。
8. 为“全部未勾选组件”的情况返回“跳过安装”结果，而不是报错。

## 7.4 进度通信设计

建议让下载器支持如下参数：

- `--progress-file`：把当前进度写入 `json` 文件
- `--selected-components`：写入用户实际勾选的组件列表
- `--missing-components-file`：输出未安装组件列表，供安装完成页提醒使用

建议进度文件格式如下：

```json
{
  "component": "ffmpeg",
  "phase": "download",
  "current": 31457280,
  "total": 104857600,
  "attempt": 2,
  "max_attempts": 3,
  "message": "正在下载 ffmpeg..."
}
```

`Inno Setup` 通过定时轮询该文件，即可在安装向导中显示实时进度与重试状态。

## 7.5 下载结果约定

建议下载器最终输出统一结果：

- 全部成功：退出码 `0`
- 选中组件中存在失败：退出码 `1`
- 参数错误：退出码 `2`
- 安装目录不可写：退出码 `3`
- 网络/下载致命失败：退出码 `4`
- 未选择任何组件并已跳过：退出码 `0`

这样 `Inno Setup` 可以根据退出码决定：

- 正常完成安装
- 弹窗提醒用户部分组件未安装成功
- 引导用户再次重试
- 必要时中止安装

---

## 8. Inno Setup 方案计划

## 8.1 安装脚本职责

后续的 [`setup.iss`](installer/setup.iss) 负责：

1. 定义安装包元数据，其中版本使用 `AppVersion=0.1.0`、`AppVerName=YCB v0.1.0`、`OutputBaseFilename=YCB-Setup-v0.1.0`
2. 复制主程序文件
3. 提供组件勾选界面
4. 提供安装进度页面，显示当前组件安装状态与重试进度
5. 把下载器 exe 临时放到 `{tmp}` 或直接放入 `{app}`
6. 安装阶段调用下载器
7. 根据退出码处理成功/失败提示
8. 如果用户未勾选全部或部分组件，在完成页显示“需手动安装组件才能使用完整功能”的提醒
9. 创建桌面快捷方式、开始菜单快捷方式

## 8.2 组件勾选页设计

推荐使用 `Inno Setup` 的 `[Components]` 做勾选页，再额外增加自定义进度页：

### 勾选页实现

建议组件定义：

- `main`：主程序，固定
- `comp_ytdlp`：yt-dlp（推荐）
- `comp_ffmpeg`：ffmpeg（推荐）
- `comp_deno`：deno（可选）

页面说明中明确写出：

- 勾选后：安装时自动下载并安装到程序目录
- 不勾选：不会自动安装，后续需手动安装才能使用完整功能

## 8.3 安装进度页设计

由于用户明确要求“显示安装进度”，所以首版就应实现自定义安装进度页，而不是放到后续版本。

推荐方案：

1. `Inno Setup` 在安装阶段创建自定义 `WizardPage`
2. 页面展示：
   - 当前组件名称
   - 当前阶段（下载 / 解压 / 校验 / 重试）
   - 单组件进度条
   - 总体进度条
   - 当前重试次数
3. 下载器通过 [`backend_setup.py`](backend_setup.py) 持续更新 `progress.json`
4. `Inno Setup` 每 `300~500ms` 轮询一次进度文件并刷新 UI

## 8.4 安装阶段调用方式

推荐通过 `[Code]` 中的 `Exec(...)` 调用下载器，而不是只靠 `[Run]`：

- 更容易拿到退出码
- 更容易轮询进度文件
- 更容易在失败后触发再次重试或弹出提示

建议调用参数形态：

```pascal
backend_setup.exe --dir "{app}" --components "yt-dlp,ffmpeg" --retry 3 --progress-file "{tmp}\component_progress.json"
```

## 8.5 勾选 / 未勾选 / 失败场景策略

### 场景 A：用户勾选了组件

- 安装器执行下载与安装
- 页面实时显示进度
- 单组件失败时自动重试，默认 `3` 次
- 重试中显示如“正在重试 ffmpeg（第 2/3 次）”

### 场景 B：用户未勾选某些组件

- 安装器不下载这些组件
- 不视为错误
- 在完成页列出未安装组件，例如：
  - `yt-dlp.exe`
  - `ffmpeg.exe`
  - `deno.exe`
- 同时提示：“若要使用完整功能，请稍后手动安装这些组件。”

### 场景 C：重试后仍失败

建议策略：

- 自动重试 `3` 次后，弹出结果提示
- 提供以下处理：
  - 重新重试当前组件
  - 跳过该组件继续安装
  - 取消整个安装
- 如果用户选择“跳过”，完成页仍要提醒该组件需手动安装

---

## 9. PyInstaller 计划

## 9.1 主程序打包

继续使用 [`YCB.spec`](YCB.spec) 打包主程序。

需要确认输出形式：

- 当前 [`YCB.spec`](YCB.spec) 中 [`EXE(...)`](YCB.spec:129) 只定义了主 exe，未见 `COLLECT(...)`；
- 但现有目录中已经存在 `build\YCB\` 相关产物，说明已有实际工作流；
- 后续需要统一明确为“目录版分发”，供 `Inno Setup` 直接打包整个 `dist\YCB\` 目录。

## 9.2 组件下载器打包

继续使用 [`YCB.spec`](YCB.spec:152) 中现有的 [`backend_setup.py`](backend_setup.py) 分析配置，但后续建议单独拆出一个更清晰的 `spec` 或构建命令：

- 方案 A：保留在同一个 [`YCB.spec`](YCB.spec)
- 方案 B：新增 `backend_setup.spec`

推荐方案 B，理由：

1. 主程序和下载器构建目标不同，便于独立调试。
2. 下载器可以保留控制台，主程序必须是 GUI。
3. 安装包构建流水线更清晰。

---

## 10. 实施阶段拆分

## 阶段 1：整理构建产物

目标：先稳定得到两个可分发产物。

工作项：

1. 校正主程序 `PyInstaller` 输出目录结构。
2. 让 [`backend_setup.py`](backend_setup.py) 独立打包为下载器 exe。
3. 明确 `dist\YCB\` 和 `dist\backend_setup.exe` 的位置。

交付物：

- 主程序目录版
- 下载器 exe

## 阶段 2：增强组件下载器

目标：让下载器真正适合安装阶段使用。

工作项：

1. 支持 `--components`
2. 支持 `--retry 3`
3. 支持进度文件输出
4. 支持退出码
5. 支持重试与日志
6. 支持已存在跳过
7. 支持解压后校验
8. 支持输出“未安装组件列表”

交付物：

- 改造后的 [`backend_setup.py`](backend_setup.py)
- 下载器测试命令说明
- 进度文件协议说明

## 阶段 3：编写 Inno Setup 脚本

目标：实现安装向导 + 组件勾选 + 安装时下载。

工作项：

1. 新建 `installer\setup.iss`
2. 配置 `v0.1.0` 安装包元数据
3. 添加 `[Setup]`、`[Files]`、`[Icons]`
4. 添加组件勾选逻辑
5. 添加自定义安装进度页
6. 添加 `Exec(...)` 调用下载器
7. 添加下载失败重试和退出码处理
8. 添加安装完成页的“手动安装组件提醒”逻辑

交付物：

- 可编译的 `installer\setup.iss`

## 阶段 4：联调与打包脚本

目标：一键生成最终安装包。

工作项：

1. 增加 `build_installer.bat`
2. 顺序执行主程序打包、下载器打包、Inno 编译
3. 输出最终 `YCB-Setup.exe`

交付物：

- 一键打包脚本
- 最终安装包

## 阶段 5：安装体验与异常验证

目标：保证用户侧可用。

工作项：

1. 测试仅主程序安装（全部组件不勾选）
2. 测试勾选 `yt-dlp + ffmpeg`
3. 测试勾选全部组件
4. 测试安装进度页是否正确显示下载 / 解压 / 校验状态
5. 测试断网 / GitHub 失败 / 自动重试逻辑
6. 测试重试三次后仍失败时的用户选择流程
7. 测试安装完成页对“未安装组件”的手动安装提醒
8. 测试安装到无权限目录的报错
9. 测试组件已存在时的覆盖/跳过策略

---

## 11. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| GitHub 下载慢或失败 | 安装时间长 / 失败 | 下载器增加重试、超时、日志，并在进度页展示当前重试状态；后续预留镜像源 |
| 安装器界面与下载器进度不同步 | 用户误以为卡死 | 使用 `progress.json` 轮询方案，统一由下载器写状态、安装器只负责显示 |
| `ffmpeg` / `deno` ZIP 结构变化 | 解压失败 | 使用“按文件名匹配提取”而不是写死目录层级，复用 [`extract_zip()`](backend_setup.py:51) |
| 用户未勾选组件后误以为功能完整 | 运行时缺组件 | 在勾选页、准备安装页、完成页三处重复提示“需手动安装组件才能使用完整功能” |
| 杀软误报 | 安装受阻 | 后续考虑签名、减少可疑行为、保留日志 |
| 用户安装目录无写权限 | 安装失败 | 在下载器启动前检测目录可写，并给出明确错误码 |

---

## 12. 首版落地建议

建议先做一个 **MVP 安装包版**：

1. 主程序用 [`PyInstaller`](YCB.spec) 生成目录版。
2. 下载器继续基于 [`backend_setup.py`](backend_setup.py) 改造。
3. `Inno Setup` 使用原生组件勾选页 + 自定义安装进度页。
4. 安装时调用下载器，把文件写入 `{app}`。
5. 第一版就实现以下必需能力：
   - 勾选组件
   - 显示安装进度
   - 失败自动重试
   - 未勾选组件时提醒手动安装
6. 第二版再优化界面美化、多语言细节、镜像源等增强项。

---

## 13. 建议的下一步执行顺序

下一步实施时，建议严格按下面顺序推进：

1. 确认 [`YCB.spec`](YCB.spec) 的主程序输出目录结构
2. 改造 [`backend_setup.py`](backend_setup.py) 为可按组件下载的安装器辅助程序
3. 单独打包 `backend_setup.exe`
4. 新建 `installer\setup.iss`
5. 接入组件勾选与安装阶段调用
6. 本机完整安装测试
7. 输出最终 `YCB-Setup.exe`

---

## 14. 结论

本项目完全适合采用：

- [`PyInstaller`](YCB.spec) 负责主程序打包
- [`backend_setup.py`](backend_setup.py) / `backend_setup.exe` 负责安装时组件下载
- `Inno Setup` 负责安装向导、组件勾选和最终安装包封装

这条路线与当前项目结构最匹配，改造量最小，也最容易实现“用户在安装界面勾选组件，安装时直接下载到程序目录”的目标。

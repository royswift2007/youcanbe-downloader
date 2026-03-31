# -*- mode: python ; coding: utf-8 -*-
"""
YCB 主程序 PyInstaller 打包配置

使用方法:
    pyinstaller YCB.spec --noconfirm

输出:
    dist/YCB.exe - 主程序可执行文件
"""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# 获取项目根目录
project_root = os.path.dirname(os.path.abspath(SPEC))

# 收集 customtkinter 的数据文件（主题、图标等）
datas = []
datas += collect_data_files('customtkinter')

# 添加图标文件及说明文档
datas.append(('ycb.ico', '.'))
datas.append(('usage_intro.md', '.'))
datas.append(('usage_intro_en.md', '.'))
datas.append(('tools', 'tools'))

# 隐式导入模块
hiddenimports = [
    # GUI 框架
    'tkinter',
    'tkinter.filedialog',
    'tkinter.messagebox',
    'tkinter.scrolledtext',
    'tkinter.ttk',
    'customtkinter',
    
    # 网络请求
    'requests',
    'urllib',
    'urllib.request',
    'urllib.parse',
    'urllib.error',
    
    # 下载引擎
    'yt_dlp',
    'yt_dlp.utils',
    'yt_dlp.extractor',
    'yt_dlp.downloader',
    'yt_dlp.postprocessor',
    
    # 其他依赖
    'pyperclip',
    'psutil',
    'loguru',
    
    # 项目模块
    'core',
    'core.advanced_args_policy',
    'core.auth_models',
    'core.components_manager',
    'core.cookies_args',
    'core.deno_runner',
    'core.download_manager',
    'core.ffmpeg_args_policy',
    'core.ffmpeg_builder',
    'core.history_repo',
    'core.hooks',
    'core.log_sink',
    'core.manual_format_policy',
    'core.media_jobs',
    'core.po_token_manager',
    'core.release_validator',
    'core.settings',
    'core.youtube_metadata',
    'core.youtube_models',
    'core.ytdlp_builder',
    
    'ui',
    'ui.app_actions',
    'ui.app_shell',
    'ui.bootstrap',
    'ui.components_center',
    'ui.download_tab',
    'ui.history_actions',
    'ui.history_center',
    'ui.i18n',
    'ui.input_validators',
    'ui.queue_tab',
    'ui.video_actions',
    
    'ui.pages',
    'ui.pages.batch_source',
    'ui.pages.history_page',
    'ui.pages.media_tools',
    'ui.pages.settings_page',
    'ui.pages.single_video',
]

a = Analysis(
    ['YCB.pyw'],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的模块以减小体积
        'matplotlib',
        'numpy',
        'pandas',
        'PIL',
        'scipy',
        'pytest',
        'IPython',
        'jupyter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='YCB',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI 模式，不显示控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='ycb.ico',  # 应用图标
)

# --- 增加后端组件下载助手 ---
a_setup = Analysis(
    ['backend_setup.py'],
    pathex=[project_root],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz_setup = PYZ(a_setup.pure, a_setup.zipped_data, cipher=None)

exe_setup = EXE(
    pyz_setup,
    a_setup.scripts,
    a_setup.binaries,
    a_setup.zipfiles,
    a_setup.datas,
    [],
    name='backend_setup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 使用控制台模式，方便查看下载进度
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='ycb.ico',
)

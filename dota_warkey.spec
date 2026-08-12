# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包脚本：一个单文件、带管理员提权、无图标的 exe。
# 用法：  pyinstaller --noconfirm --clean dota_warkey.spec
import os

here = SPECPATH  # spec 所在目录（PyInstaller 自动注入）

a = Analysis(
    [os.path.join(here, 'dota_warkey.py')],
    pathex=[here],
    binaries=[],
    datas=[
        (os.path.join(here, 'config.json'), '.'),   # 把默认配置打进 exe
        (os.path.join(here, 'logo.ico'), '.'),       # 运行时给窗口(标题栏+任务栏)当图标
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DotA改键精灵',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # GUI 程序，不弹黑框
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(here, 'logo.ico'),   # exe 文件图标（资源管理器/任务栏）
    uac_admin=True,         # 内置管理员提权（键盘钩子需要）
)

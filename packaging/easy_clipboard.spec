# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Easy Clipboard Manager.

Build (from the repository root):

    pyinstaller packaging/easy_clipboard.spec

Produces a one-folder build in ``dist/EasyClipboardManager`` with
``EasyClipboardManager.exe`` at the top level.
"""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 - SPECPATH is injected by PyInstaller

block_cipher = None

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "easy_clipboard",
        "easy_clipboard.app",
        "easy_clipboard.ui.tray",
        "easy_clipboard.windows.hotkey",
        "easy_clipboard.windows.autostart",
        "easy_clipboard.windows.single_instance",
        "easy_clipboard.windows.window_info",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EasyClipboardManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="EasyClipboardManager",
)

# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Easy Clipboard Manager (single-file build).

Build (from the repository root):

    pyinstaller --noconfirm --clean packaging/easy_clipboard.spec

or simply:

    packaging\\build_windows.bat

Produces ONE self-contained executable:

    dist\\EasyClipboardManager.exe

No Python installation, console window or administrator rights are needed
on the target machine.  The app icon (packaging/app.ico) is generated from
theme.render_logo() via packaging/generate_icon.py, and the Windows version
resource comes from packaging/file_version_info.txt.
"""

from pathlib import Path

# SPECPATH is injected by PyInstaller and points at packaging/.
ROOT = Path(SPECPATH).resolve().parent  # noqa: F821

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
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="EasyClipboardManager",
    icon=str(ROOT / "packaging" / "app.ico"),
    version=str(ROOT / "packaging" / "file_version_info.txt"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,  # onefile unpacks to a %TEMP% folder at runtime
    console=False,        # no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

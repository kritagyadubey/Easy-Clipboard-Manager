"""End-to-end verification harness for dist/EasyClipboardManager.exe.

Runs the packaged executable against a throw-away LOCALAPPDATA folder so the
developer's real clipboard history, settings and logs are never touched (the
real data folder is snapshotted before and after to prove that).

Usage:
    python scripts/verify_exe.py phase1   # launch, capture, privacy, single
                                          # instance, graceful exit, screenshot
    python scripts/verify_exe.py full     # everything, incl. UI copy-back with
                                          # synthesized keys, restart
                                          # persistence, unicode data folder

Every check prints [PASS]/[FAIL]; the process exits non-zero on any failure.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "dist" / "EasyClipboardManager.exe"
WINDOW_TITLE = "Easy Clipboard Manager"
APP_DIR = "EasyClipboardManager"

RESULTS: list[tuple[bool, str]] = []


def check(ok: bool, label: str) -> bool:
    RESULTS.append((bool(ok), label))
    print(f"[{'PASS' if ok else 'FAIL'}] {label}", flush=True)
    return bool(ok)


def info(label: str) -> None:
    print(f"[....] {label}", flush=True)


# ----------------------------------------------------------------------
# Win32 helpers
# ----------------------------------------------------------------------
def _user32():
    import ctypes

    return ctypes.windll.user32


def set_dpi_aware() -> None:
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


def enum_windows_for_pid(pid: int) -> list[tuple[int, str, str, bool]]:
    """Return (hwnd, title, class_name, visible) for a process's windows."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    results: list[tuple[int, str, str, bool]] = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        got = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(got))
        if got.value == pid:
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            visible = bool(user32.IsWindowVisible(hwnd))
            results.append((int(hwnd), buf.value, cls.value, visible))
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return results


def app_pids() -> set[int]:
    """All PIDs running the packaged app.

    PyInstaller's one-file bootloader runs the real application in a CHILD
    process, so windows never belong to the PID we spawned — everything
    window-related must go through this lookup.
    """
    out = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq EasyClipboardManager.exe",
         "/FO", "CSV", "/NH"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    ).stdout
    pids: set[int] = set()
    for line in out.splitlines():
        parts = line.split('","')
        if len(parts) >= 2 and parts[0].strip('"') == "EasyClipboardManager.exe":
            try:
                pids.add(int(parts[1]))
            except ValueError:
                continue
    return pids


def all_app_windows() -> list[tuple[int, str, str, bool]]:
    windows: list[tuple[int, str, str, bool]] = []
    for pid in app_pids():
        windows.extend(enum_windows_for_pid(pid))
    return windows


def kill_tree(proc: "subprocess.Popen[bytes]") -> None:
    """Kill the bootloader AND its one-file child."""
    subprocess.run(
        ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
        capture_output=True,
    )


def wait_for_window(timeout: float) -> int | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for hwnd, title, _cls, visible in all_app_windows():
            if visible and title == WINDOW_TITLE:
                return hwnd
        time.sleep(0.3)
    return None


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    import ctypes
    from ctypes import wintypes

    rect = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def screenshot(path: Path, rect: tuple[int, int, int, int]) -> None:
    from PIL import ImageGrab

    left, top, right, bottom = rect
    ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True).save(path)


def close_window(hwnd: int) -> None:
    import ctypes

    WM_CLOSE = 0x0010
    ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


# ----------------------------------------------------------------------
# Clipboard helpers (PowerShell so we never fight 64-bit ctypes handles)
# ----------------------------------------------------------------------
def _powershell(script: str, stdin_text: str | None = None, timeout: int = 30) -> str:
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "[Console]::OutputEncoding = [Text.Encoding]::UTF8; " + script,
        ],
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )
    return proc.stdout


def set_clipboard(text: str) -> None:
    # Pass the payload as base64: [Console]::In.ReadToEnd() would decode stdin
    # with the console's ANSI codepage, mangling non-ASCII text before it ever
    # reaches the clipboard (this broke the unicode marker check).
    import base64

    b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
    _powershell(
        "$t = [Text.Encoding]::UTF8.GetString("
        f"[Convert]::FromBase64String('{b64}')); Set-Clipboard -Value $t"
    )


def get_clipboard() -> str | None:
    out = _powershell("$v = Get-Clipboard -Raw -ErrorAction SilentlyContinue; "
                      "if ($null -ne $v) { [Console]::Out.Write($v) }")
    return out


# ----------------------------------------------------------------------
# Environment helpers
# ----------------------------------------------------------------------
def sandbox_root() -> Path:
    base = Path(os.environ.get("TEMP", ".")) / "opencode" / "ecm_verify"
    base.mkdir(parents=True, exist_ok=True)
    return base


def make_sandbox(name: str, *, unicode_dir: bool = False) -> Path:
    run = sandbox_root() / f"{name}_{uuid.uuid4().hex[:6]}"
    local = run / ("ECM Тест Данные ❤" if unicode_dir else "LocalAppData")
    local.mkdir(parents=True, exist_ok=True)
    (run / "foreign cwd").mkdir(parents=True, exist_ok=True)
    seed = local / APP_DIR
    seed.mkdir(parents=True, exist_ok=True)
    (seed / "settings.json").write_text(
        json.dumps({"minimize_to_tray": False}), encoding="utf-8"
    )
    return run


def launch(sandbox: Path) -> "subprocess.Popen[bytes]":
    env = dict(os.environ)
    env["LOCALAPPDATA"] = str(sandbox / _local_dir_name(sandbox))
    return subprocess.Popen(
        [str(EXE)],
        env=env,
        cwd=str(sandbox / "foreign cwd"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _local_dir_name(sandbox: Path) -> str:
    return "ECM Тест Данные ❤" if any(
        "❤" in p.name for p in sandbox.iterdir() if p.is_dir()
    ) else "LocalAppData"


def data_dir_of(sandbox: Path) -> Path:
    return sandbox / _local_dir_name(sandbox) / APP_DIR


def marker_rows(db_path: Path, marker: str) -> int:
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM items WHERE content LIKE ?",
            (f"%{marker}%",),
        ).fetchone()
        return int(row[0])
    finally:
        conn.close()


def snapshot_real_data() -> list[tuple] | None:
    real = Path(os.environ["LOCALAPPDATA"]) / APP_DIR
    if not real.exists():
        return None
    return sorted(
        (p.name, p.stat().st_size, int(p.stat().st_mtime)) for p in real.iterdir()
    )


def assert_real_data_untouched(before: list[tuple] | None, label: str) -> None:
    after = snapshot_real_data()
    check(before == after, f"{label}: real user data folder untouched")


def pe_subsystem(path: Path) -> int:
    """Read the PE optional-header subsystem field (2 = GUI, 3 = console)."""
    import struct

    data = path.read_bytes()
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    opt = e_lfanew + 4 + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    assert magic in (0x10B, 0x20B), hex(magic)
    return struct.unpack_from("<H", data, opt + 68)[0]


# ----------------------------------------------------------------------
# Phases
# ----------------------------------------------------------------------
def phase1() -> None:
    set_dpi_aware()
    check(EXE.exists(), f"executable exists ({EXE})")
    size_mb = EXE.stat().st_size / (1024 * 1024)
    info(f"executable size: {size_mb:.1f} MiB")

    # Static checks on the file itself -----------------------------------
    import importlib.util

    check(
        importlib.util.find_spec("PIL") is not None,
        "Pillow available for screenshots",
    )

    version = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"(Get-Item -LiteralPath '{EXE}').VersionInfo | "
         "Select-Object ProductVersion, FileDescription, ProductName | ConvertTo-Json"],
        capture_output=True, text=True, encoding="utf-8",
    ).stdout
    try:
        import json as _json

        info_json = _json.loads(version)
        check(
            str(info_json.get("ProductVersion", "")).startswith("1.1"),
            f"version resource present ({info_json})",
        )
    except Exception:
        check(False, f"version resource present ({version!r})")

    check(pe_subsystem(EXE) == 2, "PE subsystem is GUI (no console window)")

    # Live run -----------------------------------------------------------
    running = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq EasyClipboardManager.exe"],
        capture_output=True, text=True, encoding="utf-8",
    ).stdout
    check(
        "EasyClipboardManager.exe" not in running,
        "no pre-existing instance (would break single-instance test)",
    )

    real_before = snapshot_real_data()
    sandbox = make_sandbox("phase1")
    marker = f"ECM_VERIFY_MARKER_{uuid.uuid4().hex[:8].upper()} ✓ «хвост»"

    info(f"sandbox: {sandbox}")
    t0 = time.monotonic()
    proc = launch(sandbox)
    hwnd = wait_for_window(timeout=90)
    startup = time.monotonic() - t0
    info(f"window appeared after {startup:.1f}s")
    if not check(hwnd is not None, "main window appeared with correct title"):
        for w in all_app_windows():
            if w[3]:
                info(f"visible window of the app: title={w[1]!r} class={w[2]!r}")
        log_file = data_dir_of(sandbox) / "app.log"
        if log_file.exists():
            info("---- app.log ----")
            print(log_file.read_text(encoding="utf-8", errors="replace"))
        kill_tree(proc)
        return

    wins = [w for w in all_app_windows() if w[3]]
    check(
        not any(w[2] == "ConsoleWindowClass" for w in wins),
        "no console window belongs to the process",
    )
    check(len([w for w in wins if w[1] == WINDOW_TITLE]) == 1,
          "exactly one application window")

    shot = sandbox / "phase1-window.png"
    screenshot(shot, window_rect(hwnd))
    info(f"screenshot: {shot}")

    data_dir = data_dir_of(sandbox)
    expected = {"settings.json", "history.db", "app.log"}
    created = {p.name for p in data_dir.iterdir()} if data_dir.exists() else set()
    check(expected <= created, f"data written to sandbox only ({sorted(created)})")
    check(
        str(data_dir).startswith(str(sandbox)),
        "data directory is inside the sandboxed LOCALAPPDATA",
    )

    # Clipboard capture ---------------------------------------------------
    set_clipboard(marker)
    db = data_dir / "history.db"
    found = 0
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            found = marker_rows(db, marker)
        except sqlite3.Error:
            found = 0
        if found:
            break
        time.sleep(0.5)
    check(found >= 1, f"clipboard capture reached the database (rows={found})")

    # Privacy: the log must never contain clipboard text -------------------
    log_text = (data_dir / "app.log").read_text(encoding="utf-8", errors="replace")
    check(marker not in log_text, "log file contains no clipboard text")
    check(marker.split()[0] not in log_text, "log file contains no marker token")

    # Single instance -------------------------------------------------------
    second = launch(sandbox)
    try:
        code = second.wait(timeout=20)
    except subprocess.TimeoutExpired:
        kill_tree(second)
        code = -1
    check(code == 0, f"second launch exits immediately (code={code})")
    check(
        wait_for_window(timeout=3) is not None,
        "first instance still has its window",
    )
    visible_now = {w[0] for w in all_app_windows() if w[3]}
    check(visible_now == {hwnd}, "second launch created no window of its own")

    # Graceful exit ---------------------------------------------------------
    check(bool(_user32().IsWindow(hwnd)), "window handle valid before close")
    close_window(hwnd)
    try:
        code = proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        kill_tree(proc)
        code = -1
    check(code == 0, f"window close exits the app gracefully (code={code})")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and app_pids():
        time.sleep(0.3)
    check(not app_pids(), "app process (and one-file child) fully exited")
    check(
        not [w for w in all_app_windows() if w[3]],
        "no windows left behind",
    )

    settings = json.loads(
        (data_dir / "settings.json").read_text(encoding="utf-8")
    )
    check(
        settings.get("minimize_to_tray") is False,
        "close did not rewrite the minimize-to-tray preference",
    )
    check(
        bool(settings.get("window_geometry")),
        "window geometry was persisted on close",
    )

    # Keep the sandbox for the 'full' phase? It makes a fresh one; remove.
    shutil.rmtree(sandbox, ignore_errors=True)
    assert_real_data_untouched(real_before, "phase1")


def phase_full() -> None:
    set_dpi_aware()
    real_before = snapshot_real_data()
    sandbox = make_sandbox("full")
    marker = f"ECM_FULL_MARKER_{uuid.uuid4().hex[:8].upper()} ✓ «хвост»"
    info(f"sandbox: {sandbox}")

    proc = launch(sandbox)
    hwnd = wait_for_window(timeout=90)
    if not check(hwnd is not None, "launch: window appeared"):
        for w in all_app_windows():
            if w[3]:
                info(f"visible window of the app: title={w[1]!r} class={w[2]!r}")
        log_file = data_dir_of(sandbox) / "app.log"
        if log_file.exists():
            info("---- app.log ----")
            print(log_file.read_text(encoding="utf-8", errors="replace"))
        kill_tree(proc)
        return

    data_dir = data_dir_of(sandbox)
    set_clipboard(marker)
    db = data_dir / "history.db"
    deadline = time.monotonic() + 20
    found = 0
    while time.monotonic() < deadline:
        try:
            found = marker_rows(db, marker)
        except sqlite3.Error:
            found = 0
        if found:
            break
        time.sleep(0.5)
    check(found == 1, f"capture: marker stored exactly once (rows={found})")
    if not found:
        kill_tree(proc)
        return

    # --- UI copy-back: focus, click first row, press Return ---------------
    time.sleep(0.5)
    rect = window_rect(hwnd)
    shot = sandbox / "full-window.png"
    screenshot(shot, rect)
    info(f"screenshot before interaction: {shot}")

    import ctypes

    user32 = ctypes.windll.user32
    foreground_ok = bool(user32.SetForegroundWindow(hwnd))
    time.sleep(0.4)
    if not foreground_ok or user32.GetForegroundWindow() != hwnd:
        # Windows foreground-lock fallback: toggle Alt to release the lock.
        user32.keybd_event(0x12, 0, 0, 0)
        user32.keybd_event(0x12, 0, 2, 0)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.4)
    check(
        user32.GetForegroundWindow() == hwnd,
        "window can be brought to the foreground",
    )

    # First row of the list: below the title bar + toolbar, right of the
    # sidebar.  Calibrated against the phase1 screenshot of this layout.
    click_x = rect[0] + 300
    click_y = rect[1] + 150
    user32.SetCursorPos(click_x, click_y)
    time.sleep(0.2)
    user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
    user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP
    time.sleep(0.4)
    VK_RETURN = 0x0D
    user32.keybd_event(VK_RETURN, 0, 0, 0)
    user32.keybd_event(VK_RETURN, 0, 2, 0)
    time.sleep(0.6)

    clipboard_now = get_clipboard()
    copy_ok = check(
        clipboard_now == marker,
        "copy-back: Return copies the selected history entry to the clipboard",
    )
    if not copy_ok:
        info(f"clipboard contained: {clipboard_now!r}")
        screenshot(sandbox / "full-after-return.png", window_rect(hwnd))

    # The app's own write must not be re-captured (ignore_next fix).
    time.sleep(2.0)
    try:
        rows_after = marker_rows(db, marker)
    except sqlite3.Error:
        rows_after = -1
    check(
        rows_after == 1,
        f"no duplicate capture from our own copy (rows={rows_after})",
    )

    # --- Single instance + graceful exit ----------------------------------
    second = launch(sandbox)
    try:
        code = second.wait(timeout=20)
    except subprocess.TimeoutExpired:
        kill_tree(second)
        code = -1
    check(code == 0, f"single instance: second launch exits (code={code})")

    close_window(hwnd)
    try:
        code = proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        kill_tree(proc)
        code = -1
    check(code == 0, f"graceful exit after interaction (code={code})")

    # --- Restart persistence ----------------------------------------------
    proc2 = launch(sandbox)
    hwnd2 = wait_for_window(timeout=90)
    check(hwnd2 is not None, "restart: window appeared again")
    check(
        marker_rows(db, marker) == 1,
        "restart: captured entry persisted across restart",
    )
    close_window(hwnd2)
    try:
        code = proc2.wait(timeout=20)
    except subprocess.TimeoutExpired:
        kill_tree(proc2)
        code = -1
    check(code == 0, f"second graceful exit (code={code})")

    # --- Unicode + spaces in the data folder -------------------------------
    sandbox_u = make_sandbox("full_unicode", unicode_dir=True)
    proc3 = launch(sandbox_u)
    hwnd3 = wait_for_window(timeout=90)
    check(
        hwnd3 is not None,
        "unicode/space LOCALAPPDATA folder is supported",
    )
    du = data_dir_of(sandbox_u)
    check(
        du.exists() and (du / "history.db").exists(),
        f"data written into unicode folder ({du.name})",
    )
    close_window(hwnd3)
    try:
        code = proc3.wait(timeout=20)
    except subprocess.TimeoutExpired:
        kill_tree(proc3)
        code = -1
    check(code == 0, f"unicode scenario exits gracefully (code={code})")

    # Restore the user's clipboard ------------------------------------------
    original = phase_full._original_clipboard  # type: ignore[attr-defined]
    if original is not None:
        set_clipboard(original)
        info("original clipboard content restored")

    if copy_ok:
        shutil.rmtree(sandbox, ignore_errors=True)
    else:
        info(f"keeping sandbox for inspection: {sandbox}")
    shutil.rmtree(sandbox_u, ignore_errors=True)
    assert_real_data_untouched(real_before, "full")


def main() -> int:
    if not EXE.exists():
        print(f"Missing {EXE}; build first.", file=sys.stderr)
        return 2
    mode = sys.argv[1] if len(sys.argv) > 1 else "phase1"

    # Save the user's clipboard once so it can be put back at the end.
    original = get_clipboard()

    if mode == "phase1":
        try:
            phase1()
        finally:
            if original:
                set_clipboard(original)
    elif mode == "full":
        phase_full._original_clipboard = original  # type: ignore[attr-defined]
        phase_full()
    else:
        print(f"unknown mode {mode!r}", file=sys.stderr)
        return 2

    failed = [label for ok, label in RESULTS if not ok]
    print()
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        for label in failed:
            print(f"  FAILED: {label}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

@echo off
rem Build a standalone Windows executable with PyInstaller.
rem Run from the repository root:  packaging\build_windows.bat
setlocal
cd /d "%~dp0.."

where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo PyInstaller is not installed. Run:  pip install -r requirements-dev.txt
    exit /b 1
)

pyinstaller --noconfirm packaging\easy_clipboard.spec
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)

echo.
echo Build complete: dist\EasyClipboardManager\EasyClipboardManager.exe
endlocal

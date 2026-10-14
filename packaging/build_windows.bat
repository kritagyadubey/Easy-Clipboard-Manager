@echo off
rem Build the standalone single-file Windows executable with PyInstaller.
rem Run from the repository root:  packaging\build_windows.bat
setlocal
cd /d "%~dp0.."

where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo PyInstaller is not installed. Run:  pip install -r requirements-dev.txt
    exit /b 1
)

if not exist packaging\app.ico (
    echo Generating the application icon...
    python packaging\generate_icon.py
    if errorlevel 1 (
        echo Icon generation failed.
        exit /b 1
    )
)

pyinstaller --noconfirm --clean packaging\easy_clipboard.spec
if errorlevel 1 (
    echo Build failed.
    exit /b 1
)

echo.
echo Build complete: dist\EasyClipboardManager.exe
endlocal

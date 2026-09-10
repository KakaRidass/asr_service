@echo off
REM ============================================
REM File: setup.bat
REM Purpose: Windows launcher wrapper for setup.ps1
REM
REM Why this .bat exists:
REM   When you right-click a .ps1 and "Run with PowerShell", Windows
REM   uses a TEMP console that auto-closes when the script ends (or
REM   crashes). The user never sees the error.
REM   This .bat opens a PERSISTENT console window first, then runs
REM   the .ps1 inside it, so the window stays open until you press
REM   a key.
REM
REM Encoding:
REM   This file is saved as plain UTF-8 (NO BOM). cmd.exe does NOT
REM   skip a BOM in .bat files, so a BOM would corrupt the very
REM   first line and disable @echo off. All content is ASCII so
REM   GBK (cp936) decoding on Chinese Windows is a no-op.
REM ============================================

setlocal
cd /d "%~dp0"

echo =========================================
echo   Recording Transcript Service - Setup
echo =========================================
echo.
echo About to run setup.ps1 in a new PowerShell window.
echo You will see a GUI dialog asking for your DeepSeek API Key.
echo.
echo [TIP] If the new window closes too fast, check setup-error.log
echo       next to setup.ps1 for the full error trace.
echo.
pause

REM /WAIT: wait until the new window closes before exiting this launcher.
REM cmd /c + powershell.exe + "pause" inside the inner cmd keeps the
REM window alive even if the script crashes (trap in setup.ps1 also
REM calls pause before exit).
REM Build a single quoted command string. We deliberately call
REM powershell.exe via cmd /c so we can append "echo done + pause"
REM in the SAME persistent window. Using %~dp0 resolves to the
REM absolute directory of this .bat, ending with a backslash.
REM Note: there are no nested quotes around the path here. cmd
REM strips the outer "..." wrapping, so the inner path is left
REM bare — which is exactly what -File expects.
set "PS_CMD=powershell.exe -NoProfile -ExecutionPolicy Bypass -File %~dp0setup.ps1"
set "TAIL=echo. & echo *** setup.ps1 has exited *** & pause >nul"
start "Recording Transcript Service - Setup" /WAIT cmd /c "%PS_CMD% & %TAIL%"

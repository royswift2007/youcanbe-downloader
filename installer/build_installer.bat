@echo off
setlocal enabledelayedexpansion

set "ROOT=%~dp0.."
cd /d "%ROOT%"

echo [1/4] Cleaning previous setup output...
if not exist "dist-setup" mkdir "dist-setup"
del /q "dist-setup\YCB-Setup-v0.1.0.exe" 2>nul

echo [2/4] Building main application with [`YCB.spec`](YCB.spec)...
py -m PyInstaller --noconfirm "YCB.spec"
if errorlevel 1 goto :fail_main

echo [3/4] Building backend installer helper with [`backend_setup.spec`](backend_setup.spec)...
py -m PyInstaller --noconfirm "backend_setup.spec"
if errorlevel 1 goto :fail_backend

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC for %%I in (ISCC.exe) do set "ISCC=%%~$PATH:I"

if not defined ISCC goto :fail_iscc

echo [4/4] Compiling installer with [`installer/setup.iss`](installer/setup.iss)...
"%ISCC%" "installer\setup.iss"
if errorlevel 1 goto :fail_setup

echo.
echo Build completed successfully.
echo Output: "dist-setup\YCB-Setup-v0.1.0.exe"
goto :eof

:fail_main
echo.
echo [ERROR] Failed to build main application.
exit /b 1

:fail_backend
echo.
echo [ERROR] Failed to build backend installer helper.
exit /b 1

:fail_iscc
echo.
echo [ERROR] Inno Setup compiler [`ISCC.exe`](installer/build_installer.bat) was not found.
echo Install Inno Setup 6 or add [`ISCC.exe`](installer/build_installer.bat) to PATH.
exit /b 2

:fail_setup
echo.
echo [ERROR] Failed to compile installer script.
exit /b 3

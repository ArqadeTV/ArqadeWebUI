@echo off
rem Arqade setup for Windows.
rem   setup.bat             standard install (UI + PyTorch + TensorFlow + Transformers + ONNX + GGUF ...)
rem   setup.bat --lite      UI only (fast); add libraries later from the Libraries tab
rem   setup.bat --full      every supported AI library (large; failures are skipped, not fatal)
rem   setup.bat --no-run    install but don't launch
setlocal EnableExtensions
cd /d "%~dp0"

set "PROFILE=standard"
set "RUN=1"
:args
if "%~1"=="" goto args_done
if /i "%~1"=="--lite" set "PROFILE=lite"
if /i "%~1"=="--standard" set "PROFILE=standard"
if /i "%~1"=="--full" set "PROFILE=full"
if /i "%~1"=="--no-run" set "RUN=0"
shift
goto args
:args_done

rem Prefer 3.12/3.11 (best wheel coverage for TensorFlow & friends), accept anything >= 3.9.
set "PY="
for %%V in (3.12 3.11 3.13 3.10 3.9) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo [X] Python 3.9+ not found. Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^) and re-run.
  goto fail
)
echo ^> Using %PY%

if not exist ".venv\Scripts\python.exe" (
  echo ^> Creating virtual environment ^(.venv^)
  %PY% -m venv .venv
  if errorlevel 1 goto fail
)
set "VPY=.venv\Scripts\python.exe"

echo ^> Upgrading pip
"%VPY%" -m pip install --disable-pip-version-check -q --upgrade pip
if errorlevel 1 goto fail

echo ^> Installing the UI ^(core^)
"%VPY%" -m pip install --disable-pip-version-check -q -r requirements-core.txt
if errorlevel 1 goto fail

if /i not "%PROFILE%"=="lite" (
  echo ^> Installing AI libraries ^(profile: %PROFILE%^) - this can take a while
  "%VPY%" scripts\install_all.py --profile %PROFILE%
  if errorlevel 1 echo Some optional libraries failed; Arqade still works.
)

echo.
echo Setup complete!
if "%RUN%"=="1" (
  "%VPY%" -m arqade
) else (
  echo Start it any time with:  run.bat
)
endlocal
exit /b 0

:fail
echo.
echo Setup did not finish. See the messages above.
pause
endlocal
exit /b 1

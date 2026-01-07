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

echo Устанавливаем зависимости клиента...
python -m pip install -r requirements-client.txt
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
    --collect-all pyautogui ^
    --collect-all numpy ^
    client.py
if errorlevel 1 (
    echo Сборка завершилась с ошибкой.
    popd
    exit /b 1
)

echo.
echo Готово! Файл: dist\\RemoteControllerClient.exe
echo.

popd
endlocal

@echo off
setlocal enabledelayedexpansion

rem === Configurable settings ===
set "DEFAULT_REPO_DIR=remote_controller"
set "REPO_URL="

echo.
echo [Remote Controller] Windows setup
echo --------------------------------

rem Ensure Git is available (for cloning when repo files are missing).
where git >nul 2>nul
if errorlevel 1 (
    echo Git не найден. Пытаемся установить через winget...
    where winget >nul 2>nul
    if errorlevel 1 (
        echo winget не найден. Установите Git вручную и повторите запуск.
        exit /b 1
    )
    winget install --id Git.Git -e --source winget
)

rem Ensure Python is available.
where python >nul 2>nul
if errorlevel 1 (
    echo Python не найден. Пытаемся установить через winget...
    where winget >nul 2>nul
    if errorlevel 1 (
        echo winget не найден. Установите Python 3.11+ вручную и повторите запуск.
        exit /b 1
    )
    winget install --id Python.Python.3.11 -e --source winget
)

rem Determine working directory (either current repo or cloned repo).
set "SCRIPT_DIR=%~dp0"
set "WORK_DIR=%SCRIPT_DIR%"

if not exist "%SCRIPT_DIR%requirements.txt" (
    echo requirements.txt не найден рядом со скриптом.
    if not defined REPO_URL (
        echo Введите URL репозитория (например, https://github.com/org/repo.git):
        set /p REPO_URL=
    )
    if "%REPO_URL%"=="" (
        echo URL репозитория не задан. Завершение работы.
        exit /b 1
    )

    set "WORK_DIR=%SCRIPT_DIR%%DEFAULT_REPO_DIR%"
    if exist "%WORK_DIR%" (
        echo Каталог %WORK_DIR% уже существует. Используем его.
    ) else (
        echo Клонируем репозиторий в %WORK_DIR%...
        git clone "%REPO_URL%" "%WORK_DIR%"
        if errorlevel 1 (
            echo Не удалось клонировать репозиторий.
            exit /b 1
        )
    )
)

pushd "%WORK_DIR%"

rem Create virtual environment if missing.
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

echo Устанавливаем зависимости...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Установка зависимостей завершилась с ошибкой.
    popd
    exit /b 1
)

echo.
echo Готово! Чтобы запустить клиент на этом ПК:
echo   .venv\\Scripts\\python.exe client.py
echo Или:
echo   .venv\\Scripts\\python.exe -m remote_client.main
echo.

popd
endlocal

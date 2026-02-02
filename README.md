# Remote Controller

Remote Controller — система удалённого доступа к экрану и управлению компьютером через WebRTC.

## Компоненты

- `client/` — клиент удалённого доступа (захват экрана/аудио, управление вводом, файловые операции).
- `server/` — signaling‑сервер + REST API для операторской части, хранение статуса клиентов.
- `operator/` — web‑консоль оператора (браузерный WebRTC UI).
- `operator_desktop/` — десктоп‑клиент оператора (PyQt).

## Быстрый старт (Docker)

Рекомендуемый способ для сервера и web‑консоли:

```bash
cd server
./run.sh
```

Альтернатива (Windows/PowerShell):

```powershell
docker compose --project-directory server -f server/deploy/docker/docker-compose.yml up -d --build
```

После запуска:
- Web‑консоль: `http://localhost/`
- Signaling: `ws://localhost:8000/ws`

## Быстрый старт (ручной запуск)

### Общие зависимости (единый файл)

Самый простой способ — установить все зависимости сразу:

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Далее запускайте нужные компоненты из этой же среды.

> Примечание: в папках компонентов остаются локальные `requirements*.txt` для минимальных установок,
> но для стабильной работы всего проекта достаточно `requirements.txt` в корне.

### 1) Сервер (FastAPI)

```bash
cd server/app
pip install -r ../../requirements.txt
python signaling_server.py
```

### 2) Клиент

```bash
cd client
pip install -r ../requirements.txt
python client.py
```

### 3) Web‑оператор

Откройте `operator/index.html` в браузере или раздайте статикой (nginx/любая статика).

## Десктоп‑оператор (PyQt)

```bash
cd operator_desktop
pip install -r ../requirements.txt
python -m operator_desktop
```

## Сборка клиента в EXE (Windows)

```bat
cd client
build_windows.bat
```

Тихая сборка:

```bat
cd client
build_windows_silent.bat
```

Готовый файл появится в `client/dist/RemoteControllerClient.exe`.

## Конфигурация (ключевые переменные)

### Общие
- `RC_LOG_LEVEL` — уровень логов (`INFO`, `DEBUG` и т.д.).
- `RC_SIGNALING_URL` — полный URL signaling сервера (`ws(s)://.../ws`).
- `RC_SIGNALING_HOST`, `RC_SIGNALING_PORT` — хост/порт при отсутствии `RC_SIGNALING_URL`.
- `RC_SIGNALING_TOKEN` — токен signaling (рекомендуется всегда задавать).
- `RC_API_TOKEN` — токен REST API.

### Клиент
- `RC_SIGNALING_SESSION` — фиксированный `session_id` (если не задан, генерируется).
- `RC_DEVICE_TOKEN`, `RC_DEVICE_TOKEN_PATH` — токен устройства.
- `RC_E2EE_PASSPHRASE` или `RC_E2EE_KEY` — включение E2EE.
- `RC_ICE_SERVERS` — ICE‑серверы (JSON‑массив).
- `RC_CURSOR_MODE` — режим курсора: `independent` (скрытый desktop) или `shared` (обычный).
- `RC_ENABLE_HIDDEN_DESKTOP` — скрытый desktop (Windows, manage‑сессии), можно отключить через `0`.
- `RC_INPUT_STABILIZER` — стабилизация мыши (по умолчанию включена).
- `RC_PREFER_SENDINPUT` — предпочитать SendInput на Windows.

### Сервер
- `RC_DATABASE_URL` — PostgreSQL, если нужна регистрация клиентов/команд.
- `RC_SESSION_IDLE_TIMEOUT`, `RC_SESSION_CLEANUP_INTERVAL` — idle‑таймауты.
- `RC_TURN_HOST`, `RC_TURN_PORT`, `RC_TURN_USER`, `RC_TURN_PASSWORD` — TURN.
- `RC_INCLUDE_PUBLIC_STUN` — добавлять публичные STUN.
- `RC_ERROR_LOG_FILE` — файл для логов ошибок (по умолчанию `/data/logs/signaling-error.log` или `logs/signaling-error.log`).
- `RC_ERROR_LOG_LEVEL` — минимальный уровень для файла (`WARNING` по умолчанию).
- `RC_ERROR_LOG_MAX_BYTES`, `RC_ERROR_LOG_BACKUP_COUNT` — параметры ротации файла ошибок.

## E2EE

Если задан `RC_E2EE_PASSPHRASE/RC_E2EE_KEY` на клиенте, оператору нужно ввести тот же ключ в web‑консоли.

## Тесты

```bash
py -m pytest
```

## Безопасность

- Не используйте дефолтные токены в продакшене — задайте свои `RC_SIGNALING_TOKEN` и `RC_API_TOKEN`.
- При включённом anti‑fraud клиент может выполнить self‑uninstall при подозрении на VM/регион.

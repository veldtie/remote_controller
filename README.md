# Remote Controller

Проект предоставляет удалённый доступ к экрану и управлению компьютером через WebRTC.

## Используемые технологии

- **Python 3** — основной язык для клиентской части и сервера сигналинга.
- **aiortc** — реализация WebRTC в Python (создание peer connection, обмен SDP, медиа-треки).
- **FastAPI** — HTTP API для передачи offer/answer между браузером и клиентом.
- **Uvicorn** — ASGI-сервер для запуска FastAPI.
- **mss** — захват экрана для видео-трека.
- **av** — формирование видео/аудио кадров для WebRTC.
- **sounddevice** — захват аудио с микрофона.
- **pyautogui** — выполнение действий мыши и клавиатуры на стороне клиента.
- **HTML/JavaScript (WebRTC API)** — браузерный интерфейс для отображения видео и отправки управляющих событий.

## Структура программы

```
.
├── client/                     # Клиент удаленного доступа
│   ├── client.py               # Совместимый entrypoint для запуска клиента
│   ├── remote_client/          # Основной пакет клиента
│   │   ├── main.py             # Точка входа и сборка зависимостей
│   │   ├── media/              # Медиа-треки (экран, микрофон)
│   │   ├── control/            # Парсинг и выполнение команд управления
│   │   ├── files/              # Работа с файловой системой
│   │   ├── security/           # Проверки окружения (anti-fraud)
│   │   └── webrtc/             # Жизненный цикл WebRTC и сигналинг
│   ├── requirements-client.txt # Зависимости клиента
│   └── setup_windows.bat       # Установка клиента на Windows
├── server/                     # Сервер сигналинга + деплой
│   ├── signaling_server.py     # HTTP + WebSocket сигналинг для WebRTC
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── nginx.conf
│   ├── healthcheck.py
│   ├── requirements-signaling.txt
│   └── deploy/                 # systemd units и скрипты
├── operator/                   # Веб-интерфейс оператора
│   └── index.html
└── tests/                      # Тесты (если присутствуют)
```

## Порядок запуска программы

1. Установите зависимости клиента (пример):
   ```bash
   cd client
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements-client.txt
   ```
   Если `requirements-client.txt` отсутствует, установите зависимости вручную (aiortc, mss, av, sounddevice, pyautogui).

2. Запустите сервер сигналинга:
   ```bash
   cd server
   python signaling_server.py
   ```
   По умолчанию он слушает HTTP на `:8000` и WebSocket signaling на `:8000/ws`.

3. Запустите клиент (на машине, которой нужно управлять):
   ```bash
   cd client
   python client.py
   ```
   Или напрямую:
   ```bash
   python -m remote_client.main
   ```

4. Откройте `operator/index.html` в браузере и нажмите **Connect**.

## Сборка клиента в EXE (Windows)

Сборку нужно делать на Windows машине (PyInstaller не кросс-компилирует).

```bat
cd client
build_windows.bat
```

Готовый файл появится в `client/dist/RemoteControllerClient.exe`.

Тихий режим (для финальной сборки):
```bat
cd client
build_windows_silent.bat
```

## Скрипты для Ubuntu сервера

Скрипты лежат в `server/deploy/`:
- `add_root_ssh_key.sh` — добавить SSH-ключ в `/root/.ssh/authorized_keys`.
- `ubuntu_setup.sh` — первичная установка Docker/Compose и деплой.
- `ubuntu_update.sh` — обновление деплоя после правок.

## Подключение через интернет (не в локальной сети)

1. Разместите сервер сигналинга на публичном хосте и убедитесь, что порт доступен извне
   (например, `80/443` через reverse proxy или напрямую `8000`).
2. Укажите клиенту публичный URL сигналинга:
   - `RC_SIGNALING_URL=wss://your-domain.example` (если используется TLS)
   - или `RC_SIGNALING_URL=ws://<public-ip>:8000`
3. В браузерном интерфейсе укажите тот же публичный URL сервера в поле **Server URL**.
4. Для соединений через NAT/мобильные сети настройте TURN/ICE (см. `RC_ICE_SERVERS` ниже).

## Формат сообщений

### Сигналинг (WebSocket `/ws`)

Подключение выполняется с параметрами `session_id` и `role`:

```
ws://<host>:<port>/ws?session_id=<SESSION_ID>&role=browser|client&token=<TOKEN>
```

Токен также можно отправить в заголовке `x-rc-token`.

После открытия соединения стороны отправляют сообщение регистрации:

```json
{
  "type": "register",
  "session_id": "<SESSION_ID>",
  "role": "browser|client",
  "token": "<SIGNALING_TOKEN>",
  "device_token": "<DEVICE_TOKEN>"
}
```

Основные сообщения сигналинга:

```json
{ "type": "offer", "sdp": "..." }
{ "type": "answer", "sdp": "..." }
{ "type": "ice", "candidate": "...", "sdpMid": "0", "sdpMLineIndex": 0 }
```

### Управляющий канал (DataChannel `control`)

Сообщения управления отправляются как JSON с `action`:

```json
{ "action": "control", "type": "mouse_move", "x": 100, "y": 50 }
{ "action": "control", "type": "mouse_click", "x": 100, "y": 50, "button": "left" }
{ "action": "control", "type": "keypress", "key": "a" }
```

Файловые операции:

```json
{ "action": "list_files", "path": "." }
{ "action": "download", "path": "example.txt" }
```

Ответ на `list_files`:

```json
{ "files": [ { "name": "example.txt", "type": "file", "size": 123 } ] }
```

Ответ на `download`:

```json
"<base64-содержимое файла>"
```

## Запуск тестов

1. Установите зависимости (см. шаг 1 в разделе выше).
2. Активируйте виртуальное окружение, если используется:
   ```bash
   source .venv/bin/activate
   ```
3. Запустите полный набор тестов:
   ```bash
   python -m pytest
   ```
4. При необходимости запустите конкретный файл тестов:
   ```bash
   python -m pytest tests/test_client.py
   ```
5. Для более подробного вывода добавьте флаги:
   ```bash
   python -m pytest -v
   ```

### Полезные заметки по тестированию

- Все тесты собираются из директории `tests/`, а параметры запуска берутся из `pytest.ini`.
- Если тесты падают из-за отсутствующих зависимостей, проверьте установку `client/requirements-client.txt`.
- Если требуется изоляция окружения, используйте отдельную виртуальную среду и убедитесь, что активировали её перед запуском тестов.

## Дополнительные замечания

- Если нужно указать другой адрес сигналинга, используйте переменные окружения:
  - `RC_SIGNALING_HOST` (по умолчанию `localhost`)
  - `RC_SIGNALING_PORT` (по умолчанию `8000`)
  - `RC_SIGNALING_URL` (полный WebSocket-URL, например `wss://signaling.example.com/ws`)
    - При использовании `RC_SIGNALING_URL` переменные `RC_SIGNALING_HOST` и
      `RC_SIGNALING_PORT` игнорируются.
    - Поддерживаются схемы `ws`, `wss`, `http`, `https` (для HTTP будет выбран `ws`,
      для HTTPS — `wss`).
    - Можно указать базовый URL без `/ws` — клиент добавит его автоматически.
    - Query-параметры из URL будут сохранены и дополнены `session_id`/`role`/`token`.
- Для включения проверки токена используйте `RC_SIGNALING_TOKEN` на сервере и передавайте его клиентам:
  - Клиент может передавать токен через переменную окружения `RC_SIGNALING_TOKEN`.
  - Браузерный интерфейс принимает токен в поле **Token** и добавляет его в query-параметры.
- Если `RC_SIGNALING_TOKEN` не задан, можно задать `RC_SIGNALING_TOKEN_FILE` —
  сервер сгенерирует токен и сохранит его в файл (удобно для Docker volume).
- Клиент может генерировать и хранить постоянный токен устройства:
  - `RC_DEVICE_TOKEN` — явное значение токена устройства (если задано, файл не используется).
  - `RC_DEVICE_TOKEN_PATH` — путь к файлу токена (по умолчанию `~/.remote_controller/device_token`).
- Для задания ICE-серверов используйте `RC_ICE_SERVERS` (JSON-массив конфигураций). Пример:
  ```json
  [
    { "urls": ["stun:stun.l.google.com:19302"] },
    { "urls": ["turn:turn.example.com:3478"], "username": "user", "credential": "pass" }
  ]
  ```
  Сервер сигналинга выдаёт конфигурацию по `/ice-config`, браузерный интерфейс загружает её автоматически.
- Тайм-аут неактивности сессии настраивается через `RC_SESSION_IDLE_TIMEOUT` (секунды, по умолчанию 300).
  Если за это время нет сообщений от браузера или клиента, сервер закрывает WebSocket соединения и удаляет сессию.
  Проверка выполняется периодически с интервалом `RC_SESSION_CLEANUP_INTERVAL` (секунды, по умолчанию 30).
- Логи сервера сигналинга пишутся в stdout/stderr (uvicorn). В логах фиксируются подключения,
  отключения, ошибки WebSocket и срабатывания idle-timeout. Уровень логирования можно задать
  переменной `RC_LOG_LEVEL` (например, `INFO`, `DEBUG`).
- Идентификатор сессии можно задать через `RC_SIGNALING_SESSION` или флаг `--session-id`.
  Если нужен новый `session_id` при каждом запуске, не задавайте эти параметры.
- Для работы с мышью/клавиатурой требуется доступ к системному вводу (зависит от ОС).
- Захват экрана/аудио может потребовать разрешений ОС.

## Хранение устройств (PostgreSQL)

Сервер может сохранять данные устройств в PostgreSQL при получении сообщения `register` от роли
`client`, если задан `RC_DATABASE_URL`.

Переменные окружения:
- `RC_DATABASE_URL` — строка подключения (например, `postgresql://user:pass@db:5432/remote_controller`).
- `RC_TRUST_PROXY` — `true`, чтобы использовать `X-Forwarded-For` при работе за reverse proxy.
- `RC_DB_POOL_MIN`, `RC_DB_POOL_MAX` — размеры пула (по умолчанию 1 и 5).
- `RC_DB_CONNECT_RETRIES` — число попыток подключения (по умолчанию 5).
- `RC_DB_STATEMENT_CACHE_SIZE` — размер statement cache для asyncpg (по умолчанию 0 для совместимости с pgbouncer).

Схема таблицы:
```sql
CREATE TABLE device_registry (
  device_token TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  external_ip TEXT,
  status TEXT NOT NULL DEFAULT 'inactive',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Статусы устройств:
- `active` — клиент подключен и есть активный браузер в той же сессии.
- `inactive` — клиент подключен, но браузер не подключен.
- `disconnected` — клиент отключен от сигналинга.

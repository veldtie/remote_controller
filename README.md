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
├── client.py                   # Совместимый entrypoint для запуска клиента
├── signaling_server.py         # HTTP + TCP сигналинг для WebRTC
├── index.html                  # Веб-интерфейс (браузерный клиент)
├── remote_client/              # Основной пакет клиента
│   ├── main.py                 # Точка входа и сборка зависимостей
│   ├── media/                  # Медиа-треки (экран, микрофон)
│   │   ├── screen.py
│   │   └── audio.py
│   ├── control/                # Парсинг и выполнение команд управления
│   │   ├── handlers.py
│   │   └── input_controller.py
│   ├── files/                  # Работа с файловой системой
│   │   └── file_service.py
│   ├── security/               # Проверки окружения (anti-fraud)
│   │   └── anti_fraud.py
│   └── webrtc/                 # Жизненный цикл WebRTC и сигналинг
│       ├── client.py
│       └── signaling.py
└── tests/                      # Тесты (если присутствуют)
```

## Порядок запуска программы

1. Установите зависимости (пример):
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
   Если `requirements.txt` отсутствует, установите зависимости вручную (aiortc, fastapi, uvicorn, mss, av, sounddevice, pyautogui).

2. Запустите сервер сигналинга:
   ```bash
   python signaling_server.py
   ```
   По умолчанию он слушает HTTP на `:8000` и TCP signaling на `:9999`.

3. Запустите клиент (на машине, которой нужно управлять):
   ```bash
   python client.py
   ```
   Или напрямую:
   ```bash
   python -m remote_client.main
   ```

4. Откройте `index.html` в браузере и нажмите **Connect**.

## Формат сообщений

### Сигналинг (WebSocket `/ws`)

Подключение выполняется с параметрами `session_id` и `role`:

```
ws://<host>:<port>/ws?session_id=<SESSION_ID>&role=browser|client&token=<TOKEN>
```

Токен также можно отправить в заголовке `x-rc-token`.

После открытия соединения стороны отправляют сообщение регистрации:

```json
{ "type": "register", "session_id": "<SESSION_ID>", "role": "browser|client", "token": "<TOKEN>" }
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
- Если тесты падают из-за отсутствующих зависимостей, проверьте установку `requirements.txt`.
- Если требуется изоляция окружения, используйте отдельную виртуальную среду и убедитесь, что активировали её перед запуском тестов.

## Дополнительные замечания

- Если нужно указать другой адрес сигналинга, используйте переменные окружения:
  - `RC_SIGNALING_HOST` (по умолчанию `localhost`)
  - `RC_SIGNALING_PORT` (по умолчанию `9999`)
- Для включения проверки токена используйте `RC_SIGNALING_TOKEN` на сервере и передавайте его клиентам:
  - Клиент может передавать токен через переменную окружения `RC_SIGNALING_TOKEN`.
  - Браузерный интерфейс принимает токен в поле **Token** и добавляет его в query-параметры.
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
- Для работы с мышью/клавиатурой требуется доступ к системному вводу (зависит от ОС).
- Захват экрана/аудио может потребовать разрешений ОС.

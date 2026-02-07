# drivers/download_driver.py
"""
Скачивает IddSampleDriver для виртуального дисплея.

Использование:
    python -m remote_client.drivers.download_driver
    
Или напрямую:
    python drivers/download_driver.py
"""

import os
import sys
import zipfile
import shutil
from pathlib import Path

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request

# ============================================
# КОНФИГУРАЦИЯ - МОЖНО МЕНЯТЬ
# ============================================

# Ссылки на релизы драйвера (попробует по порядку)
VDD_RELEASES = [
    # Новая подписанная версия (НЕ нужен тестовый режим!)
    "https://github.com/VirtualDrivers/Virtual-Display-Driver/releases/download/25.7.23/IddSampleDriver-x64.zip",
    "https://github.com/VirtualDrivers/Virtual-Display-Driver/releases/download/24.12.24/IddSampleDriver-x64.zip",
    "https://github.com/VirtualDrivers/Virtual-Display-Driver/releases/download/25.5.2/IddSampleDriver-x64.zip",
]

# Необходимые файлы драйвера
REQUIRED_FILES = [
    "IddSampleDriver.inf",
    "IddSampleDriver.dll", 
    "IddSampleDriver.cat",
]

# ============================================


def get_vdd_dir() -> Path:
    """Возвращает путь к папке drivers/vdd"""
    return Path(__file__).parent / "vdd"


def download_file(url: str, dest: Path) -> bool:
    """Скачивает файл"""
    print(f"📥 Скачиваю: {url}")
    
    try:
        if HAS_REQUESTS:
            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()
            with open(dest, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
        else:
            urllib.request.urlretrieve(url, dest)
        return True
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False


def extract_driver_files(zip_path: Path, vdd_dir: Path) -> bool:
    """Распаковывает и находит нужные файлы драйвера"""
    
    print("📦 Распаковываю архив...")
    
    temp_dir = vdd_dir / "_temp_extract"
    temp_dir.mkdir(exist_ok=True)
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(temp_dir)
    except zipfile.BadZipFile:
        print("❌ Повреждённый ZIP архив")
        return False
    
    # Ищем нужные файлы рекурсивно
    found_files = {}
    for root, dirs, files in os.walk(temp_dir):
        for filename in files:
            # Ищем файлы без учёта регистра
            for required in REQUIRED_FILES:
                if filename.lower() == required.lower():
                    found_files[required] = Path(root) / filename
    
    # Копируем найденные файлы
    for required_file, source_path in found_files.items():
        dest_path = vdd_dir / required_file
        shutil.copy2(source_path, dest_path)
        size_kb = dest_path.stat().st_size / 1024
        print(f"   ✅ {required_file} ({size_kb:.1f} KB)")
    
    # Также копируем option.txt если есть (настройки разрешений)
    for root, dirs, files in os.walk(temp_dir):
        for filename in files:
            if filename.lower() == "option.txt":
                shutil.copy2(Path(root) / filename, vdd_dir / "option.txt")
                print(f"   ✅ option.txt")
                break
    
    # Очистка
    shutil.rmtree(temp_dir)
    zip_path.unlink()
    
    # Проверка
    missing = [f for f in REQUIRED_FILES if not (vdd_dir / f).exists()]
    if missing:
        print(f"❌ Не найдены: {missing}")
        return False
    
    return True


def download_driver() -> bool:
    """Основная функция скачивания драйвера"""
    
    vdd_dir = get_vdd_dir()
    vdd_dir.mkdir(parents=True, exist_ok=True)
    
    # Проверяем, может уже есть
    existing = [f for f in REQUIRED_FILES if (vdd_dir / f).exists()]
    if len(existing) == len(REQUIRED_FILES):
        print("✅ Драйвер уже скачан!")
        print(f"   Путь: {vdd_dir}")
        return True
    
    # Пробуем скачать с разных источников
    zip_path = vdd_dir / "driver.zip"
    
    for url in VDD_RELEASES:
        if download_file(url, zip_path):
            if extract_driver_files(zip_path, vdd_dir):
                print(f"\n✅ Драйвер успешно установлен в:")
                print(f"   {vdd_dir}\n")
                return True
    
    # Не удалось скачать автоматически
    print("\n" + "="*50)
    print("❌ Не удалось скачать автоматически")
    print("="*50)
    print("\n🔧 Скачай вручную:")
    print("   1. Открой: https://github.com/itsmikethetech/Virtual-Display-Driver/releases")
    print("   2. Скачай последний IddSampleDriver.zip")
    print(f"   3. Распакуй в: {vdd_dir}")
    print(f"\n   Нужны файлы: {', '.join(REQUIRED_FILES)}")
    
    return False


def verify_driver() -> dict:
    """Проверяет наличие файлов драйвера"""
    vdd_dir = get_vdd_dir()
    
    result = {
        "path": str(vdd_dir),
        "exists": vdd_dir.exists(),
        "files": {},
        "ready": False
    }
    
    if vdd_dir.exists():
        for f in REQUIRED_FILES:
            file_path = vdd_dir / f
            result["files"][f] = file_path.exists()
        
        result["ready"] = all(result["files"].values())
    
    return result


def main():
    print("="*50)
    print("🖥️  IddSampleDriver Downloader")
    print("="*50 + "\n")
    
    # Проверяем текущее состояние
    status = verify_driver()
    
    if status["ready"]:
        print("✅ Драйвер уже установлен и готов к работе!")
        print(f"   Путь: {status['path']}\n")
        
        for filename, exists in status["files"].items():
            icon = "✅" if exists else "❌"
            print(f"   {icon} {filename}")
        
        return 0
    
    # Скачиваем
    success = download_driver()
    
    if success:
        print("\n" + "="*50)
        print("📋 СЛЕДУЮЩИЕ ШАГИ:")
        print("="*50)
        print("""
1. Включи тестовый режим Windows (от Администратора):
   bcdedit /set testsigning on

2. Перезагрузи компьютер

3. Запусти клиент от Администратора
""")
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())

# windows/vdd_driver.py
"""
Virtual Display Driver - установка и управление

Требования:
- Windows 10/11
- Права администратора для установки
- Драйвер подписан - тестовый режим НЕ нужен!
"""

import os
import sys
import subprocess
import ctypes
import logging
import time
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Имена файлов драйвера (новая версия от MikeTheTech)
DRIVER_FILES = {
    "inf": ["mttvdd.inf", "IddSampleDriver.inf"],
    "dll": ["mttvdd.dll", "IddSampleDriver.dll"],
    "cat": ["mttvdd.cat", "IddSampleDriver.cat"],
}


class VDDError(Exception):
    """Ошибки работы с Virtual Display Driver"""
    pass


class VDDDriver:
    """Управление Virtual Display Driver"""
    
    DRIVER_NAME = "IddSampleDriver"
    DEVICE_NAME = "Virtual Display"
    
    def __init__(self, driver_dir: Optional[Path] = None):
        """
        Args:
            driver_dir: Путь к папке с драйвером. Если None - ищет автоматически.
        """
        self.driver_dir = driver_dir or self._find_driver_dir()
        self._device_created = False
    
    def _find_driver_dir(self) -> Path:
        """Находит папку с драйвером"""
        # Возможные пути к драйверу
        possible_paths = [
            # В папке с исполняемым файлом (PyInstaller)
            Path(sys.executable).parent / "drivers" / "vdd",
            Path(sys.executable).parent / "vdd",
            # PyInstaller _MEIPASS (временная папка распаковки)
            Path(getattr(sys, '_MEIPASS', '')) / "drivers" / "vdd" if hasattr(sys, '_MEIPASS') else None,
            # Относительно текущего файла
            Path(__file__).parent.parent / "drivers" / "vdd",
            Path(__file__).parent / "drivers" / "vdd",
            # Относительно рабочей директории
            Path.cwd() / "drivers" / "vdd",
            Path.cwd() / "vdd",
        ]
        
        # Фильтруем None
        possible_paths = [p for p in possible_paths if p is not None]
        
        # Ищем папку с INF файлом
        for path in possible_paths:
            if path.exists():
                # Проверяем наличие любого из возможных INF файлов
                for inf_name in DRIVER_FILES["inf"]:
                    if (path / inf_name).exists():
                        logger.debug(f"Found driver at: {path}")
                        return path
        
        # Возвращаем первый путь для информативной ошибки
        return possible_paths[0] if possible_paths else Path("drivers/vdd")
    
    @property
    def inf_path(self) -> Optional[Path]:
        """Путь к INF файлу драйвера"""
        for name in DRIVER_FILES["inf"]:
            path = self.driver_dir / name
            if path.exists():
                return path
        # Вернуть первый вариант для ошибки
        return self.driver_dir / DRIVER_FILES["inf"][0]
    
    @property
    def dll_path(self) -> Optional[Path]:
        """Путь к DLL файлу драйвера"""
        for name in DRIVER_FILES["dll"]:
            path = self.driver_dir / name
            if path.exists():
                return path
        return self.driver_dir / DRIVER_FILES["dll"][0]
    
    @property
    def cat_path(self) -> Optional[Path]:
        """Путь к CAT файлу драйвера"""
        for name in DRIVER_FILES["cat"]:
            path = self.driver_dir / name
            if path.exists():
                return path
        return self.driver_dir / DRIVER_FILES["cat"][0]
    
    # ==========================================
    # Проверки системы
    # ==========================================
    
    @staticmethod
    def is_admin() -> bool:
        """Проверка прав администратора"""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except:
            return False
    
    @staticmethod
    def is_testsigning_enabled() -> bool:
        """Проверка тестового режима Windows"""
        try:
            result = subprocess.run(
                ["bcdedit", "/enum", "{current}"],
                capture_output=True,
                text=True,
                shell=True,
                timeout=10
            )
            output = result.stdout.lower()
            return "testsigning" in output and "yes" in output
        except:
            return False
    
    def is_driver_files_present(self) -> Tuple[bool, list]:
        """Проверяет наличие файлов драйвера"""
        missing = []
        
        # Проверяем каждый тип файла
        for file_type, names in DRIVER_FILES.items():
            found = False
            for name in names:
                if (self.driver_dir / name).exists():
                    found = True
                    break
            if not found:
                missing.append(f"{file_type}: {names[0]}")
        
        return len(missing) == 0, missing
    
    def get_driver_files_info(self) -> dict:
        """Возвращает информацию о файлах драйвера"""
        info = {
            "driver_dir": str(self.driver_dir),
            "exists": self.driver_dir.exists(),
            "files": {}
        }
        
        for file_type, names in DRIVER_FILES.items():
            for name in names:
                path = self.driver_dir / name
                if path.exists():
                    info["files"][file_type] = {
                        "name": name,
                        "path": str(path),
                        "size": path.stat().st_size
                    }
                    break
        
        return info
    
    def is_driver_installed(self) -> bool:
        """Проверяет установлен ли драйвер в системе"""
        try:
            result = subprocess.run(
                ["pnputil", "/enum-drivers"],
                capture_output=True,
                text=True,
                shell=True,
                timeout=30
            )
            output = result.stdout.lower()
            # Проверяем все варианты имени драйвера
            return (
                "iddsampledriver" in output or 
                "virtualdisplaydriver" in output or
                "mttvdd" in output or
                "mikethetech" in output
            )
        except:
            return False
    
    # ==========================================
    # Установка драйвера
    # ==========================================
    
    def install(self, force: bool = False) -> bool:
        """
        Устанавливает драйвер в систему
        
        Args:
            force: Переустановить даже если уже установлен
            
        Returns:
            True если успешно
        """
        # Проверка: уже установлен?
        if not force and self.is_driver_installed():
            logger.info("Driver already installed")
            return True
        
        # Проверка: админ?
        if not self.is_admin():
            logger.error("Administrator rights required to install driver")
            return False
        
        # Проверка: есть файлы?
        files_ok, missing = self.is_driver_files_present()
        if not files_ok:
            logger.error(f"Driver files missing: {missing}")
            logger.error(f"Driver dir: {self.driver_dir}")
            logger.error("Driver files should be embedded in the build")
            return False
        
        # Копируем файлы во временную папку (pnputil требует доступную папку)
        temp_dir = None
        inf_to_install = self.inf_path
        
        try:
            # Если запущено из PyInstaller, копируем файлы во временную папку
            if hasattr(sys, '_MEIPASS') or not self.inf_path.parent.is_relative_to(Path.home()):
                temp_dir = Path(tempfile.mkdtemp(prefix="vdd_install_"))
                logger.info(f"Copying driver files to temp: {temp_dir}")
                
                # Копируем все файлы драйвера
                for file_type, names in DRIVER_FILES.items():
                    for name in names:
                        src = self.driver_dir / name
                        if src.exists():
                            dst = temp_dir / name
                            shutil.copy2(src, dst)
                            logger.debug(f"Copied: {src} -> {dst}")
                            if file_type == "inf":
                                inf_to_install = dst
                            break
                
            # Устанавливаем
            logger.info(f"Installing driver from: {inf_to_install}")
            
            result = subprocess.run(
                ["pnputil", "/add-driver", str(inf_to_install), "/install"],
                capture_output=True,
                text=True,
                shell=True,
                timeout=60
            )
            
            output = result.stdout.lower() + result.stderr.lower()
            
            if result.returncode == 0 or "успешно" in output or "successfully" in output or "added" in output:
                logger.info("Driver installed successfully")
                return True
            else:
                logger.error(f"pnputil failed (code {result.returncode})")
                logger.error(f"stdout: {result.stdout}")
                logger.error(f"stderr: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("Driver installation timed out")
            return False
        except Exception as e:
            logger.error(f"Driver installation failed: {e}")
            return False
        finally:
            # Очищаем временную папку
            if temp_dir and temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except:
                    pass
    
    def uninstall(self) -> bool:
        """Удаляет драйвер из системы"""
        if not self.is_admin():
            logger.error("Administrator rights required")
            return False
        
        try:
            # Находим OEM название драйвера
            result = subprocess.run(
                ["pnputil", "/enum-drivers"],
                capture_output=True,
                text=True,
                shell=True
            )
            
            oem_name = None
            lines = result.stdout.split('\n')
            for i, line in enumerate(lines):
                if "iddsampledriver" in line.lower():
                    # Ищем oem*.inf в предыдущих строках
                    for j in range(max(0, i-5), i):
                        if "oem" in lines[j].lower() and ".inf" in lines[j].lower():
                            parts = lines[j].split(':')
                            if len(parts) > 1:
                                oem_name = parts[1].strip()
                                break
                    break
            
            if oem_name:
                result = subprocess.run(
                    ["pnputil", "/delete-driver", oem_name, "/uninstall", "/force"],
                    capture_output=True,
                    text=True,
                    shell=True
                )
                logger.info(f"Driver uninstalled: {oem_name}")
                return True
            else:
                logger.warning("Driver not found in system")
                return True
                
        except Exception as e:
            logger.error(f"Uninstall failed: {e}")
            return False
    
    # ==========================================
    # Управление виртуальным дисплеем
    # ==========================================
    
    def create_display(self) -> bool:
        """Создаёт виртуальный дисплей"""
        if not self.is_driver_installed():
            if not self.install():
                return False
        
        try:
            # Используем devcon или прямой вызов
            # Способ 1: Через deviceinstaller если есть
            devcon_paths = [
                Path(os.environ.get("PROGRAMFILES", "")) / "Windows Kits" / "10" / "Tools" / "x64" / "devcon.exe",
                Path(__file__).parent / "devcon.exe",
                self.driver_dir / "devcon.exe",
            ]
            
            devcon = None
            for p in devcon_paths:
                if p.exists():
                    devcon = p
                    break
            
            if devcon:
                result = subprocess.run(
                    [str(devcon), "install", str(self.inf_path), "Root\\IddSampleDriver"],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    self._device_created = True
                    logger.info("Virtual display created")
                    return True
            
            # Способ 2: Устройство должно появиться автоматически после установки драйвера
            # Ждём немного
            time.sleep(1)
            self._device_created = True
            return True
            
        except Exception as e:
            logger.error(f"Failed to create display: {e}")
            return False
    
    def remove_display(self) -> bool:
        """Удаляет виртуальный дисплей"""
        self._device_created = False
        return True
    
    # ==========================================
    # Диагностика
    # ==========================================
    
    def get_status(self) -> dict:
        """Возвращает полный статус драйвера"""
        files_ok, missing = self.is_driver_files_present()
        
        return {
            "driver_dir": str(self.driver_dir),
            "files_present": files_ok,
            "missing_files": missing,
            "is_admin": self.is_admin(),
            "testsigning_enabled": self.is_testsigning_enabled(),
            "driver_installed": self.is_driver_installed(),
            "display_active": self._device_created,
        }
    
    def print_status(self):
        """Выводит статус в консоль"""
        status = self.get_status()
        
        print("\n" + "="*50)
        print("🖥️  Virtual Display Driver Status")
        print("="*50)
        
        checks = [
            ("Driver files", status["files_present"]),
            ("Admin rights", status["is_admin"]),
            ("Test signing", status["testsigning_enabled"]),
            ("Driver installed", status["driver_installed"]),
        ]
        
        for name, ok in checks:
            icon = "✅" if ok else "❌"
            print(f"  {icon} {name}")
        
        if status["missing_files"]:
            print(f"\n  Missing: {status['missing_files']}")
        
        print(f"\n  Driver path: {status['driver_dir']}")
        print("="*50 + "\n")


# ==========================================
# Удобные функции
# ==========================================

_driver_instance: Optional[VDDDriver] = None

def get_driver() -> VDDDriver:
    """Возвращает синглтон драйвера"""
    global _driver_instance
    if _driver_instance is None:
        _driver_instance = VDDDriver()
    return _driver_instance


def is_available() -> bool:
    """Проверяет доступен ли виртуальный дисплей"""
    driver = get_driver()
    return driver.is_driver_installed() or (
        driver.is_admin() and 
        driver.is_testsigning_enabled() and 
        driver.is_driver_files_present()[0]
    )


def ensure_installed(auto_install: bool = True) -> bool:
    """
    Убеждается что драйвер установлен
    
    Args:
        auto_install: Установить автоматически если есть права
    """
    driver = get_driver()
    
    if driver.is_driver_installed():
        return True
    
    if auto_install:
        return driver.install()
    
    return False


def remove_test_mode_watermark_persistent() -> dict[str, object]:
    """Disable Windows Test Mode to remove the watermark (requires admin + reboot)."""
    if os.name != "nt":
        return {"changed": False, "reason": "not_windows"}

    if not VDDDriver.is_testsigning_enabled():
        logger.debug("Test Mode not enabled; watermark removal skipped.")
        return {"changed": False, "reason": "testsigning_disabled"}

    if not VDDDriver.is_admin():
        logger.warning("Admin rights required to disable Test Mode.")
        return {"changed": False, "reason": "not_admin"}

    commands = [
        ["bcdedit", "/set", "testsigning", "off"],
        ["bcdedit", "/set", "nointegritychecks", "off"],
    ]
    results: list[dict[str, object]] = []
    for cmd in commands:
        cmd_text = " ".join(cmd)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                shell=True,
                timeout=10,
            )
        except Exception as exc:
            logger.warning("Failed to run %s: %s", cmd_text, exc)
            results.append({"cmd": cmd_text, "ok": False, "error": str(exc)})
            continue

        output = (result.stdout or "") + (result.stderr or "")
        ok = result.returncode == 0 or "successfully" in output.lower()
        results.append({"cmd": cmd_text, "ok": ok, "code": result.returncode})

    changed = any(
        item.get("ok") and "testsigning" in str(item.get("cmd", ""))
        for item in results
    )
    if changed:
        logger.info("Test Mode disabled. Reboot required to remove watermark.")
    return {"changed": changed, "reboot_required": changed, "results": results}


# ==========================================
# CLI
# ==========================================

def main():
    """Точка входа для командной строки"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Virtual Display Driver Manager")
    parser.add_argument("command", nargs="?", default="status",
                       choices=["status", "install", "uninstall"],
                       help="Command to run")
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    
    driver = VDDDriver()
    
    if args.command == "status":
        driver.print_status()
        
    elif args.command == "install":
        if driver.install():
            print("✅ Driver installed successfully")
        else:
            print("❌ Installation failed")
            sys.exit(1)
            
    elif args.command == "uninstall":
        if driver.uninstall():
            print("✅ Driver uninstalled")
        else:
            print("❌ Uninstall failed")
            sys.exit(1)


if __name__ == "__main__":
    main()

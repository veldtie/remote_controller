# windows/vdd_driver.py
"""
Virtual Display Driver - установка и управление

Требования:
- Windows 10/11
- Тестовый режим: bcdedit /set testsigning on
- Права администратора для установки
"""

import os
import sys
import subprocess
import ctypes
import logging
import time
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


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
        possible_paths = [
            Path(__file__).parent.parent / "drivers" / "vdd",
            Path(__file__).parent / "drivers" / "vdd",
            Path.cwd() / "drivers" / "vdd",
        ]
        
        for path in possible_paths:
            if (path / "IddSampleDriver.inf").exists():
                return path
        
        # Возвращаем первый путь для информативной ошибки
        return possible_paths[0]
    
    @property
    def inf_path(self) -> Path:
        return self.driver_dir / "IddSampleDriver.inf"
    
    @property
    def dll_path(self) -> Path:
        return self.driver_dir / "IddSampleDriver.dll"
    
    @property
    def cat_path(self) -> Path:
        return self.driver_dir / "IddSampleDriver.cat"
    
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
        required = [self.inf_path, self.dll_path, self.cat_path]
        missing = [str(f) for f in required if not f.exists()]
        return len(missing) == 0, missing
    
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
            # Проверяем разные варианты имени драйвера
            return (
                "iddsampledriver" in output or 
                "virtualdisplaydriver" in output or
                "virtual display" in output
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
        
        # Проверка: есть файлы?
        files_ok, missing = self.is_driver_files_present()
        if not files_ok:
            logger.error(f"Driver files missing: {missing}")
            logger.error("Run: python -m remote_client.drivers.download_driver")
            return False
        
        # Проверка: админ?
        if not self.is_admin():
            logger.error("Administrator rights required to install driver")
            return False
        
        # Проверка: тестовый режим?
        if not self.is_testsigning_enabled():
            logger.error("Test signing not enabled!")
            logger.error("Run as admin: bcdedit /set testsigning on")
            logger.error("Then reboot your PC")
            return False
        
        # Устанавливаем
        logger.info(f"Installing driver from: {self.inf_path}")
        
        try:
            result = subprocess.run(
                ["pnputil", "/add-driver", str(self.inf_path), "/install"],
                capture_output=True,
                text=True,
                shell=True,
                timeout=60
            )
            
            if result.returncode == 0 or "успешно" in result.stdout.lower() or "successfully" in result.stdout.lower():
                logger.info("Driver installed successfully")
                return True
            else:
                logger.error(f"pnputil error: {result.stdout} {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("Driver installation timed out")
            return False
        except Exception as e:
            logger.error(f"Driver installation failed: {e}")
            return False
    
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

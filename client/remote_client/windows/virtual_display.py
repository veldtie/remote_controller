# windows/virtual_display.py
"""
Высокоуровневый API для работы с виртуальным дисплеем
"""

import logging
from typing import Optional, Tuple

from .vdd_driver import VDDDriver, get_driver, is_available, ensure_installed

logger = logging.getLogger(__name__)


class VirtualDisplay:
    """
    Виртуальный дисплей для скрытого захвата экрана
    
    Использование:
        with VirtualDisplay() as display:
            # display.width, display.height
            # capture screen...
    """
    
    def __init__(
        self,
        width: int = 1920,
        height: int = 1080,
        refresh_rate: int = 60,
        auto_install: bool = True
    ):
        self.width = width
        self.height = height
        self.refresh_rate = refresh_rate
        self.auto_install = auto_install
        
        self._driver: Optional[VDDDriver] = None
        self._active = False
        self._fallback_mode = False
    
    def start(self) -> bool:
        """
        Запускает виртуальный дисплей
        
        Returns:
            True если запущен (включая fallback режим)
        """
        logger.info("Trying embedded VDD driver...")
        
        self._driver = get_driver()
        
        # Пробуем установить/использовать драйвер
        if ensure_installed(auto_install=self.auto_install):
            if self._driver.create_display():
                self._active = True
                logger.info("Virtual display started")
                return True
        
        # Fallback
        logger.warning("Embedded VDD failed, trying fallback methods")
        self._log_install_help()
        
        self._fallback_mode = True
        logger.warning("Virtual display not available, using fallback mode")
        return True  # Возвращаем True чтобы приложение работало в fallback
    
    def _log_install_help(self):
        """Выводит справку по установке"""
        logger.error(
            "Virtual Display Driver not available. Options:\n"
            "1. Run as Administrator for auto-install\n"
            "2. Install manually from: https://github.com/itsmikethetech/Virtual-Display-Driver\n"
            "3. Embed driver in build (see drivers/download_driver.py)"
        )
    
    def stop(self):
        """Останавливает виртуальный дисплей"""
        if self._driver and self._active:
            self._driver.remove_display()
        self._active = False
        self._fallback_mode = False
    
    @property
    def is_active(self) -> bool:
        """Активен ли виртуальный дисплей (не fallback)"""
        return self._active and not self._fallback_mode
    
    @property
    def is_fallback(self) -> bool:
        """Работает ли в режиме fallback"""
        return self._fallback_mode
    
    @property
    def resolution(self) -> Tuple[int, int]:
        """Текущее разрешение"""
        return (self.width, self.height)
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False


# ==========================================
# Быстрый доступ
# ==========================================

def create_virtual_display(
    width: int = 1920,
    height: int = 1080,
    auto_install: bool = True
) -> VirtualDisplay:
    """
    Создаёт и запускает виртуальный дисплей
    
    Args:
        width: Ширина в пикселях
        height: Высота в пикселях
        auto_install: Автоустановка драйвера (требует админ)
        
    Returns:
        VirtualDisplay instance
    """
    display = VirtualDisplay(width, height, auto_install=auto_install)
    display.start()
    return display


def check_virtual_display_available() -> dict:
    """
    Проверяет доступность виртуального дисплея
    
    Returns:
        dict со статусом всех проверок
    """
    driver = get_driver()
    return driver.get_status()

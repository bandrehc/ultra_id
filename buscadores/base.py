from __future__ import annotations
import time
from typing import Optional, Callable, Any

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException

TIMEOUTS = [2, 4, 6]
DELAY_BETWEEN = 0.15


def _build_driver(headless: bool = True, anti_bot: bool = False) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,900")
    opts.add_argument("--log-level=3")
    if anti_bot:
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
    else:
        opts.add_experimental_option("excludeSwitches", ["enable-logging"])

    driver = webdriver.Chrome(options=opts)

    if anti_bot:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"},
        )
        driver.execute_cdp_cmd("Page.setBypassCSP", {"enabled": True})

    return driver


class BaseBuscador:
    """Clase base con driver Chrome, retry 3-tier y context manager."""

    TIMEOUTS = TIMEOUTS

    def __init__(self, headless: bool = True, anti_bot: bool = False):
        self._headless = headless
        self._anti_bot = anti_bot
        self.driver: Optional[webdriver.Chrome] = None
        self._loaded = False

    def _ensure_driver(self):
        if self.driver is None:
            self.driver = _build_driver(self._headless, self._anti_bot)

    def _consultar_con_retry(
        self,
        fn: Callable[..., Optional[Any]],
        *args,
        **kwargs,
    ) -> Optional[Any]:
        for intento, timeout in enumerate(self.TIMEOUTS, start=1):
            try:
                resultado = fn(*args, timeout=timeout, **kwargs)
                if resultado is not None:
                    return resultado
                if intento == len(self.TIMEOUTS):
                    return None
                self._loaded = False
                time.sleep(0.05)
            except WebDriverException:
                if intento < len(self.TIMEOUTS):
                    self._loaded = False
                    time.sleep(0.05)
                else:
                    raise
        return None

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

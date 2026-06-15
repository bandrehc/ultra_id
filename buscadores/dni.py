"""DNI → edad y fecha de nacimiento (buscardniperu.com)"""
from __future__ import annotations
import time
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

from buscadores.base import BaseBuscador, DELAY_BETWEEN
from core.models import ResultadoDocumento

_URL    = "https://buscardniperu.com/como-saber-la-edad-por-dni/"
_INPUT  = "(//input)[1]"
_BUTTON = "(//button)[1]"
_TABLE  = "//table[1]"


class DNIBuscador(BaseBuscador):
    def __init__(self, headless: bool = True, delay: float = DELAY_BETWEEN):
        super().__init__(headless=headless, anti_bot=False)
        self.delay = delay

    def _consultar_una_vez(self, dni: str, timeout: int) -> Optional[dict]:
        self._ensure_driver()
        if not self._loaded:
            self.driver.get(_URL)
            self._loaded = True

        wait = WebDriverWait(self.driver, timeout)
        campo = wait.until(EC.presence_of_element_located((By.XPATH, _INPUT)))
        campo.clear()
        campo.send_keys(dni.strip())
        self.driver.find_element(By.XPATH, _BUTTON).click()
        tabla = wait.until(EC.presence_of_element_located((By.XPATH, _TABLE)))

        for fila in tabla.find_elements(By.TAG_NAME, "tr"):
            celdas = fila.find_elements(By.TAG_NAME, "td")
            if len(celdas) >= 2:
                try:
                    edad = int(celdas[0].text.strip().split()[0])
                except (ValueError, IndexError):
                    continue
                return {"edad": edad, "fecha_nacimiento": celdas[1].text.strip()}
        return None

    def consultar(self, resultado: ResultadoDocumento) -> ResultadoDocumento:
        dni = resultado.numero_documento
        for intento, timeout in enumerate(self.TIMEOUTS, start=1):
            try:
                r = self._consultar_una_vez(dni, timeout)
                if r:
                    resultado.dni_edad = r["edad"]
                    resultado.dni_fecha_nacimiento = r["fecha_nacimiento"]
                    return resultado
                if intento == len(self.TIMEOUTS):
                    resultado.error_dni = "Sin resultado en tabla"
                    return resultado
                self._loaded = False
                time.sleep(0.05)
            except TimeoutException:
                if intento < len(self.TIMEOUTS):
                    self._loaded = False
                    time.sleep(0.05)
                else:
                    resultado.error_dni = f"Timeout tras {intento} intentos"
            except (NoSuchElementException, WebDriverException) as exc:
                if intento < len(self.TIMEOUTS):
                    self._loaded = False
                    time.sleep(0.05)
                else:
                    resultado.error_dni = str(exc)[:120]
        return resultado

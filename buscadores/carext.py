"""Carnet de Extranjería → datos RREE (sistemasdgc.rree.gob.pe)"""
from __future__ import annotations
import time
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

from buscadores.base import BaseBuscador, DELAY_BETWEEN
from core.models import ResultadoDocumento

_URL = "https://sistemasdgc.rree.gob.pe/carext_consulta_webapp/"

# Selectores para el portal RREE.
# Actualizar si el sitio modifica ids/clases.
_SEL_INPUT   = "input[type='text'], input[id*='carnet' i], input[id*='ce' i], input[id*='numero' i], (//input)[1]"
_SEL_SUBMIT  = "input[type='submit'], button[type='submit'], button[id*='buscar' i], (//button)[1]"
_SEL_RESULT  = "[id*='result'], [id*='datos'], [id*='nombre'], table, .resultado"
_SEL_NO_RES  = "[class*='no-result'], [class*='error'], [class*='no-encontrado']"


class CarextBuscador(BaseBuscador):
    def __init__(self, headless: bool = True, delay: float = DELAY_BETWEEN):
        super().__init__(headless=headless, anti_bot=False)
        self.delay = delay

    def _load_page(self):
        self._ensure_driver()
        self.driver.get(_URL)
        WebDriverWait(self.driver, 15).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        self._loaded = True

    def _consultar_una_vez(self, ce: str, timeout: int) -> Optional[dict]:
        if not self._loaded:
            self._load_page()

        wait = WebDriverWait(self.driver, timeout)

        # Localizar campo de entrada (XPath como fallback)
        try:
            inp = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR,
                "input[type='text'], input[id*='carnet' i], input[id*='ce' i], input[id*='numero' i]"
            )))
        except TimeoutException:
            try:
                inp = wait.until(EC.presence_of_element_located((By.XPATH, "(//input)[1]")))
            except TimeoutException:
                return None

        inp.clear()
        inp.send_keys(ce.strip())

        try:
            btn = self.driver.find_element(By.CSS_SELECTOR,
                "input[type='submit'], button[type='submit'], button[id*='buscar' i]"
            )
            btn.click()
        except NoSuchElementException:
            try:
                btn = self.driver.find_element(By.XPATH, "(//button)[1]")
                btn.click()
            except NoSuchElementException:
                inp.send_keys(Keys.RETURN)

        # Esperar respuesta
        try:
            wait.until(
                lambda d:
                d.find_elements(By.CSS_SELECTOR, _SEL_RESULT) or
                "no se encontr" in d.page_source.lower() or
                "sin resultado" in d.page_source.lower() or
                "no existe" in d.page_source.lower()
            )
        except TimeoutException:
            return None

        page = self.driver.page_source.lower()
        if any(x in page for x in ("no se encontr", "sin resultado", "no existe", "no registrado")):
            self._loaded = False
            return {
                "carext_apellidos": None,
                "carext_nombres": None,
                "carext_nacionalidad": None,
                "carext_estado_carnet": "NO ENCONTRADO",
            }

        # Extraer datos — intentar varios patrones de presentación
        apellidos = nombres = nacionalidad = estado = None

        # Patrón tabla (filas clave-valor o columnas)
        tablas = self.driver.find_elements(By.TAG_NAME, "table")
        for tabla in tablas:
            filas = tabla.find_elements(By.TAG_NAME, "tr")
            for fila in filas:
                celdas = fila.find_elements(By.TAG_NAME, "td")
                if len(celdas) >= 2:
                    lbl = celdas[0].text.strip().lower()
                    val = celdas[1].text.strip() or None
                    if "apellido" in lbl:
                        apellidos = val
                    elif "nombre" in lbl and "apellido" not in lbl:
                        nombres = val
                    elif "nacional" in lbl:
                        nacionalidad = val
                    elif "estado" in lbl or "vigencia" in lbl:
                        estado = val

        # Patrón alternativo: spans o divs con labels
        if not apellidos:
            for el in self.driver.find_elements(By.CSS_SELECTOR, "span, div, label, p"):
                txt = el.text.strip().lower()
                if "apellidos:" in txt or "apellido:" in txt:
                    apellidos = txt.split(":", 1)[-1].strip() or apellidos

        self._loaded = False
        self.driver.get(_URL)
        self._loaded = True

        return {
            "carext_apellidos":     apellidos,
            "carext_nombres":       nombres,
            "carext_nacionalidad":  nacionalidad,
            "carext_estado_carnet": estado or "ENCONTRADO",
        }

    def consultar(self, resultado: ResultadoDocumento) -> ResultadoDocumento:
        ce = resultado.numero_documento
        for intento, timeout in enumerate(self.TIMEOUTS, start=1):
            try:
                r = self._consultar_una_vez(ce, timeout)
                if r is not None:
                    for campo, valor in r.items():
                        if hasattr(resultado, campo):
                            setattr(resultado, campo, valor)
                    return resultado
                if intento == len(self.TIMEOUTS):
                    resultado.error_carext = "Timeout al consultar RREE"
                    return resultado
                self._loaded = False
                time.sleep(0.05)
            except (TimeoutException, NoSuchElementException, WebDriverException) as exc:
                if intento < len(self.TIMEOUTS):
                    self._loaded = False
                    time.sleep(0.05)
                else:
                    resultado.error_carext = str(exc)[:120]
        return resultado

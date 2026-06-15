"""RUC → Registro de Sujeto Obligado SBS/UIF (sbs.gob.pe/app/uif/voc/)"""
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

_URL = "https://www.sbs.gob.pe/app/uif/voc/"

# Selectores para el formulario y resultados.
# La página SBS usa ASP.NET WebForms o similar.
# Actualizar si el sitio modifica su estructura.
_SEL_INPUT   = "input[type='text'], #txtRUC, input[id*='ruc' i], input[id*='RUC']"
_SEL_SUBMIT  = "input[type='submit'], button[type='submit'], #btnBuscar, button[id*='buscar' i]"
_SEL_TABLA   = "table, #gvResultados, [id*='Grid'], [id*='grid']"
_SEL_NO_RES  = "[class*='no-result'], [class*='sin-resultado']"


class SbsBuscador(BaseBuscador):
    def __init__(self, headless: bool = True, delay: float = DELAY_BETWEEN):
        super().__init__(headless=headless, anti_bot=True)
        self.delay = delay

    def _load_page(self):
        self._ensure_driver()
        self.driver.get(_URL)
        WebDriverWait(self.driver, 15).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        self._loaded = True

    def _consultar_una_vez(self, ruc: str, timeout: int) -> Optional[dict]:
        if not self._loaded:
            self._load_page()

        wait = WebDriverWait(self.driver, timeout)

        # Localizar campo de búsqueda (varios ids posibles)
        try:
            inp = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, _SEL_INPUT)))
        except TimeoutException:
            return None

        inp.clear()
        inp.send_keys(ruc.strip())

        # Intentar submit button; fallback a Enter
        try:
            btn = self.driver.find_element(By.CSS_SELECTOR, _SEL_SUBMIT)
            btn.click()
        except NoSuchElementException:
            inp.send_keys(Keys.RETURN)

        # Esperar resultados o mensaje de no encontrado
        try:
            wait.until(
                lambda d:
                d.find_elements(By.CSS_SELECTOR, _SEL_TABLA) or
                d.find_elements(By.CSS_SELECTOR, _SEL_NO_RES) or
                "no se encontr" in d.page_source.lower() or
                "sin resultado" in d.page_source.lower()
            )
        except TimeoutException:
            return None

        page = self.driver.page_source.lower()
        if "no se encontr" in page or "sin resultado" in page:
            self._loaded = False  # recargar para próxima consulta
            self.driver.get(_URL)
            self._loaded = True
            return {"sbs_registrado": False, "sbs_nombre": None,
                    "sbs_tipo_sujeto": None, "sbs_estado": "NO REGISTRADO"}

        # Parsear tabla de resultados
        tablas = self.driver.find_elements(By.CSS_SELECTOR, _SEL_TABLA)
        nombre = tipo = estado = None
        for tabla in tablas:
            filas = tabla.find_elements(By.TAG_NAME, "tr")
            for fila in filas[1:]:  # saltar encabezado
                celdas = fila.find_elements(By.TAG_NAME, "td")
                if len(celdas) >= 2:
                    # Heurística: primera fila con datos útiles
                    nombre = nombre or celdas[0].text.strip() or None
                    tipo   = tipo   or (celdas[1].text.strip() if len(celdas) > 1 else None)
                    estado = estado or (celdas[2].text.strip() if len(celdas) > 2 else None)
                    if nombre:
                        break
            if nombre:
                break

        self._loaded = False
        self.driver.get(_URL)
        self._loaded = True

        return {
            "sbs_registrado": True,
            "sbs_nombre":     nombre,
            "sbs_tipo_sujeto": tipo,
            "sbs_estado":     estado,
        }

    def consultar(self, resultado: ResultadoDocumento) -> ResultadoDocumento:
        ruc = resultado.numero_documento
        for intento, timeout in enumerate(self.TIMEOUTS, start=1):
            try:
                r = self._consultar_una_vez(ruc, timeout)
                if r is not None:
                    for campo, valor in r.items():
                        if hasattr(resultado, campo):
                            setattr(resultado, campo, valor)
                    return resultado
                if intento == len(self.TIMEOUTS):
                    resultado.sbs_registrado = False
                    resultado.error_sbs = "Timeout al consultar SBS/UIF"
                    return resultado
                self._loaded = False
                time.sleep(0.05)
            except (TimeoutException, NoSuchElementException, WebDriverException) as exc:
                if intento < len(self.TIMEOUTS):
                    self._loaded = False
                    time.sleep(0.05)
                else:
                    resultado.error_sbs = str(exc)[:120]
        return resultado

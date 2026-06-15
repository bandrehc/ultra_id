"""RUC → Registro Nacional de Proveedores OSCE (apps.osce.gob.pe)"""
from __future__ import annotations
import re
import time
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

from buscadores.base import BaseBuscador, DELAY_BETWEEN
from core.models import ResultadoDocumento

_BASE_URL = "https://apps.osce.gob.pe/perfilprov-ui/ficha/{ruc}"

# Selectores CSS para la SPA de OSCE (React).
# Si la SPA cambia su estructura, actualizar estos selectores.
_SEL_NOMBRE       = "[class*='proveedor'] h1, [class*='nombre'], h1.titulo-proveedor"
_SEL_ESTADO       = "[class*='estado'], [class*='habilitacion'], .chip-estado"
_SEL_TIPO         = "[class*='tipo-proveedor'], [class*='categoria']"
_SEL_NO_REG       = "[class*='no-registrado'], [class*='not-found'], [class*='sin-resultado']"
_SEL_PENALIDADES  = "[class*='penalidad'] [class*='count'], [class*='penalidad'] span.numero"
_SEL_SANCIONES    = "[class*='sancion'] [class*='count'], [class*='sancion'] span.numero"
_SEL_INHABILITACION = "[class*='inhabilitacion'] [class*='count'], [class*='inhabilitacion'] span.numero"

# Selector de espera: cualquier elemento que indique carga completa
_SEL_LOADED = "[class*='proveedor'], [class*='no-registrado'], [class*='not-found'], [class*='error-page']"


def _parse_int(texto: str) -> Optional[int]:
    m = re.search(r"\d+", texto or "")
    return int(m.group()) if m else None


class OsceBuscador(BaseBuscador):
    def __init__(self, headless: bool = True, delay: float = DELAY_BETWEEN):
        super().__init__(headless=headless, anti_bot=True)
        self.delay = delay

    def _consultar_una_vez(self, ruc: str, timeout: int) -> Optional[dict]:
        self._ensure_driver()
        url = _BASE_URL.format(ruc=ruc.strip())
        self.driver.get(url)

        wait = WebDriverWait(self.driver, max(timeout, 8))
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, _SEL_LOADED)))
        except TimeoutException:
            return None

        # Verificar si el RUC no está registrado
        no_reg = self.driver.find_elements(By.CSS_SELECTOR, _SEL_NO_REG)
        page_src = self.driver.page_source.lower()
        if no_reg or "no registrado" in page_src or "no se encontr" in page_src:
            return {
                "osce_registrado": False,
                "osce_nombre_proveedor": None,
                "osce_estado_rns": "NO REGISTRADO",
                "osce_tipo_proveedor": None,
                "osce_n_penalidades": 0,
                "osce_n_sanciones": 0,
                "osce_n_inhabilitaciones": 0,
                "osce_detalle_url": url,
            }

        def _text(sel: str) -> str:
            els = self.driver.find_elements(By.CSS_SELECTOR, sel)
            return els[0].text.strip() if els else ""

        nombre     = _text(_SEL_NOMBRE)
        estado     = _text(_SEL_ESTADO)
        tipo       = _text(_SEL_TIPO)
        pen_txt    = _text(_SEL_PENALIDADES)
        san_txt    = _text(_SEL_SANCIONES)
        inhab_txt  = _text(_SEL_INHABILITACION)

        return {
            "osce_registrado":       bool(nombre or estado),
            "osce_nombre_proveedor": nombre or None,
            "osce_estado_rns":       estado or None,
            "osce_tipo_proveedor":   tipo or None,
            "osce_n_penalidades":    _parse_int(pen_txt),
            "osce_n_sanciones":      _parse_int(san_txt),
            "osce_n_inhabilitaciones": _parse_int(inhab_txt),
            "osce_detalle_url":      url,
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
                    resultado.osce_registrado = False
                    resultado.error_osce = "Timeout: no se pudo cargar la ficha OSCE"
                    return resultado
                time.sleep(0.05)
            except (TimeoutException, NoSuchElementException, WebDriverException) as exc:
                if intento < len(self.TIMEOUTS):
                    time.sleep(0.05)
                else:
                    resultado.error_osce = str(exc)[:120]
        return resultado

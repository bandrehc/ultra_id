"""RUC → estado REINFO (pad.minem.gob.pe) — registro minero MINEM"""
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

_URL       = "https://pad.minem.gob.pe/REINFO_WEB/Index.aspx"
_INPUT_RUC = '//*[@id="txtruc"]'

_SPANS = {
    "reinfo_nombre":          "stdregistro_lblgnomcompleto_0",
    "reinfo_codigo_derecho":  "stdregistro_lblgidunidad_0",
    "reinfo_nombre_derecho":  "stdregistro_lblgderecho_0",
    "reinfo_departamento":    "stdregistro_lblgdepartamento_0",
    "reinfo_provincia":       "stdregistro_lblgprovincia_0",
    "reinfo_distrito":        "stdregistro_lblgdistrito_0",
    "reinfo_estado":          "stdregistro_lblgglfvigente_0",
    "_ruc_check":             "stdregistro_lblgruc_0",
}


class ReinfoBuscador(BaseBuscador):
    def __init__(self, headless: bool = True, delay: float = DELAY_BETWEEN):
        super().__init__(headless=headless, anti_bot=False)
        self.delay = delay

    def _load_page(self):
        self._ensure_driver()
        self.driver.get(_URL)
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.XPATH, _INPUT_RUC))
        )
        self._loaded = True

    def _consultar_una_vez(self, ruc: str, timeout: int) -> Optional[dict]:
        if not self._loaded:
            self._load_page()

        wait = WebDriverWait(self.driver, timeout)
        campo = wait.until(EC.element_to_be_clickable((By.XPATH, _INPUT_RUC)))

        try:
            old_span = self.driver.find_element(By.ID, _SPANS["_ruc_check"])
        except NoSuchElementException:
            old_span = None

        campo.clear()
        campo.send_keys(ruc.strip())
        campo.send_keys(Keys.RETURN)

        try:
            btn = self.driver.find_element(
                By.CSS_SELECTOR, 'input[type="submit"], button[type="submit"]'
            )
            btn.click()
        except NoSuchElementException:
            pass

        if old_span is not None:
            try:
                WebDriverWait(self.driver, min(timeout, 2)).until(
                    EC.staleness_of(old_span)
                )
            except TimeoutException:
                pass

        try:
            wait.until(
                EC.text_to_be_present_in_element(
                    (By.ID, _SPANS["_ruc_check"]), ruc.strip()
                )
            )
        except TimeoutException:
            return None

        data = {}
        for campo_dest, span_id in _SPANS.items():
            if campo_dest == "_ruc_check":
                continue
            try:
                el = self.driver.find_element(By.ID, span_id)
                data[campo_dest] = el.text.strip()
            except NoSuchElementException:
                data[campo_dest] = ""

        estado = data.get("reinfo_estado", "").upper()
        if "VIGENTE" in estado:
            data["reinfo_estado"] = "VIGENTE"
        elif "EXCLUIDO" in estado:
            data["reinfo_estado"] = "EXCLUIDO"

        return data if any(data.values()) else None

    def consultar(self, resultado: ResultadoDocumento) -> ResultadoDocumento:
        ruc = resultado.numero_documento
        for intento, timeout in enumerate(self.TIMEOUTS, start=1):
            try:
                r = self._consultar_una_vez(ruc, timeout)
                if r is not None:
                    for campo, valor in r.items():
                        if hasattr(resultado, campo):
                            setattr(resultado, campo, valor)
                    if not resultado.reinfo_estado:
                        resultado.reinfo_estado = "NO_REGISTRADO"
                    return resultado
                if intento == len(self.TIMEOUTS):
                    resultado.reinfo_estado = "NO_REGISTRADO"
                    resultado.error_reinfo = "RUC no encontrado en REINFO"
                    return resultado
                self._loaded = False
                time.sleep(0.05)
            except (TimeoutException, NoSuchElementException, WebDriverException) as exc:
                if intento < len(self.TIMEOUTS):
                    self._loaded = False
                    time.sleep(0.05)
                else:
                    resultado.reinfo_estado = "ERROR"
                    resultado.error_reinfo = str(exc)[:120]
        return resultado

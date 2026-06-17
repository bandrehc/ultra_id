"""RUC → datos de empresa (universidadperu.com)"""
from __future__ import annotations
import time
from datetime import date, datetime
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from bs4 import BeautifulSoup

from buscadores.base import BaseBuscador, DELAY_BETWEEN
from core.models import ResultadoDocumento

_URL        = "https://www.universidadperu.com/empresas/busqueda/"
_XPATH_INPUT = '//*[@id="buscaempresa1"]'
_TIMEOUT_NAV = 12
_CAMPOS = {
    "RUC":                      "ruc_razon_social",
    "Razón Social":             "ruc_razon_social",
    "Nombre Comercial":         "ruc_nombre_comercial",
    "Tipo Empresa":             "ruc_tipo_empresa",
    "Condición":                "ruc_condicion",
    "Fecha Inicio Actividades": "ruc_fecha_inicio",
    "Dirección Legal":          "ruc_direccion",
    "Urbanizacion":             "ruc_urbanizacion",
    "Distrito / Ciudad":        "ruc_distrito",
    "Departamento":             "ruc_departamento",
    "Estado Domicilio":         "ruc_estado_domicilio",
}


def _anos_desde(fecha_str: str) -> Optional[int]:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            inicio = datetime.strptime(fecha_str.strip(), fmt).date()
            hoy = date.today()
            anos = hoy.year - inicio.year - ((hoy.month, hoy.day) < (inicio.month, inicio.day))
            return max(0, anos)
        except ValueError:
            continue
    return None


def _parsear_html(html: str) -> Optional[dict]:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    if h1 and "No hay ninguna empresa" in h1.text:
        return None

    data: dict = {}
    for dt in soup.select("#infoempresa dl dt"):
        label = dt.get_text(strip=True)
        dd = dt.find_next_sibling("dd")
        if not dd:
            continue
        campo = _CAMPOS.get(label)
        if campo:
            data[campo] = dd.get_text(" ", strip=True)

    if not data:
        return None
    if "ruc_fecha_inicio" in data:
        anos = _anos_desde(data["ruc_fecha_inicio"])
        if anos is not None:
            data["ruc_anos_actividad"] = anos
    return data


class RucBuscador(BaseBuscador):
    def __init__(self, headless: bool = True, delay: float = DELAY_BETWEEN):
        super().__init__(headless=headless, anti_bot=True)
        self.delay = delay

    def _consultar_una_vez(self, ruc: str, timeout: int) -> Optional[dict]:
        self._ensure_driver()
        wait = WebDriverWait(self.driver, max(timeout, 15))

        if _URL not in self.driver.current_url:
            self.driver.get(_URL)

        try:
            inp = wait.until(EC.presence_of_element_located((By.XPATH, _XPATH_INPUT)))
        except TimeoutException:
            return None

        inp.clear()
        inp.send_keys(ruc.strip())
        inp.send_keys(Keys.RETURN)

        try:
            WebDriverWait(self.driver, _TIMEOUT_NAV).until(
                lambda d: d.current_url != _URL
                or d.find_elements(By.CSS_SELECTOR, "#infoempresa")
                or d.find_elements(By.XPATH, "//h1[contains(text(),'No hay')]")
            )
        except TimeoutException:
            return None

        html = self.driver.page_source
        resultado = _parsear_html(html)
        self.driver.get(_URL)
        return resultado

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
                    resultado.error_ruc = "RUC no encontrado en universidadperu.com"
                    return resultado
                self._loaded = False
                time.sleep(0.05)
            except (TimeoutException, WebDriverException) as exc:
                if intento < len(self.TIMEOUTS):
                    self._loaded = False
                    time.sleep(0.05)
                else:
                    resultado.error_ruc = str(exc)[:120]
        return resultado

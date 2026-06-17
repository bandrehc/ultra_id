"""RUC → Registro de Sujeto Obligado SBS/UIF (sbs.gob.pe/app/uif/voc/)

Formulario ASP.NET WebForms con postback. Flujo:
  1. Cargar página, esperar que esté disponible #txtRuc
  2. Ingresar RUC, click en botón de búsqueda
  3. Esperar que aparezca #divResultado (postback completo)
  4. Detectar "no encontrado" vía span#rptResultao_ctl00_lblMensajeVacio
     (typo intencionado — así se llama el elemento en el HTML del sitio)
  5. Si encontrado: parsear tabla #tblResultado (columnas: RUC, Razón social, Resultado)
  6. Recargar página limpia para la próxima consulta
"""
from __future__ import annotations
import time
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

from buscadores.base import BaseBuscador, DELAY_BETWEEN
from core.models import ResultadoDocumento

_URL = "https://www.sbs.gob.pe/app/uif/voc/"

# XPaths exactos provistos por el usuario
_XPATH_INPUT  = '//*[@id="txtRuc"]'
_XPATH_BOTON  = '//*[@id="divBusqueda"]/div[2]/div/button'

# Selectores para detectar el estado del resultado
_CSS_RESULTADO_DIV = "#divResultado"
_CSS_VACIO_SPAN    = "span[id*='lblMensajeVacio']"  # "rptResultao_ctl00_lblMensajeVacio" (typo del sitio)
_XPATH_TABLA       = '//*[@id="tblResultado"]'

_TEXTO_NO_REG = "no se encuentra registrado como sujeto obligado"


class SbsBuscador(BaseBuscador):
    def __init__(self, headless: bool = True, delay: float = DELAY_BETWEEN):
        super().__init__(headless=headless, anti_bot=True)
        self.delay = delay

    def _load_page(self) -> bool:
        self._ensure_driver()
        self.driver.get(_URL)
        try:
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.XPATH, _XPATH_INPUT))
            )
            self._loaded = True
            return True
        except TimeoutException:
            return False

    def _consultar_una_vez(self, ruc: str, timeout: int) -> Optional[dict]:
        if not self._loaded:
            if not self._load_page():
                return None

        wait = WebDriverWait(self.driver, max(timeout, 8))

        try:
            inp = wait.until(EC.presence_of_element_located((By.XPATH, _XPATH_INPUT)))
        except TimeoutException:
            self._loaded = False
            return None

        inp.clear()
        inp.send_keys(ruc.strip())

        try:
            btn = self.driver.find_element(By.XPATH, _XPATH_BOTON)
            btn.click()
        except (NoSuchElementException, WebDriverException):
            self._loaded = False
            return None

        # Esperar postback: #divResultado aparece tras la respuesta del servidor
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, _CSS_RESULTADO_DIV)))
        except TimeoutException:
            self._loaded = False
            return None

        # "No encontrado": el span de mensaje vacío está presente con texto relevante
        no_encontrado = False
        try:
            vacio = self.driver.find_element(By.CSS_SELECTOR, _CSS_VACIO_SPAN)
            if _TEXTO_NO_REG in (vacio.text or "").lower():
                no_encontrado = True
        except NoSuchElementException:
            pass

        # Fallback: texto plano de la página
        if not no_encontrado and _TEXTO_NO_REG in self.driver.page_source.lower():
            no_encontrado = True

        if no_encontrado:
            self._loaded = False
            self.driver.get(_URL)
            self._loaded = True
            return {
                "sbs_registrado": False,
                "sbs_nombre": None,
                "sbs_tipo_sujeto": None,
                "sbs_estado": "NO REGISTRADO",
            }

        # Parsear tabla de resultados:
        #   col 0 = RUC (ya conocido)
        #   col 1 = Razón social  → sbs_nombre
        #   col 2 = Resultado     → sbs_tipo_sujeto (ej. "Empresa del Sistema Financiero")
        nombre = tipo_sujeto = None
        try:
            tabla = self.driver.find_element(By.XPATH, _XPATH_TABLA)
            filas = tabla.find_elements(By.TAG_NAME, "tr")
            for fila in filas[1:]:  # saltar fila de cabecera
                celdas = fila.find_elements(By.TAG_NAME, "td")
                if len(celdas) >= 3:
                    nombre      = celdas[1].text.strip() or None
                    tipo_sujeto = celdas[2].text.strip() or None
                    if nombre:
                        break
                elif len(celdas) == 1:
                    # Fila de "no encontrado" con colspan=3
                    if _TEXTO_NO_REG in celdas[0].text.strip().lower():
                        no_encontrado = True
                        break
        except (NoSuchElementException, WebDriverException):
            pass

        self._loaded = False
        self.driver.get(_URL)
        self._loaded = True

        if no_encontrado:
            return {
                "sbs_registrado": False,
                "sbs_nombre": None,
                "sbs_tipo_sujeto": None,
                "sbs_estado": "NO REGISTRADO",
            }

        return {
            "sbs_registrado": True,
            "sbs_nombre": nombre,
            "sbs_tipo_sujeto": tipo_sujeto,
            "sbs_estado": "REGISTRADO",
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

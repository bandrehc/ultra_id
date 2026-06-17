"""
RUC → Registro Nacional de Proveedores OSCE (apps.osce.gob.pe)

Flujo real (la ficha NO carga bien por navegación directa a /ficha/{ruc}):
  1. Navegar a /perfilprov-ui/buscar?q={ruc}&pageSize=6&pageNumber=1&export=1&langTag=es
  2. Esperar la tarjeta de resultado (o detectar "sin resultados" → no registrado)
  3. Click en el link de la tarjeta (genérico: cualquier <a> con 'ficha' en href/routerlink)
  4. Esperar que cargue <app-prov-ficha>
  5. Extraer contadores (sanciones TCP, penalidades, inhabilitaciones), socios,
     representantes, servicios vigentes/no vigentes
  6. Click "Ver Detalle" de Experiencia del Proveedor → extraer genéricamente
     (mismo patrón de componente Angular app-tile-* reutilizado en socios/representantes)
"""
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

_SEARCH_URL = (
    "https://apps.osce.gob.pe/perfilprov-ui/buscar"
    "?q={ruc}&pageSize=6&pageNumber=1&export=1&langTag=es"
)

_SEL_FICHA_LINK = "a[href*='/ficha/'], a[routerlink*='ficha']"
_SEL_FICHA_ROOT = "app-prov-ficha"

# XPaths absolutos provistos por el usuario (frágiles ante cambios de UI;
# cada uno se extrae de forma aislada — si uno falla, no bloquea a los demás)
_XPATH_SANCIONES_TCP   = "/html/body/app-root/div/div/app-prov-ficha/div/div/div[1]/div[2]/div[2]/div[3]/div[1]/a/span[1]"
_XPATH_PENALIDADES     = "/html/body/app-root/div/div/app-prov-ficha/div/div/div[1]/div[2]/div[2]/div[3]/div[2]/a/span[1]"
_XPATH_INHAB_JUDICIAL  = "/html/body/app-root/div/div/app-prov-ficha/div/div/div[1]/div[2]/div[2]/div[3]/div[3]/a/span[1]"
_XPATH_INHAB_ADMIN     = "/html/body/app-root/div/div/app-prov-ficha/div/div/div[1]/div[2]/div[2]/div[3]/div[4]/a/span[1]"
_XPATH_SOCIOS          = "/html/body/app-root/div/div/app-prov-ficha/div/div/div[2]/div[1]/div[1]/div[1]/div"
_XPATH_REPRESENTANTES  = "/html/body/app-root/div/div/app-prov-ficha/div/div/div[2]/div[1]/div[1]/div[2]/div"
_XPATH_SERV_VIGENTES   = "/html/body/app-root/div/div/app-prov-ficha/div/div/div[1]/div[1]/div[1]/div[1]/div[2]/div/div[2]/div[1]/span"
_XPATH_SERV_NO_VIGENTES = "/html/body/app-root/div/div/app-prov-ficha/div/div/div[1]/div[1]/div[1]/div[1]/div[2]/div/div[2]/div[2]/span"
_XPATH_VER_DETALLE_EXPERIENCIA = "/html/body/app-root/div/div/app-prov-ficha/div/div/div[2]/div[2]/div[3]/div/div[2]/span[2]/a"

_SEL_TILE_DETALLE = "[class*='contract-details']"
_SEL_VER_TODOS    = ".moreless-contracts a"

_MAX_EXPERIENCIA_RESUMEN = 10


def _parse_int(texto: str) -> Optional[int]:
    m = re.search(r"\d+", texto or "")
    return int(m.group()) if m else None


def _safe_text_by_xpath(driver, xpath: str, timeout: float = 3) -> Optional[str]:
    try:
        el = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
        return el.text.strip()
    except (TimeoutException, NoSuchElementException, WebDriverException):
        return None


def _expand_ver_todos(driver, container) -> None:
    try:
        ver_todos = container.find_element(By.CSS_SELECTOR, _SEL_VER_TODOS)
        if ver_todos.is_displayed():
            driver.execute_script("arguments[0].click();", ver_todos)
            time.sleep(0.4)
    except (NoSuchElementException, WebDriverException):
        pass


def _parse_tiles(container) -> list[dict]:
    """Extrae genéricamente los componentes Angular app-tile-* (socios,
    representantes, experiencia) basados en el patrón compartido
    .contract-details: '<strong>NOMBRE</strong><br> Tipo de Documento: X - NUM'."""
    items = []
    try:
        tiles = container.find_elements(By.CSS_SELECTOR, _SEL_TILE_DETALLE)
    except WebDriverException:
        return items
    for t in tiles:
        texto = t.text.strip()
        if not texto:
            continue
        lineas = [l.strip() for l in texto.split("\n") if l.strip()]
        nombre = lineas[0] if lineas else ""
        detalle = " ".join(lineas[1:]) if len(lineas) > 1 else ""
        items.append({"nombre": nombre, "detalle": detalle})
    return items


def _formatear_lista(items: list[dict]) -> str:
    return "; ".join(
        f"{i['nombre']} ({i['detalle']})" if i["detalle"] else i["nombre"]
        for i in items
    )


class OsceBuscador(BaseBuscador):
    def __init__(self, headless: bool = True, delay: float = DELAY_BETWEEN):
        super().__init__(headless=headless, anti_bot=True)
        self.delay = delay

    def _no_registrado(self) -> dict:
        return {
            "osce_registrado": False,
            "osce_nombre_proveedor": None,
            "osce_estado_rns": "NO REGISTRADO",
            "osce_tipo_proveedor": None,
            "osce_n_sanciones_tcp": 0,
            "osce_n_penalidades": 0,
            "osce_n_inhabilitacion_judicial": 0,
            "osce_n_inhabilitacion_administrativa": 0,
            "osce_n_socios": 0,
            "osce_socios_accionistas": None,
            "osce_n_representantes": 0,
            "osce_representantes": None,
            "osce_n_servicios_vigentes": 0,
            "osce_n_servicios_no_vigentes": 0,
            "osce_n_experiencia": 0,
            "osce_experiencia_resumen": None,
        }

    def _extraer_experiencia(self, timeout: float) -> tuple[int, str]:
        """Click en 'Ver Detalle' de Experiencia del Proveedor; maneja tanto
        navegación en la misma pestaña como apertura de pestaña nueva."""
        try:
            btn = WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located((By.XPATH, _XPATH_VER_DETALLE_EXPERIENCIA))
            )
        except (TimeoutException, NoSuchElementException):
            return 0, ""

        handles_antes = self.driver.window_handles
        try:
            self.driver.execute_script("arguments[0].click();", btn)
        except WebDriverException:
            return 0, ""

        time.sleep(1.0)
        handles_despues = self.driver.window_handles
        pestaña_nueva = len(handles_despues) > len(handles_antes)

        if pestaña_nueva:
            nuevo = [h for h in handles_despues if h not in handles_antes][0]
            self.driver.switch_to.window(nuevo)

        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            time.sleep(0.5)
            tiles = _parse_tiles(self.driver)
            n = len(tiles)
            resumen = _formatear_lista(tiles[:_MAX_EXPERIENCIA_RESUMEN])
        except (TimeoutException, WebDriverException):
            n, resumen = 0, ""

        if pestaña_nueva:
            self.driver.close()
            self.driver.switch_to.window(handles_antes[0])
        else:
            try:
                self.driver.back()
            except WebDriverException:
                pass

        return n, resumen

    def _consultar_una_vez(self, ruc: str, timeout: int) -> Optional[dict]:
        self._ensure_driver()
        url = _SEARCH_URL.format(ruc=ruc.strip())
        self.driver.get(url)

        wait = WebDriverWait(self.driver, max(timeout, 8))

        # Esperar tarjeta de resultado o agotar tiempo (= no registrado)
        try:
            wait.until(
                lambda d: d.find_elements(By.CSS_SELECTOR, _SEL_FICHA_LINK)
            )
        except TimeoutException:
            return self._no_registrado()

        links = self.driver.find_elements(By.CSS_SELECTOR, _SEL_FICHA_LINK)
        if not links:
            return self._no_registrado()

        try:
            self.driver.execute_script("arguments[0].click();", links[0])
        except WebDriverException:
            return None

        try:
            wait.until(EC.presence_of_element_located((By.TAG_NAME, _SEL_FICHA_ROOT)))
        except TimeoutException:
            return None
        time.sleep(0.6)  # margen para que Angular renderice los datos async

        data: dict = {"osce_registrado": True, "osce_detalle_url": self.driver.current_url}

        data["osce_n_sanciones_tcp"]  = _parse_int(_safe_text_by_xpath(self.driver, _XPATH_SANCIONES_TCP))
        data["osce_n_penalidades"]    = _parse_int(_safe_text_by_xpath(self.driver, _XPATH_PENALIDADES))
        data["osce_n_inhabilitacion_judicial"] = _parse_int(_safe_text_by_xpath(self.driver, _XPATH_INHAB_JUDICIAL))
        data["osce_n_inhabilitacion_administrativa"] = _parse_int(_safe_text_by_xpath(self.driver, _XPATH_INHAB_ADMIN))
        data["osce_n_servicios_vigentes"]    = _parse_int(_safe_text_by_xpath(self.driver, _XPATH_SERV_VIGENTES))
        data["osce_n_servicios_no_vigentes"] = _parse_int(_safe_text_by_xpath(self.driver, _XPATH_SERV_NO_VIGENTES))

        # Socios accionistas
        try:
            cont_socios = WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located((By.XPATH, _XPATH_SOCIOS))
            )
            _expand_ver_todos(self.driver, cont_socios)
            socios = _parse_tiles(cont_socios)
            data["osce_n_socios"] = len(socios)
            data["osce_socios_accionistas"] = _formatear_lista(socios) or None
        except (TimeoutException, NoSuchElementException, WebDriverException):
            data["osce_n_socios"] = None
            data["osce_socios_accionistas"] = None

        # Representantes
        try:
            cont_repr = WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located((By.XPATH, _XPATH_REPRESENTANTES))
            )
            _expand_ver_todos(self.driver, cont_repr)
            reps = _parse_tiles(cont_repr)
            data["osce_n_representantes"] = len(reps)
            data["osce_representantes"] = _formatear_lista(reps) or None
        except (TimeoutException, NoSuchElementException, WebDriverException):
            data["osce_n_representantes"] = None
            data["osce_representantes"] = None

        # Experiencia del Proveedor (click "Ver Detalle")
        n_exp, resumen_exp = self._extraer_experiencia(timeout=max(timeout, 8))
        data["osce_n_experiencia"] = n_exp
        data["osce_experiencia_resumen"] = resumen_exp or None

        # Nombre / estado / tipo de proveedor: capturar del encabezado de la ficha
        try:
            header = self.driver.find_element(By.TAG_NAME, _SEL_FICHA_ROOT)
            primer_h1 = header.find_elements(By.CSS_SELECTOR, "h1, h2, [class*='nombre']")
            data["osce_nombre_proveedor"] = primer_h1[0].text.strip() if primer_h1 else None
            estado_el = header.find_elements(By.CSS_SELECTOR, "[class*='estado'], [class*='habilitacion']")
            data["osce_estado_rns"] = estado_el[0].text.strip() if estado_el else None
        except WebDriverException:
            data["osce_nombre_proveedor"] = None
            data["osce_estado_rns"] = None
        data.setdefault("osce_tipo_proveedor", None)

        return data

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

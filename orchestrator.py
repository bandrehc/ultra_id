"""
UltraBuscador: orquestador que consolida todas las fuentes.

Arquitectura de paralelismo:
  - Nivel documento: ThreadPoolExecutor(max_workers) distribuye documentos entre workers.
  - Nivel fuente:    dentro de cada documento, las fuentes Selenium se ejecutan en paralelo
                     (ThreadPoolExecutor interno). Cada fuente tiene su propio driver en
                     _WorkerContext, por lo que no comparten estado mutable.
  - Tiempo por RUC ≈ max(fuente_más_lenta) en vez de sum(todas las fuentes).
  - RECPO: API pre-batcheada antes del loop; se aplica desde cache sin bloquear.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from core.models import ResultadoDocumento, TIPO_NOMBRES
from core.validator import validar_documento, crear_resultado_vacio
from buscadores.dni import DNIBuscador
from buscadores.ruc import RucBuscador
from buscadores.reinfo import ReinfoBuscador
from buscadores.recpo import RecpoBuscador
from buscadores.osce import OsceBuscador
from buscadores.sbs import SbsBuscador
from buscadores.carext import CarextBuscador

# Fuentes Selenium que aplican por tipo de documento
_FUENTES_SELENIUM = {
    1: ["dni"],
    6: ["ruc", "reinfo", "osce", "sbs"],
    3: ["carext"],
    4: [],
}

# Fuentes API (sin Selenium) que aplican por tipo
_FUENTES_API = {
    1: [],
    6: ["recpo"],
    3: [],
    4: [],
}


class _WorkerContext:
    """Instancias de buscadores por worker thread (thread-local)."""

    def __init__(self, headless: bool):
        self.headless = headless
        self._dni: Optional[DNIBuscador] = None
        self._ruc: Optional[RucBuscador] = None
        self._reinfo: Optional[ReinfoBuscador] = None
        self._osce: Optional[OsceBuscador] = None
        self._sbs: Optional[SbsBuscador] = None
        self._carext: Optional[CarextBuscador] = None
        self._recpo: Optional[RecpoBuscador] = None

    def get(self, nombre: str):
        if nombre == "dni":
            if not self._dni:
                self._dni = DNIBuscador(headless=self.headless)
            return self._dni
        if nombre == "ruc":
            if not self._ruc:
                self._ruc = RucBuscador(headless=self.headless)
            return self._ruc
        if nombre == "reinfo":
            if not self._reinfo:
                self._reinfo = ReinfoBuscador(headless=self.headless)
            return self._reinfo
        if nombre == "osce":
            if not self._osce:
                self._osce = OsceBuscador(headless=self.headless)
            return self._osce
        if nombre == "sbs":
            if not self._sbs:
                self._sbs = SbsBuscador(headless=self.headless)
            return self._sbs
        if nombre == "carext":
            if not self._carext:
                self._carext = CarextBuscador(headless=self.headless)
            return self._carext
        if nombre == "recpo":
            if not self._recpo:
                self._recpo = RecpoBuscador()
            return self._recpo
        raise ValueError(f"Buscador desconocido: {nombre}")

    def close_all(self):
        for b in [self._dni, self._ruc, self._reinfo, self._osce,
                  self._sbs, self._carext, self._recpo]:
            if b is not None:
                try:
                    b.close()
                except Exception:
                    pass


class UltraBuscador:
    def __init__(self, headless: bool = True, workers: int = 4):
        self.headless = headless
        self.workers = max(1, min(workers, 5))
        self._recpo_cache: dict[str, dict] = {}
        self._recpo_buscador = RecpoBuscador()

    def _prefetch_recpo(self, rucs: list[str]) -> None:
        """Pre-carga todos los RUCs en la cache RECPO antes del loop principal."""
        BATCH = 100
        for i in range(0, len(rucs), BATCH):
            batch = rucs[i:i + BATCH]
            data = self._recpo_buscador.consultar_batch_rucs(batch)
            self._recpo_cache.update(data)

    def _run_fuentes_en_paralelo(
        self,
        fuentes: list,
        ctx: _WorkerContext,
        resultado: ResultadoDocumento,
    ) -> None:
        """Ejecuta fuentes Selenium en paralelo para un mismo documento.

        Cada fuente tiene su propio driver en _WorkerContext; al escribir campos
        disjuntos (ruc_*, osce_*, sbs_*, reinfo_*) en el mismo ResultadoDocumento
        no hay race conditions. Los buscadores se pre-inicializan en el thread
        actual antes de despacharlos a threads internos para evitar lazy-init races.
        """
        if not fuentes:
            return

        if len(fuentes) == 1:
            f = fuentes[0]
            try:
                ctx.get(f).consultar(resultado)
            except Exception as exc:
                ec = f"error_{f}"
                if hasattr(resultado, ec):
                    setattr(resultado, ec, str(exc)[:120])
            return

        # Pre-inicializar buscadores en el thread actual del worker
        buscadores = {f: ctx.get(f) for f in fuentes}

        with ThreadPoolExecutor(max_workers=len(fuentes)) as inner:
            fut_to_fuente = {
                inner.submit(buscadores[f].consultar, resultado): f
                for f in fuentes
            }
            for fut in as_completed(fut_to_fuente):
                f = fut_to_fuente[fut]
                try:
                    fut.result()
                except Exception as exc:
                    ec = f"error_{f}"
                    if hasattr(resultado, ec):
                        setattr(resultado, ec, str(exc)[:120])

    def _consultar_uno_con_ctx(
        self,
        numero: str,
        tipo: int,
        ctx: _WorkerContext,
    ) -> ResultadoDocumento:
        """Consulta un documento con el contexto (buscadores) del worker."""
        ok, err = validar_documento(numero, tipo)
        resultado = crear_resultado_vacio(numero, tipo)
        if not ok:
            return resultado

        # Fuentes Selenium — en paralelo (cada fuente usa su propio driver)
        self._run_fuentes_en_paralelo(_FUENTES_SELENIUM.get(tipo, []), ctx, resultado)

        # Fuentes API — aplicar desde cache (pre-fetched) o consultar si falta
        for fuente in _FUENTES_API.get(tipo, []):
            if fuente == "recpo":
                if numero in self._recpo_cache:
                    ctx.get("recpo").aplicar_a_resultado(resultado, self._recpo_cache[numero])
                else:
                    try:
                        ctx.get("recpo").consultar(resultado)
                    except Exception as exc:
                        resultado.error_recpo = str(exc)[:120]

        return resultado

    def consultar_uno(self, numero: str, tipo: int) -> ResultadoDocumento:
        """Consulta individual (single-threaded)."""
        ctx = _WorkerContext(self.headless)
        try:
            return self._consultar_uno_con_ctx(numero, tipo, ctx)
        finally:
            ctx.close_all()

    def consultar_masivo(
        self,
        documentos: list[tuple[str, int]],
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> list[ResultadoDocumento]:
        """
        Batch con pre-fetch RECPO + ThreadPoolExecutor (workers=self.workers).
        Cada thread tiene su propio _WorkerContext con drivers reutilizados.
        """
        total = len(documentos)
        resultados: list[Optional[ResultadoDocumento]] = [None] * total

        # Pre-fetch RECPO para todos los RUCs
        rucs = [n for n, t in documentos if t == 6]
        if rucs:
            if on_log:
                on_log(f"Pre-cargando {len(rucs)} RUCs en API RECPO...")
            self._prefetch_recpo(rucs)

        _local = threading.local()

        def _get_ctx() -> _WorkerContext:
            if not hasattr(_local, "ctx"):
                _local.ctx = _WorkerContext(self.headless)
            return _local.ctx

        def _procesar(idx_item):
            idx, (numero, tipo) = idx_item
            if stop_event and stop_event.is_set():
                return idx, crear_resultado_vacio(numero, tipo)
            ctx = _get_ctx()
            r = self._consultar_uno_con_ctx(numero, tipo, ctx)
            return idx, r

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futuros = {
                executor.submit(_procesar, (i, doc)): i
                for i, doc in enumerate(documentos)
            }
            completados = 0
            for futuro in as_completed(futuros):
                if stop_event and stop_event.is_set():
                    break
                try:
                    idx, r = futuro.result()
                    resultados[idx] = r
                    completados += 1
                    tipo_n = TIPO_NOMBRES.get(r.tipo_codigo, "?")
                    errs = r.resumen_errores()
                    if errs:
                        msg = f"[{completados}/{total}] ERROR {tipo_n} {r.numero_documento}: {errs[0]}"
                    else:
                        msg = f"[{completados}/{total}] OK {tipo_n} {r.numero_documento}"
                    if on_log:
                        on_log(msg)
                    if on_progress:
                        on_progress(completados, total)
                except Exception as exc:
                    completados += 1
                    if on_log:
                        on_log(f"[{completados}/{total}] FATAL: {exc}")
                    if on_progress:
                        on_progress(completados, total)

        # Completar slots cancelados con resultados vacíos
        for i, doc in enumerate(documentos):
            if resultados[i] is None:
                resultados[i] = crear_resultado_vacio(doc[0], doc[1])

        return resultados

    def close(self):
        try:
            self._recpo_buscador.close()
        except Exception:
            pass

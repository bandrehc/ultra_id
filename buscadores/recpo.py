"""RUC → registro minero RECPO + Formalizados (API mineros-peru.vercel.app)"""
from __future__ import annotations
import time
from typing import Optional

import requests

from core.models import ResultadoDocumento

_API_URL    = "https://mineros-peru.vercel.app/api/mineria"
_TIMEOUTS   = [5, 10, 15]
_BATCH_SIZE = 100
_DELAY      = 0.1

_FORM_FIELDS = [
    "cod_unico", "derecho_minero", "depto", "provincia", "distrito",
    "numero_resolucion", "fecha_rd",
]
_DEST_MAP = {
    "cod_unico":        "recpo_cod_unico",
    "derecho_minero":   "recpo_derecho_minero",
    "depto":            "recpo_departamento",
    "provincia":        "recpo_provincia",
    "distrito":         "recpo_distrito",
    "numero_resolucion":"recpo_nro_resolucion",
    "fecha_rd":         "recpo_fecha_rd",
}


def _parsear(item: dict) -> dict:
    en_recpo       = "Si" if item.get("flag_recpo") == 1 else "No"
    en_formalizado = "Si" if item.get("flag_formalizado") == 1 else "No"

    recpo = item.get("recpo") or {}
    declarante   = recpo.get("declarante")   or "Sin Datos"
    nro_registro = recpo.get("nro_registro") or "Sin Datos"
    condicion    = recpo.get("condicion")    or "Sin Datos"
    situacion    = recpo.get("situacion")    or "Sin Datos"

    formalizados = item.get("formalizados") or []
    first = {}
    if isinstance(formalizados, list) and formalizados:
        first = formalizados[0] if isinstance(formalizados[0], dict) else {}
    elif isinstance(formalizados, dict):
        first = formalizados

    minero = first.get("nombre") or "Sin Datos"
    extras = {}
    for f in _FORM_FIELDS:
        val = first.get(f)
        extras[f] = str(val) if val not in (None, "", 0) else "Sin Datos"

    return {
        "recpo_en_recpo":        en_recpo,
        "recpo_en_formalizado":  en_formalizado,
        "recpo_declarante":      declarante,
        "recpo_nro_registro":    nro_registro,
        "recpo_condicion":       condicion,
        "recpo_situacion":       situacion,
        "recpo_minero_formalizado": minero,
        **{_DEST_MAP[f]: extras[f] for f in _FORM_FIELDS},
    }


class RecpoBuscador:
    """Buscador sin Selenium — usa la REST API en batch."""

    def __init__(self, delay: float = _DELAY):
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def consultar_batch_rucs(self, rucs: list[str]) -> dict[str, dict]:
        """Retorna {ruc: campos_dict}. Maneja errores por RUC."""
        if not rucs:
            return {}
        rucs_str = ",".join(rucs)
        for intento, timeout in enumerate(_TIMEOUTS, start=1):
            try:
                r = self.session.get(_API_URL, params={"rucs": rucs_str}, timeout=timeout)
                r.raise_for_status()
                data = r.json()
                api_map = {item["ruc"]: item for item in data.get("data", [])}
                result = {}
                for ruc in rucs:
                    if ruc in api_map:
                        result[ruc] = _parsear(api_map[ruc])
                    else:
                        result[ruc] = {
                            "recpo_en_recpo": "No", "recpo_en_formalizado": "No",
                            "recpo_declarante": "Sin Datos", "recpo_nro_registro": "Sin Datos",
                            "recpo_condicion": "Sin Datos", "recpo_situacion": "Sin Datos",
                            "recpo_minero_formalizado": "Sin Datos",
                            **{v: "Sin Datos" for v in _DEST_MAP.values()},
                        }
                return result
            except requests.exceptions.RequestException as exc:
                if intento == len(_TIMEOUTS):
                    err = str(exc)[:80]
                    return {ruc: {"error_recpo": err} for ruc in rucs}
                time.sleep(0.05)
        return {ruc: {"error_recpo": "Fallo desconocido"} for ruc in rucs}

    def aplicar_a_resultado(self, resultado: ResultadoDocumento, data: dict) -> ResultadoDocumento:
        for campo, valor in data.items():
            if hasattr(resultado, campo):
                setattr(resultado, campo, valor)
        return resultado

    def consultar(self, resultado: ResultadoDocumento) -> ResultadoDocumento:
        ruc = resultado.numero_documento
        batch_data = self.consultar_batch_rucs([ruc])
        return self.aplicar_a_resultado(resultado, batch_data.get(ruc, {}))

    def close(self):
        try:
            self.session.close()
        except Exception:
            pass

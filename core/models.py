from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional


TIPO_NOMBRES = {1: "DNI", 3: "Carnet Extranjería", 4: "Pasaporte", 6: "RUC"}


@dataclass
class ResultadoDocumento:
    # --- Identificación ---
    numero_documento: str = ""
    tipo_codigo: int = 0
    tipo_nombre: str = ""
    codigo_procesado: str = ""

    # --- DNI (buscardniperu.com) ---
    dni_edad: Optional[int] = None
    dni_fecha_nacimiento: Optional[str] = None

    # --- RUC (universidadperu.com) ---
    ruc_razon_social: Optional[str] = None
    ruc_nombre_comercial: Optional[str] = None
    ruc_tipo_empresa: Optional[str] = None
    ruc_condicion: Optional[str] = None
    ruc_fecha_inicio: Optional[str] = None
    ruc_direccion: Optional[str] = None
    ruc_urbanizacion: Optional[str] = None
    ruc_distrito: Optional[str] = None
    ruc_departamento: Optional[str] = None
    ruc_estado_domicilio: Optional[str] = None

    # --- REINFO (pad.minem.gob.pe) ---
    reinfo_nombre: Optional[str] = None
    reinfo_codigo_derecho: Optional[str] = None
    reinfo_nombre_derecho: Optional[str] = None
    reinfo_departamento: Optional[str] = None
    reinfo_provincia: Optional[str] = None
    reinfo_distrito: Optional[str] = None
    reinfo_estado: Optional[str] = None

    # --- RECPO API (mineros-peru.vercel.app) ---
    recpo_en_recpo: Optional[str] = None
    recpo_en_formalizado: Optional[str] = None
    recpo_declarante: Optional[str] = None
    recpo_nro_registro: Optional[str] = None
    recpo_condicion: Optional[str] = None
    recpo_situacion: Optional[str] = None
    recpo_minero_formalizado: Optional[str] = None
    recpo_cod_unico: Optional[str] = None
    recpo_derecho_minero: Optional[str] = None
    recpo_nro_resolucion: Optional[str] = None
    recpo_fecha_rd: Optional[str] = None

    # --- OSCE (apps.osce.gob.pe) ---
    osce_registrado: Optional[bool] = None
    osce_nombre_proveedor: Optional[str] = None
    osce_estado_rns: Optional[str] = None
    osce_tipo_proveedor: Optional[str] = None
    osce_n_penalidades: Optional[int] = None
    osce_n_sanciones: Optional[int] = None
    osce_n_inhabilitaciones: Optional[int] = None
    osce_detalle_url: Optional[str] = None

    # --- SBS Sujeto Obligado (sbs.gob.pe) ---
    sbs_registrado: Optional[bool] = None
    sbs_nombre: Optional[str] = None
    sbs_tipo_sujeto: Optional[str] = None
    sbs_estado: Optional[str] = None

    # --- Carnet Extranjería (RREE) ---
    carext_apellidos: Optional[str] = None
    carext_nombres: Optional[str] = None
    carext_nacionalidad: Optional[str] = None
    carext_estado_carnet: Optional[str] = None

    # --- Errores por fuente ---
    error_dni: Optional[str] = None
    error_ruc: Optional[str] = None
    error_reinfo: Optional[str] = None
    error_recpo: Optional[str] = None
    error_osce: Optional[str] = None
    error_sbs: Optional[str] = None
    error_carext: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def resumen_errores(self) -> list[str]:
        campos = ["error_dni", "error_ruc", "error_reinfo", "error_recpo",
                  "error_osce", "error_sbs", "error_carext"]
        return [f"{c}: {getattr(self, c)}" for c in campos if getattr(self, c)]

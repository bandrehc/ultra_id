"""
Benchmark: 10 RUCs con workers=4, mide tiempo total y por documento.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from orchestrator import UltraBuscador

# 10 RUCs de empresas peruanas conocidas (diversas: banca, telecomunicaciones,
# minería, empresas medianas — mix de probablemente registradas/no en cada fuente)
RUCS_TEST = [
    "20100047218",  # BCP - Banco de Crédito del Perú
    "20131312955",  # BBVA Perú
    "20100070970",  # Interbank
    "20100030595",  # Rimac Seguros
    "20100055237",  # Telefónica del Perú
    "20418897422",  # Scotiabank Perú
    "20100041953",  # Alicorp
    "20332970411",  # empresa mediana (usada en pruebas OSCE)
    "20513851104",  # empresa NO registrada en OSCE (prueba negativa)
    "20602130061",  # Yape (PagoEfectivo)
]

documentos = [(ruc, 6) for ruc in RUCS_TEST]

print(f"\n{'='*60}")
print(f" BENCHMARK ultra_id — {len(RUCS_TEST)} RUCs / workers=4")
print(f"{'='*60}\n")

tiempos_doc: dict[str, float] = {}
completados = 0
t_total_inicio = time.time()

def on_log(msg):
    elapsed = time.time() - t_total_inicio
    print(f"  [{elapsed:6.1f}s]  {msg}")

def on_progress(done, total):
    global completados
    completados = done

buscador = UltraBuscador(headless=True, workers=4)

# Medición por documento: registramos cuándo llega cada resultado
tiempos_inicio_doc: dict[str, float] = {ruc: t_total_inicio for ruc in RUCS_TEST}

try:
    resultados = buscador.consultar_masivo(
        documentos,
        on_progress=on_progress,
        on_log=on_log,
    )
finally:
    buscador.close()

t_total_fin = time.time()
t_total = t_total_fin - t_total_inicio

print(f"\n{'='*60}")
print(f" RESULTADOS")
print(f"{'='*60}")

campos_por_fuente = {
    "RUC":        ["ruc_razon_social", "ruc_condicion", "ruc_anos_actividad"],
    "REINFO":     ["reinfo_estado"],
    "RECPO":      ["recpo_en_recpo"],
    "OSCE":       ["osce_registrado", "osce_n_penalidades", "osce_n_sanciones_tcp"],
    "SBS":        ["sbs_registrado", "sbs_tipo_sujeto"],
}

for i, r in enumerate(resultados):
    ruc = r.numero_documento
    errores = r.resumen_errores()
    print(f"\n  [{i+1:2d}] RUC {ruc}")
    for fuente, campos in campos_por_fuente.items():
        vals = {c: getattr(r, c, None) for c in campos}
        resumen = " | ".join(f"{c.split('_',1)[1]}={v}" for c, v in vals.items() if v is not None)
        if resumen:
            print(f"       {fuente:8s}: {resumen}")
    if errores:
        for e in errores:
            print(f"       ERROR  : {e}")

print(f"\n{'='*60}")
print(f" TIEMPOS")
print(f"{'='*60}")
print(f"  Total           : {t_total:.1f}s  ({t_total/60:.1f} min)")
print(f"  Promedio/doc    : {t_total/len(RUCS_TEST):.1f}s")
print(f"  Documentos/min  : {len(RUCS_TEST)/(t_total/60):.1f}")
print(f"  Workers         : 4")
print(f"  Fuentes/RUC     : ruc + reinfo + osce + sbs (paralelas) + recpo (API cache)")
print(f"{'='*60}\n")

"""
Mide el tiempo real de cada fuente por separado para un RUC conocido.
Usa BCP (20100047218) — registrado en OSCE, SBS, RUC, no en REINFO/RECPO.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.validator import crear_resultado_vacio
from buscadores.ruc    import RucBuscador
from buscadores.reinfo import ReinfoBuscador
from buscadores.osce   import OsceBuscador
from buscadores.sbs    import SbsBuscador
from buscadores.recpo  import RecpoBuscador

RUC = "20100047218"   # BCP — garantiza datos reales en todas las fuentes
RUC2 = "20513851104"  # PEPITA E.I.R.L. — NOT en OSCE/SBS → prueba el "no encontrado"

FUENTES = [
    ("RUC  (universidadperu)", RucBuscador,    RUC),
    ("REINFO (MINEM)",         ReinfoBuscador, RUC),
    ("OSCE  (RNP registrado)", OsceBuscador,   RUC),
    ("OSCE  (NO registrado)",  OsceBuscador,   RUC2),
    ("SBS   (registrado)",     SbsBuscador,    RUC),
    ("SBS   (NO registrado)",  SbsBuscador,    RUC2),
    ("RECPO (API)",            RecpoBuscador,  RUC),
]

print(f"\n{'='*62}")
print(f"  TIMING POR FUENTE — medición aislada")
print(f"{'='*62}\n")

resultados_timing = []

for nombre, BuscadorClass, ruc_test in FUENTES:
    resultado = crear_resultado_vacio(ruc_test, 6)
    b = BuscadorClass() if BuscadorClass is RecpoBuscador else BuscadorClass(headless=True)
    try:
        t0 = time.time()
        b.consultar(resultado)
        elapsed = time.time() - t0

        # Determinar estado
        errores = resultado.resumen_errores()
        ok = "OK" if not errores else f"ERR: {errores[0][:60]}"

        resultados_timing.append((elapsed, nombre, ok))
        print(f"  {nombre:30s}  {elapsed:6.1f}s  {ok}")
    except Exception as exc:
        elapsed = time.time() - t0
        resultados_timing.append((elapsed, nombre, f"EXCEPCION: {str(exc)[:50]}"))
        print(f"  {nombre:30s}  {elapsed:6.1f}s  EXCEPCION: {str(exc)[:50]}")
    finally:
        b.close()

print(f"\n{'='*62}")
print(f"  RANKING (mayor a menor)")
print(f"{'='*62}")
for elapsed, nombre, ok in sorted(resultados_timing, reverse=True):
    bar = "█" * int(elapsed / 3)
    print(f"  {elapsed:6.1f}s  {bar:<20s}  {nombre}")
print()

"""
ultra_id — Buscador Universal de Documentos Peruanos (Modo Consola)

Tipos de documento:
  1 = DNI              (8 dígitos numéricos)
  3 = Carnet Extranjería (4–12 alfanuméricos)
  4 = Pasaporte        (5–20 alfanuméricos)
  6 = RUC              (11 dígitos numéricos)

Uso:
  python console.py 73231883 1                          # DNI
  python console.py 20100041953 6                       # RUC
  python console.py --codigo-procesado 0000732318831    # usar código procesado
  python console.py -f datos.xlsx --workers 4           # batch desde archivo
  python console.py --stdin                             # leer de stdin
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

import pandas as pd

# Ajuste de path para imports relativos cuando se ejecuta directamente
sys.path.insert(0, str(Path(__file__).parent))

from core.validator import validar_documento, parse_codigo_procesado, crear_resultado_vacio
from core.exporter import exportar, FORMATOS
from core.models import ResultadoDocumento
from orchestrator import UltraBuscador

TIPO_NOMBRES = {1: "DNI", 3: "CE", 4: "Pasaporte", 6: "RUC"}


def _leer_archivo(ruta: str) -> list[tuple[str, int]]:
    """
    Lee archivo CSV o Excel. Espera columnas: numero_documento, tipo_codigo.
    Si solo hay una columna, intenta inferir el tipo por el largo del valor.
    """
    path = Path(ruta)
    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(ruta, dtype=str)
    else:
        df = pd.read_csv(ruta, dtype=str)

    df.columns = [c.strip().lower() for c in df.columns]
    df = df.fillna("").apply(lambda col: col.map(str.strip) if col.dtype == object else col)

    if "numero_documento" in df.columns and "tipo_codigo" in df.columns:
        pairs = [
            (row["numero_documento"], int(row["tipo_codigo"]))
            for _, row in df.iterrows()
            if row["numero_documento"]
        ]
    elif "codigo_procesado" in df.columns:
        pairs = []
        for cp in df["codigo_procesado"]:
            if cp:
                try:
                    num, tipo = parse_codigo_procesado(cp)
                    pairs.append((num, tipo))
                except ValueError:
                    pass
    else:
        # Columna 1 = numero, columna 2 = tipo (si existe)
        cols = list(df.columns)
        pairs = []
        for _, row in df.iterrows():
            num = row[cols[0]].strip()
            if not num:
                continue
            if len(cols) >= 2:
                try:
                    tipo = int(row[cols[1]])
                except (ValueError, KeyError):
                    tipo = _inferir_tipo(num)
            else:
                tipo = _inferir_tipo(num)
            pairs.append((num, tipo))

    return pairs


def _inferir_tipo(numero: str) -> int:
    """Inferencia de tipo por longitud si no se especifica."""
    n = numero.strip()
    if re.fullmatch(r"\d{8}", n):
        return 1
    if re.fullmatch(r"\d{11}", n):
        return 6
    return 3


def _leer_stdin() -> list[tuple[str, int]]:
    print("Ingrese documentos (formato: 'numero tipo' por línea, ENTER vacío para terminar):",
          file=sys.stderr)
    pairs = []
    while True:
        try:
            linea = input().strip()
        except EOFError:
            break
        if not linea:
            break
        partes = re.split(r"[\s,;]+", linea)
        if len(partes) >= 2:
            try:
                tipo = int(partes[1])
                pairs.append((partes[0], tipo))
            except ValueError:
                print(f"Tipo inválido en: {linea}", file=sys.stderr)
        elif len(partes) == 1:
            pairs.append((partes[0], _inferir_tipo(partes[0])))
    return pairs


def _resultado_a_csv_row(r: ResultadoDocumento) -> dict:
    d = r.to_dict()
    return {k: ("" if v is None else str(v)) for k, v in d.items()}


def main():
    parser = argparse.ArgumentParser(
        description="ultra_id — Buscador Universal de Documentos Peruanos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("numero", nargs="?", help="Número de documento")
    parser.add_argument("tipo", nargs="?", type=int,
                        help="Tipo: 1=DNI 3=CE 4=Pasaporte 6=RUC")
    parser.add_argument("--codigo-procesado", metavar="CP",
                        help="Usar código procesado (0000+numero+tipo)")
    parser.add_argument("-f", "--archivo", metavar="ARCHIVO",
                        help="Archivo CSV/Excel con documentos a consultar")
    parser.add_argument("--stdin", action="store_true",
                        help="Leer documentos de stdin")
    parser.add_argument("-o", "--output", metavar="ARCHIVO",
                        help="Archivo de salida (default: stdout JSON)")
    parser.add_argument("--formato", choices=FORMATOS, default="xlsx",
                        help="Formato de salida para archivo (default: xlsx)")
    parser.add_argument("--workers", type=int, default=4, metavar="N",
                        help="Workers paralelos para batch (1–5, default: 4)")
    parser.add_argument("--no-headless", action="store_true",
                        help="Mostrar navegador (debug)")
    parser.add_argument("--json", action="store_true", dest="salida_json",
                        help="Forzar salida JSON a stdout")

    args = parser.parse_args()

    # --- Recopilar documentos a consultar ---
    documentos: list[tuple[str, int]] = []

    if args.codigo_procesado:
        try:
            num, tipo = parse_codigo_procesado(args.codigo_procesado)
            documentos.append((num, tipo))
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.numero and args.tipo:
        documentos.append((args.numero, args.tipo))
    elif args.numero:
        documentos.append((args.numero, _inferir_tipo(args.numero)))

    if args.archivo:
        try:
            documentos.extend(_leer_archivo(args.archivo))
        except Exception as e:
            print(f"ERROR leyendo archivo: {e}", file=sys.stderr)
            sys.exit(1)

    if args.stdin:
        documentos.extend(_leer_stdin())

    if not documentos:
        parser.print_help(file=sys.stderr)
        sys.exit(1)

    # Validar
    invalidos = [(n, t) for n, t in documentos if not validar_documento(n, t)[0]]
    if invalidos:
        for n, t in invalidos[:5]:
            _, msg = validar_documento(n, t)
            print(f"[WARN] Documento inválido ({n}, tipo={t}): {msg}", file=sys.stderr)

    headless = not args.no_headless
    workers  = max(1, min(5, args.workers))

    buscador = UltraBuscador(headless=headless, workers=workers)

    try:
        if len(documentos) == 1:
            resultados = [buscador.consultar_uno(*documentos[0])]
        else:
            def _log(msg): print(msg, file=sys.stderr)
            resultados = buscador.consultar_masivo(documentos, on_log=_log)
    finally:
        buscador.close()

    # --- Salida ---
    if args.salida_json or (not args.output and not args.archivo):
        print(json.dumps([r.to_dict() for r in resultados], ensure_ascii=False, indent=2))
    elif args.output:
        exportar(resultados, args.formato, args.output)
        print(f"Exportado: {args.output}", file=sys.stderr)
    else:
        # batch sin --output → CSV a stdout
        if resultados:
            fieldnames = list(resultados[0].to_dict().keys())
            writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
            writer.writeheader()
            for r in resultados:
                writer.writerow(_resultado_a_csv_row(r))


if __name__ == "__main__":
    main()

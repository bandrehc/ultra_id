from __future__ import annotations
from typing import Union
import pandas as pd
from core.models import ResultadoDocumento

FORMATOS = ["xlsx", "csv", "txt", "parquet", "html"]


def exportar(
    datos: list[Union[ResultadoDocumento, dict]],
    formato: str,
    ruta: str,
) -> None:
    rows = [d.to_dict() if isinstance(d, ResultadoDocumento) else d for d in datos]
    df = pd.DataFrame(rows)
    fmt = formato.lower().lstrip(".")

    if fmt == "xlsx":
        df.to_excel(ruta, index=False, engine="openpyxl")
    elif fmt == "csv":
        df.to_csv(ruta, index=False, encoding="utf-8-sig")
    elif fmt == "txt":
        df.to_csv(ruta, index=False, sep="\t", encoding="utf-8-sig")
    elif fmt == "parquet":
        df.to_parquet(ruta, index=False, engine="pyarrow")
    elif fmt == "html":
        df.to_html(ruta, index=False)
    else:
        raise ValueError(f"Formato no soportado: {formato}. Válidos: {FORMATOS}")

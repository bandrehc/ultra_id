from __future__ import annotations
import re
from core.models import ResultadoDocumento, TIPO_NOMBRES

TIPO_CODIGOS = {1, 3, 4, 6}

_RE_DNI       = re.compile(r"^\d{8}$")
_RE_RUC       = re.compile(r"^\d{11}$")
_RE_CE        = re.compile(r"^[A-Za-z0-9]{4,12}$")
_RE_PASAPORTE = re.compile(r"^[A-Za-z0-9]{5,20}$")


def validar_documento(numero: str, tipo: int) -> tuple[bool, str]:
    """Retorna (ok, mensaje_error)."""
    if tipo not in TIPO_CODIGOS:
        return False, f"Tipo de documento desconocido: {tipo}. Válidos: {sorted(TIPO_CODIGOS)}"
    n = numero.strip()
    if tipo == 1 and not _RE_DNI.match(n):
        return False, "DNI debe tener exactamente 8 dígitos numéricos"
    if tipo == 6 and not _RE_RUC.match(n):
        return False, "RUC debe tener exactamente 11 dígitos numéricos"
    if tipo == 3 and not _RE_CE.match(n):
        return False, "Carnet de Extranjería: 4–12 caracteres alfanuméricos"
    if tipo == 4 and not _RE_PASAPORTE.match(n):
        return False, "Pasaporte: 5–20 caracteres alfanuméricos"
    return True, ""


def generar_codigo_procesado(numero: str, tipo: int) -> str:
    """'0000' + numero + str(tipo)  →  ej: DNI 73231883 → '0000732318831'"""
    return f"0000{numero.strip()}{tipo}"


def parse_codigo_procesado(cp: str) -> tuple[str, int]:
    """
    Invierte generar_codigo_procesado.
    Formato esperado: '0000' + numero + tipo_codigo (1 o 2 dígitos al final).
    Prueba primero tipo de 2 dígitos (para RUC=6 que tiene 11 dígitos → posición clara).
    """
    cp = cp.strip()
    if not cp.startswith("0000"):
        raise ValueError(f"codigo_procesado debe empezar con '0000': {cp!r}")
    cuerpo = cp[4:]

    # Intentar extraer tipo (1 dígito al final primero, luego sin éxito)
    for largo_tipo in (1, 2):
        try:
            tipo = int(cuerpo[-largo_tipo:])
            numero = cuerpo[:-largo_tipo]
            if tipo in TIPO_CODIGOS and numero:
                return numero, tipo
        except ValueError:
            continue
    raise ValueError(f"No se pudo determinar tipo/número de: {cp!r}")


def crear_resultado_vacio(numero: str, tipo: int) -> ResultadoDocumento:
    ok, err = validar_documento(numero, tipo)
    return ResultadoDocumento(
        numero_documento=numero.strip(),
        tipo_codigo=tipo,
        tipo_nombre=TIPO_NOMBRES.get(tipo, "Desconocido"),
        codigo_procesado=generar_codigo_procesado(numero, tipo),
        error_dni=err if tipo == 1 and not ok else None,
        error_ruc=err if tipo == 6 and not ok else None,
        error_reinfo=err if tipo == 6 and not ok else None,
        error_recpo=err if tipo == 6 and not ok else None,
        error_osce=err if tipo == 6 and not ok else None,
        error_sbs=err if tipo == 6 and not ok else None,
        error_carext=err if tipo == 3 and not ok else None,
    )

"""
Conexión a la base de datos SAP para buscar imágenes asociadas a planos.
"""
import re
import logging
from functools import lru_cache

from config.settings import SAP_SERVER, SAP_DATABASE, SAP_USER, SAP_PASSWORD, SAP_DRIVER

log = logging.getLogger(__name__)

_conn_str = (
    f"DRIVER={{{SAP_DRIVER}}};"
    f"SERVER={SAP_SERVER};"
    f"DATABASE={SAP_DATABASE};"
    f"UID={SAP_USER};"
    f"PWD={SAP_PASSWORD};"
    "Connection Timeout=10;"
)


def _get_connection():
    try:
        import pyodbc
        return pyodbc.connect(_conn_str)
    except Exception as e:
        log.error("No se pudo conectar a SAP: %s", e)
        return None


def _parse_doc_number(filename: str) -> str | None:
    """
    Extrae el número de documento del nombre del archivo.
    Ej: '1754 000 000 A.dwg' → 'M1754000000A'
    """
    stem = re.sub(r"\.(dwg|dxf)$", "", filename, flags=re.IGNORECASE)
    digits = re.findall(r"\d+", stem)
    if not digits:
        return None
    return "M" + "".join(digits)


def buscar_imagenes(filename: str) -> list[str]:
    """
    Busca todas las imágenes en SAP asociadas a un archivo DWG.
    Retorna lista de rutas de imagen (strings).
    """
    doc_num = _parse_doc_number(filename)
    if not doc_num:
        return []

    conn = _get_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        query = """
            SELECT RUTA_JPG
            FROM [dbo].[ODATA_ZFER_RUTAS_JPG]
            WHERE DOCUMENT_NUMBER LIKE ?
            ORDER BY RUTA_JPG
        """
        cursor.execute(query, f"%{doc_num}%")
        rows = cursor.fetchall()
        return [row[0] for row in rows if row[0]]
    except Exception as e:
        log.error("Error consultando SAP para %s: %s", filename, e)
        return []
    finally:
        conn.close()


def test_connection() -> bool:
    """Verifica si la conexión SAP funciona."""
    conn = _get_connection()
    if conn:
        conn.close()
        return True
    return False

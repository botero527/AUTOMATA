"""
Conexión a la base de datos SAP para buscar imágenes asociadas a planos.
Columnas reales: DOCUMENTO (ej: 'M1761 006 005 A'), PLANO (ruta UNC del JPG)
"""
import re
import logging

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
    Construye el código de documento SAP desde el nombre del DWG.
    Ej: '1761 006 005 A.dwg' → buscar con DOCUMENTO LIKE '%1761 006 005%'
    El campo DOCUMENTO en SAP tiene formato 'M1761 006 005 A' (con M inicial y espacios).
    """
    stem = re.sub(r"\.(dwg|dxf)$", "", filename, flags=re.IGNORECASE).strip()
    # Quitar letra de revisión final si existe (A, B, C...)
    # Ej: '1761 006 005 A' → buscar '1761 006 005'
    stem_no_rev = re.sub(r"\s+[A-Z]$", "", stem).strip()
    return stem_no_rev if stem_no_rev else None


def buscar_imagenes(filename: str) -> list[dict]:
    """
    Busca imágenes en SAP para un archivo DWG.
    Retorna lista de dicts: {documento, plano, plano_url}
    plano_url es la ruta convertida para el endpoint /sap-image
    """
    doc_query = _parse_doc_number(filename)
    if not doc_query:
        return []

    conn = _get_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        query = """
            SELECT DOCUMENTO, PLANO
            FROM [dbo].[ODATA_ZFER_RUTAS_JPG]
            WHERE DOCUMENTO LIKE ?
            ORDER BY DOCUMENTO
        """
        cursor.execute(query, f"%{doc_query}%")
        rows = cursor.fetchall()
        results = []
        for doc, plano in rows:
            if not plano:
                continue
            # Construir URL para el proxy local
            plano_url = f"/sap-image?ruta={plano}"
            results.append({
                "documento": doc,
                "plano":     plano,
                "plano_url": plano_url,
            })
        log.info("SAP: %d imagen(es) para '%s'", len(results), doc_query)
        return results
    except Exception as e:
        log.error("Error consultando SAP para %s: %s", filename, e)
        return []
    finally:
        conn.close()


def test_connection() -> bool:
    conn = _get_connection()
    if conn:
        conn.close()
        return True
    return False

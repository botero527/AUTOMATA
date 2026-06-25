"""
Conexión a AGP_Ingenieria — schema AUTOMATA.
Funciones de escritura/lectura para planos, cajetines, textos, radios, cotas.
"""
import json
import logging
import re
from pathlib import Path

from config.settings import ING_SERVER, ING_DATABASE, ING_USER, ING_PASSWORD, ING_DRIVER

log = logging.getLogger(__name__)

_conn_str = (
    f"DRIVER={{{ING_DRIVER}}};"
    f"SERVER={ING_SERVER};"
    f"DATABASE={ING_DATABASE};"
    f"UID={ING_USER};"
    f"PWD={ING_PASSWORD};"
    "Connection Timeout=20;"
)


def _get_connection():
    try:
        import pyodbc
        return pyodbc.connect(_conn_str)
    except Exception as e:
        log.error("No se pudo conectar a AGP_Ingenieria: %s", e)
        return None


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _calc_zona(rel_x: float, rel_y_img: float) -> tuple:
    """
    Calcula zona semántica en grid 3x3.
    rel_y_img: 0=arriba, 1=abajo (coordenadas de pantalla/imagen).
    """
    zona_h = "IZQ" if rel_x < 0.33 else ("DER" if rel_x > 0.66 else "CENTER")
    zona_v = "TOP" if rel_y_img < 0.33 else ("BOT" if rel_y_img > 0.66 else "MID")
    return zona_h, zona_v, f"{zona_v}_{zona_h}"


def _normalize_rel(val: float, total: float) -> float:
    """Convierte coordenada absoluta a relativa 0-1."""
    if not total:
        return 0.0
    return max(0.0, min(1.0, val / total))


def _parse_bn_total(val: str) -> float | None:
    """'69+5' → 74.0  |  '25' → 25.0"""
    if not val:
        return None
    m = re.match(r'^(\d+\.?\d*)\+(\d+\.?\d*)$', str(val).strip())
    if m:
        return float(m.group(1)) + float(m.group(2))
    try:
        return float(val)
    except Exception:
        return None


# ─── PLANOS ───────────────────────────────────────────────────────────────────

def plano_existe(conn, vehiculo: str, carpeta: str, archivo: str) -> int | None:
    """Retorna el ID del plano si ya existe en DB, None si no."""
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT ID FROM [AUTOMATA].[PLANOS] WHERE VEHICULO=? AND CARPETA=? AND ARCHIVO=?",
            vehiculo, carpeta or "", archivo
        )
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception as e:
        log.error("plano_existe error: %s", e)
        return None


def upsert_plano(conn, data: dict) -> int | None:
    """
    Inserta o actualiza el registro en PLANOS.
    Retorna el ID del registro.
    data keys: vehiculo, archivo, carpeta, carpeta_parts, vehiculo_marca, vehiculo_modelo,
               vehiculo_version, pieza_cod, pieza_nombre, dxf_bounds, render_path,
               render_w, render_h, dxf_version, total_textos, total_cajetines,
               total_radios, total_cotas, hash_archivo, ruta_red, error
    """
    bounds = data.get("dxf_bounds") or [0, 0, 0, 0]
    xmin, ymin, xmax, ymax = bounds[0], bounds[1], bounds[2], bounds[3]
    ancho = xmax - xmin
    alto  = ymax - ymin
    aspect = round(ancho / alto, 4) if alto else None
    carpeta_parts = data.get("carpeta_parts", [])

    vehiculo = data.get("vehiculo", "")
    carpeta  = data.get("carpeta", "") or ""
    archivo  = data.get("archivo", "")

    existing_id = plano_existe(conn, vehiculo, carpeta, archivo)

    try:
        cursor = conn.cursor()
        if existing_id:
            cursor.execute("""
                UPDATE [AUTOMATA].[PLANOS] SET
                    MARCA=?, MODELO=?, VERSION=?,
                    CARPETA_PARTS_JSON=?, RUTA_RED_COMPLETA=?,
                    PIEZA_COD=?, PIEZA_NOMBRE=?, PIEZAS_COD=?,
                    DXF_XMIN=?, DXF_YMIN=?, DXF_XMAX=?, DXF_YMAX=?,
                    DXF_ANCHO=?, DXF_ALTO=?, ASPECT_RATIO=?,
                    RENDER_PATH=?, RENDER_W_PX=?, RENDER_H_PX=?,
                    DXF_VERSION=?, TOTAL_TEXTOS=?, TOTAL_CAJETINES=?,
                    TOTAL_RADIOS=?, TOTAL_COTAS=?,
                    HASH_ARCHIVO=?, ESTADO=?, ERROR_MSG=?,
                    FECHA_PROCESO=GETDATE()
                WHERE ID=?
            """,
                data.get("vehiculo_marca"), data.get("vehiculo_modelo"), data.get("vehiculo_version"),
                json.dumps(carpeta_parts, ensure_ascii=False), data.get("ruta_red"),
                data.get("pieza_cod"), data.get("pieza_nombre"), data.get("piezas_cod"),
                xmin, ymin, xmax, ymax, ancho, alto, aspect,
                data.get("render_path"), data.get("render_w"), data.get("render_h"),
                data.get("dxf_version"),
                data.get("total_textos", 0), data.get("total_cajetines", 0),
                data.get("total_radios", 0), data.get("total_cotas", 0),
                data.get("hash_archivo"), data.get("estado", "OK"), data.get("error"),
                existing_id
            )
            conn.commit()
            return existing_id
        else:
            cursor.execute("""
                INSERT INTO [AUTOMATA].[PLANOS]
                (VEHICULO, ARCHIVO, CARPETA, MARCA, MODELO, VERSION,
                 CARPETA_PARTS_JSON, RUTA_RED_COMPLETA,
                 PIEZA_COD, PIEZA_NOMBRE, PIEZAS_COD,
                 DXF_XMIN, DXF_YMIN, DXF_XMAX, DXF_YMAX,
                 DXF_ANCHO, DXF_ALTO, ASPECT_RATIO,
                 RENDER_PATH, RENDER_W_PX, RENDER_H_PX,
                 DXF_VERSION, TOTAL_TEXTOS, TOTAL_CAJETINES,
                 TOTAL_RADIOS, TOTAL_COTAS,
                 HASH_ARCHIVO, ESTADO, ERROR_MSG)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
                vehiculo, archivo, carpeta,
                data.get("vehiculo_marca"), data.get("vehiculo_modelo"), data.get("vehiculo_version"),
                json.dumps(carpeta_parts, ensure_ascii=False), data.get("ruta_red"),
                data.get("pieza_cod"), data.get("pieza_nombre"), data.get("piezas_cod"),
                xmin, ymin, xmax, ymax, ancho, alto, aspect,
                data.get("render_path"), data.get("render_w"), data.get("render_h"),
                data.get("dxf_version"),
                data.get("total_textos", 0), data.get("total_cajetines", 0),
                data.get("total_radios", 0), data.get("total_cotas", 0),
                data.get("hash_archivo"), data.get("estado", "OK"), data.get("error")
            )
            conn.commit()
            cursor.execute("SELECT @@IDENTITY")
            return int(cursor.fetchone()[0])
    except Exception as e:
        log.error("upsert_plano error para %s: %s", archivo, e)
        conn.rollback()
        return None


# ─── CAJETINES ────────────────────────────────────────────────────────────────

def save_cajetines(conn, plano_id: int, cajetines: list, dxf_bounds: list,
                   render_info: dict | None = None):
    """
    Guarda todos los cajetines del plano. Borra los anteriores primero.
    cajetines: lista de dicts con campos del extractor + bbox_px/center_px opcionales.
    """
    bounds = dxf_bounds or [0, 0, 1000, 1000]
    xmin, ymin, xmax, ymax = bounds
    dxf_w = xmax - xmin
    dxf_h = ymax - ymin

    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM [AUTOMATA].[CAJETINES] WHERE PLANO_ID=?", plano_id)

        for caj in cajetines:
            campos = caj.get("campos", {})
            offset_val = campos.get("OFFSET")
            bn_d_val   = campos.get("BN+D") or campos.get("BN INT")
            bn_val     = campos.get("BN")
            bn_total   = _parse_bn_total(bn_d_val)
            if offset_val is not None:
                try:
                    offset_val = float(offset_val)
                except Exception:
                    offset_val = None

            # Posición absoluta DXF
            dxf_x = caj.get("x", 0)
            dxf_y = caj.get("y", 0)

            # Posición relativa (0-1) — DXF Y crece hacia arriba
            rel_x     = _normalize_rel(dxf_x - xmin, dxf_w)
            rel_y     = _normalize_rel(dxf_y - ymin, dxf_h)      # 0=abajo, 1=arriba
            rel_y_img = 1.0 - rel_y                                 # 0=arriba, 1=abajo

            zona_h, zona_v, zona = _calc_zona(rel_x, rel_y_img)

            # BBox DXF
            bbox = caj.get("bbox") or [dxf_x, dxf_y, dxf_x, dxf_y]

            # Píxeles (del render si disponible)
            bp  = caj.get("bbox_px") or {}
            cp  = caj.get("center_px") or {}

            cursor.execute("""
                INSERT INTO [AUTOMATA].[CAJETINES]
                (PLANO_ID, CAJ_INDEX,
                 OFFSET_VAL, BN_D_VAL, BN_VAL, BN_TOTAL,
                 ACERO_VAL, STEEL_VAL, ESPESOR_VAL, MATERIAL_VAL, TIPO_VAL, BANDA_VAL,
                 CAMPOS_JSON,
                 DXF_X, DXF_Y, BBOX_XMIN, BBOX_YMIN, BBOX_XMAX, BBOX_YMAX,
                 REL_X, REL_Y, REL_Y_IMG,
                 ZONA_H, ZONA_V, ZONA,
                 PX_X, PX_Y, BBOX_PX_LEFT, BBOX_PX_TOP, BBOX_PX_W, BBOX_PX_H)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
                plano_id, caj.get("id", 0),
                offset_val, str(bn_d_val) if bn_d_val else None,
                str(bn_val) if bn_val else None, bn_total,
                campos.get("ACERO"), campos.get("STEEL"),
                campos.get("ESPESOR"), campos.get("MATERIAL"),
                campos.get("TIPO"), campos.get("BANDA"),
                json.dumps(campos, ensure_ascii=False),
                dxf_x, dxf_y,
                bbox[0] if len(bbox) > 3 else dxf_x,
                bbox[1] if len(bbox) > 3 else dxf_y,
                bbox[2] if len(bbox) > 3 else dxf_x,
                bbox[3] if len(bbox) > 3 else dxf_y,
                round(rel_x, 4), round(rel_y, 4), round(rel_y_img, 4),
                zona_h, zona_v, zona,
                cp.get("x"), cp.get("y"),
                bp.get("left"), bp.get("top"), bp.get("width"), bp.get("height")
            )
        conn.commit()
        log.info("CAJETINES: %d guardados para plano_id=%d", len(cajetines), plano_id)
    except Exception as e:
        log.error("save_cajetines error: %s", e)
        conn.rollback()


# ─── TEXTOS ───────────────────────────────────────────────────────────────────

def save_textos(conn, plano_id: int, textos: list, dxf_bounds: list):
    """Guarda todos los textos extraídos del DXF con clasificación semántica."""
    bounds = dxf_bounds or [0, 0, 1000, 1000]
    xmin, ymin, xmax, ymax = bounds
    dxf_w = xmax - xmin
    dxf_h = ymax - ymin

    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM [AUTOMATA].[TEXTOS] WHERE PLANO_ID=?", plano_id)

        for t in textos:
            texto = str(t.get("text", "")).strip()
            if not texto:
                continue
            dxf_x = t.get("x", 0)
            dxf_y = t.get("y", 0)
            rel_x    = _normalize_rel(dxf_x - xmin, dxf_w)
            rel_y    = _normalize_rel(dxf_y - ymin, dxf_h)
            rel_y_img = 1.0 - rel_y
            layer = t.get("layer", "")

            # Clasificación semántica
            es_radio  = bool(re.match(r'^R\d+(\.\d+)?$', texto, re.IGNORECASE))
            val_num   = None
            if es_radio:
                val_num = float(re.sub(r'[Rr]', '', texto))
                tipo = "RADIO"
            elif re.match(r'^\d+(\.\d+)?$', texto):
                val_num = float(texto)
                tipo = "COTA" if val_num > 50 else "NUMERO"
            else:
                from config.settings import TECHNICAL_FIELDS
                tipo = "CAMPO_TEC" if any(f in texto.upper() for f in TECHNICAL_FIELDS) else "LABEL"

            cursor.execute("""
                INSERT INTO [AUTOMATA].[TEXTOS]
                (PLANO_ID, TEXTO, TIPO_ENTIDAD, LAYER, LAYER_UPPER,
                 TIPO, VALOR_NUMERICO, ES_RADIO, ES_COTA, ES_CAMPO_TEC,
                 DXF_X, DXF_Y, REL_X, REL_Y, REL_Y_IMG)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
                plano_id, texto[:500],
                t.get("tipo_entidad", "TEXT"),
                layer, layer.upper() if layer else None,
                tipo, val_num,
                1 if es_radio else 0,
                1 if tipo == "COTA" else 0,
                1 if tipo == "CAMPO_TEC" else 0,
                dxf_x, dxf_y,
                round(rel_x, 4), round(rel_y, 4), round(rel_y_img, 4)
            )
        conn.commit()
        log.info("TEXTOS: %d guardados para plano_id=%d", len(textos), plano_id)
    except Exception as e:
        log.error("save_textos error: %s", e)
        conn.rollback()


# ─── RADIOS ───────────────────────────────────────────────────────────────────

def save_radios(conn, plano_id: int, radios: list, dxf_bounds: list):
    bounds = dxf_bounds or [0, 0, 1000, 1000]
    xmin, ymin, xmax, ymax = bounds
    dxf_w = xmax - xmin
    dxf_h = ymax - ymin

    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM [AUTOMATA].[RADIOS] WHERE PLANO_ID=?", plano_id)
        for r in radios:
            dxf_x = r.get("x", 0)
            dxf_y = r.get("y", 0)
            rel_x    = _normalize_rel(dxf_x - xmin, dxf_w)
            rel_y    = _normalize_rel(dxf_y - ymin, dxf_h)
            rel_y_img = 1.0 - rel_y
            _, _, zona = _calc_zona(rel_x, rel_y_img)
            cursor.execute("""
                INSERT INTO [AUTOMATA].[RADIOS]
                (PLANO_ID, TEXTO_ORIG, VALOR, LAYER, DXF_X, DXF_Y, REL_X, REL_Y, ZONA)
                VALUES (?,?,?,?,?,?,?,?,?)
            """,
                plano_id, r.get("texto"), r.get("valor"),
                r.get("layer"), dxf_x, dxf_y,
                round(rel_x, 4), round(rel_y_img, 4), zona
            )
        conn.commit()
    except Exception as e:
        log.error("save_radios error: %s", e)
        conn.rollback()


# ─── COTAS ────────────────────────────────────────────────────────────────────

def save_cotas(conn, plano_id: int, cotas: list, dxf_bounds: list):
    bounds = dxf_bounds or [0, 0, 1000, 1000]
    xmin, ymin, xmax, ymax = bounds
    dxf_w = xmax - xmin
    dxf_h = ymax - ymin

    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM [AUTOMATA].[COTAS] WHERE PLANO_ID=?", plano_id)
        for c in cotas:
            dxf_x = c.get("x", 0)
            dxf_y = c.get("y", 0)
            rel_x    = _normalize_rel(dxf_x - xmin, dxf_w)
            rel_y    = _normalize_rel(dxf_y - ymin, dxf_h)
            rel_y_img = 1.0 - rel_y
            _, _, zona = _calc_zona(rel_x, rel_y_img)
            cursor.execute("""
                INSERT INTO [AUTOMATA].[COTAS]
                (PLANO_ID, VALOR, ORIENTACION, LAYER, DXF_X, DXF_Y, REL_X, REL_Y, ZONA)
                VALUES (?,?,?,?,?,?,?,?,?)
            """,
                plano_id, c.get("valor"),
                c.get("orientacion"),
                c.get("layer"), dxf_x, dxf_y,
                round(rel_x, 4), round(rel_y_img, 4), zona
            )
        conn.commit()
    except Exception as e:
        log.error("save_cotas error: %s", e)
        conn.rollback()


# ─── IMAGENES SAP ─────────────────────────────────────────────────────────────

def save_imagenes_sap(conn, plano_id: int, imagenes: list):
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM [AUTOMATA].[IMAGENES_SAP] WHERE PLANO_ID=?", plano_id)
        if not imagenes:
            cursor.execute("""
                INSERT INTO [AUTOMATA].[IMAGENES_SAP] (PLANO_ID, ENCONTRADA)
                VALUES (?, 0)
            """, plano_id)
        else:
            for img in imagenes:
                cursor.execute("""
                    INSERT INTO [AUTOMATA].[IMAGENES_SAP]
                    (PLANO_ID, DOCUMENTO, RUTA_SAP, ENCONTRADA)
                    VALUES (?,?,?,1)
                """, plano_id, img.get("documento"), img.get("plano"))
        conn.commit()
    except Exception as e:
        log.error("save_imagenes_sap error: %s", e)
        conn.rollback()


# ─── LECTURA para API ─────────────────────────────────────────────────────────

def get_plano_completo(vehiculo: str, carpeta: str, archivo: str) -> dict | None:
    """
    Carga todos los datos de un plano desde DB para servir en la API.
    Retorna None si no existe o hay error.
    """
    conn = _get_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ID, PIEZA_COD, PIEZA_NOMBRE,
                   DXF_XMIN, DXF_YMIN, DXF_XMAX, DXF_YMAX,
                   RENDER_PATH, RENDER_W_PX, RENDER_H_PX, ESTADO, ERROR_MSG
            FROM [AUTOMATA].[PLANOS]
            WHERE VEHICULO=? AND CARPETA=? AND ARCHIVO=?
        """, vehiculo, carpeta or "", archivo)
        row = cursor.fetchone()
        if not row:
            return None
        plano_id = row[0]

        dxf_bounds = [row[3] or 0, row[4] or 0, row[5] or 0, row[6] or 0]

        # Cajetines
        cursor.execute("""
            SELECT CAJ_INDEX, CAMPOS_JSON, DXF_X, DXF_Y, ZONA,
                   REL_X, REL_Y_IMG, BBOX_XMIN, BBOX_YMIN, BBOX_XMAX, BBOX_YMAX,
                   PX_X, PX_Y, BBOX_PX_LEFT, BBOX_PX_TOP, BBOX_PX_W, BBOX_PX_H,
                   OFFSET_VAL, BN_D_VAL
            FROM [AUTOMATA].[CAJETINES]
            WHERE PLANO_ID=? ORDER BY CAJ_INDEX
        """, plano_id)
        cajetines = []
        for c in cursor.fetchall():
            campos = json.loads(c[1]) if c[1] else {}
            cajetines.append({
                "id": c[0], "campos": campos,
                "x": c[2], "y": c[3], "zona": c[4],
                "rel_x": c[5], "rel_y_img": c[6],
                "bbox": [c[7], c[8], c[9], c[10]],
                "center_px": {"x": c[11], "y": c[12]},
                "bbox_px": {"left": c[13], "top": c[14],
                            "width": c[15], "height": c[16]},
            })

        # Imágenes SAP
        cursor.execute("""
            SELECT DOCUMENTO, RUTA_SAP, ENCONTRADA
            FROM [AUTOMATA].[IMAGENES_SAP]
            WHERE PLANO_ID=?
        """, plano_id)
        imagenes_sap = []
        for img in cursor.fetchall():
            if img[2]:  # ENCONTRADA=1
                ruta = img[1] or ""
                imagenes_sap.append({
                    "documento": img[0],
                    "plano": ruta,
                    "plano_url": f"/sap-image?ruta={ruta}"
                })

        render_path = row[7] or ""
        render_filename = Path(render_path).name if render_path else ""

        return {
            "plano_id":     plano_id,
            "archivo":      archivo,
            "vehiculo":     vehiculo,
            "carpeta":      carpeta,
            "pieza_cod":    row[1],
            "pieza_nombre": row[2],
            "cajetines":    cajetines,
            "render": {
                "png":        render_path,
                "png_url":    f"/renders/{render_filename}" if render_filename else None,
                "width_px":   row[8],
                "height_px":  row[9],
                "dxf_bounds": dxf_bounds,
            },
            "imagenes_sap": imagenes_sap,
            "error":        row[11] or "",
        }
    except Exception as e:
        log.error("get_plano_completo error: %s", e)
        return None
    finally:
        conn.close()


def get_hash_en_db(conn, vehiculo: str, carpeta: str, archivo: str) -> str | None:
    """Retorna el hash guardado en DB para detectar cambios."""
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT HASH_ARCHIVO FROM [AUTOMATA].[PLANOS] WHERE VEHICULO=? AND CARPETA=? AND ARCHIVO=?",
            vehiculo, carpeta or "", archivo
        )
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception:
        return None


def test_connection() -> bool:
    conn = _get_connection()
    if conn:
        conn.close()
        return True
    return False

"""
Comparador de similitud entre planos del mismo tipo de pieza.
Algoritmo por zonas: empareja cajetines por zona semántica, luego compara valores.
Score 0.0-1.0 ponderado por: cajetines (40%) + radios (25%) + cotas (20%) + geometría (15%).
"""
import logging
import re
from pathlib import Path
from config.settings import PARES_SIMETRIA

log = logging.getLogger(__name__)

# Pesos del score final
W_CAJETINES = 0.40
W_RADIOS    = 0.25
W_COTAS     = 0.20
W_GEOM      = 0.15


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _jaccard(set_a: set, set_b: set) -> float:
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def _bn_d_to_float(val: str) -> float | None:
    """'69+5' → 74.0, '25' → 25.0"""
    if not val:
        return None
    m = re.match(r'^(\d+\.?\d*)\+(\d+\.?\d*)$', str(val).strip())
    if m:
        return float(m.group(1)) + float(m.group(2))
    try:
        return float(val)
    except Exception:
        return None


def _round_cota(val: float, tolerance: float = 0.05) -> int:
    """Redondea cota al entero más cercano para comparar con tolerancia."""
    return round(val)


def _piezas_a_buscar(pieza_cod: str, piezas_cod_str: str | None) -> set[str]:
    """
    Devuelve todos los códigos que deben buscarse al comparar este plano.
    Incluye pieza principal, todas las del PIEZAS_COD y su par de simetría.
    """
    codigos = set()
    if pieza_cod:
        codigos.add(pieza_cod)
        if pieza_cod in PARES_SIMETRIA:
            codigos.add(PARES_SIMETRIA[pieza_cod])
    if piezas_cod_str:
        for c in piezas_cod_str.split(","):
            c = c.strip()
            if c:
                codigos.add(c)
                if c in PARES_SIMETRIA:
                    codigos.add(PARES_SIMETRIA[c])
    return codigos


# ─── Score de cajetines por zona ──────────────────────────────────────────────

def _score_cajetines(cajs_a: list[dict], cajs_b: list[dict]) -> tuple[float, list]:
    """
    Empareja cajetines por zona semántica y compara valores OFFSET y BN+D.
    Retorna (score 0-1, lista de matches/diffs para UI).
    """
    if not cajs_a and not cajs_b:
        return 1.0, []
    if not cajs_a or not cajs_b:
        return 0.0, []

    # Agrupar por zona
    by_zona_a = {}
    by_zona_b = {}
    for c in cajs_a:
        z = c.get("zona") or "UNKNOWN"
        by_zona_a.setdefault(z, []).append(c)
    for c in cajs_b:
        z = c.get("zona") or "UNKNOWN"
        by_zona_b.setdefault(z, []).append(c)

    todas_zonas = set(by_zona_a) | set(by_zona_b)
    scores_zona = []
    detalles    = []

    for zona in sorted(todas_zonas):
        lista_a = by_zona_a.get(zona, [])
        lista_b = by_zona_b.get(zona, [])

        if not lista_a and not lista_b:
            continue

        # Conteo de cajetines por zona (penaliza diferencia en cantidad)
        n_a, n_b = len(lista_a), len(lista_b)
        count_score = 1.0 - abs(n_a - n_b) / max(n_a, n_b)

        # Comparar OFFSET y BN+D: tomar el mejor emparejamiento
        offsets_a = {c.get("offset_val") for c in lista_a if c.get("offset_val") is not None}
        offsets_b = {c.get("offset_val") for c in lista_b if c.get("offset_val") is not None}

        bn_a = {_bn_d_to_float(c.get("bn_d_val")) for c in lista_a if c.get("bn_d_val")}
        bn_b = {_bn_d_to_float(c.get("bn_d_val")) for c in lista_b if c.get("bn_d_val")}
        bn_a.discard(None); bn_b.discard(None)

        offset_score = _jaccard(offsets_a, offsets_b)
        bn_score     = _jaccard(bn_a, bn_b)

        zona_score = count_score * 0.3 + offset_score * 0.4 + bn_score * 0.3
        scores_zona.append(zona_score)

        detalles.append({
            "zona": zona,
            "score": round(zona_score, 3),
            "n_a": n_a, "n_b": n_b,
            "offsets_a": sorted(offsets_a), "offsets_b": sorted(offsets_b),
            "bn_a": sorted(bn_a), "bn_b": sorted(bn_b),
            "match": zona_score >= 0.7,
        })

    score = sum(scores_zona) / len(scores_zona) if scores_zona else 0.0
    return round(score, 4), detalles


def _score_radios(radios_a: list[dict], radios_b: list[dict]) -> float:
    vals_a = {round(r["valor"]) for r in radios_a if r.get("valor")}
    vals_b = {round(r["valor"]) for r in radios_b if r.get("valor")}
    return _jaccard(vals_a, vals_b)


def _score_cotas(cotas_a: list[dict], cotas_b: list[dict],
                 tolerancia_pct: float = 0.05) -> float:
    """
    Compara cotas con tolerancia ±5%. Una cota de A 'coincide' con una de B
    si están dentro del rango de tolerancia.
    """
    if not cotas_a and not cotas_b:
        return 1.0
    if not cotas_a or not cotas_b:
        return 0.0

    vals_a = sorted(c["valor"] for c in cotas_a if c.get("valor"))
    vals_b = sorted(c["valor"] for c in cotas_b if c.get("valor"))

    matched_a = set()
    matched_b = set()
    for i, va in enumerate(vals_a):
        for j, vb in enumerate(vals_b):
            if j in matched_b:
                continue
            if va == 0:
                continue
            if abs(va - vb) / max(va, vb) <= tolerancia_pct:
                matched_a.add(i)
                matched_b.add(j)
                break

    total = len(vals_a) + len(vals_b)
    if total == 0:
        return 1.0
    return (len(matched_a) + len(matched_b)) / total


def _score_geometria(plano_a: dict, plano_b: dict) -> float:
    """Compara aspect ratio y dimensiones relativas del bounding box."""
    ar_a = plano_a.get("aspect_ratio")
    ar_b = plano_b.get("aspect_ratio")
    if not ar_a or not ar_b:
        return 0.5  # neutro si no hay datos
    diff = abs(ar_a - ar_b) / max(ar_a, ar_b)
    return max(0.0, 1.0 - diff * 3)  # penaliza fuerte diferencia de forma


# ─── Score total ──────────────────────────────────────────────────────────────

def calcular_score(plano_a: dict, cajs_a: list, radios_a: list, cotas_a: list,
                   plano_b: dict, cajs_b: list, radios_b: list, cotas_b: list) -> dict:
    """
    Calcula score de similitud completo entre dos planos.
    Retorna dict con score_total y desglose.
    """
    sc_caj, detalles_caj = _score_cajetines(cajs_a, cajs_b)
    sc_rad  = _score_radios(radios_a, radios_b)
    sc_cot  = _score_cotas(cotas_a, cotas_b)
    sc_geom = _score_geometria(plano_a, plano_b)

    total = (sc_caj  * W_CAJETINES +
             sc_rad  * W_RADIOS    +
             sc_cot  * W_COTAS     +
             sc_geom * W_GEOM)

    return {
        "score_total":     round(total, 4),
        "score_cajetines": round(sc_caj, 4),
        "score_radios":    round(sc_rad, 4),
        "score_cotas":     round(sc_cot, 4),
        "score_geometria": round(sc_geom, 4),
        "detalles_zonas":  detalles_caj,
        "cajetines_a":     len(cajs_a),
        "cajetines_b":     len(cajs_b),
    }


# ─── API principal ────────────────────────────────────────────────────────────

def buscar_similares(plano_id: int, top_n: int = 10,
                     mismo_vehiculo: bool = False) -> list[dict]:
    """
    Busca los N planos más similares al dado.
    Por defecto busca en todos los vehículos (para comparación cross-vehicle).
    Si mismo_vehiculo=True, solo compara dentro del mismo vehículo.

    Retorna lista ordenada de mayor a menor similitud:
    [{plano_id, vehiculo, archivo, carpeta, pieza_cod, pieza_nombre,
      score_total, score_cajetines, score_radios, score_cotas, score_geometria,
      detalles_zonas, cajetines_a, cajetines_b}]
    """
    from core.ing_database import _get_connection
    conn = _get_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()

        # Cargar plano de referencia
        cursor.execute("""
            SELECT ID, VEHICULO, ARCHIVO, CARPETA, PIEZA_COD, PIEZAS_COD,
                   ASPECT_RATIO, DXF_ANCHO, DXF_ALTO
            FROM [AUTOMATA].[PLANOS] WHERE ID=?
        """, plano_id)
        ref = cursor.fetchone()
        if not ref:
            log.error("buscar_similares: plano_id=%d no encontrado", plano_id)
            return []

        ref_pieza    = ref[4]
        ref_piezas   = ref[5]
        ref_vehiculo = ref[1]

        # Códigos a buscar (pieza + simetría)
        codigos = _piezas_a_buscar(ref_pieza, ref_piezas)
        if not codigos:
            log.warning("buscar_similares: plano_id=%d sin pieza_cod", plano_id)
            return []

        plano_ref = {"aspect_ratio": ref[6], "dxf_ancho": ref[7], "dxf_alto": ref[8]}

        # Cargar cajetines, radios, cotas del plano de referencia
        cajs_ref    = _load_cajetines(conn, plano_id)
        radios_ref  = _load_radios(conn, plano_id)
        cotas_ref   = _load_cotas(conn, plano_id)

        # Buscar candidatos: misma pieza (o simetría), excluyendo el propio plano
        placeholders = ",".join("?" * len(codigos))
        vehiculo_filter = "AND VEHICULO=?" if mismo_vehiculo else ""
        params = list(codigos)
        if mismo_vehiculo:
            params.append(ref_vehiculo)
        params.append(plano_id)

        cursor.execute(f"""
            SELECT ID, VEHICULO, ARCHIVO, CARPETA, PIEZA_COD, PIEZA_NOMBRE,
                   PIEZAS_COD, ASPECT_RATIO, DXF_ANCHO, DXF_ALTO, RENDER_PATH
            FROM [AUTOMATA].[PLANOS]
            WHERE (
                PIEZA_COD IN ({placeholders})
                OR PIEZAS_COD LIKE '%' + ? + '%'
            )
            {vehiculo_filter}
            AND ID != ?
            AND ESTADO = 'OK'
        """, *params[:len(codigos)], list(codigos)[0], *params[len(codigos):])

        candidatos = cursor.fetchall()
        log.info("buscar_similares: %d candidatos para pieza(s) %s", len(candidatos), codigos)

        resultados = []
        for cand in candidatos:
            cand_id = cand[0]
            render_path = cand[10] or ""
            render_filename = Path(render_path).name if render_path else ""
            # png_url: intenta /renders/filename primero, fallback a /api/render/<id>
            png_url = f"/renders/{render_filename}" if render_filename else f"/api/render/{cand_id}"
            plano_cand = {"aspect_ratio": cand[7], "dxf_ancho": cand[8], "dxf_alto": cand[9]}

            cajs_cand   = _load_cajetines(conn, cand_id)
            radios_cand = _load_radios(conn, cand_id)
            cotas_cand  = _load_cotas(conn, cand_id)

            score = calcular_score(
                plano_ref, cajs_ref, radios_ref, cotas_ref,
                plano_cand, cajs_cand, radios_cand, cotas_cand
            )

            resultados.append({
                "plano_id":        cand_id,
                "vehiculo":        cand[1],
                "archivo":         cand[2],
                "carpeta":         cand[3],
                "pieza_cod":       cand[4],
                "pieza_nombre":    cand[5],
                "piezas_cod":      cand[6],
                **score,
            })

        # Ordenar por score descendente y retornar top N
        resultados.sort(key=lambda x: x["score_total"], reverse=True)
        return resultados[:top_n]

    except Exception as e:
        log.error("buscar_similares error: %s", e)
        return []
    finally:
        conn.close()


# ─── Loaders internos ─────────────────────────────────────────────────────────

def _load_cajetines(conn, plano_id: int) -> list[dict]:
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ZONA, OFFSET_VAL, BN_D_VAL, BN_VAL, REL_X, REL_Y_IMG
        FROM [AUTOMATA].[CAJETINES] WHERE PLANO_ID=?
    """, plano_id)
    return [{"zona": r[0], "offset_val": r[1], "bn_d_val": r[2],
             "bn_val": r[3], "rel_x": r[4], "rel_y_img": r[5]}
            for r in cursor.fetchall()]


def _load_radios(conn, plano_id: int) -> list[dict]:
    cursor = conn.cursor()
    cursor.execute("SELECT VALOR, ZONA FROM [AUTOMATA].[RADIOS] WHERE PLANO_ID=?", plano_id)
    return [{"valor": r[0], "zona": r[1]} for r in cursor.fetchall()]


def _load_cotas(conn, plano_id: int) -> list[dict]:
    cursor = conn.cursor()
    cursor.execute("SELECT VALOR, ZONA FROM [AUTOMATA].[COTAS] WHERE PLANO_ID=?", plano_id)
    return [{"valor": r[0], "zona": r[1]} for r in cursor.fetchall()]

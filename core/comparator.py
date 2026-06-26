"""
Comparador de similitud entre planos del mismo tipo de pieza.
Algoritmo por zonas: empareja métricas por zona semántica, luego compara valores.

Score 0.0-1.0 ponderado:
  Cajetines   25%  (por zona: OFFSET + BN+D)
  Perímetro   20%  (área real del layer PERIMETRO + longitud)
  Radios      15%  (por zona: valores de R*)
  Cotas       15%  (por zona: dimensiones lineales ±5%)
  Ángulo      10%  (ángulo de instalación)
  Layers      10%  (presencia y densidad de layers)
  Geometría    5%  (aspect ratio, tiebreaker)
"""
import logging
import re
from pathlib import Path
from config.settings import PARES_SIMETRIA

log = logging.getLogger(__name__)

W_CAJETINES = 0.25
W_PERIMETRO = 0.20
W_RADIOS    = 0.15
W_COTAS     = 0.15
W_ANGULO    = 0.10
W_LAYERS    = 0.10
W_GEOM      = 0.05


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _jaccard(set_a: set, set_b: set) -> float:
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    return len(set_a & set_b) / len(union) if union else 0.0


def _bn_d_to_float(val: str) -> float | None:
    if not val:
        return None
    m = re.match(r'^(\d+\.?\d*)\+(\d+\.?\d*)$', str(val).strip())
    if m:
        return float(m.group(1)) + float(m.group(2))
    try:
        return float(val)
    except Exception:
        return None


def _piezas_a_buscar(pieza_cod: str, piezas_cod_str: str | None) -> set[str]:
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


# ─── Cajetines por zona ───────────────────────────────────────────────────────

def _score_cajetines(cajs_a: list[dict], cajs_b: list[dict]) -> tuple[float, list]:
    if not cajs_a and not cajs_b:
        return 1.0, []
    if not cajs_a or not cajs_b:
        return 0.0, []

    by_zona_a, by_zona_b = {}, {}
    for c in cajs_a:
        by_zona_a.setdefault(c.get("zona") or "UNKNOWN", []).append(c)
    for c in cajs_b:
        by_zona_b.setdefault(c.get("zona") or "UNKNOWN", []).append(c)

    todas_zonas = set(by_zona_a) | set(by_zona_b)
    scores, detalles = [], []

    for zona in sorted(todas_zonas):
        la, lb = by_zona_a.get(zona, []), by_zona_b.get(zona, [])
        if not la and not lb:
            continue
        na, nb = len(la), len(lb)
        count_score = 1.0 - abs(na - nb) / max(na, nb)

        offsets_a = {c.get("offset_val") for c in la if c.get("offset_val") is not None}
        offsets_b = {c.get("offset_val") for c in lb if c.get("offset_val") is not None}
        bn_a = {_bn_d_to_float(c.get("bn_d_val")) for c in la if c.get("bn_d_val")}
        bn_b = {_bn_d_to_float(c.get("bn_d_val")) for c in lb if c.get("bn_d_val")}
        bn_a.discard(None); bn_b.discard(None)

        offset_score = _jaccard(offsets_a, offsets_b)
        bn_score     = _jaccard(bn_a, bn_b)
        zona_score   = count_score * 0.3 + offset_score * 0.4 + bn_score * 0.3
        scores.append(zona_score)
        detalles.append({
            "zona": zona, "score": round(zona_score, 3),
            "n_a": na, "n_b": nb,
            "offsets_a": sorted(offsets_a), "offsets_b": sorted(offsets_b),
            "bn_a": sorted(bn_a), "bn_b": sorted(bn_b),
            "match": zona_score >= 0.7,
        })

    score = sum(scores) / len(scores) if scores else 0.0
    return round(score, 4), detalles


# ─── Radios por zona ──────────────────────────────────────────────────────────

def _score_radios_por_zona(radios_a: list[dict], radios_b: list[dict]) -> tuple[float, list]:
    """Agrupa radios por zona 3x3 y compara valores dentro de cada zona."""
    if not radios_a and not radios_b:
        return 1.0, []
    if not radios_a or not radios_b:
        return 0.0, []

    by_zona_a, by_zona_b = {}, {}
    for r in radios_a:
        z = r.get("zona") or "UNKNOWN"
        v = round(r["valor"]) if r.get("valor") else None
        if v is not None:
            by_zona_a.setdefault(z, set()).add(v)
    for r in radios_b:
        z = r.get("zona") or "UNKNOWN"
        v = round(r["valor"]) if r.get("valor") else None
        if v is not None:
            by_zona_b.setdefault(z, set()).add(v)

    todas = set(by_zona_a) | set(by_zona_b)
    scores, detalles = [], []

    for zona in sorted(todas):
        va = by_zona_a.get(zona, set())
        vb = by_zona_b.get(zona, set())
        s = _jaccard(va, vb)
        scores.append(s)
        detalles.append({
            "zona": zona, "score": round(s, 3),
            "vals_a": sorted(va), "vals_b": sorted(vb),
            "match": s >= 0.7,
            "solo_a": sorted(va - vb),   # radios que solo tiene A
            "solo_b": sorted(vb - va),   # radios que solo tiene B
        })

    return round(sum(scores) / len(scores), 4) if scores else 0.0, detalles


# ─── Cotas por zona ───────────────────────────────────────────────────────────

def _score_cotas_por_zona(cotas_a: list[dict], cotas_b: list[dict],
                           tolerancia_pct: float = 0.05) -> tuple[float, list]:
    """Compara cotas por zona con tolerancia ±5%."""
    if not cotas_a and not cotas_b:
        return 1.0, []
    if not cotas_a or not cotas_b:
        return 0.0, []

    by_zona_a, by_zona_b = {}, {}
    for c in cotas_a:
        z = c.get("zona") or "UNKNOWN"
        if c.get("valor"):
            by_zona_a.setdefault(z, []).append(c["valor"])
    for c in cotas_b:
        z = c.get("zona") or "UNKNOWN"
        if c.get("valor"):
            by_zona_b.setdefault(z, []).append(c["valor"])

    todas = set(by_zona_a) | set(by_zona_b)
    scores, detalles = [], []

    for zona in sorted(todas):
        va = sorted(by_zona_a.get(zona, []))
        vb = sorted(by_zona_b.get(zona, []))
        if not va and not vb:
            continue
        matched_a, matched_b = set(), set()
        for i, a in enumerate(va):
            for j, b in enumerate(vb):
                if j in matched_b or a == 0:
                    continue
                if abs(a - b) / max(a, b) <= tolerancia_pct:
                    matched_a.add(i); matched_b.add(j); break
        total = len(va) + len(vb)
        s = (len(matched_a) + len(matched_b)) / total if total else 1.0
        scores.append(s)
        detalles.append({
            "zona": zona, "score": round(s, 3),
            "vals_a": [round(v) for v in va[:6]],
            "vals_b": [round(v) for v in vb[:6]],
            "match": s >= 0.6,
        })

    return round(sum(scores) / len(scores), 4) if scores else 0.0, detalles


# ─── Perímetro ────────────────────────────────────────────────────────────────

def _score_perimetro(plano_a: dict, plano_b: dict) -> float:
    """
    Compara área real del polígono PERIMETRO y su longitud.
    Diferencia de 10% en área → penalización fuerte.
    """
    area_a = plano_a.get("perimetro_area") or 0.0
    area_b = plano_b.get("perimetro_area") or 0.0
    long_a = plano_a.get("perimetro_long") or 0.0
    long_b = plano_b.get("perimetro_long") or 0.0

    if not area_a and not area_b:
        return 0.5  # sin datos → neutro

    scores = []
    if area_a and area_b:
        diff = abs(area_a - area_b) / max(area_a, area_b)
        scores.append(max(0.0, 1.0 - diff * 6))   # 17% diff → score 0

    if long_a and long_b:
        diff = abs(long_a - long_b) / max(long_a, long_b)
        scores.append(max(0.0, 1.0 - diff * 6))

    return round(sum(scores) / len(scores), 4) if scores else 0.5


# ─── Ángulo de instalación ────────────────────────────────────────────────────

def _score_angulo(plano_a: dict, plano_b: dict) -> float:
    """
    Compara ángulo de instalación extraído del texto del plano.
    ±2° = perfecto, ±15° = 0.
    """
    ang_a = plano_a.get("angulo_instalacion")
    ang_b = plano_b.get("angulo_instalacion")
    if ang_a is None or ang_b is None:
        return 0.5
    diff = abs(ang_a - ang_b)
    return round(max(0.0, 1.0 - diff / 15.0), 4)


# ─── Layers ───────────────────────────────────────────────────────────────────

# Layers técnicamente relevantes (ignorar los de dimensiones/texto/viewport)
_LAYERS_RELEVANTES = {
    "PERIMETRO", "PERIMETR", "CORTE", "ACERO", "BANDA", "RADIO",
    "SECCION", "SECTION", "LINEA", "OUTLINE", "GLASS", "VIDRIO",
    "SELLANTE", "SEALANT", "CLIP", "BRACKET", "MOLDURA",
}

def _score_layers(layers_a: dict, layers_b: dict) -> float:
    """
    Compara layers técnicos presentes y densidad de entidades.
    Ignora layers de texto, cotas y viewports.
    """
    def _filtrar(layers: dict) -> dict:
        out = {}
        for name, stats in layers.items():
            n = name.upper()
            # Incluir si es relevante o tiene muchas entidades
            if any(r in n for r in _LAYERS_RELEVANTES) or stats.get("count", 0) > 10:
                out[name] = stats
        return out

    fa = _filtrar(layers_a)
    fb = _filtrar(layers_b)

    if not fa and not fb:
        return 0.5

    names_a = set(fa.keys())
    names_b = set(fb.keys())
    presence = _jaccard(names_a, names_b)

    comunes = names_a & names_b
    density_scores = []
    for layer in comunes:
        ca = fa[layer].get("count", 0)
        cb = fb[layer].get("count", 0)
        if ca == 0 and cb == 0:
            density_scores.append(1.0)
        else:
            diff = abs(ca - cb) / max(ca, cb)
            density_scores.append(max(0.0, 1.0 - diff))

    density = sum(density_scores) / len(density_scores) if density_scores else 0.0
    return round(presence * 0.6 + density * 0.4, 4)


# ─── Geometría (tiebreaker) ───────────────────────────────────────────────────

def _score_geometria(plano_a: dict, plano_b: dict) -> float:
    ar_a = plano_a.get("aspect_ratio")
    ar_b = plano_b.get("aspect_ratio")
    if not ar_a or not ar_b:
        return 0.5
    diff = abs(ar_a - ar_b) / max(ar_a, ar_b)
    return max(0.0, 1.0 - diff * 3)


# ─── Score total ──────────────────────────────────────────────────────────────

def calcular_score(plano_a: dict, cajs_a: list, radios_a: list, cotas_a: list,
                   plano_b: dict, cajs_b: list, radios_b: list, cotas_b: list,
                   layers_a: dict = None, layers_b: dict = None) -> dict:

    sc_caj,  det_caj  = _score_cajetines(cajs_a, cajs_b)
    sc_rad,  det_rad  = _score_radios_por_zona(radios_a, radios_b)
    sc_cot,  det_cot  = _score_cotas_por_zona(cotas_a, cotas_b)
    sc_per              = _score_perimetro(plano_a, plano_b)
    sc_ang              = _score_angulo(plano_a, plano_b)
    sc_lay              = _score_layers(layers_a or {}, layers_b or {})
    sc_geom             = _score_geometria(plano_a, plano_b)

    total = (sc_caj  * W_CAJETINES +
             sc_per  * W_PERIMETRO +
             sc_rad  * W_RADIOS    +
             sc_cot  * W_COTAS     +
             sc_ang  * W_ANGULO    +
             sc_lay  * W_LAYERS    +
             sc_geom * W_GEOM)

    return {
        "score_total":       round(total, 4),
        "score_cajetines":   round(sc_caj, 4),
        "score_perimetro":   round(sc_per, 4),
        "score_radios":      round(sc_rad, 4),
        "score_cotas":       round(sc_cot, 4),
        "score_angulo":      round(sc_ang, 4),
        "score_layers":      round(sc_lay, 4),
        "score_geometria":   round(sc_geom, 4),
        "detalles_cajetines": det_caj,
        "detalles_radios":    det_rad,
        "detalles_cotas":     det_cot,
    }


# ─── API principal ────────────────────────────────────────────────────────────

def buscar_similares(plano_id: int, top_n: int = 10,
                     mismo_vehiculo: bool = False) -> list[dict]:
    from core.ing_database import _get_connection
    conn = _get_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT ID, VEHICULO, ARCHIVO, CARPETA, PIEZA_COD, PIEZAS_COD,
                   ASPECT_RATIO, DXF_ANCHO, DXF_ALTO,
                   PERIMETRO_AREA, PERIMETRO_LONG, PERIMETRO_VERTICES, ANGULO_INSTALACION
            FROM [AUTOMATA].[PLANOS] WHERE ID=?
        """, plano_id)
        ref = cursor.fetchone()
        if not ref:
            log.error("buscar_similares: plano_id=%d no encontrado", plano_id)
            return []

        ref_vehiculo = ref[1]
        ref_pieza    = ref[4]
        ref_piezas   = ref[5]
        codigos = _piezas_a_buscar(ref_pieza, ref_piezas)
        if not codigos:
            log.warning("buscar_similares: plano_id=%d sin pieza_cod", plano_id)
            return []

        plano_ref = {
            "aspect_ratio":      ref[6],
            "dxf_ancho":         ref[7],
            "dxf_alto":          ref[8],
            "perimetro_area":    ref[9],
            "perimetro_long":    ref[10],
            "perimetro_vertices": ref[11],
            "angulo_instalacion": ref[12],
        }

        cajs_ref    = _load_cajetines(conn, plano_id)
        radios_ref  = _load_radios(conn, plano_id)
        cotas_ref   = _load_cotas(conn, plano_id)
        layers_ref  = _load_layer_stats(conn, plano_id)

        placeholders = ",".join("?" * len(codigos))
        vehiculo_filter = "AND VEHICULO=?" if mismo_vehiculo else ""
        params = list(codigos)
        if mismo_vehiculo:
            params.append(ref_vehiculo)
        params.append(plano_id)

        cursor.execute(f"""
            SELECT ID, VEHICULO, ARCHIVO, CARPETA, PIEZA_COD, PIEZA_NOMBRE,
                   PIEZAS_COD, ASPECT_RATIO, DXF_ANCHO, DXF_ALTO, RENDER_PATH,
                   PERIMETRO_AREA, PERIMETRO_LONG, PERIMETRO_VERTICES, ANGULO_INSTALACION
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
            render_path     = cand[10] or ""
            render_filename = Path(render_path).name if render_path else ""
            png_url = f"/renders/{render_filename}" if render_filename else f"/api/render/{cand_id}"

            plano_cand = {
                "aspect_ratio":      cand[7],
                "dxf_ancho":         cand[8],
                "dxf_alto":          cand[9],
                "perimetro_area":    cand[11],
                "perimetro_long":    cand[12],
                "perimetro_vertices": cand[13],
                "angulo_instalacion": cand[14],
            }

            cajs_cand   = _load_cajetines(conn, cand_id)
            radios_cand = _load_radios(conn, cand_id)
            cotas_cand  = _load_cotas(conn, cand_id)
            layers_cand = _load_layer_stats(conn, cand_id)

            score = calcular_score(
                plano_ref, cajs_ref, radios_ref, cotas_ref,
                plano_cand, cajs_cand, radios_cand, cotas_cand,
                layers_ref, layers_cand,
            )

            resultados.append({
                "plano_id":     cand_id,
                "vehiculo":     cand[1],
                "archivo":      cand[2],
                "carpeta":      cand[3],
                "pieza_cod":    cand[4],
                "pieza_nombre": cand[5],
                "piezas_cod":   cand[6],
                "png_url":      png_url,
                **score,
            })

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


def _load_layer_stats(conn, plano_id: int) -> dict:
    """Retorna {LAYER_NAME: {count, length}} para el plano."""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT LAYER_NAME, ENTIDADES, LONGITUD_TOTAL
            FROM [AUTOMATA].[LAYER_STATS] WHERE PLANO_ID=?
        """, plano_id)
        return {r[0]: {"count": r[1], "length": r[2] or 0.0} for r in cursor.fetchall()}
    except Exception:
        return {}

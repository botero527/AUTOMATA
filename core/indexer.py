"""
Indexador de planos DWG → DB [AUTOMATA].
Escanea la red, detecta archivos nuevos/modificados y los procesa completo.
Guarda en AGP_Ingenieria.AUTOMATA (no JSON).
"""
import hashlib
import logging
import re
from pathlib import Path

from config.settings import (
    NETWORK_BASE_PATH, RENDERS_DIR, DXF_DIR,
    PIECE_TYPES, TECHNICAL_FIELDS
)

log = logging.getLogger(__name__)

# Carpetas a ignorar en el escaneo
_SKIP = re.compile(
    r"^(3D|ACERO|ARTES|ARCHIVOS|BACKUP|BAE|BRAZO|DESARROLLO|DIGITALIZACION|"
    r"ESCANEADO|GALGAS|GALGA|INFO|INFORMACION|Nueva carpeta|OBSOLETO|obsoletos|"
    r"OneDrive|PBS|Pedidos|PLANTILLAS|PLANOS PERU|PLANOS PER|PREMIUM EDGE|"
    r"PROPUESTA|PRUEBA|PVTE|RHINO|SUPERFICIES)",
    re.IGNORECASE
)


# ─── Utilidades ───────────────────────────────────────────────────────────────

def _hash_file(path: Path, chunk=65536) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                data = f.read(chunk)
                if not data:
                    break
                h.update(data)
        return h.hexdigest()
    except Exception:
        return ""


def _parse_piezas_cod(filename: str) -> list[str]:
    """
    Extrae código(s) de pieza del nombre del archivo.
    Retorna lista de códigos (normalmente 1, a veces 2 cuando son piezas combinadas).

    Ejemplos:
      '1761 006 005 A.dwg'      → ['005']
      '1761 006 05 A.dwg'       → ['005']
      'CR 1576 000 007-008 B'   → ['007', '008']
      'CR 958 00 03-04 A.dwg'   → ['003', '004']
      '1056 00 01-02.dwg'       → ['001', '002']
    """
    stem = re.sub(r"\.(dwg|dxf)$", "", filename, flags=re.IGNORECASE).strip()
    stem = re.sub(r"\s+[A-Z]{1,2}$", "", stem).strip()  # quitar revisión final (A, B, EO...)

    # Detectar patrón de dos piezas: NN-NN o NNN-NNN (máx 3 dígitos cada lado)
    m = re.search(r"\b(\d{1,3})-(\d{1,3})\b", stem)
    if m:
        return [m.group(1).zfill(3), m.group(2).zfill(3)]

    # Caso normal: tomar el último grupo de 1-3 dígitos
    parts = re.findall(r"\b(\d{1,3})\b", stem)
    if not parts:
        return []
    candidates = parts[1:] if len(parts) > 1 else parts
    return [candidates[-1].zfill(3)]


def _parse_carpeta_parts(vehiculo: str, carpeta: str) -> tuple:
    """
    Extrae marca/modelo/version de la ruta de carpetas.
    carpeta='V-02/ASTON MARTIN/DBX707' → ('ASTON MARTIN','DBX707', 'V-02')
    """
    if not carpeta or carpeta == "(raíz)":
        return (None, None, None)
    parts = [p for p in carpeta.replace("\\", "/").split("/") if p]
    marca   = parts[0] if len(parts) > 0 else None
    modelo  = parts[1] if len(parts) > 1 else None
    version = parts[2] if len(parts) > 2 else None
    return (marca, modelo, version)


def _extract_radios_cotas(textos: list, cajetin_values: set) -> tuple:
    """
    Filtra textos para separar radios (R6, R50) y cotas (números grandes).
    Excluye valores que ya están en cajetines.
    Retorna (radios, cotas).
    """
    radios = []
    cotas  = []
    for t in textos:
        texto = str(t.get("text", "")).strip()
        # Radio: 'R6', 'R50', 'R6.5'
        m = re.match(r'^R(\d+\.?\d*)$', texto, re.IGNORECASE)
        if m:
            radios.append({
                "texto": texto,
                "valor": float(m.group(1)),
                "x": t.get("x", 0),
                "y": t.get("y", 0),
                "layer": t.get("layer", ""),
            })
            continue
        # Cota: número puro > 50 que no es OFFSET ni BN
        if re.match(r'^\d+(\.\d+)?$', texto):
            val = float(texto)
            if val > 50 and texto not in cajetin_values:
                cotas.append({
                    "valor": val,
                    "x": t.get("x", 0),
                    "y": t.get("y", 0),
                    "layer": t.get("layer", ""),
                    "orientacion": None,
                })
    return radios, cotas


# ─── Pipeline de un plano ─────────────────────────────────────────────────────

def process_plano(vehiculo: str, carpeta: str, archivo: str,
                  dwg_path: Path, conn, force: bool = False) -> dict:
    """
    Procesa un DWG completo y guarda en DB.
    Retorna dict con resultado: {ok, plano_id, error}
    """
    from core.converter   import convert_dwg_to_dxf
    from core.extractor   import extract_from_dxf
    from core.renderer    import render_dxf
    from core.database    import buscar_imagenes
    from core.ing_database import (
        upsert_plano, save_cajetines, save_textos,
        save_radios, save_cotas, save_imagenes_sap,
        get_hash_en_db
    )

    current_hash = _hash_file(dwg_path)

    # ¿Ya procesado y sin cambios?
    if not force:
        db_hash = get_hash_en_db(conn, vehiculo, carpeta, archivo)
        if db_hash and db_hash == current_hash:
            log.info("SKIP (sin cambios): %s/%s/%s", vehiculo, carpeta, archivo)
            return {"ok": True, "skipped": True, "plano_id": None}

    log.info("Procesando: %s/%s/%s", vehiculo, carpeta, archivo)

    piezas_cods = _parse_piezas_cod(archivo)
    pieza_cod    = piezas_cods[0] if piezas_cods else None
    pieza_nombre = " + ".join(PIECE_TYPES.get(c, c) for c in piezas_cods) if piezas_cods else ""
    piezas_cod_str = ",".join(piezas_cods) if piezas_cods else None  # '007,008' o '005'
    marca, modelo, version = _parse_carpeta_parts(vehiculo, carpeta)
    carpeta_parts = [p for p in (carpeta or "").replace("\\","/").split("/") if p]

    safe_stem = re.sub(r"[^A-Za-z0-9_\-]", "_", f"{vehiculo}__{carpeta}__{Path(archivo).stem}")

    # 1. DWG → DXF
    dxf_path = convert_dwg_to_dxf(dwg_path)
    if not dxf_path:
        plano_data = {
            "vehiculo": vehiculo, "archivo": archivo, "carpeta": carpeta,
            "carpeta_parts": carpeta_parts,
            "pieza_cod": pieza_cod, "pieza_nombre": pieza_nombre, "piezas_cod": piezas_cod_str,
            "vehiculo_marca": marca, "vehiculo_modelo": modelo, "vehiculo_version": version,
            "ruta_red": str(dwg_path),
            "hash_archivo": current_hash, "estado": "ERROR",
            "error": "No se pudo convertir DWG",
        }
        upsert_plano(conn, plano_data)
        return {"ok": False, "error": "No se pudo convertir DWG"}

    # 2. Extraer cajetines y textos
    plano = extract_from_dxf(dxf_path, archivo, vehiculo, carpeta)

    # 3. Renderizar imagen
    render = render_dxf(dxf_path, safe_stem)

    # 4. Radios y cotas desde textos
    cajetin_values = set()
    for caj in plano.cajetines:
        for v in caj.campos.values():
            cajetin_values.add(str(v))
    radios, cotas = _extract_radios_cotas(plano.todos_los_textos, cajetin_values)

    # 5. Cajetines con coordenadas px
    cajetines_full = []
    for caj in plano.cajetines:
        caj_dict = caj.to_dict()
        if render:
            caj_dict["bbox_px"]   = render.bbox_to_px(caj.bbox)
            pt = render.dxf_to_px(caj.x, caj.y)
            caj_dict["center_px"] = {"x": pt[0], "y": pt[1]}
        cajetines_full.append(caj_dict)

    # 6. SAP
    imagenes_sap = buscar_imagenes(archivo)

    # 7. Guardar en DB
    render_info = render.to_dict() if render else {}
    plano_data = {
        "vehiculo": vehiculo, "archivo": archivo, "carpeta": carpeta,
        "carpeta_parts": carpeta_parts,
        "vehiculo_marca": marca, "vehiculo_modelo": modelo, "vehiculo_version": version,
        "pieza_cod": pieza_cod, "pieza_nombre": pieza_nombre, "piezas_cod": piezas_cod_str,
        "dxf_bounds": plano.dxf_bounds,
        "render_path": str(render.png_path) if render else None,
        "render_w": render_info.get("width_px"), "render_h": render_info.get("height_px"),
        "dxf_version": None,
        "total_textos":    len(plano.todos_los_textos),
        "total_cajetines": len(cajetines_full),
        "total_radios":    len(radios),
        "total_cotas":     len(cotas),
        "hash_archivo": current_hash,
        "ruta_red":     str(dwg_path),
        "estado": "ERROR" if plano.error else "OK",
        "error":  plano.error or None,
    }

    plano_id = upsert_plano(conn, plano_data)
    if not plano_id:
        return {"ok": False, "error": "No se pudo guardar en DB"}

    # Guardar detalle
    save_cajetines(conn, plano_id, cajetines_full, plano.dxf_bounds)
    save_textos(conn, plano_id, plano.todos_los_textos, plano.dxf_bounds)
    save_radios(conn, plano_id, radios, plano.dxf_bounds)
    save_cotas(conn, plano_id, cotas, plano.dxf_bounds)
    save_imagenes_sap(conn, plano_id, imagenes_sap)

    log.info("OK plano_id=%d | %d cajetines | %d radios | %d cotas",
             plano_id, len(cajetines_full), len(radios), len(cotas))
    return {"ok": True, "plano_id": plano_id, "skipped": False}


# ─── Escaneo y escaneo por vehículo ───────────────────────────────────────────

def _walk_dwgs(base: Path, vehiculo: str, rel_parts: list = None) -> list:
    """Recorre recursivamente buscando DWGs. Retorna lista de dicts."""
    if rel_parts is None:
        rel_parts = []
    results = []
    try:
        entries = sorted(base.iterdir(), key=lambda x: x.name)
    except Exception:
        return results

    for f in entries:
        if f.is_file() and f.suffix.lower() == ".dwg":
            carpeta = "/".join(rel_parts) if rel_parts else ""
            results.append({
                "vehiculo": vehiculo,
                "carpeta":  carpeta,
                "archivo":  f.name,
                "dwg_path": f,
            })

    for f in entries:
        if f.is_dir() and not _SKIP.match(f.name):
            results.extend(_walk_dwgs(f, vehiculo, rel_parts + [f.name]))

    return results


def index_vehiculo(vehiculo: str, force: bool = False) -> dict:
    """
    Indexa todos los planos de un vehículo.
    Retorna resumen: {total, procesados, skipped, errores}
    """
    from core.ing_database import _get_connection
    base = NETWORK_BASE_PATH / vehiculo
    if not base.exists():
        return {"error": f"Carpeta no encontrada: {vehiculo}"}

    planos = _walk_dwgs(base, vehiculo)
    log.info("Vehículo '%s': %d DWGs encontrados", vehiculo, len(planos))

    conn = _get_connection()
    if not conn:
        return {"error": "No se pudo conectar a AGP_Ingenieria"}

    stats = {"total": len(planos), "procesados": 0, "skipped": 0, "errores": 0, "detalles": []}
    try:
        for p in planos:
            try:
                result = process_plano(
                    p["vehiculo"], p["carpeta"], p["archivo"],
                    p["dwg_path"], conn, force=force
                )
                if result.get("skipped"):
                    stats["skipped"] += 1
                elif result.get("ok"):
                    stats["procesados"] += 1
                else:
                    stats["errores"] += 1
                    stats["detalles"].append({
                        "archivo": p["archivo"],
                        "error": result.get("error", "desconocido")
                    })
            except Exception as e:
                stats["errores"] += 1
                stats["detalles"].append({"archivo": p["archivo"], "error": str(e)})
                log.error("Error procesando %s: %s", p["archivo"], e)
    finally:
        conn.close()

    log.info("index_vehiculo '%s' completado: %s", vehiculo, stats)
    return stats


def index_all(force: bool = False) -> dict:
    """Indexa todos los vehículos disponibles en la red."""
    from api.server import get_vehiculos
    vehiculos = get_vehiculos()
    resumen = {"vehiculos": len(vehiculos), "detalles": {}}
    for v in vehiculos:
        log.info("=== Indexando vehículo: %s ===", v)
        resumen["detalles"][v] = index_vehiculo(v, force=force)
    return resumen

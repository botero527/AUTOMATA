"""
API Flask para AUTOMATA.
Endpoints:
  GET  /api/vehiculos               → lista de vehículos disponibles
  GET  /api/vehiculos/<v>/planos    → lista de planos de un vehículo
  GET  /api/plano/<v>/<carpeta>/<archivo>  → datos completos + imagen + cajetines
  GET  /renders/<filename>          → servir imágenes PNG
  GET  /sap-image                   → proxy de imágenes SAP (Z: drive)
  GET  /                            → visor principal
"""
import json
import logging
import os
import re
import base64
from pathlib import Path

from flask import Flask, jsonify, send_file, abort, request, send_from_directory
from flask_cors import CORS

from config.settings import NETWORK_BASE_PATH, RENDERS_DIR, DATA_DIR, PIECE_TYPES
from core.converter import convert_dwg_to_dxf
from core.extractor import extract_from_dxf
from core.renderer import render_dxf
from core.database import buscar_imagenes

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__, static_folder=str(Path(__file__).parent.parent / "web"))
CORS(app)

WEB_DIR = Path(__file__).parent.parent / "web"


# ─── Utilidades ───────────────────────────────────────────────────────────────

# Patrones de carpetas administrativas a excluir
_EXCLUDE_PATTERNS = re.compile(
    r"^(\d{2}-|Z[ZV]|AGP|ARCHIVOS|CARGUE|CONSECUTIVO|CORTE|DESARROLLOS|"
    r"ESCANER|ESTANDARES|FORMATO|FORMULAS|HZJ|INFORMES|LIBERACIONES|MESA|"
    r"PASATA|PASTA|PERU|PLANOS 3D|PLANTILLAS|PROY|PROYECTO|PVTE|RP2|"
    r"SOPORTE|STRIP|VINILOS|Backup|Nueva|OneDrive|Users|prueba|proyecto|"
    r"12mm|AAA|AG$|L$|n$|PJ$|NMI|ZPRO|Premium|Pedidos)",
    re.IGNORECASE
)

_SKIP_FOLDERS = re.compile(
    r"^(3D|ACERO|ARTES|ARCHIVOS|BACKUP|BAE|BRAZO|DESARROLLO|DIGITALIZACION|"
    r"ESCANEADO|GALGAS|GALGA|INFO|INFORMACION|Nueva carpeta|OBSOLETO|obsoletos|"
    r"OneDrive|PBS|Pedidos|PLANTILLAS|PLANOS PERU|PLANOS PER|PREMIUM EDGE|"
    r"PROPUESTA|PRUEBA|PVTE|RHINO|SUPERFICIES)",
    re.IGNORECASE
)

def _tiene_dwgs(folder: Path) -> bool:
    """Verifica rápido si una carpeta tiene DWGs en cualquier subnivel."""
    try:
        # rglob es la forma más sencilla — paramos al primer match
        for _ in folder.rglob("*.dwg"):
            return True
        for _ in folder.rglob("*.DWG"):
            return True
    except Exception:
        pass
    return False


def get_vehiculos() -> list[str]:
    try:
        vehiculos = []
        for d in sorted(NETWORK_BASE_PATH.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            if _EXCLUDE_PATTERNS.match(d.name):
                continue
            if _tiene_dwgs(d):
                vehiculos.append(d.name)
        return vehiculos
    except Exception as e:
        log.error("Error listando vehículos: %s", e)
        return []


def _walk_dwgs(base: Path, vehiculo: str, rel_parts: list[str] = None) -> list[dict]:
    """
    Recorre recursivamente buscando DWGs.
    Retorna lista de planos con ruta completa relativa como carpeta_path.
    Ignora subcarpetas de soporte (3D, ARTES, DESARROLLO, etc.)
    """
    if rel_parts is None:
        rel_parts = []

    results = []
    try:
        entries = sorted(base.iterdir(), key=lambda x: x.name)
    except Exception:
        return results

    # DWGs directamente en esta carpeta
    for f in entries:
        if f.is_file() and f.suffix.lower() == ".dwg":
            carpeta_path = "/".join(rel_parts) if rel_parts else "(raíz)"
            code_match = re.search(r"(\d{3})", f.stem)
            tipo = PIECE_TYPES.get(code_match.group(1), "") if code_match else ""
            results.append({
                "archivo":       f.name,
                "carpeta":       carpeta_path,          # ruta relativa completa
                "carpeta_parts": rel_parts.copy(),      # para árbol jerárquico
                "vehiculo":      vehiculo,
                "tipo":          tipo,
                "stem":          f.stem,
            })

    # Subcarpetas — recursión
    for f in entries:
        if not f.is_dir():
            continue
        if _SKIP_FOLDERS.match(f.name):
            continue
        results.extend(_walk_dwgs(f, vehiculo, rel_parts + [f.name]))

    return results


def get_planos(vehiculo: str) -> list[dict]:
    base = NETWORK_BASE_PATH / vehiculo
    try:
        return _walk_dwgs(base, vehiculo)
    except Exception as e:
        log.error("Error listando planos de %s: %s", vehiculo, e)
        return []


def _safe_stem(vehiculo: str, carpeta: str, archivo: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]", "_", f"{vehiculo}__{carpeta}__{archivo}")


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(str(WEB_DIR), "index.html")


@app.route("/assets/<path:filename>")
def assets(filename):
    return send_from_directory(str(WEB_DIR / "assets"), filename)


@app.route("/api/vehiculos")
def api_vehiculos():
    return jsonify(get_vehiculos())


@app.route("/api/vehiculos/<vehiculo>/planos")
def api_planos(vehiculo):
    return jsonify(get_planos(vehiculo))


@app.route("/api/plano/<vehiculo>/<path:carpeta_path>/<archivo>")
def api_plano(vehiculo, carpeta_path, archivo):
    # carpeta_path puede ser "MODELO/VERSION" o solo "VERSION"
    # En la red, "/" separa carpetas reales
    dwg_path = NETWORK_BASE_PATH / vehiculo / Path(carpeta_path.replace("/", "\\")) / archivo
    if not dwg_path.exists():
        # Intentar también con la carpeta directamente (DWGs en raíz del vehículo)
        dwg_path = NETWORK_BASE_PATH / vehiculo / archivo
        if not dwg_path.exists():
            abort(404, f"Archivo no encontrado: {vehiculo}/{carpeta_path}/{archivo}")
    carpeta = carpeta_path

    stem      = _safe_stem(vehiculo, carpeta, dwg_path.stem)
    data_file = DATA_DIR / (stem + ".json")

    # Usar caché si existe
    if data_file.exists():
        with open(data_file, encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)

    # 1. Convertir DWG → DXF
    log.info("Procesando: %s", archivo)
    dxf_path = convert_dwg_to_dxf(dwg_path)
    if not dxf_path:
        return jsonify({"error": "No se pudo convertir el DWG", "archivo": archivo}), 500

    # 2. Extraer cajetines
    plano = extract_from_dxf(dxf_path, archivo, vehiculo, carpeta)

    # 3. Renderizar imagen
    render = render_dxf(dxf_path, stem)
    render_info = render.to_dict() if render else {}

    # 4. Convertir coordenadas DXF → px para cada cajetín
    cajetines_px = []
    for caj in plano.cajetines:
        caj_dict = caj.to_dict()
        if render:
            caj_dict["bbox_px"] = render.bbox_to_px(caj.bbox)
            pt = render.dxf_to_px(caj.x, caj.y)
            caj_dict["center_px"] = {"x": pt[0], "y": pt[1]}
        cajetines_px.append(caj_dict)

    # 5. Buscar imágenes en SAP
    imagenes_sap = buscar_imagenes(archivo)

    result = {
        "archivo":      archivo,
        "vehiculo":     vehiculo,
        "carpeta":      carpeta,
        "cajetines":    cajetines_px,
        "render":       render_info,
        "imagenes_sap": imagenes_sap,
        "error":        plano.error,
    }

    # Guardar en caché
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return jsonify(result)


@app.route("/renders/<filename>")
def serve_render(filename):
    return send_from_directory(str(RENDERS_DIR), filename)


@app.route("/sap-image")
def sap_image():
    """Sirve imágenes desde rutas UNC/Z: del servidor SAP."""
    ruta = request.args.get("ruta", "")
    if not ruta:
        abort(400)
    # Convertir ruta UNC a local (Z: drive mapeado)
    ruta_local = ruta.replace("\\\\192.168.2.2\\Sapfiles", "Z:").replace("\\", "/")
    p = Path(ruta_local)
    if not p.exists():
        abort(404)
    return send_file(str(p), mimetype="image/jpeg")


@app.route("/api/indexar/<vehiculo>", methods=["POST"])
def api_indexar_vehiculo(vehiculo):
    """Dispara el indexado de un vehículo en background."""
    import threading
    from core.indexer import index_vehiculo
    force = request.args.get("force", "0") == "1"

    def _run():
        log.info("Indexado iniciado: %s (force=%s)", vehiculo, force)
        result = index_vehiculo(vehiculo, force=force)
        log.info("Indexado completado %s: %s", vehiculo, result)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"mensaje": f"Indexado iniciado para '{vehiculo}'", "force": force})


@app.route("/api/indexar/estado/<vehiculo>")
def api_indexar_estado(vehiculo):
    """Cuántos planos hay en DB para un vehículo, agrupado por estado."""
    from core.ing_database import _get_connection
    conn = _get_connection()
    if not conn:
        return jsonify({"error": "Sin conexion a DB"}), 500
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ESTADO, COUNT(*) FROM [AUTOMATA].[PLANOS]
            WHERE VEHICULO=? GROUP BY ESTADO
        """, vehiculo)
        rows = cursor.fetchall()
        return jsonify({r[0]: r[1] for r in rows})
    finally:
        conn.close()


@app.route("/api/status")
def api_status():
    from core.database import test_connection
    from core.ing_database import test_connection as test_ing
    return jsonify({
        "servidor_red": NETWORK_BASE_PATH.exists(),
        "sap_db": test_connection(),
        "ing_db": test_ing(),
        "oda": Path(str(__import__("config.settings", fromlist=["ODA_PATH"]).ODA_PATH)).exists(),
    })


if __name__ == "__main__":
    from config.settings import WEB_PORT, WEB_HOST
    import webbrowser
    webbrowser.open(f"http://{WEB_HOST}:{WEB_PORT}")
    app.run(host=WEB_HOST, port=WEB_PORT, debug=False)

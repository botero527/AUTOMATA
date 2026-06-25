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

def get_vehiculos() -> list[str]:
    try:
        return sorted([
            d.name for d in NETWORK_BASE_PATH.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ])
    except Exception as e:
        log.error("Error listando vehículos: %s", e)
        return []


def get_planos(vehiculo: str) -> list[dict]:
    base = NETWORK_BASE_PATH / vehiculo
    planos = []
    try:
        for carpeta in sorted(base.iterdir()):
            if not carpeta.is_dir():
                continue
            for dwg in sorted(carpeta.glob("*.dwg")):
                stem = dwg.stem
                code_match = re.search(r"(\d{3})", stem)
                tipo = PIECE_TYPES.get(code_match.group(1), "Desconocido") if code_match else "Desconocido"
                planos.append({
                    "archivo":  dwg.name,
                    "carpeta":  carpeta.name,
                    "vehiculo": vehiculo,
                    "tipo":     tipo,
                    "stem":     stem,
                })
    except Exception as e:
        log.error("Error listando planos de %s: %s", vehiculo, e)
    return planos


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


@app.route("/api/plano/<vehiculo>/<carpeta>/<archivo>")
def api_plano(vehiculo, carpeta, archivo):
    dwg_path = NETWORK_BASE_PATH / vehiculo / carpeta / archivo
    if not dwg_path.exists():
        abort(404, f"Archivo no encontrado: {dwg_path}")

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


@app.route("/api/status")
def api_status():
    from core.database import test_connection
    return jsonify({
        "servidor_red": NETWORK_BASE_PATH.exists(),
        "sap_db": test_connection(),
        "oda": Path(str(__import__("config.settings", fromlist=["ODA_PATH"]).ODA_PATH)).exists(),
    })


if __name__ == "__main__":
    from config.settings import WEB_PORT, WEB_HOST
    import webbrowser
    webbrowser.open(f"http://{WEB_HOST}:{WEB_PORT}")
    app.run(host=WEB_HOST, port=WEB_PORT, debug=False)

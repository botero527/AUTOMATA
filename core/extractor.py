"""
Extrae cajetines técnicos de archivos DXF con sus coordenadas X/Y.
Un cajetín es un grupo de texto (campo + valor) cercano en el plano.
"""
import re
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path

import ezdxf
from ezdxf.math import BoundingBox2d

from config.settings import TECHNICAL_FIELDS

log = logging.getLogger(__name__)

# Distancia máxima (unidades DXF) para agrupar textos en un mismo cajetín
PROXIMITY_Y = 25.0
PROXIMITY_X = 300.0


@dataclass
class Cajetin:
    """Representa un cajetín técnico en el plano con su posición y datos."""
    id: int
    x: float          # coordenada X centro (unidades DXF)
    y: float          # coordenada Y centro (unidades DXF)
    campos: dict      # {campo: valor}
    bbox: list        # [x_min, y_min, x_max, y_max] en unidades DXF

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PlanoData:
    """Resultado completo de la extracción de un plano."""
    archivo: str
    vehiculo: str
    carpeta: str
    cajetines: list[Cajetin] = field(default_factory=list)
    todos_los_textos: list[dict] = field(default_factory=list)
    dxf_bounds: list = field(default_factory=list)  # [x_min, y_min, x_max, y_max]
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "archivo": self.archivo,
            "vehiculo": self.vehiculo,
            "carpeta": self.carpeta,
            "cajetines": [c.to_dict() for c in self.cajetines],
            "dxf_bounds": self.dxf_bounds,
            "error": self.error,
        }


def _get_all_texts(msp) -> list[dict]:
    """Extrae todos los textos del modelspace con posición."""
    texts = []
    for entity in msp:
        try:
            if entity.dxftype() == "TEXT":
                pos = entity.dxf.insert
                texts.append({"text": entity.dxf.text.strip(), "x": pos.x, "y": pos.y})

            elif entity.dxftype() == "MTEXT":
                pos = entity.dxf.insert
                raw = entity.plain_mtext().strip()
                raw = re.sub(r"\\[A-Za-z][^;]*;", "", raw).strip()
                if raw:
                    texts.append({"text": raw, "x": pos.x, "y": pos.y})

            elif entity.dxftype() == "INSERT":
                for attrib in entity.attribs:
                    pos = attrib.dxf.insert
                    val = attrib.dxf.text.strip()
                    if val:
                        texts.append({"text": val, "x": pos.x, "y": pos.y})
        except Exception:
            continue
    return texts


def _normalize_field(text: str) -> str | None:
    """Retorna el nombre del campo técnico si el texto coincide, si no None."""
    upper = text.upper().strip()
    for f in TECHNICAL_FIELDS:
        if f in upper:
            return f
    return None


def _group_into_cajetines(texts: list[dict]) -> list[Cajetin]:
    """
    Agrupa textos cercanos que forman un cajetín (campo técnico + valor).
    Estrategia:
      1. Busca textos que sean campos técnicos conocidos.
      2. Busca el valor más cercano a la derecha o debajo.
      3. Agrupa en un Cajetin si hay al menos un campo reconocido.
    """
    if not texts:
        return []

    # Ordenar por Y desc (arriba primero), luego X asc
    sorted_texts = sorted(texts, key=lambda t: (-t["y"], t["x"]))

    used = set()
    cajetines_raw = []  # lista de [(campo, valor, x, y)]

    for i, t in enumerate(sorted_texts):
        if i in used:
            continue
        campo = _normalize_field(t["text"])
        if campo is None:
            continue

        # Buscar valor: texto más cercano a la derecha (mismo Y ±5) o abajo (mismo X ±50)
        best_val = None
        best_dist = float("inf")

        for j, v in enumerate(sorted_texts):
            if j == i or j in used:
                continue
            if _normalize_field(v["text"]) is not None:
                continue  # otro campo, no un valor

            dx = v["x"] - t["x"]
            dy = abs(v["y"] - t["y"])

            # A la derecha en la misma línea
            if 0 < dx < PROXIMITY_X and dy < PROXIMITY_Y:
                dist = dx + dy * 2
                if dist < best_dist:
                    best_dist = dist
                    best_val = (j, v)

            # Justo debajo
            elif dy < PROXIMITY_Y * 2 and abs(dx) < 80:
                dist = dy + abs(dx)
                if dist < best_dist:
                    best_dist = dist
                    best_val = (j, v)

        if best_val:
            j_val, v = best_val
            used.add(i)
            used.add(j_val)
            cajetines_raw.append({
                "campo": campo,
                "valor": v["text"],
                "cx": (t["x"] + v["x"]) / 2,
                "cy": (t["y"] + v["y"]) / 2,
                "x_min": min(t["x"], v["x"]) - 5,
                "y_min": min(t["y"], v["y"]) - 5,
                "x_max": max(t["x"], v["x"]) + 80,
                "y_max": max(t["y"], v["y"]) + 15,
            })

    # Agrupar pares cercanos en cajetines compuestos
    merged = _merge_nearby_pairs(cajetines_raw)
    return merged


def _merge_nearby_pairs(pairs: list[dict]) -> list[Cajetin]:
    """Une pares campo-valor que están muy cercanos en un solo cajetín."""
    used = set()
    cajetines = []
    caj_id = 0

    for i, p in enumerate(pairs):
        if i in used:
            continue
        group = [p]
        used.add(i)

        for j, q in enumerate(pairs):
            if j in used:
                continue
            if abs(p["cx"] - q["cx"]) < PROXIMITY_X and abs(p["cy"] - q["cy"]) < PROXIMITY_Y * 3:
                group.append(q)
                used.add(j)

        campos = {g["campo"]: g["valor"] for g in group}
        all_x = [g["x_min"] for g in group] + [g["x_max"] for g in group]
        all_y = [g["y_min"] for g in group] + [g["y_max"] for g in group]
        cx = sum(g["cx"] for g in group) / len(group)
        cy = sum(g["cy"] for g in group) / len(group)

        cajetines.append(Cajetin(
            id=caj_id,
            x=round(cx, 2),
            y=round(cy, 2),
            campos=campos,
            bbox=[round(min(all_x), 2), round(min(all_y), 2),
                  round(max(all_x), 2), round(max(all_y), 2)],
        ))
        caj_id += 1

    return cajetines


def _get_dxf_bounds(msp) -> list:
    """Calcula el bounding box del modelspace."""
    try:
        bbox = BoundingBox2d()
        for entity in msp:
            try:
                if hasattr(entity.dxf, "insert"):
                    p = entity.dxf.insert
                    bbox.extend([p])
            except Exception:
                continue
        if bbox.is_empty:
            return [0, 0, 1000, 1000]
        ext = bbox.extents
        return [round(ext[0].x, 2), round(ext[0].y, 2),
                round(ext[1].x, 2), round(ext[1].y, 2)]
    except Exception:
        return [0, 0, 1000, 1000]


def extract_from_dxf(dxf_path: Path, archivo: str, vehiculo: str, carpeta: str) -> PlanoData:
    """
    Lee un DXF y extrae todos los cajetines con coordenadas.
    """
    plano = PlanoData(archivo=archivo, vehiculo=vehiculo, carpeta=carpeta)
    try:
        doc = ezdxf.readfile(str(dxf_path))
        msp = doc.modelspace()

        texts = _get_all_texts(msp)
        plano.todos_los_textos = texts
        plano.dxf_bounds = _get_dxf_bounds(msp)
        plano.cajetines = _group_into_cajetines(texts)

        log.info("Extraído %s → %d cajetines, %d textos",
                 archivo, len(plano.cajetines), len(texts))
    except Exception as e:
        plano.error = str(e)
        log.error("Error extrayendo %s: %s", archivo, e)

    return plano

"""
Renderiza archivos DXF a imágenes PNG usando ezdxf + matplotlib.
Retorna también el mapeo de coordenadas DXF → píxeles para los overlays.
"""
import logging
from pathlib import Path
from dataclasses import dataclass

import ezdxf
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
import matplotlib
matplotlib.use("Agg")  # sin GUI
import matplotlib.pyplot as plt

from config.settings import RENDERS_DIR

log = logging.getLogger(__name__)

# Resolución de la imagen exportada
DPI    = 150
FIG_W  = 20   # pulgadas
FIG_H  = 12


@dataclass
class RenderResult:
    png_path: Path
    width_px: int
    height_px: int
    dxf_x_min: float
    dxf_y_min: float
    dxf_x_max: float
    dxf_y_max: float

    def dxf_to_px(self, x: float, y: float) -> tuple[int, int]:
        """
        Convierte coordenadas DXF a píxeles en la imagen renderizada.
        Matplotlib puede invertir el eje Y según el viewport — aquí lo compensamos.
        """
        dxf_w = self.dxf_x_max - self.dxf_x_min or 1
        dxf_h = self.dxf_y_max - self.dxf_y_min or 1

        px_x = int((x - self.dxf_x_min) / dxf_w * self.width_px)
        # Y en DXF va hacia arriba, en imagen hacia abajo
        px_y = int((1 - (y - self.dxf_y_min) / dxf_h) * self.height_px)
        return px_x, px_y

    def bbox_to_px(self, bbox: list) -> dict:
        """bbox = [x_min, y_min, x_max, y_max] → {left, top, width, height} en píxeles."""
        x1, y1 = self.dxf_to_px(bbox[0], bbox[3])  # esquina sup-izq (y invertida)
        x2, y2 = self.dxf_to_px(bbox[2], bbox[1])  # esquina inf-der
        return {
            "left":   max(0, x1),
            "top":    max(0, y1),
            "width":  max(1, x2 - x1),
            "height": max(1, y2 - y1),
        }

    def to_dict(self) -> dict:
        return {
            "png": str(self.png_path),
            "width_px": self.width_px,
            "height_px": self.height_px,
            "dxf_bounds": [self.dxf_x_min, self.dxf_y_min, self.dxf_x_max, self.dxf_y_max],
        }


def render_dxf(dxf_path: Path, stem: str, force: bool = False) -> RenderResult | None:
    """
    Renderiza un DXF a PNG. Retorna RenderResult con info de coordenadas.
    Cachea: si el PNG ya existe y no se fuerza, lo retorna sin re-renderizar.
    """
    dxf_path = Path(dxf_path)
    png_path  = RENDERS_DIR / (stem + ".png")

    if png_path.exists() and not force:
        log.debug("PNG ya en caché: %s", png_path.name)
        from PIL import Image
        with Image.open(png_path) as im:
            w, h = im.size
        # Sin info de bounds guardada — re-renderizamos para obtenerla
        # En producción guardaríamos los bounds en un sidecar JSON
        result = _do_render(dxf_path, png_path)
        return result

    return _do_render(dxf_path, png_path)


def _do_render(dxf_path: Path, png_path: Path) -> RenderResult | None:
    try:
        doc = ezdxf.readfile(str(dxf_path))
        msp = doc.modelspace()

        fig = plt.figure(figsize=(FIG_W, FIG_H), facecolor="#0d1117")
        ax  = fig.add_axes([0, 0, 1, 1])
        ax.set_facecolor("#0d1117")
        ax.set_axis_off()

        ctx = RenderContext(doc)
        out = MatplotlibBackend(ax)
        Frontend(ctx, out).draw_layout(msp)

        # Bounds reales del dibujo según matplotlib
        x_min, x_max = ax.get_xlim()
        y_min, y_max = ax.get_ylim()

        fig.savefig(str(png_path), dpi=DPI, bbox_inches="tight", facecolor="#0d1117")
        plt.close(fig)

        width_px  = int(FIG_W * DPI)
        height_px = int(FIG_H * DPI)

        log.info("PNG generado: %s (%dx%d)", png_path.name, width_px, height_px)
        return RenderResult(
            png_path=png_path,
            width_px=width_px,
            height_px=height_px,
            dxf_x_min=x_min,
            dxf_y_min=y_min,
            dxf_x_max=x_max,
            dxf_y_max=y_max,
        )
    except Exception as e:
        log.error("Error renderizando %s: %s", dxf_path.name, e)
        if "fig" in dir():
            plt.close(fig)
        return None

"""
Convierte archivos DWG a DXF usando ODA File Converter.
"""
import subprocess
import shutil
import tempfile
import logging
from pathlib import Path
from config.settings import ODA_PATH, DXF_DIR

log = logging.getLogger(__name__)


def convert_dwg_to_dxf(dwg_path: Path, force: bool = False) -> Path | None:
    """
    Convierte un DWG a DXF. Retorna la ruta del DXF generado o None si falla.
    Cachea el resultado — si ya existe y no se fuerza, lo retorna directamente.
    """
    dwg_path = Path(dwg_path)
    dxf_out = DXF_DIR / (dwg_path.stem + ".dxf")

    if dxf_out.exists() and not force:
        log.debug("DXF ya existe en caché: %s", dxf_out)
        return dxf_out

    if not ODA_PATH.exists():
        log.error("ODA no encontrado en: %s", ODA_PATH)
        return None

    # ODA necesita leer desde un directorio, no un archivo individual
    # Copiamos el DWG a un temp dir para evitar problemas de red
    with tempfile.TemporaryDirectory() as tmp_in:
        tmp_dwg = Path(tmp_in) / dwg_path.name
        try:
            shutil.copy2(dwg_path, tmp_dwg)
        except Exception as e:
            log.error("No se pudo copiar DWG: %s", e)
            return None

        tmp_out = Path(tmp_in) / "out"
        tmp_out.mkdir()

        cmd = [
            str(ODA_PATH),
            str(tmp_in),
            str(tmp_out),
            "ACAD2018", "DXF", "0", "0",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            log.debug("ODA stdout: %s", result.stdout)
        except subprocess.TimeoutExpired:
            log.error("ODA timeout para: %s", dwg_path.name)
            return None
        except Exception as e:
            log.error("ODA error: %s", e)
            return None

        generated = list(tmp_out.glob("*.dxf"))
        if not generated:
            log.warning("ODA no generó DXF para: %s", dwg_path.name)
            return None

        shutil.copy2(generated[0], dxf_out)
        log.info("DXF generado: %s", dxf_out.name)
        return dxf_out


def batch_convert(dwg_paths: list[Path], workers: int = 4) -> dict[str, Path]:
    """
    Convierte múltiples DWGs en paralelo.
    Retorna dict {nombre_archivo: ruta_dxf}
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(convert_dwg_to_dxf, p): p for p in dwg_paths}
        for future in as_completed(futures):
            dwg = futures[future]
            dxf = future.result()
            if dxf:
                results[dwg.name] = dxf
    return results

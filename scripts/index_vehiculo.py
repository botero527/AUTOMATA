"""
CLI para indexar un vehículo (o todos) a la base de datos AUTOMATA.

Uso:
    python scripts/index_vehiculo.py SUZUKI
    python scripts/index_vehiculo.py SUZUKI --force
    python scripts/index_vehiculo.py --todos
    python scripts/index_vehiculo.py --listar
"""
import sys
import logging
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)

from config.settings import NETWORK_BASE_PATH
from core.indexer import index_vehiculo, index_all


def listar_vehiculos():
    from api.server import get_vehiculos
    vs = get_vehiculos()
    print(f"\n{len(vs)} vehiculos disponibles:")
    for v in vs:
        print(f"  - {v}")


def main():
    args = sys.argv[1:]
    force = "--force" in args
    args = [a for a in args if a != "--force"]

    if not args or "--ayuda" in args or "--help" in args:
        print(__doc__)
        return

    if "--listar" in args:
        listar_vehiculos()
        return

    if "--todos" in args:
        print("\nIndexando TODOS los vehiculos (esto puede tardar mucho)...")
        result = index_all(force=force)
        print(f"\nCompletado: {result['vehiculos']} vehiculos")
        for v, stats in result["detalles"].items():
            if "error" in stats:
                print(f"  {v}: ERROR — {stats['error']}")
            else:
                print(f"  {v}: {stats['procesados']} procesados | "
                      f"{stats['skipped']} sin cambios | {stats['errores']} errores")
        return

    vehiculo = args[0]
    print(f"\nIndexando vehiculo: {vehiculo}  (force={force})")
    result = index_vehiculo(vehiculo, force=force)

    if "error" in result:
        print(f"ERROR: {result['error']}")
        sys.exit(1)

    print(f"\nResultado:")
    print(f"  Total DWGs:      {result['total']}")
    print(f"  Procesados:      {result['procesados']}")
    print(f"  Sin cambios:     {result['skipped']}")
    print(f"  Errores:         {result['errores']}")
    if result["detalles"]:
        print(f"\nErrores detalle:")
        for d in result["detalles"]:
            print(f"  {d['archivo']}: {d['error']}")


if __name__ == "__main__":
    main()

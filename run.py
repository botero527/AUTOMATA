"""
Punto de entrada principal de AUTOMATA.
Ejecutar: python run.py
"""
import sys
import webbrowser
from pathlib import Path

# Asegurar que el directorio raíz está en el path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from config.settings import WEB_HOST, WEB_PORT
from api.server import app

if __name__ == "__main__":
    url = f"http://{WEB_HOST}:{WEB_PORT}"
    print(f"\n  AUTOMATA — AGP Glass")
    print(f"  ─────────────────────────────")
    print(f"  Servidor: {url}")
    print(f"  Ctrl+C para detener\n")
    webbrowser.open(url)
    app.run(host=WEB_HOST, port=WEB_PORT, debug=False, threaded=True)

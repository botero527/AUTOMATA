from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv(Path(__file__).parent.parent / ".env")

# Rutas
NETWORK_BASE_PATH = Path(os.getenv("NETWORK_BASE_PATH", r"\\192.168.2.37\ingenieria\PRODUCCION\AGP PLANOS TECNICOS"))
ODA_PATH          = Path(os.getenv("ODA_PATH", r"C:\Program Files\ODA\ODAFileConverter 27.1.0\ODAFileConverter.exe"))
BASE_DIR          = Path(__file__).parent.parent
OUTPUT_DIR        = BASE_DIR / "output"
RENDERS_DIR       = OUTPUT_DIR / "renders"
DXF_DIR           = OUTPUT_DIR / "dxf"
DATA_DIR          = OUTPUT_DIR / "data"

for _d in (OUTPUT_DIR, RENDERS_DIR, DXF_DIR, DATA_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# SAP
SAP_SERVER   = os.getenv("SAP_SERVER")
SAP_DATABASE = os.getenv("SAP_DATABASE")
SAP_USER     = os.getenv("SAP_USER")
SAP_PASSWORD = os.getenv("SAP_PASSWORD")
SAP_DRIVER   = os.getenv("SAP_DRIVER", "ODBC Driver 17 for SQL Server")

# Web
WEB_PORT = int(os.getenv("WEB_PORT", 8081))
WEB_HOST = os.getenv("WEB_HOST", "localhost")

# Campos técnicos que se buscan en los planos
TECHNICAL_FIELDS = [
    "OFFSET", "BN+D", "BN INT", "ACERO", "STEEL",
    "ESPESOR", "LARGO", "ANCHO", "PESO", "MATERIAL",
    "BANDA", "TIPO", "MEDIDA", "RADIO", "ANGULO",
]

# Tipos de pieza por código en el nombre del archivo
PIECE_TYPES = {
    "000": "Parabrisas",
    "010": "Lunar Trasero",
    "020": "Lateral Fijo",
    "025": "Lateral Fijo Pequeño",
    "030": "Lateral Deslizable",
    "035": "Lateral Abatible",
    "040": "Lateral Triangular",
    "045": "Lateral Especial",
    "050": "Cuarto Trasero",
    "055": "Cuarto Delantero",
    "060": "Deflector",
    "065": "Deflector Pequeño",
    "070": "Techo",
    "075": "Techo Corredizo",
    "080": "Sunroof",
    "085": "Sunroof Fijo",
    "090": "Sunroof Panorámico",
    "095": "Panorámico Trasero",
}

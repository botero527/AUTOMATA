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

# SAP (solo lectura — imágenes de planos)
SAP_SERVER   = os.getenv("SAP_SERVER")
SAP_DATABASE = os.getenv("SAP_DATABASE")
SAP_USER     = os.getenv("SAP_USER")
SAP_PASSWORD = os.getenv("SAP_PASSWORD")
SAP_DRIVER   = os.getenv("SAP_DRIVER", "ODBC Driver 17 for SQL Server")

# Ingeniería (lectura/escritura — schema AUTOMATA)
ING_SERVER   = os.getenv("ING_SERVER")
ING_DATABASE = os.getenv("ING_DATABASE")
ING_USER     = os.getenv("ING_USER")
ING_PASSWORD = os.getenv("ING_PASSWORD")
ING_DRIVER   = os.getenv("ING_DRIVER", "ODBC Driver 17 for SQL Server")

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
# Normalizar siempre a 3 dígitos: "01" → "001", "9" → "009"
PIECE_TYPES = {
    "000": "Parabrisas",
    "001": "Lateral Delantero Izquierdo", "002": "Lateral Delantero Derecho",
    "003": "Lateral Trasero Izquierdo",   "004": "Lateral Trasero Derecho",
    "005": "Ventilete Trasero Izquierdo", "006": "Ventilete Trasero Derecho",
    "007": "Cabina Trasera Izquierda",    "008": "Cabina Trasera Derecha",
    "009": "Posterior",                   "010": "Techo Solar Delantero",
    "011": "Lateral Extendido Izquierdo", "012": "Lateral Extendido Derecho",
    "013": "Posterior Izquierdo",         "014": "Posterior Derecho",
    "015": "Claraboya Izquierda",         "016": "Claraboya Derecha",
    "017": "Mirilla",                     "018": "Probeta",
    "019": "Ventilete Delantero Izquierdo","020": "Ventilete Delantero Derecho",
    "021": "Cabina Delantera Izquierda",  "022": "Cabina Delantera Derecha",
    "023": "Cabina Superior Izquierda",   "024": "Cabina Superior Derecha",
    "025": "Techo Solar B",               "026": "Parabrisas Derecho",
    "027": "Parabrisas Izquierdo",        "028": "Lateral Secundario Derecho",
    "029": "Lateral Secundario Izquierdo","030": "Particion",
    "031": "Arquitectura",                "034": "Porthole 1",
    "035": "Porthole 2",                  "036": "Porthole 3",
    "037": "Porthole 4",                  "040": "Pummel",
    "085": "Posterior Secundario",        "087": "Techo Solar Centrico",
    "088": "Techo Solar D",               "090": "Techo Solar Panoramico",
    "091": "Probeta 2",  "092": "Probeta 3", "093": "Probeta Especial",
    "094": "Probeta 4",  "095": "Kit Opaco", "096": "Probeta 5",
    "097": "Probeta 6",
    "110": "Techo Solar A Paquete",       "125": "Techo Solar B Paquete",
    "187": "Techo Solar C Paquete",       "190": "Techo Solar Panoramico Paquete",
}

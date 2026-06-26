"""Aplica alter_schema_v2.sql contra AGP_Ingenieria."""
import re, sys
sys.path.insert(0, r'c:\Users\abotero\OneDrive - AGP GROUP\Documentos\automata')
import pyodbc
from config.settings import ING_SERVER, ING_DATABASE, ING_USER, ING_PASSWORD, ING_DRIVER

conn = pyodbc.connect(
    f"DRIVER={{{ING_DRIVER}}};SERVER={ING_SERVER};DATABASE={ING_DATABASE};"
    f"UID={ING_USER};PWD={ING_PASSWORD};Connection Timeout=20;"
)
sql = open(r'scripts\alter_schema_v2.sql', encoding='utf-8').read()
blocks = [b.strip() for b in re.split(r'\bGO\b', sql, flags=re.IGNORECASE)]
cursor = conn.cursor()
ok = 0
for b in blocks:
    clean = re.sub(r'--[^\n]*', '', b).strip()
    if not clean:
        continue
    try:
        cursor.execute(b)
        conn.commit()
        ok += 1
        print(f"OK: {clean[:80]}")
    except Exception as e:
        print(f"ERR: {e} | sql={clean[:60]}")

# Verificar
cursor.execute("SELECT name FROM sys.columns WHERE object_id=OBJECT_ID('[AUTOMATA].[PLANOS]') AND name IN ('PERIMETRO_AREA','ANGULO_INSTALACION','TOTAL_LAYERS')")
cols = [r[0] for r in cursor.fetchall()]
print("Columnas nuevas:", cols)
cursor.execute("SELECT OBJECT_ID('[AUTOMATA].[LAYER_STATS]')")
row = cursor.fetchone()
print("LAYER_STATS existe:", row[0] is not None)
conn.close()

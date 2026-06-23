"""
CONTADOR DE ARCHIVOS DWG - CUENTA TODOS LOS ARCHIVOS
=====================================================
Cuenta cuántos archivos DWG hay en cada carpeta de vehículo
"""
import os
from pathlib import Path
from datetime import datetime

SERVIDOR = r"\\192.168.2.37\ingenieria\PRODUCCION\AGP PLANOS TECNICOS"

def contar_por_carpeta():
    print("\n" + "="*60)
    print("  CONTANDO ARCHIVOS DWG POR CARPETA")
    print("="*60)
    
    base = Path(SERVIDOR)
    if not base.exists():
        print(f"ERROR: No se encontró {SERVIDOR}")
        return
    
    total_general = 0
    carpetas = []
    
    # Ordenar carpetas
    for carpeta in sorted(base.iterdir()):
        if not carpeta.is_dir() or carpeta.name.startswith('.'):
            continue
        
        # Contar DWG en esta carpeta
        try:
            dwg_files = list(carpeta.rglob("*.dwg"))
            cantidad = len(dwg_files)
        except:
            cantidad = 0
        
        if cantidad > 0:
            carpetas.append((carpeta.name, cantidad))
            total_general += cantidad
    
    # Mostrar resultados
    print(f"\n{'Carpeta':<50} {'DWG':>10}")
    print("-" * 60)
    
    for nombre, cantidad in carpetas:
        print(f"{nombre:<50} {cantidad:>10,}")
    
    print("-" * 60)
    print(f"{'TOTAL GENERAL':<50} {total_general:>10,}")
    print("="*60)

if __name__ == "__main__":
    contar_por_carpeta()

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Buscador de imágenes en la base de datos SAP
Usa el número de documento del DWG para buscar la imagen对应的
"""
import pyodbc
import re
import os

# Credenciales de la base de datos
SERVER = 'agpcolsap.database.windows.net'
DB = 'DB_COL_SAP'
USER = 'Viewer'
PSW = 'AgpconsCol2023'

def buscar_imagen_en_db(nombre_dwg):
    """
    Busca la URL de la imagen en la base de datos SAP
    usando el número de documento del archivo DWG
    """
    try:
        # Extraer el número del documento del nombre del DWG
        # Ejemplos: "1490 005 090.dwg" -> "M1490 005 090"
        #           "P A-13136 090.dwg" -> Buscar diferentes formatos
        nombre_base = os.path.splitext(nombre_dwg)[0].upper()
        
        # Extraer grupos de números
        numeros = re.split(r'[^0-9]+', nombre_base)
        numeros = [n for n in numeros if n]
        
        if not numeros:
            return None
        
        # Construir el código de búsqueda con formato M + números
        # El formato en la BD es como: M1490 005 090
        if len(numeros) >= 3:
            # Formato: M + numero1 + numero2 + numero3
            codigo = f"M{numeros[0]} {numeros[1]} {numeros[2]}"
        elif len(numeros) == 2:
            codigo = f"M{numeros[0]} {numeros[1]}"
        else:
            codigo = f"M{numeros[0]}"
        
        print(f"Buscando en BD: '{codigo}' (desde '{nombre_dwg}')")
        
        # Conectar a la base de datos
        conn_str = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={SERVER};DATABASE={DB};UID={USER};PWD={PSW}'
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        # Consultar la tabla correcta
        query = """
            SELECT TOP 1 DOCUMENTO, PLANO 
            FROM [dbo].[ODATA_ZFER_RUTAS_JPG] 
            WHERE PLANO LIKE ? 
            OR DOCUMENTO LIKE ?
        """
        
        # Buscar con wildcards
        param = f"%{codigo}%"
        cursor.execute(query, (param, param))
        
        row = cursor.fetchone()
        
        conn.close()
        
        if row:
            plano_url = row.PLANO
            print(f"  -> Encontrado: {plano_url}")
            return plano_url
        
        print(f"  -> No encontrado en BD")
        return None
        
    except Exception as e:
        print(f"Error consultando BD: {e}")
        return None


def buscar_varias_imagenes(nombre_dwg):
    """
    Busca todas las imágenes relacionadas con el archivo DWG
    """
    try:
        # Extraer el número del documento
        nombre_base = os.path.splitext(nombre_dwg)[0].upper()
        numeros = re.split(r'[^0-9]+', nombre_base)
        numeros = [n for n in numeros if n]
        
        if not numeros:
            return []
        
        # Construir el código de búsqueda
        if len(numeros) >= 3:
            codigo = f"M{numeros[0]} {numeros[1]} {numeros[2]}"
        elif len(numeros) == 2:
            codigo = f"M{numeros[0]} {numeros[1]}"
        else:
            codigo = f"M{numeros[0]}"
        
        # Conectar a la base de datos
        conn_str = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={SERVER};DATABASE={DB};UID={USER};PWD={PSW}'
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        
        # Buscar TODAS las imágenes relacionadas
        query = """
            SELECT DOCUMENTO, PLANO 
            FROM [dbo].[ODATA_ZFER_RUTAS_JPG] 
            WHERE PLANO LIKE ? 
            OR DOCUMENTO LIKE ?
        """
        
        param = f"%{codigo}%"
        cursor.execute(query, (param, param))
        
        resultados = []
        for row in cursor.fetchall():
            if row.PLANO:
                resultados.append(row.PLANO)
        
        conn.close()
        
        return resultados
        
    except Exception as e:
        print(f"Error: {e}")
        return []


# Prueba
if __name__ == "__main__":
    print("=== Prueba de búsqueda de imágenes en BD SAP ===\n")
    
    # Pruebas con diferentes archivos
    archivos_prueba = [
        "1490 005 090.dwg",
        "1656 033 090.dwg",
        "P A-13136 090.dwg"
    ]
    
    for archivo in archivos_prueba:
        print(f"\n--- {archivo} ---")
        imagenes = buscar_varias_imagenes(archivo)
        if imagenes:
            print(f"Encontradas {len(imagenes)} imágenes:")
            for img in imagenes[:5]:
                print(f"  - {img}")
        else:
            print("Sin imágenes")

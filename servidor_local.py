#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Servidor local simple para ver las imágenes en el navegador
Sirve tanto los archivos locales como las imágenes de la unidad Z:

PASO 1: Ejecutar mapear_unidad_z.bat (una vez)
PASO 2: Ejecutar este script (servidor_local.py)
PASO 3: Abrir http://localhost:8080 en Chrome
"""
import http.server
import socketserver
import webbrowser
import os
import sys
from urllib.parse import unquote

# Cambiar al directorio del proyecto
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

PORT = 8081
Z_DRIVE = r"Z:"

class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()
    
    def translate_path(self, path):
        """Sirve archivos desde la carpeta local Y desde Z:"""
        from urllib.parse import unquote
        
        # Decodificar URL
        path = unquote(path)
        print(f"Solicitado: {path}")
        
        # Si pide una imagen de Z/, sirvela desde la unidad Z:
        if path.startswith('/Z/'):
            # Extraer la ruta relativa de la imagen
            img_path = path[3:]  # Quitar /Z/
            # Combinar con la ruta base de Z:
            full_path = os.path.join(Z_DRIVE, img_path)
            print(f"Buscando imagen: {full_path}")
            if os.path.exists(full_path):
                return full_path
            else:
                print(f"NO ENCONTRADO: {full_path}")
        
        # Para cualquier otro archivo, usar el comportamiento por defecto
        return super().translate_path(path)

print("=" * 50)
print("  SERVIDOR LOCAL PARA VISOR DE PLANOS")
print("=" * 50)
print()
print(f"Iniciando servidor en http://localhost:{PORT}")
print()
print("PASOS PARA VER IMÁGENES:")
print("1. Ejecuta mapear_unidad_z.bat (si no has iniciado Z:)")
print("2. Ejecuta este script (servidor_local.py)")
print("3. Abre http://localhost:8081 en Chrome")
print()
print("Presiona Ctrl+C para detener el servidor")
print("=" * 50)

# Abrir automáticamente el navegador
webbrowser.open(f'http://localhost:{PORT}/nuevo.html')

# Iniciar servidor
with socketserver.TCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
 
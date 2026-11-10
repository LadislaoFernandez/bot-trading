"""Intermediario de avisos push: el servidor del dueño del repositorio, que tiene la clave de Firebase de la app.

Los servidores que no tienen su propia clave (firebase-servidor.json) le mandan los avisos a este y él se los pasa a
Google. Solo reenvía a celulares cuyo token ya conoce quien lo pide (el token lo da el celular a su propio servidor).
Se completa con la salida de `servidor.py relay_info` en el servidor del dueño.
"""
RELAY = None  # {"url": "https://IP:8443", "huella": "<sha256 del certificado>"}

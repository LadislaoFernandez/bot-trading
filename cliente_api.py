"""Cliente de la API del servidor del bot (lo usan la app de control de Windows y la de Android).

Solo usa la biblioteca estándar de Python. La conexión es HTTPS con el certificado propio del servidor "fijado": en cada
conexión se compara la huella SHA-256 del certificado con la del código de conexión, así que nadie puede hacerse pasar
por el servidor aunque esté en el medio de la red.
"""
import base64
import hashlib
import http.client
import json
import socket
import ssl

PREFIJO = "BOT1-"


class ErrorConexion(Exception):
    """No se pudo hablar con el servidor (apagado, sin internet, puerto cerrado...)."""


class ErrorServidor(Exception):
    """El servidor respondió con un error (por ejemplo, una acción que no se puede hacer ahora)."""


def leer_codigo(codigo):
    """Valida un código de conexión y devuelve {"h", "p", "t", "f"} o lanza ValueError."""
    c = "".join((codigo or "").split())
    if not c.startswith(PREFIJO):
        raise ValueError("El código tiene que empezar con BOT1-")
    cuerpo = c[len(PREFIJO):]
    try:
        d = json.loads(base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4)).decode("utf-8"))
    except Exception:
        raise ValueError("El código está incompleto o mal copiado")
    if not all(k in d for k in ("h", "p", "t", "f")) or len(d["f"]) != 64:
        raise ValueError("El código está incompleto o mal copiado")
    return d


class _Conexion(http.client.HTTPSConnection):
    def __init__(self, host, port, huella, timeout):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE  # la verificación es por huella (abajo), no por autoridad certificante
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        super().__init__(host, port, timeout=timeout, context=ctx)
        self.huella = huella.lower()

    def connect(self):
        super().connect()
        der = self.sock.getpeercert(binary_form=True)
        if not der or hashlib.sha256(der).hexdigest() != self.huella:
            self.sock.close()
            raise ErrorConexion("El certificado del servidor no coincide con el del código de conexión. Por seguridad "
                                "no se conectó. Si volviste a preparar el servidor, pedí un código nuevo.")


class Cliente:
    def __init__(self, codigo, timeout=15):
        d = leer_codigo(codigo)
        self.host, self.puerto, self.token, self.huella = d["h"], int(d["p"]), d["t"], d["f"]
        self.timeout = timeout

    def _pedido(self, metodo, ruta, datos=None):
        con = _Conexion(self.host, self.puerto, self.huella, self.timeout)
        try:
            cuerpo = json.dumps(datos).encode("utf-8") if datos is not None else None
            cab = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
            if cuerpo is not None:
                cab["Content-Type"] = "application/json"
            con.request(metodo, ruta, body=cuerpo, headers=cab)
            r = con.getresponse()
            texto = r.read().decode("utf-8", "replace")
        except ErrorConexion:
            raise
        except (OSError, socket.timeout, http.client.HTTPException, ssl.SSLError) as e:
            raise ErrorConexion(f"No se pudo conectar con el servidor ({type(e).__name__}). ¿Está prendido y con el "
                                f"puerto {self.puerto} abierto?")
        finally:
            con.close()
        try:
            d = json.loads(texto)
        except ValueError:
            raise ErrorServidor(f"Respuesta inválida del servidor ({r.status})")
        if r.status == 401:
            raise ErrorServidor("El servidor rechazó el código de conexión (token inválido).")
        if r.status >= 400:
            raise ErrorServidor(d.get("error") or f"Error {r.status}")
        return d

    def estado(self):
        return self._pedido("GET", "/api/estado")

    def detalle(self, que):
        return self._pedido("GET", f"/api/detalle/{que}")

    def accion(self, accion, **datos):
        return self._pedido("POST", "/api/accion", dict(datos, accion=accion)).get("resultado")

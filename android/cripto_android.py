"""Claves para el asistente de Oracle en Android, sin la librería cryptography (no viene en el APK).

En el celular las hace Java (java.security, que trae todo Android) a través de pyjnius; en la PC (pruebas) usa
cryptography. Las dos dan lo mismo:
- generar_clave_api(): par RSA 2048 para la API de Oracle -> (privada DER PKCS#8, pública PEM, huella MD5).
- firmador(privada_der): función que firma bytes con RSA-SHA256 (PKCS#1 v1.5), como pide la firma HTTP de Oracle.
- generar_ssh(): llave SSH RSA por si alguna vez hace falta entrar al servidor -> (privada PEM, pública 'ssh-rsa ...').
"""
import base64
import hashlib
import struct

try:
    from jnius import autoclass
    _JAVA = True
except ImportError:  # PC
    _JAVA = False


def _bytes(b):
    """byte[] de Java a bytes de Python (según la versión, pyjnius devuelve bytes o una lista de números con signo)."""
    if isinstance(b, (bytes, bytearray)):
        return bytes(b)
    return bytes(x & 0xFF for x in b)


def _pem(der, tipo):
    b = base64.b64encode(der).decode()
    return f"-----BEGIN {tipo}-----\n" + "\n".join(b[i:i + 64] for i in range(0, len(b), 64)) + f"\n-----END {tipo}-----\n"


def huella_md5(der):
    return ":".join(f"{x:02x}" for x in hashlib.md5(der).digest())


def _par_rsa(bits):
    """(privada DER PKCS#8, pública DER SubjectPublicKeyInfo, exponente, módulo)."""
    if _JAVA:
        g = autoclass("java.security.KeyPairGenerator").getInstance("RSA")
        g.initialize(bits)
        kp = g.generateKeyPair()
        pub = kp.getPublic()
        rsa_pub = autoclass("java.security.interfaces.RSAPublicKey")
        from jnius import cast
        rp = cast(rsa_pub, pub)
        return (_bytes(kp.getPrivate().getEncoded()), _bytes(pub.getEncoded()),
                int(rp.getPublicExponent().toString()), int(rp.getModulus().toString()))
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    k = rsa.generate_private_key(public_exponent=65537, key_size=bits)
    n = k.public_key().public_numbers()
    return (k.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()),
            k.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo),
            n.e, n.n)


def generar_clave_api():
    priv, pub, _, _ = _par_rsa(2048)
    return priv, _pem(pub, "PUBLIC KEY"), huella_md5(pub)


def publica_de(priv_der):
    """(pública PEM, huella MD5) de una privada guardada."""
    if _JAVA:
        kf = autoclass("java.security.KeyFactory").getInstance("RSA")
        spec = autoclass("java.security.spec.PKCS8EncodedKeySpec")(priv_der)
        from jnius import cast
        k = cast(autoclass("java.security.interfaces.RSAPrivateCrtKey"), kf.generatePrivate(spec))
        pub_spec = autoclass("java.security.spec.RSAPublicKeySpec")(k.getModulus(), k.getPublicExponent())
        pub = _bytes(kf.generatePublic(pub_spec).getEncoded())
    else:
        from cryptography.hazmat.primitives import serialization
        k = serialization.load_der_private_key(priv_der, None)
        pub = k.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return _pem(pub, "PUBLIC KEY"), huella_md5(pub)


def firmador(priv_der):
    if _JAVA:
        kf = autoclass("java.security.KeyFactory").getInstance("RSA")
        clave = kf.generatePrivate(autoclass("java.security.spec.PKCS8EncodedKeySpec")(priv_der))
        Signature = autoclass("java.security.Signature")

        def firmar(datos):
            s = Signature.getInstance("SHA256withRSA")
            s.initSign(clave)
            s.update(datos, 0, len(datos))
            return _bytes(s.sign())
        return firmar
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    k = serialization.load_der_private_key(priv_der, None)
    return lambda datos: k.sign(datos, padding.PKCS1v15(), hashes.SHA256())


def _mpint(n):
    b = n.to_bytes((n.bit_length() + 8) // 8, "big")  # con un byte de más para que quede positivo
    return struct.pack(">I", len(b)) + b


def generar_ssh():
    priv, _, e, n = _par_rsa(3072)
    tipo = b"ssh-rsa"
    blob = struct.pack(">I", len(tipo)) + tipo + _mpint(e) + _mpint(n)
    return _pem(priv, "PRIVATE KEY"), "ssh-rsa " + base64.b64encode(blob).decode() + " bot-trading"


def soltar_hilo():
    """Los hilos que usaron Java tienen que soltarse antes de terminar (si no, Android cierra la app)."""
    if _JAVA:
        try:
            from jnius import detach
            detach()
        except Exception:
            pass

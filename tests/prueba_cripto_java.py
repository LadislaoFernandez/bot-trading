"""Prueba las claves del asistente de Android con Java de verdad (pyjnius + JDK, como en el celular) y verifica todo con
la librería cryptography: la firma de Oracle, la huella, la clave pública guardada y la llave SSH."""
import base64
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "android"))
import cripto_android as K  # noqa: E402

from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding  # noqa: E402

assert K._JAVA, "pyjnius no está: esta prueba es para el camino de Java"
priv, pub_pem, huella = K.generar_clave_api()
pub = serialization.load_pem_public_key(pub_pem.encode())
der = pub.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
assert huella == K.huella_md5(der) and len(huella) == 47, huella
assert K.publica_de(priv) == (pub_pem, huella)
k = serialization.load_der_private_key(priv, None)
assert k.key_size == 2048
texto = b"date: Tue, 10 Nov 2026 12:00:00 GMT\n(request-target): get /20160918/vcns\nhost: iaas.sa-saopaulo-1.oraclecloud.com"
firma = K.firmador(priv)(texto)
pub.verify(firma, texto, padding.PKCS1v15(), hashes.SHA256())
# la misma firma que hace la app de Windows (PKCS#1 v1.5 es determinista)
assert firma == k.sign(texto, padding.PKCS1v15(), hashes.SHA256())

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import oci_api as O  # noqa: E402
cfg = {"user": "ocid1.user.oc1..u", "fingerprint": huella, "tenancy": "ocid1.tenancy.oc1..t", "region": "sa-saopaulo-1"}
h = O.OCI(cfg, firmar=K.firmador(priv)).cabeceras("POST", "https://iaas.sa-saopaulo-1.oraclecloud.com/20160918/vcns",
                                                    b'{"a":1}', fecha="Tue, 10 Nov 2026 12:00:00 GMT")
pem_priv = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                           serialization.NoEncryption()).decode()
h2 = O.OCI(cfg, pem_priv).cabeceras("POST", "https://iaas.sa-saopaulo-1.oraclecloud.com/20160918/vcns", b'{"a":1}',
                                     fecha="Tue, 10 Nov 2026 12:00:00 GMT")
assert h == h2

ssh_priv, ssh_pub = K.generar_ssh()
sp = serialization.load_ssh_public_key(ssh_pub.rsplit(" ", 1)[0].encode())
sk = serialization.load_pem_private_key(ssh_priv.encode(), None)
assert sp.public_numbers() == sk.public_key().public_numbers() and sk.key_size == 3072
print("OK: claves de Java para Oracle y SSH")

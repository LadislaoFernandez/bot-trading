"""Crea el servidor del bot en Oracle Cloud (gratis) desde la app de Windows, con la API de Oracle.

El usuario solo crea su cuenta de Oracle y agrega una "clave de API" (la pública la genera la app). Con eso la app
crea la red, abre el puerto de las apps, lanza una máquina Always Free y le pasa un script de arranque (cloud-init) que
instala el bot con un token y un certificado generados acá, así la app ya conoce el código de conexión sin entrar por
SSH. Las peticiones a Oracle se firman como pide su API (firma HTTP con RSA-SHA256), sin el SDK de Oracle.
"""
import base64
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from email.utils import formatdate

REGIONES_OK = {"sa-saopaulo-1": "Brazil East (Sao Paulo)", "sa-santiago-1": "Chile Central (Santiago)"}
INSTALADOR = "https://raw.githubusercontent.com/LadislaoFernandez/bot-trading/main/instalar_servidor.sh"
NOMBRE = "bot-trading"
PUERTO = 8443
# formas Always Free, en orden de preferencia (Ampere suele no tener lugar en Sao Paulo: la micro siempre alcanza)
FORMAS = [("VM.Standard.A1.Flex", {"ocpus": 1, "memoryInGBs": 6}), ("VM.Standard.E2.1.Micro", None)]


class ErrorOCI(Exception):
    def __init__(self, estado, codigo, mensaje):
        super().__init__(f"{estado} {codigo}: {mensaje}")
        self.estado, self.codigo, self.mensaje = estado, codigo, mensaje

    def sin_capacidad(self):
        t = f"{self.codigo} {self.mensaje}".lower()
        return "capacity" in t or (self.estado == 500 and "internalerror" in t)

    def sin_cupo(self):
        t = f"{self.codigo} {self.mensaje}".lower()
        return "limitexceeded" in t or "limit" in t and "exceed" in t or "quota" in t


# ---------------------------------------------------------------- claves
def generar_clave_api():
    """Par RSA para la API de Oracle: (privada PEM, pública PEM, huella MD5 como la muestra Oracle)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                           serialization.NoEncryption()).decode()
    pub_der = k.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    pub = k.public_key().public_bytes(serialization.Encoding.PEM,
                                      serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return priv, pub, huella_md5(pub_der)


def huella_md5(der):
    return ":".join(f"{b:02x}" for b in hashlib.md5(der).digest())


def huella_de_privada(priv_pem):
    from cryptography.hazmat.primitives import serialization
    k = serialization.load_pem_private_key(priv_pem.encode(), None)
    return huella_md5(k.public_key().public_bytes(serialization.Encoding.DER,
                                                  serialization.PublicFormat.SubjectPublicKeyInfo))


def generar_ssh():
    """Llave SSH Ed25519 para entrar al servidor si alguna vez hace falta: (privada OpenSSH, pública 'ssh-ed25519 ...')."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    k = ed25519.Ed25519PrivateKey.generate()
    priv = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                           serialization.NoEncryption()).decode()
    pub = k.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()
    return priv, pub + " bot-trading"


def generar_certificado():
    """Certificado del servidor (10 años) y su clave, generados en la app: (cert PEM, clave PEM, huella SHA-256)."""
    from datetime import datetime, timedelta, timezone

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    k = ec.generate_private_key(ec.SECP256R1())
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "bot-trading")])
    ahora = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(nombre).issuer_name(nombre).public_key(k.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(ahora - timedelta(days=1))
            .not_valid_after(ahora + timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("bot-trading")]), critical=False)
            .sign(k, hashes.SHA256()))
    clave = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    return (cert.public_bytes(serialization.Encoding.PEM).decode(), clave,
            hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest())


def codigo_conexion(ip, token, huella, puerto=PUERTO):
    datos = {"h": ip, "p": puerto, "t": token, "f": huella}
    return "BOT1-" + base64.urlsafe_b64encode(json.dumps(datos, separators=(",", ":")).encode()).decode().rstrip("=")


def script_arranque(token, cert_pem, clave_pem, ssh_pub=None):
    """cloud-init: deja el token y el certificado en la carpeta del bot y corre el instalador como el usuario ubuntu."""
    cfg = json.dumps({"token": token, "huella": hashlib.sha256(_der(cert_pem)).hexdigest(), "puerto": PUERTO})
    return "\n".join([
        "#!/bin/bash",
        "# Instalación del bot de trading (la generó la app de control de Windows)",
        "install -d -o ubuntu -g ubuntu -m 700 /home/ubuntu/bot-trading",
        "cd /home/ubuntu/bot-trading",
        "cat > servidor_config.json <<'FIN_CONFIG'", cfg, "FIN_CONFIG",
        "cat > servidor.crt <<'FIN_CERT'", cert_pem.strip(), "FIN_CERT",
        "cat > servidor.key <<'FIN_CLAVE'", clave_pem.strip(), "FIN_CLAVE",
        "chown ubuntu:ubuntu servidor_config.json servidor.crt servidor.key",
        "chmod 600 servidor_config.json servidor.key",
        f"sudo -u ubuntu -H bash -lc 'cd ~ && curl -fsSL {INSTALADOR} | bash' > /var/log/bot-instalacion.log 2>&1",
        ""])


def _der(cert_pem):
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    return x509.load_pem_x509_certificate(cert_pem.encode()).public_bytes(serialization.Encoding.DER)


def leer_configuracion(texto):
    """Lee el 'Configuration file preview' que muestra Oracle al agregar la clave de API."""
    c = {}
    for linea in (texto or "").splitlines():
        if "=" in linea and not linea.strip().startswith("#"):
            k, v = linea.split("=", 1)
            c[k.strip().lower()] = v.strip()
    falta = [k for k in ("user", "fingerprint", "tenancy", "region") if not c.get(k)]
    if falta:
        raise ValueError("Falta " + ", ".join(falta) + ": pegá todo el texto que muestra Oracle al agregar la clave "
                         "(empieza con [DEFAULT]).")
    if not c["user"].startswith("ocid1.user") or not c["tenancy"].startswith("ocid1.tenancy"):
        raise ValueError("El texto pegado no parece la configuración de una clave de API de Oracle.")
    return {k: c[k] for k in ("user", "fingerprint", "tenancy", "region")}


# ---------------------------------------------------------------- cliente de la API (firma HTTP de Oracle)
class OCI:
    def __init__(self, cfg, clave_privada_pem, abrir=None):
        from cryptography.hazmat.primitives import serialization
        self.cfg = cfg
        self.clave = serialization.load_pem_private_key(clave_privada_pem.encode(), None)
        self.region = cfg["region"]
        self.iaas = f"https://iaas.{self.region}.oraclecloud.com/20160918"
        self.identity = f"https://identity.{self.region}.oraclecloud.com/20160918"
        self.abrir = abrir or (lambda req: urllib.request.urlopen(req, timeout=60))

    def cabeceras(self, metodo, url, cuerpo=None, fecha=None):
        """Cabeceras firmadas de una petición (separado para poder probarlo)."""
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        u = urllib.parse.urlsplit(url)
        destino = u.path + (f"?{u.query}" if u.query else "")
        h = {"date": fecha or formatdate(usegmt=True), "host": u.netloc}
        nombres = ["date", "(request-target)", "host"]
        if metodo in ("POST", "PUT", "PATCH"):
            cuerpo = cuerpo or b""
            h.update({"content-length": str(len(cuerpo)), "content-type": "application/json",
                      "x-content-sha256": base64.b64encode(hashlib.sha256(cuerpo).digest()).decode()})
            nombres += ["content-length", "content-type", "x-content-sha256"]
        texto = "\n".join(f"{n}: {metodo.lower()} {destino}" if n == "(request-target)" else f"{n}: {h[n]}"
                          for n in nombres)
        firma = base64.b64encode(self.clave.sign(texto.encode(), padding.PKCS1v15(), hashes.SHA256())).decode()
        clave_id = f"{self.cfg['tenancy']}/{self.cfg['user']}/{self.cfg['fingerprint']}"
        h["authorization"] = (f'Signature version="1",keyId="{clave_id}",algorithm="rsa-sha256",'
                              f'headers="{" ".join(nombres)}",signature="{firma}"')
        return h

    def pedir(self, metodo, url, datos=None, params=None):
        if params:
            url += "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        cuerpo = json.dumps(datos).encode() if datos is not None else (b"" if metodo in ("POST", "PUT") else None)
        req = urllib.request.Request(url, data=cuerpo, method=metodo, headers=self.cabeceras(metodo, url, cuerpo))
        try:
            with self.abrir(req) as r:
                txt = r.read()
                return json.loads(txt) if txt else {}
        except urllib.error.HTTPError as e:
            try:
                d = json.loads(e.read() or b"{}")
            except ValueError:
                d = {}
            raise ErrorOCI(e.code, d.get("code", ""), d.get("message", str(e)))

    # atajos
    def get(self, ruta, **params):
        return self.pedir("GET", self.iaas + ruta, params=params or None)

    def post(self, ruta, datos):
        return self.pedir("POST", self.iaas + ruta, datos)

    def put(self, ruta, datos):
        return self.pedir("PUT", self.iaas + ruta, datos)

    def esperar(self, ruta, estado="AVAILABLE", maximo=600, cada=5):
        fin = time.time() + maximo
        while True:
            x = self.get(ruta)
            if x.get("lifecycleState") == estado:
                return x
            if x.get("lifecycleState") in ("TERMINATED", "TERMINATING", "FAILED"):
                raise ErrorOCI(0, x.get("lifecycleState"), f"{ruta} quedó {x.get('lifecycleState')}")
            if time.time() > fin:
                raise ErrorOCI(0, "Timeout", f"{ruta} no llegó a {estado}")
            time.sleep(cada)


# ---------------------------------------------------------------- crear el servidor
def crear_servidor(oci, script, ssh_pub, log=print, reintentar_minutos=120, espera=60, cancelado=lambda: False):
    """Red + puerto 8443 + máquina Always Free con el script de arranque. Devuelve {ip, instancia, forma}.

    Las máquinas gratis muchas veces no tienen lugar ("Out of host capacity"): en ese caso reintenta cada `espera`
    segundos hasta `reintentar_minutos`, como hacen todos los que las consiguen."""
    if oci.region not in REGIONES_OK:
        raise ValueError(f"Tu cuenta de Oracle está en la región {oci.region}. Binance no funciona desde los "
                         "servidores de Estados Unidos y las máquinas gratis solo se crean en la región de inicio: "
                         "hace falta una cuenta con región de inicio Sao Paulo o Santiago.")
    comp = oci.cfg["tenancy"]
    log("Verificando la cuenta de Oracle…")
    ads = [a["name"] for a in oci.pedir("GET", oci.identity + "/availabilityDomains", params={"compartmentId": comp})]
    if not ads:
        raise ErrorOCI(0, "SinZonas", "La cuenta no tiene zonas de disponibilidad.")

    log("Red virtual…")
    vcn = next((v for v in oci.get("/vcns", compartmentId=comp)
                if v.get("displayName") == f"{NOMBRE}-vcn" and v.get("lifecycleState") == "AVAILABLE"), None)
    if not vcn:
        vcn = oci.post("/vcns", {"compartmentId": comp, "cidrBlocks": ["10.0.0.0/16"], "displayName": f"{NOMBRE}-vcn",
                                 "dnsLabel": "bottrading"})
        vcn = oci.esperar(f"/vcns/{vcn['id']}")
    igw = next((g for g in oci.get("/internetGateways", compartmentId=comp, vcnId=vcn["id"])
                if g.get("lifecycleState") == "AVAILABLE"), None)
    if not igw:
        igw = oci.post("/internetGateways", {"compartmentId": comp, "vcnId": vcn["id"], "isEnabled": True,
                                             "displayName": f"{NOMBRE}-igw"})
        igw = oci.esperar(f"/internetGateways/{igw['id']}")
    oci.put(f"/routeTables/{vcn['defaultRouteTableId']}", {"routeRules": [
        {"destination": "0.0.0.0/0", "destinationType": "CIDR_BLOCK", "networkEntityId": igw["id"]}]})
    log("Abriendo el puerto de las apps (8443)…")
    tcp = lambda p: {"protocol": "6", "source": "0.0.0.0/0", "isStateless": False,  # noqa: E731
                     "tcpOptions": {"destinationPortRange": {"min": p, "max": p}}}
    oci.put(f"/securityLists/{vcn['defaultSecurityListId']}", {
        "ingressSecurityRules": [tcp(22), tcp(PUERTO),
                                 {"protocol": "1", "source": "0.0.0.0/0", "icmpOptions": {"type": 3, "code": 4}}],
        "egressSecurityRules": [{"protocol": "all", "destination": "0.0.0.0/0", "isStateless": False}]})
    sub = next((s for s in oci.get("/subnets", compartmentId=comp, vcnId=vcn["id"])
                if s.get("lifecycleState") == "AVAILABLE"), None)
    if not sub:
        sub = oci.post("/subnets", {"compartmentId": comp, "vcnId": vcn["id"], "cidrBlock": "10.0.0.0/24",
                                    "displayName": f"{NOMBRE}-subred", "dnsLabel": "bot",
                                    "prohibitPublicIpOnVnic": False, "routeTableId": vcn["defaultRouteTableId"],
                                    "securityListIds": [vcn["defaultSecurityListId"]]})
        sub = oci.esperar(f"/subnets/{sub['id']}")

    datos_usuario = base64.b64encode(script.encode()).decode()
    imagenes = {}
    for forma, _ in FORMAS:
        imgs = oci.get("/images", compartmentId=comp, operatingSystem="Canonical Ubuntu", operatingSystemVersion="22.04",
                       shape=forma, sortBy="TIMECREATED", sortOrder="DESC", limit=1)
        if imgs:
            imagenes[forma] = imgs[0]["id"]
    if not imagenes:
        raise ErrorOCI(0, "SinForma", "No se encontró una imagen de Ubuntu para las formas gratis.")
    fin, intento = time.time() + reintentar_minutos * 60, 0
    while True:
        intento += 1
        ultimo, sin_lugar = None, True
        for forma, config in FORMAS:
            if forma not in imagenes:
                continue
            for ad in ads:
                if intento == 1:
                    log(f"Creando la máquina ({forma}, {ad.split(':')[-1]})…")
                cuerpo = {"availabilityDomain": ad, "compartmentId": comp, "displayName": NOMBRE, "shape": forma,
                          "sourceDetails": {"sourceType": "image", "imageId": imagenes[forma]},
                          "createVnicDetails": {"subnetId": sub["id"], "assignPublicIp": True},
                          "metadata": {"ssh_authorized_keys": ssh_pub, "user_data": datos_usuario}}
                if config:
                    cuerpo["shapeConfig"] = config
                try:
                    inst = oci.post("/instances", cuerpo)
                except ErrorOCI as e:
                    ultimo = e
                    if e.sin_capacidad() or e.sin_cupo():
                        sin_lugar = sin_lugar and e.sin_capacidad()
                        if intento == 1:
                            log(f"  {'Sin lugar' if e.sin_capacidad() else 'Sin cupo gratis'} para {forma} ahí.")
                        continue
                    raise
                log(f"Máquina creada ({forma}). Esperando que arranque (2 a 5 minutos)…")
                return _terminar(oci, comp, inst, forma)
        if not sin_lugar or time.time() + espera > fin or cancelado():
            raise ultimo
        log(f"Oracle no tiene lugar para máquinas gratis en este momento. Reintento en {espera} segundos "
            f"(intento {intento}; sigo probando hasta {reintentar_minutos // 60} horas, podés dejar la ventana abierta).")
        time.sleep(espera)


def _terminar(oci, comp, inst, forma):
    inst = oci.esperar(f"/instances/{inst['id']}", "RUNNING", maximo=900, cada=10)
    ip = None
    for _ in range(30):
        vnics = oci.get("/vnicAttachments", compartmentId=comp, instanceId=inst["id"])
        if vnics and vnics[0].get("vnicId"):
            ip = oci.get(f"/vnics/{vnics[0]['vnicId']}").get("publicIp")
            if ip:
                break
        time.sleep(5)
    if not ip:
        raise ErrorOCI(0, "SinIP", "La máquina arrancó pero no tiene IP pública.")
    return {"ip": ip, "instancia": inst["id"], "forma": forma}


def nuevo_token():
    return secrets.token_urlsafe(32)

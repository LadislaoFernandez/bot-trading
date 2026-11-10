#!/bin/bash
# Instala el bot de trading en un servidor Ubuntu (por ejemplo, una máquina gratis de Oracle Cloud).
# Uso (en la consola del servidor):
#   curl -fsSL https://raw.githubusercontent.com/LadislaoFernandez/bot-trading/main/instalar_servidor.sh | bash
# Se puede volver a correr: actualiza el código y conserva los datos, el certificado y las claves.
set -euo pipefail

REPO="LadislaoFernandez/bot-trading"
CARPETA="$HOME/bot-trading"
PUERTO="${PUERTO:-8443}"

echo "== 1/7 Paquetes del sistema"
sudo DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=900 update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=900 install -y -qq python3 python3-venv python3-pip unzip curl iptables-persistent >/dev/null

echo "== 2/7 Hora de Argentina (para que los días y el registro coincidan con la app)"
sudo timedatectl set-timezone America/Argentina/Buenos_Aires || true

echo "== 3/7 Memoria de intercambio (si la máquina tiene menos de 2 GB)"
if [ "$(free -m | awk '/Mem:/ {print $2}')" -lt 2000 ] && [ ! -f /swapfile ]; then
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile
  echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab >/dev/null
fi

echo "== 4/7 Código del bot (última versión publicada)"
mkdir -p "$CARPETA"
TMP=$(mktemp -d)
if [ -n "${ZIP_LOCAL:-}" ]; then  # para probar el instalador con un paquete armado localmente
  cp "$ZIP_LOCAL" "$TMP/actualizacion.zip"
else
  URL=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" | python3 -c "import sys,json; print(next(a['browser_download_url'] for a in json.load(sys.stdin)['assets'] if a['name']=='actualizacion.zip'))")
  curl -fsSL "$URL" -o "$TMP/actualizacion.zip"
fi
unzip -oq "$TMP/actualizacion.zip" -d "$TMP/nuevo"
# solo código: nunca pisa datos (ajustes, estado, claves, certificado)
cp -f "$TMP"/nuevo/*.py "$TMP"/nuevo/*.sh "$TMP"/nuevo/requirements*.txt "$CARPETA"/ 2>/dev/null || true
mkdir -p "$CARPETA/estrategias" && cp -f "$TMP"/nuevo/estrategias/*.json "$CARPETA/estrategias/" 2>/dev/null || true
rm -rf "$TMP"

echo "== 5/7 Python y dependencias"
cd "$CARPETA"
[ -d venv ] || python3 -m venv venv
venv/bin/pip install -q --upgrade pip
venv/bin/pip install -q -r requirements_servidor.txt
[ -f ajustes.json ] || echo '{"modo": "simulado", "auto": {"activo": true}, "laboratorio": {"activo": true}, "instalar_actualizaciones_auto": true}' > ajustes.json
venv/bin/python servidor.py preparar --puerto "$PUERTO" ${IP:+--ip "$IP"} >/dev/null

echo "== 6/7 Puerto $PUERTO abierto en el firewall del servidor"
if ! sudo iptables -C INPUT -p tcp --dport "$PUERTO" -j ACCEPT 2>/dev/null; then
  sudo iptables -I INPUT 1 -p tcp --dport "$PUERTO" -j ACCEPT
  sudo netfilter-persistent save >/dev/null
fi

echo "== 7/7 Servicio que arranca solo y se reinicia si se cae"
sudo tee /etc/systemd/system/bot-trading.service >/dev/null <<EOF
[Unit]
Description=Bot de trading
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$CARPETA
ExecStart=$CARPETA/venv/bin/python $CARPETA/servidor.py correr
Restart=always
RestartSec=10
Nice=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable bot-trading >/dev/null 2>&1
sudo systemctl restart bot-trading

echo
echo "Listo. El bot ya está corriendo (en modo simulado hasta que cargues las claves)."
echo "Falta abrir el puerto $PUERTO en Oracle Cloud (Red virtual → Lista de seguridad → Regla de entrada TCP $PUERTO)."
echo
echo "Código de conexión para las apps (copialo entero, empieza con BOT1-):"
echo
venv/bin/python servidor.py codigo
echo
echo "Próximos pasos:"
echo "  cd ~/bot-trading && venv/bin/python servidor.py claves demo     (cargar las claves de Binance demo)"
echo "  venv/bin/python servidor.py probar demo"
echo "  venv/bin/python servidor.py modo demo && sudo systemctl restart bot-trading"

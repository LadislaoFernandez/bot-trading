# Bot en la nube (Oracle Cloud, gratis)

Con el bot en un servidor, la PC y el celular no necesitan estar prendidos: el bot opera las 24 horas y vos lo mirás y
controlás desde la app de Windows o la de Android. En las simulaciones de 2023 a 2026, apagar la PC de 00:00 a 09:00
costaba entre la quinta parte y casi tres cuartos de la ganancia de cada año.

Tiempo total: unos 30 minutos, la mayoría esperando que Oracle cree la cuenta y la máquina.

## 1. Crear la cuenta de Oracle Cloud

1. Entrá a <https://www.oracle.com/cloud/free/> y tocá **Start for free**.
2. Completá tus datos. Oracle pide una tarjeta **solo para verificar tu identidad**: con los recursos "Always Free" no te
   cobra nada.
3. **Región de inicio (Home Region): elegí Brazil East (Sao Paulo) o Chile Central (Santiago).** Es importante y no se
   puede cambiar después: Binance bloquea los servidores de Estados Unidos, y las máquinas gratis solo se pueden crear en
   la región de inicio.

## 2. Crear la máquina virtual

1. En la consola: menú ☰ → **Compute → Instances → Create instance**.
2. **Name**: `bot-trading`.
3. **Image**: tocá *Change image* → **Canonical Ubuntu 22.04** (o 24.04).
4. **Shape**: tocá *Change shape* → **Ampere → VM.Standard.A1.Flex**, con **1 OCPU y 2 GB de memoria**. Tiene la etiqueta
   *Always Free eligible*. Si dice que no hay capacidad ("out of host capacity"), probá otro *availability domain* o más
   tarde; como alternativa, **VM.Standard.E2.1.Micro** también es gratis y alcanza para el bot.
5. **Networking**: dejá "Create new virtual cloud network" y "Assign a public IPv4 address" tildado.
6. **Add SSH keys**: elegí **Generate a key pair for me** y tocá **Save private key**. Guardá ese archivo (`.key`) en una
   carpeta tuya, por ejemplo `E:\Claude\oracle\`. Es la llave para entrar al servidor: no la compartas.
7. Tocá **Create**. En un par de minutos la máquina queda en verde (*Running*). Anotá la **Public IP address**.

## 3. Abrir el puerto de las apps (8443)

1. En la página de la instancia, en *Primary VNIC*, entrá a la **Subnet** → **Security Lists** → la lista que aparece
   (*Default Security List…*).
2. **Add Ingress Rules**: *Source CIDR* `0.0.0.0/0`, *IP Protocol* **TCP**, *Destination Port Range* **8443**. Guardar.

El puerto queda protegido por el token del código de conexión y el certificado del servidor: sin el código, nadie puede
leer ni controlar el bot.

## 4. Instalar el bot

1. En Windows abrí **Terminal** (o PowerShell) y conectate al servidor (cambiá la ruta de la llave y la IP):

   ```
   ssh -i E:\Claude\oracle\ssh-key.key ubuntu@IP_DEL_SERVIDOR
   ```

   La primera vez pregunta si confiás en el servidor: escribí `yes`. Si Windows se queja de los permisos de la llave,
   corré una vez: `icacls E:\Claude\oracle\ssh-key.key /inheritance:r /grant:r "%USERNAME%:R"`.

2. Ya adentro del servidor, pegá esta línea y Enter:

   ```
   curl -fsSL https://raw.githubusercontent.com/LadislaoFernandez/bot-trading/main/instalar_servidor.sh | bash
   ```

   Tarda unos 5 minutos. Al terminar muestra el **código de conexión** (empieza con `BOT1-`). Copialo y guardalo como una
   contraseña: con ese código se controla el bot.

El bot queda corriendo en **modo simulado**, con el piloto automático y el laboratorio encendidos, y arranca solo si el
servidor se reinicia. Se actualiza solo desde GitHub, igual que la app.

## 5. Conectar las apps

- **Windows**: en la app del bot, *Configuración → Bot en la nube → Abrir el control remoto* (o en el menú Inicio,
  *Bot de trading - Control remoto*). Pegá el código y listo.
- **Android**: bajá `BotTrading-Control.apk` de la última versión en
  <https://github.com/LadislaoFernandez/bot-trading/releases/latest>, abrilo y permití "instalar apps de fuentes
  desconocidas" para tu navegador o el administrador de archivos. Abrí la app y pegá el código.

Las apps solo muestran y controlan: el bot corre en el servidor, así que podés cerrarlas cuando quieras.

La app de Android además **te avisa con una notificación cada vez que el bot abre o cierra una operación**, aunque esté
cerrada y con la pantalla apagada. Los avisos los manda el servidor por **Firebase Cloud Messaging** (el sistema de
Google que usan Instagram o WhatsApp), así que no hace falta tocar ajustes de batería. Para eso:

1. Creá un proyecto gratis en <https://console.firebase.google.com> y agregale una app de Android con el paquete
   `io.github.ladislaofernandez.botcontrol` (su `google-services.json` va en `android/` del repositorio).
2. En *Configuración del proyecto → Cuentas de servicio → Generar nueva clave privada*, bajá la clave y copiala al
   servidor como `firebase-servidor.json` (es secreta):

   ```
   scp -i E:\Claude\oracle\bot-trading.key firebase-servidor.json ubuntu@IP_DEL_SERVIDOR:bot-trading/
   ```
3. Abrí la app del celular (acepta el permiso de notificaciones) y probá desde el servidor:
   `cd ~/bot-trading && venv/bin/python servidor.py probar_push`

Los avisos se encienden y apagan en *Control → Notificaciones* de la app.

## 6. Cargar las claves de Binance (en el servidor)

Las claves se cargan **en el servidor** y nunca viajan por internet ni pasan por las apps. Conectado por `ssh`:

```
cd ~/bot-trading
venv/bin/python servidor.py claves demo
```

1. Elegí **1 (Ed25519)**. El servidor muestra una clave pública.
2. En Binance Demo → *Gestión de API* → *Crear API* → **Autogenerada**, pegá esa clave pública.
3. En la demo los permisos ya vienen listos y la restricción de IP no hace falta. En la cuenta real, después de crearla,
   en *Editar restricciones*: **solo futuros**, sin retiros, y acceso restringido a la **IP del servidor**.
4. Copiá la *API Key* que te da Binance y pegala en el servidor (no se ve al escribir).

Después:

```
venv/bin/python servidor.py probar demo
venv/bin/python servidor.py modo demo
sudo systemctl restart bot-trading
```

Para dinero real es igual con `real` en lugar de `demo`. El servidor no deja pasar a real si la clave tiene retiros
habilitados o no está restringida a su IP, y pide escribir REAL para confirmar.

## 7. Apagar el bot de la PC

Con el servidor operando tu cuenta, la app de escritorio vieja ya no hace falta: si los dos operan la misma cuenta de
Binance, las órdenes se duplican. Desde la versión 1.13, al abrir el control remoto de Windows se borra solo lo que
quedaba de ella (inicio automático, accesos directos, datos y lanzadores). Si la tenés abierta, cerrala antes (ícono
junto a la hora → *Salir*).

## Actualizaciones

- **Servidor**: busca versiones nuevas cada hora y se actualiza solo.
- **Control remoto de Windows**: busca al abrirse y después cada hora; si hay una versión nueva la instala y se
  reinicia solo.
- **Android**: cuando hay una versión nueva, la app lo muestra en *Resumen* y manda una notificación. Al tocarla baja el
  APK; abrilo y tocá *Actualizar* (Android siempre pide confirmar la instalación de apps fuera de Play). Los datos y el
  código de conexión se conservan.

## Comandos útiles (en el servidor)

| Para | Comando |
|---|---|
| Ver si está corriendo | `sudo systemctl status bot-trading` |
| Ver el registro en vivo | `tail -f ~/bot-trading/bot_*.log` |
| Reiniciar | `sudo systemctl restart bot-trading` |
| Volver a ver el código de conexión | `cd ~/bot-trading && venv/bin/python servidor.py codigo` |
| Cambiar el código (si se filtró) | `venv/bin/python servidor.py preparar --nuevo && sudo systemctl restart bot-trading` |
| Reinstalar o reparar | la misma línea `curl … | bash` del paso 4 (conserva datos y claves) |

## Para tener en cuenta

- **Oracle puede detener máquinas gratis que considere "ociosas"**: si durante 7 días el uso de CPU, de red y (en
  Ampere) de memoria queda por debajo del 20 %. Por eso se recomienda Ampere con 2 GB de memoria y no más. Si alguna vez
  la detiene, se vuelve a prender desde la consola (*Start*) y el bot arranca solo.
- El servidor usa la hora de Argentina, así que los días del piloto y el registro coinciden con los de la app.
- Las posiciones abiertas siempre tienen su stop puesto en Binance, aunque el servidor se reinicie.

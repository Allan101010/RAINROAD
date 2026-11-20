# Cámaras de casa para RainTrack CR

Una tablet Android que se queda en casa lee tus cámaras cada 8 minutos, calcula unos números
(brillo, contraste, cielo, bordes) y envía **solo esos números**. La foto se borra al instante y
nunca sale de tu red. El bot los usa para aprender cómo se ve la lluvia en tu pueblo.

> Por ahora los datos solo se **recolectan**; no aparece nada nuevo en la app hasta medir qué tan bien acierta.

## 1. Instalar Termux
Instala **Termux desde F-Droid** (la versión de Play Store está desactualizada): https://f-droid.org/packages/com.termux/

## 2. Instalar lo necesario (dentro de Termux)
```
pkg update
pkg install python ffmpeg python-pillow git
```
Si `python-pillow` no existe: `pkg install libjpeg-turbo zlib freetype` y luego `pip install pillow`.

## 3. Bajar el programa
```
git clone https://github.com/Allan101010/RAINROAD
cd RAINROAD/tools/home-cameras
cp config.ejemplo.json config.json
nano config.json
```
`config.json` es solo tuyo: está excluido del repositorio y no se sube.

## 4. Dirección RTSP de cada cámara
Pon la IP de la cámara (la ves en la app o en el router; conviene reservarla en el router para que no cambie).

| Marca | Dirección | Notas |
|---|---|---|
| **Tapo** | `rtsp://USUARIO:CLAVE@IP:554/stream1` | En la app: cámara → Ajustes → Avanzados → **Cuenta de la cámara**; ahí creas USUARIO y CLAVE. `stream2` es la calidad baja. |
| **EZVIZ** | `rtsp://admin:CODIGO@IP:554/H.264` | CODIGO es el código de verificación de la etiqueta. No todos los modelos permiten RTSP. |
| **iCSee** | `rtsp://IP:554/user=admin&password=CLAVE&channel=1&stream=0.sdp?real_stream` | Si nunca pusiste clave, déjala vacía. Los modelos varían. |

Las direcciones de EZVIZ e iCSee son las más comunes pero no las he probado con tus modelos.
Si una no funciona, dime el modelo exacto y buscamos la correcta.

### Varias cámaras y cómo encontrar la dirección de una iCSee
- Puedes poner todas las cámaras que quieras en `cameras` (cada una con un `id` distinto, por ejemplo `casa-frente`). En el mapa aparecen como un solo 📷 con el número de cámaras; el popup lista cada una.
- Cada cámara se compara con **su propio** aspecto normal, así que no importa que mire a otro lado.
- Para una iCSee, en su app activa **RTSP/ONVIF** (Ajustes → Configuración de red/avanzada) y reserva su IP en el router. Luego, en Termux:
```
cd ~/RAINROAD && git pull
cd tools/home-cameras
python camaras_casa.py --descubrir 192.168.0.XXX --clave TU_CLAVE
```
Prueba nueve direcciones comunes y te dice cuál funciona (sin mostrar tu clave). Si nunca pusiste clave, omite `--clave`. Evita claves con los símbolos `& ? # %`.
- Cada cámara extra son 3 fotos más cada 8 minutos: no pasa nada con 2 o 3; con más conviene subir `intervalo_segundos`.

## 5. Tema privado de ntfy
Inventa un nombre largo y secreto (es la "contraseña" del canal). Por ejemplo, en Termux:
```
echo raintrack-casa-$(head -c 12 /dev/urandom | od -An -tx1 | tr -d ' \n')
```
Ponlo en `ntfy_topic` de `config.json`. **No lo compartas ni lo subas a ningún sitio.**

## 6. Probar
```
python camaras_casa.py --una-vez
```
Debe decir "enviado" por cada cámara. Si dice "revisa la dirección RTSP", corrige la dirección de esa cámara.

## 7. Dejarlo corriendo
```
termux-wake-lock
nohup python camaras_casa.py > camaras.log 2>&1 &
```
- Deja la tablet **enchufada** y desactiva la optimización de batería para Termux (Ajustes → Apps → Termux → Batería → Sin restricciones).
- No deslices Termux fuera de las apps recientes: eso lo cierra y detiene el programa.

### Que arranque solo al reiniciar la tablet (recomendado)
Instala **Termux:Boot** desde F-Droid, ábrelo una vez y luego, en Termux:
```
mkdir -p ~/.termux/boot
printf '#!/data/data/com.termux/files/usr/bin/sh\ntermux-wake-lock\ncd ~/RAINROAD/tools/home-cameras\nwhile true; do python camaras_casa.py >> camaras.log 2>&1; sleep 30; done\n' > ~/.termux/boot/camaras.sh
chmod +x ~/.termux/boot/camaras.sh
```
Después de un reinicio hay que **desbloquear la tablet una vez**; el programa arranca solo en pocos
minutos y, si se cae, vuelve a levantarse a los 30 segundos. En la app, el 📷 de casa se pone rojo
cuando pasan más de 20 minutos sin lecturas.

## 8. Avisarle al bot (en GitHub)
En el repositorio: Settings → Secrets and variables → Actions → New repository secret.
- `HOME_CAM_TOPIC`: el mismo nombre secreto del paso 5.
- (Opcional) `HOME_CAM_LAT` y `HOME_CAM_LON`: coordenadas **aproximadas** de tu pueblo (el centro, no tu casa). Sirven para comparar con las estaciones cercanas.

## Cuándo opina la cámara (lo decide el bot, las 24 horas)
- **De día** (imagen a color): posible lluvia si el color se ve más apagado y el suelo más oscuro que lo normal en esa cámara.
- **De noche con visión infrarroja** (imagen en blanco y negro): posible lluvia si la imagen se mueve por todas partes en dos lecturas seguidas. Una sola lectura movida no cuenta (alguien o algo que pasa).
- **De noche con una luz encendida** la cámara sale del modo nocturno: no opina.
- Tampoco opina con la imagen muy oscura, mientras la cámara ajusta el brillo al anochecer, ni la primera hora de noche (necesita 12 lecturas para saber cómo se ve normalmente).

Es una estimación, no una medición.

## Privacidad
- Salen solo unos 15 números por cámara cada 8 minutos. Nada de imágenes ni de tu dirección RTSP.
- La clave de tus cámaras queda únicamente en `config.json`, dentro de tu tablet.

## Actualizar el programa de la tablet

En Termux: detén el programa con `Ctrl` + `c`, luego

```
cd ~/RAINROAD && git pull
cd tools/home-cameras && python camaras_casa.py
```

Tu `config.json` no se toca. Desde la versión con "movimiento", cada ronda saca 3 fotos seguidas
(medio segundo entre una y otra) y manda cuánto cambió la imagen en la calle; las fotos se borran.

## Puente de aviones

El mismo programa trae los aviones para la capa "✈️ Aviones en vivo" de la app. Solo trabaja mientras alguien
tiene esa capa encendida: cada 20 s pregunta si hay interés y, si lo hay, baja los aviones de adsb.fi cada 15 s
y los sube a un Worker de Cloudflare (`tools/aircraft-worker/worker.js`). La clave para publicar se crea sola
en `~/.raintrack_aviones_clave` (no la compartas). Para apagarlo, agrega `"aviones": false` en `config.json`.
En `camaras.log` aparece como "aviones: ...".

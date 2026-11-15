# Cámaras de casa para RainTrack CR

Una tablet Android que se queda en casa lee tus cámaras cada 5 minutos, calcula unos números
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
- Cada cámara extra son 3 fotos más cada 5 minutos: no pasa nada con 2 o 3; con más conviene subir `intervalo_segundos`.

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
- Opcional: instala **Termux:Boot** (F-Droid) para que arranque solo al reiniciar la tablet.

## 8. Avisarle al bot (en GitHub)
En el repositorio: Settings → Secrets and variables → Actions → New repository secret.
- `HOME_CAM_TOPIC`: el mismo nombre secreto del paso 5.
- (Opcional) `HOME_CAM_LAT` y `HOME_CAM_LON`: coordenadas **aproximadas** de tu pueblo (el centro, no tu casa). Sirven para comparar con las estaciones cercanas.

## Privacidad
- Salen solo 12 números por cámara cada 5 minutos. Nada de imágenes ni de tu dirección RTSP.
- La clave de tus cámaras queda únicamente en `config.json`, dentro de tu tablet.

## Actualizar el programa de la tablet

En Termux: detén el programa con `Ctrl` + `c`, luego

```
cd ~/RAINROAD && git pull
cd tools/home-cameras && python camaras_casa.py
```

Tu `config.json` no se toca. Desde la versión con "movimiento", cada ronda saca 3 fotos seguidas
(medio segundo entre una y otra) y manda cuánto cambió la imagen en la calle; las fotos se borran.

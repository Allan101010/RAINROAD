# RainTrack CR

Aplicación meteorológica para Costa Rica: mapa, radar, pronóstico por hora, rutas con clima en el recorrido, estaciones del IMN y estado de cámaras públicas.

## Módulos

- Mapa meteorológico de Costa Rica, radar (LibreWXR), imágenes satelitales del IMN, pronóstico y rutas.
- **Estaciones del IMN:** la lluvia se informa solo con sus mediciones. Si una estación mide lluvia, aparece un aviso en la página.
- **Capa propia «RainTrack · lluvia medida»:** lluvia animada solo alrededor de estaciones del IMN que midieron precipitación en la última hora (no interpola entre estaciones). Se atenúa según la intensidad y la edad del dato; con ≥ 8 mm/h se dibuja como tormenta (los relámpagos son estimados, el IMN no publica rayos con coordenadas). LibreWXR queda como fuente secundaria.
- **Mapa:** fondo oscuro/claro (botón 🌙/☀️ arriba), temperaturas actuales con la más alta y la más baja en el aviso superior, volcanes con su ícono propio y foto, e íconos emblemáticos con foto de Wikimedia Commons (cada ficha enlaza al autor y la licencia). La clasificación de volcanes es general, no un reporte en vivo: consultar OVSICORI.
- **Cámaras públicas** (Webcams Costa Rica, OVSICORI, SkylineWebcams): se muestra si están en línea, qué tan reciente es su imagen y si es legible. Las cámaras **no** generan alertas de lluvia: ninguna cámara confirma lluvia por sí sola.

## Cómo funciona

- Sitio estático: `index.html`, `assets/styles.css`, `assets/app.js`.
- `scripts/monitor_cameras.py` (GitHub Actions) genera `camera-alerts.json` y `camera-catalog.json`. Se dispara cada 10 minutos desde un cronjob externo (cron-job.org → `workflow_dispatch`), porque el `schedule` gratuito de GitHub se atrasa horas. Solo publica cuando cambia el estado o pasaron 15 minutos.
- Las listas de cámaras y estaciones están en `config/camera-sources.json`.

## Uso y limitaciones

Los pronósticos, el radar y las imágenes de precipitación son estimaciones y la cobertura depende de cada proveedor. RainTrack CR es una herramienta informativa: no sustituye los avisos del IMN, la CNE, OVSICORI, RSN ni las autoridades, y no debe usarse como único medio para decisiones de emergencia.

## Desarrollo

Pruebas locales:

```
pip install -r requirements-camera-monitor.txt
python -m unittest discover -s tests -v
```

[Acciones y pruebas automatizadas](https://github.com/Allan101010/RAINROAD/actions)

Historial: una versión anterior (commit `5bb27e9`) incluía un juez de IA de visión opcional para detectar lluvia en las cámaras; se retiró para simplificar.


## Instalar en el teléfono y avisos de lluvia

- **Instalar:** abre la página en Chrome (Android) y elige «Añadir a pantalla de inicio». La app se actualiza sola cada vez que se publica un cambio.
- **Avisos:** instala la app gratuita **ntfy** y suscríbete a los canales de `config/notify-zones.json` (uno por zona). El monitor envía un aviso cuando una estación del IMN de esa zona pasa a medir lluvia, y no repite mientras siga lloviendo. El nombre del canal actúa como contraseña: no lo compartas.

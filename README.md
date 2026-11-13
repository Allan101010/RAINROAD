# RainTrack CR

Aplicación meteorológica para Costa Rica: mapa, radar, pronóstico por hora, rutas con clima en el recorrido, estaciones del IMN y estado de cámaras públicas.

## Módulos

- Mapa meteorológico de Costa Rica, radar (LibreWXR), imágenes satelitales del IMN, pronóstico y rutas.
- **Estaciones del IMN:** la lluvia se informa solo con sus mediciones. Si una estación mide lluvia, aparece un aviso en la página.
- **Cámaras públicas** (Webcams Costa Rica, OVSICORI, SkylineWebcams): se muestra si están en línea, qué tan reciente es su imagen y si es legible. Las cámaras **no** generan alertas de lluvia: ninguna cámara confirma lluvia por sí sola.

## Cómo funciona

- Sitio estático: `index.html`, `assets/styles.css`, `assets/app.js`.
- `scripts/monitor_cameras.py` (GitHub Actions, cada 10 minutos) genera `camera-alerts.json` y `camera-catalog.json`. Solo publica cuando cambia el estado o pasó una hora.
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

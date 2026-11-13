# RainTrack CR

Aplicación meteorológica para Costa Rica: mapa, radar, pronóstico por hora, rutas con clima en el recorrido, estaciones del IMN y monitoreo visual de cámaras públicas.

## Módulos

- Mapa meteorológico de Costa Rica, radar (LibreWXR / WeatherAPI), imágenes satelitales del IMN, pronóstico y rutas.
- Estaciones del IMN con lluvia medida.
- Monitoreo **experimental** de cámaras públicas (Webcams Costa Rica, OVSICORI, SkylineWebcams): disponibilidad, frescura de la imagen e indicios visuales de lluvia. Una cámara nunca confirma lluvia por sí sola.

## Cómo funciona

- Sitio estático: `index.html`, `assets/styles.css`, `assets/app.js`.
- `scripts/monitor_cameras.py` (GitHub Actions, cada 10 minutos) genera `camera-alerts.json` y `camera-catalog.json`. Solo publica cuando cambia el estado o pasó una hora.
- Las listas de cámaras y estaciones están en `config/camera-sources.json`.

## Uso y limitaciones

Los pronósticos, el radar y las imágenes de precipitación son estimaciones y la cobertura depende de cada proveedor. RainTrack CR es una herramienta informativa: no sustituye los avisos del IMN, la CNE, OVSICORI, RSN ni las autoridades, y no debe usarse como único medio para decisiones de emergencia.

## Desarrollo

Pruebas locales:

```
pip install requests beautifulsoup4 Pillow pytesseract
python -m unittest discover -s tests -v
```

[Acciones y pruebas automatizadas](https://github.com/Allan101010/RAINROAD/actions)

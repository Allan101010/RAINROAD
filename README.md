# RainTrack CR

Aplicación meteorológica para Costa Rica: mapa, radar, pronóstico por hora, rutas con clima en el recorrido, estaciones del IMN y monitoreo visual de cámaras públicas.

## Módulos

- Mapa meteorológico de Costa Rica, radar (LibreWXR / WeatherAPI), imágenes satelitales del IMN, pronóstico y rutas.
- Estaciones del IMN con lluvia medida.
- Monitoreo de cámaras públicas (Webcams Costa Rica, OVSICORI): disponibilidad, frescura de la imagen y detección de lluvia con una **IA de visión** (API de Anthropic). Los modelos pequeños (clasificador y CLIP) solo sirven de filtro.
- Una cámara por sí sola nunca confirma lluvia: si una estación IMN en línea a menos de 25 km mide lluvia, la alerta pasa a "Lluvia confirmada".
- SkylineWebcams: solo se muestra la miniatura; no se analiza.

## Cómo funciona

- Sitio estático: `index.html`, `assets/styles.css`, `assets/app.js`.
- `scripts/monitor_cameras.py` (GitHub Actions, cada 10 minutos) genera `camera-alerts.json` y `camera-catalog.json`. Solo publica cuando cambia el estado o pasó una hora.
- Las listas de cámaras y estaciones están en `config/camera-sources.json`.

### IA de visión (opcional, con costo)

Sin configurar nada, la detección de lluvia por cámara queda **desactivada** (no hay alertas de cámara; las estaciones del IMN siguen funcionando). Para activarla:

1. Crea una clave de la API de Anthropic.
2. En GitHub: Settings → Secrets and variables → Actions → New repository secret, con el nombre `ANTHROPIC_API_KEY`.

Control de costo: solo se envían las cámaras que los modelos pequeños sospechan; una captura idéntica a la anterior reutiliza el veredicto; tope de 12 llamadas por ejecución y 300 por día (`VISION_JUDGE_MAX_PER_RUN`, `VISION_JUDGE_DAILY_LIMIT` en `.github/workflows/camera-monitor.yml`). El modelo se puede cambiar con `VISION_JUDGE_MODEL` (por defecto `claude-haiku-5-5`). Los contadores se publican en `camera-alerts.json` (`vision_judge`).

## Uso y limitaciones

Los pronósticos, el radar y las imágenes de precipitación son estimaciones y la cobertura depende de cada proveedor. RainTrack CR es una herramienta informativa: no sustituye los avisos del IMN, la CNE, OVSICORI, RSN ni las autoridades, y no debe usarse como único medio para decisiones de emergencia.

## Desarrollo

Pruebas locales:

```
pip install requests beautifulsoup4 Pillow pytesseract
python -m unittest discover -s tests -v
```

[Acciones y pruebas automatizadas](https://github.com/Allan101010/RAINROAD/actions)

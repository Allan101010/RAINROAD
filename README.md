# RainTrack CR

Aplicación meteorológica y de inteligencia de fenómenos naturales con alcance global y prioridad operativa para Costa Rica y Centroamérica.

## Módulos disponibles

- Mapa meteorológico de Costa Rica, radar, pronóstico y rutas.
- Catálogo de eventos globales normalizados.
- Actualización automática del conjunto global cada 10 minutos (`global-events.json`). La página principal ya no muestra este panel; los datos se siguen generando para uso futuro. El conjunto es una instantánea actual, no un historial.

## Fuentes conectadas

- USGS Earthquake Hazards Program — GeoJSON global de sismos.
- GDACS — alertas globales multiamenaza.
- NASA EONET — eventos naturales abiertos.
- NOAA National Hurricane Center — productos RSS del Atlántico y Pacífico oriental.
- NOAA Space Weather Prediction Center — alertas oficiales de clima espacial.
- Instituto Meteorológico Nacional de Costa Rica — avisos oficiales CAP con severidad, urgencia, certeza, áreas y vencimiento.
- Red Sismológica Nacional UCR — reportes RSS de sismos sentidos, como complemento del catálogo USGS.

## Uso y limitaciones

La aplicación agrega datos públicos de proveedores externos. La cobertura, precisión y latencia dependen de cada fuente. Un evento sin coordenadas puede aparecer en el listado y no en el mapa. Un feed sin datos o temporalmente caído no significa que no exista peligro.

RainTrack CR es una herramienta informativa y de apoyo a la conciencia situacional. No predice terremotos, no reemplaza los avisos del IMN, CNE, OVSICORI, RSN ni las autoridades competentes, y no debe usarse como único medio para decisiones de emergencia.

## Desarrollo

Pruebas locales: `pip install -r requirements-global-monitor.txt requests beautifulsoup4 Pillow pytesseract` y luego `python -m unittest discover -s tests -v`.

- [Arquitectura global](docs/GLOBAL_INTELLIGENCE_ARCHITECTURE.md)
- [Estado de las fuentes](global-events.json)
- [Acciones y pruebas automatizadas](https://github.com/Allan101010/RAINROAD/actions)

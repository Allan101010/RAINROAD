# RainTrack CR

Aplicación meteorológica y de inteligencia de fenómenos naturales con alcance global y prioridad operativa para Costa Rica y Centroamérica.

## Módulos disponibles

- Mapa meteorológico de Costa Rica, radar, pronóstico y rutas.
- Catálogo de eventos globales normalizados.
- Mapa mundial interactivo de eventos con coordenadas.
- Filtros por terremotos, ciclones tropicales, inundaciones, incendios, tormentas y clima espacial.
- Estado de las fuentes, atribución, hora de observación y estado del evento.
- Actualización automática del conjunto global cada 10 minutos; la interfaz consulta el conjunto publicado cada 5 minutos.

## Fuentes conectadas

- USGS Earthquake Hazards Program — GeoJSON global de sismos.
- GDACS — alertas globales multiamenaza.
- NASA EONET — eventos naturales abiertos.
- NOAA National Hurricane Center — productos RSS del Atlántico y Pacífico oriental.
- NOAA Space Weather Prediction Center — alertas oficiales de clima espacial.

## Uso y limitaciones

La aplicación agrega datos públicos de proveedores externos. La cobertura, precisión y latencia dependen de cada fuente. Un evento sin coordenadas puede aparecer en el listado y no en el mapa. Un feed sin datos o temporalmente caído no significa que no exista peligro.

RainTrack CR es una herramienta informativa y de apoyo a la conciencia situacional. No predice terremotos, no reemplaza los avisos del IMN, CNE, OVSICORI, RSN ni las autoridades competentes, y no debe usarse como único medio para decisiones de emergencia.

## Desarrollo

- [Arquitectura global](docs/GLOBAL_INTELLIGENCE_ARCHITECTURE.md)
- [Estado de las fuentes](global-events.json)
- [Acciones y pruebas automatizadas](https://github.com/Allan101010/raintrack-cr/actions)

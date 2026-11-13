# RainTrack CR — vigilancia multi-amenaza

## Arquitectura

RainTrack CR mantiene la aplicación meteorológica existente y añade un recolector Python independiente que publica hazards.json para GitHub Pages. El navegador lee un snapshot común, evitando problemas de CORS y evitando exponer credenciales.

## Fuentes integradas

| Fuente | Cobertura | Uso |
|---|---|---|
| USGS GeoJSON | Sismos mundiales M2.5+ de 24 h | Magnitud, profundidad, epicentro y enlace al evento |
| USGS FDSN | Sismicidad regional de Costa Rica, 7 días, M1.5+ | Consulta regional de catálogo; no sustituye redes locales |
| NOAA NHC | Ciclones activos del Atlántico y Pacífico oriental | Nombre, clasificación, posición, viento y enlace de aviso |
| GDACS | Eventos mundiales | Ciclones, inundaciones, terremotos, volcanes, incendios y sequías según publicación |
| NASA EONET | Eventos ambientales abiertos | Incendios, volcanes, inundaciones, tormentas, deslizamientos y otras categorías |
| NOAA SWPC | Alertas y escalas de clima espacial | Escalas R/S/G y avisos oficiales |
| NASA DONKI | CME, tormentas geomagnéticas y llamaradas solares | Eventos documentados de clima espacial |
| NOAA PTWC / NTWC | Boletines de tsunami | Boletines oficiales; no son alertas locales emitidas por SINAMOT |

## Fuentes oficiales costarricenses

Los accesos directos a IMN, CNE, OVSICORI y SINAMOT se muestran en la aplicación. No se inventa una integración automática cuando la institución no ofrece un feed estructurado estable. Las cámaras volcánicas existentes son evidencia visual complementaria, nunca un sustituto de los niveles instrumentales publicados por OVSICORI.

## Actualización y tolerancia a fallos

- GitHub Actions intenta recolectar datos cada 10 minutos y permite ejecución manual.
- Cada fuente se registra como online, stale o unavailable.
- Si una fuente falla, se conserva temporalmente el último dato válido, marcado como desactualizado.
- Si no hay snapshot previo, la fuente queda como no disponible; no se muestra como sin peligro.
- NASA usa el secreto NASA_API_KEY si está configurado; de lo contrario usa DEMO_KEY.
- El navegador recarga el snapshot publicado y muestra la hora UTC de generación.

## Interpretación y seguridad

- La relevancia costa_rica, regional o global es una clasificación geográfica de orientación, no un pronóstico de impacto.
- La magnitud de un sismo no predice futuros terremotos.
- Un indicador de tsunami en un registro sísmico no equivale a una alerta de tsunami para Costa Rica.
- Los boletines PTWC/NTWC se presentan como boletines de sus centros emisores; SINAMOT y las autoridades nacionales determinan las indicaciones para Costa Rica.
- La actividad solar no implica automáticamente un peligro directo para las personas en superficie.
- La clasificación interna de RainTrack no reemplaza los avisos del IMN, CNE, OVSICORI o SINAMOT.

## Pruebas

Ejecutar:
python -m unittest discover -s tests -p "test_*.py" -v
python -m py_compile scripts/monitor_hazards.py

## Limitaciones conocidas

La disponibilidad, cadencia y cobertura dependen de cada proveedor. La aplicación no puede garantizar detección de todos los eventos del planeta ni funcionar como sistema certificado de alerta temprana. Las alertas críticas deben verificarse con la autoridad oficial correspondiente.

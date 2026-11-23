# Fútbol Mánager (prototipo 0.1)

Juego de fútbol para Android: eres el entrenador de **Halcones FC** y juegas tú mismo las **jugadas clave** de los partidos, en 3D y con controles táctiles al estilo de los juegos de fútbol de consola.

Hecho con [Godot 4.3](https://godotengine.org) (gratis y de código abierto). Es para uso personal y no se publica en ninguna tienda.

![Partido](docs/partido.png)

## Instalarlo en tu Android

1. Descarga el archivo [`builds/futbol-manager.apk`](builds/futbol-manager.apk) en el teléfono. En GitHub, abre el archivo y toca **Download** o **View raw**.
2. Ábrelo desde la notificación de descarga o desde la app **Archivos**.
3. Android te pedirá permiso para **instalar apps desconocidas** desde el navegador o la app de archivos. Actívalo solo para esa app.
4. Toca **Instalar**. Si aparece un aviso de Play Protect, elige **Instalar de todas formas**; sale porque la app no viene de la tienda.

Requisitos: Android 7 o superior con procesador de 64 bits (casi todos los teléfonos desde 2017).

## Controles

| Zona | En ataque | En defensa |
|---|---|---|
| Mitad izquierda | Joystick (aparece donde pongas el dedo) | Joystick |
| Botón rojo grande | **TIRO**: mantén para cargar la potencia y suelta | **BARRIDA** |
| Botón verde | **PASE** raso al compañero hacia donde apuntas | **CAMBIAR** de jugador |
| Botón azul | **AL HUECO**: pase al espacio, delante del compañero | **PRESIÓN**: mantén y tu jugador persigue al rival |
| Botón amarillo | **SPRINT** (mantener) | **SPRINT** |

Consejos:
- Al tirar, inclina el joystick hacia arriba o hacia abajo para elegir el palo. Si cargas la barra hasta el rojo, el balón se te puede ir por encima.
- Si te llega un pase y no tocas el joystick, el jugador corre solo a recibir.
- Si el balón queda suelto cerca de ti, **TIRO** remata de primera.

En PC (para pruebas): WASD o flechas para moverte, **K** tiro, **J** pase, **L** al hueco, **Shift** sprint, **Q** cambiar.

## Jugadas incluidas

| Jugada | Situación | Tiempo |
|---|---|---|
| Contraataque | Minuto 78, 1-1. Robas en el medio campo y sales con 3 compañeros contra 3 defensas y el portero | 35 s |
| Ataque en el área | Minuto 89, pierden 1-2. Balón en la frontal del área llena de defensas | 25 s |
| Mano a mano | Minuto 64, 0-0. Solo contra el portero con un defensa persiguiéndote | 12 s |

La jugada termina con gol, atajada, balón fuera, despeje o cuando se acaba el tiempo.

## Estructura

```
futbol/
├── project.godot          configuración (horizontal, renderizador compatible con móviles)
├── export_presets.cfg     exportación a Android (solo arm64)
├── build_apk.sh           compila el APK
├── scenes/                menú y partido
├── scripts/
│   ├── game_data.gd       equipos, jugadores, atributos y jugadas (base del modo mánager)
│   ├── match.gd           partido: estadio, IA, pases, tiros, portero y reglas
│   ├── player.gd          futbolista: modelo low-poly y animación por código
│   ├── ball.gd            física del balón: bote, rodado, postes y red
│   ├── hud.gd             joystick, botones multitáctiles, marcador y resultado
│   ├── menu.gd            menú principal y plantilla
│   └── mesh_util.gd       ayudas para crear geometría
├── tests/
│   ├── autotest.gd        la IA juega cada jugada 40 veces y reporta resultados
│   └── shot.gd            captura pantallas de una jugada
└── builds/                APK compilado
```

## Compilar

```bash
# Prueba automática (sin pantalla)
godot --headless -s tests/autotest.gd

# APK (requiere plantillas de exportación de Godot 4.3 y un Android SDK configurado)
GODOT=godot ./build_apk.sh
```

## Próximos pasos

1. **Sensación de juego**: ajustar velocidades, pases y tiros con tus comentarios después de probarlo.
2. **Animaciones de Mixamo** (gratis): correr, pasar, tirar, barrida, estiradas del portero. Reemplazarán los muñecos actuales.
3. **Más jugadas**: penales (deslizar para tirar), tiros libres, córners y defender un contraataque rival.
4. **Modo mánager**: alineación, tácticas, entrenamientos, liga con calendario y tabla, fichajes.
5. **Sonido**: silbato, público y gol.

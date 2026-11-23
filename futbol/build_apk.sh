#!/usr/bin/env bash
# Compila el APK de Android (debug, firmado) en futbol/builds/futbol-manager.apk
# Requiere: Godot 4.3 con plantillas de exportación y un Android SDK configurado
# en los ajustes del editor (export/android/android_sdk_path y debug_keystore).
set -euo pipefail
cd "$(dirname "$0")"
GODOT="${GODOT:-godot}"
mkdir -p builds
"$GODOT" --headless --import >/dev/null 2>&1 || true
"$GODOT" --headless --export-debug "Android" builds/futbol-manager.apk
rm -f builds/futbol-manager.apk.idsig
echo "APK listo: $(pwd)/builds/futbol-manager.apk"

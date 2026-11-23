extends SceneTree
## Captura pantallas de una jugada (necesita pantalla, p. ej. xvfb-run).
## Uso: SHOT_DIR=/ruta SCENARIO=contraataque godot --rendering-driver opengl3 -s tests/shot.gd

var f := 0
var dir := ""


func _process(_d: float) -> bool:
	f += 1
	if f == 2:
		dir = OS.get_environment("SHOT_DIR")
		if dir == "":
			dir = "user://"
		var sc := OS.get_environment("SCENARIO")
		if sc == "menu":
			root.add_child(load("res://scenes/menu.tscn").instantiate())
		else:
			root.get_node("/root/GameData").current_scenario = sc if sc != "" else "contraataque"
			var m = load("res://scenes/match.tscn").instantiate()
			root.add_child(m)
			m.autoplay = true
	for i in 3:
		if f == 30 + i * 180:
			root.get_viewport().get_texture().get_image().save_png(dir.path_join("captura_%d.png" % (i + 1)))
	return f > 30 + 2 * 180

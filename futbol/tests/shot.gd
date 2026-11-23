extends SceneTree
## Captura pantallas de todas las pantallas del juego (necesita pantalla, p. ej. xvfb-run).
## Uso: SHOT_DIR=/ruta godot --rendering-driver opengl3 --resolution 1280x720 -s tests/shot.gd

var f := 0
var dir := ""
var step := 0
var node: Node = null
var gd
var plan := [
	["frontal", 100], ["def_frontal", 112], ["contra", 104], ["falta", 120],
]


func _shot(name: String) -> void:
	root.get_viewport().get_texture().get_image().save_png(dir.path_join(name + ".png"))


func _clear() -> void:
	if node and is_instance_valid(node):
		node.queue_free()
	node = null


func _process(_d: float) -> bool:
	f += 1
	if f == 1:
		dir = OS.get_environment("SHOT_DIR")
		if dir == "":
			dir = "user://"
		gd = root.get_node("/root/GameData")
		gd.new_career(3)
		return false
	if step >= plan.size():
		gd.delete_career()
		return true
	var item: Array = plan[step]
	if f == 2:
		_clear()
		_open(item[0])
	if f >= 2 + item[1]:
		_shot(item[0])
		step += 1
		f = 1
	return false


func _open(what: String) -> void:
	Engine.time_scale = 1.0
	match what:
		"menu":
			node = load("res://scenes/menu.tscn").instantiate()
			root.add_child(node)
		"quick":
			node = load("res://scenes/menu.tscn").instantiate()
			root.add_child(node)
			node._show_quick()
		"lineup":
			node = load("res://scenes/menu.tscn").instantiate()
			root.add_child(node)
			node._quick_lineup()
		"career", "tabla":
			node = load("res://scenes/career.tscn").instantiate()
			if what == "tabla":
				node._tab = "tabla"
			root.add_child(node)
		"sim":
			var s = load("res://scripts/match_sim.gd").new()
			s.setup(gd.teams[3], gd.teams[0], true, "career")
			for i in 30:
				s.step()
				if not s.pending.is_empty():
					s.auto_resolve()
			gd.sim = s
			node = load("res://scenes/sim.tscn").instantiate()
			root.add_child(node)
		_:
			var J = load("res://scripts/jugadas.gd")
			var real_group := what.replace("2", "")
			var pool: Array = J.by_group(real_group)
			gd.moment = gd.build_moment(pool[pool.size() / 2], gd.teams[3].duplicate(true), gd.teams[0].duplicate(true), "training")
			node = load("res://scenes/match.tscn").instantiate()
			root.add_child(node)
			if what in ["def_frontal"]:
				node.autoplay = true

extends SceneTree
## Prueba automática: la IA juega cada jugada varias veces y cuenta resultados.
## Uso: godot --headless -s tests/autotest.gd

var _done := false

func _process(_delta: float) -> bool:
	if _done:
		return true
	_done = true
	var gd = root.get_node("/root/GameData")
	var packed: PackedScene = load("res://scenes/match.tscn")
	var total_errors := 0
	for key in gd.scenario_order:
		var wins := 0
		var reasons := {}
		var evs := {}
		var trials := 40
		for i in trials:
			gd.current_scenario = key
			var m = packed.instantiate()
			root.add_child(m)
			m.set_process(false)
			m.autoplay = true
			var steps := 0
			while not m.is_finished() and steps < 60 * 60:
				m.simulate(1.0 / 60.0)
				steps += 1
			if m.won():
				wins += 1
			var r: String = m.hud._result_panel.get_child(0).get_child(0).text if m.hud._result_panel else "sin terminar"
			reasons[r] = reasons.get(r, 0) + 1
			for e in m.hud.event_log:
				if e.length() > 2:
					evs[e] = evs.get(e, 0) + 1
			m.free()
			Engine.time_scale = 1.0
		print("%s: goles %d/%d  %s" % [key, wins, trials, str(reasons)])
		print("   eventos: ", evs)
	# El menú también debe cargar sin errores.
	var menu = load("res://scenes/menu.tscn").instantiate()
	root.add_child(menu)
	menu.free()
	print("OK")
	return true

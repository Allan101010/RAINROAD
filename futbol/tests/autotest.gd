extends SceneTree
## Prueba automática:
##  1) la IA juega cada una de las jugadas del catálogo,
##  2) se simulan partidos completos para revisar los marcadores,
##  3) se juega una temporada completa del modo carrera,
##  4) se abren todas las pantallas.
## Uso: godot --headless -s tests/autotest.gd

var _done := false


func _process(_delta: float) -> bool:
	if _done:
		return true
	_done = true
	var gd = root.get_node("/root/GameData")
	var packed: PackedScene = load("res://scenes/match.tscn")
	var all: Array = load("res://scripts/jugadas.gd").all()
	print("Jugadas en el catálogo: ", all.size())
	var by_group := {}
	var unfinished := 0
	for j in all:
		var reps := 3
		for r in reps:
			var ut: Dictionary = gd.teams[randi() % 20].duplicate(true)
			var rt: Dictionary = gd.teams[(int(ut.id) + 1 + randi() % 19) % 20].duplicate(true)
			gd.moment = gd.build_moment(j, ut, rt, "training")
			var m = packed.instantiate()
			root.add_child(m)
			m.set_process(false)
			m.autoplay = true
			var steps := 0
			while not m.is_finished() and steps < 60 * 70:
				m.simulate(1.0 / 60.0)
				steps += 1
			var g: String = j.group
			if not by_group.has(g):
				by_group[g] = {"n": 0, "gf": 0, "ga": 0, "titles": {}}
			var e: Dictionary = by_group[g]
			e.n += 1
			if not m.is_finished():
				unfinished += 1
			if m.result.get("goal_for", false):
				e.gf += 1
			if m.result.get("goal_against", false):
				e.ga += 1
			var t: String = m.hud.result_title()
			e.titles[t] = e.titles.get(t, 0) + 1
			m.free()
			Engine.time_scale = 1.0
	for g in by_group:
		var e: Dictionary = by_group[g]
		print("  %-14s n=%3d  goles a favor=%2d  en contra=%2d  %s" % [g, e.n, e.gf, e.ga, str(e.titles)])
	print("Jugadas sin terminar: ", unfinished)

	# Partidos simulados completos
	var goals := 0
	var moments := 0
	var results := [0, 0, 0]
	for i in 200:
		var a: Dictionary = gd.teams[randi() % 20].duplicate(true)
		var b: Dictionary = gd.teams[(int(a.id) + 1 + randi() % 19) % 20].duplicate(true)
		var s = load("res://scripts/match_sim.gd").new()
		s.setup(a, b, true, "quick")
		while not s.finished:
			if not s.pending.is_empty():
				moments += 1
				s.auto_resolve()
			s.halftime_pending = false
			s.step()
		goals += s.score[0] + s.score[1]
		results[signi(s.score[0] - s.score[1]) + 1] += 1
	print("Partidos simulados: goles por partido %.2f, jugadas clave por partido %.1f, (derrotas locales, empates, victorias) %s" % [goals / 200.0, moments / 200.0, str(results)])

	# Temporada completa
	gd.new_career(0)
	while not gd.season_over():
		var fx: Array = gd.current_fixture()
		var s2 = load("res://scripts/match_sim.gd").new()
		s2.setup(gd.team_by_id(fx[0]), gd.team_by_id(fx[1]), int(fx[0]) == 0, "career")
		while not s2.finished:
			if not s2.pending.is_empty():
				s2.auto_resolve()
			s2.halftime_pending = false
			s2.step()
		gd.finish_round(s2.score[0], s2.score[1])
	var rows: Array = gd.sorted_table()
	var pj := 0
	for r in rows:
		pj += int(r.pj)
	print("Temporada: %d partidos registrados (esperado 760). Campeón: %s con %d puntos. Tu equipo: %dº" % [pj, gd.team_by_id(rows[0].id).name, int(rows[0].pts), gd.table_position(0)])
	print("Guardado y carga: ", gd.load_career())

	# Pantallas
	for path in ["res://scenes/menu.tscn", "res://scenes/career.tscn"]:
		var n = load(path).instantiate()
		root.add_child(n)
		n.free()
	var s3 = load("res://scripts/match_sim.gd").new()
	s3.setup(gd.teams[0], gd.teams[1], true, "career")
	gd.sim = s3
	var simscene = load("res://scenes/sim.tscn").instantiate()
	root.add_child(simscene)
	simscene.free()
	gd.delete_career()
	gd.sim = null
	print("OK")
	return true

extends SceneTree
## Pruebas de mecánicas concretas: portero en tiros lejanos, pases, recepción y presión.
## Uso: godot --headless -s tests/mecanicas.gd

var _done := false
var gd
var J


func _new_match(group: String, idx := -1):
	var pool: Array = J.by_group(group)
	var j = pool[idx if idx >= 0 else randi() % pool.size()]
	gd.moment = gd.build_moment(j, gd.teams[randi() % 20].duplicate(true), gd.teams[randi() % 20].duplicate(true), "training")
	var m = load("res://scenes/match.tscn").instantiate()
	root.add_child(m)
	m.set_process(false)
	for i in 100:
		m.simulate(1.0 / 60.0)
	return m


func _process(_d: float) -> bool:
	if _done:
		return true
	_done = true
	gd = root.get_node("/root/GameData")
	J = load("res://scripts/jugadas.gd")
	_test_gk()
	_test_passes()
	_test_press()
	return true


func _test_gk() -> void:
	var on_target := 0
	var dived := 0
	var saves := 0
	var goals := 0
	for i in 60:
		var m = _new_match("frontal")
		var shooter = m.ball.carrier
		if shooter == null:
			m.free()
			continue
		# Tiro lejano: entre 24 y 34 metros.
		shooter.position = Vector3(randf_range(18.5, 28.5), 0, randf_range(-12, 12))
		m.ball.position = shooter.position + Vector3(0.5, 0.11, 0)
		for o in m.away:
			if o.role != "GK":
				o.position.z += 25.0 if o.position.z < 0 else -25.0
		var gk = m._gk_of(1)
		m._shoot(shooter, randf_range(0.6, 0.9), randf_range(-3.0, 3.0))
		var plan: Dictionary = m.gk_plan.duplicate()
		var saw_dive := false
		for k in 240:
			m.simulate(1.0 / 60.0)
			if gk.dive_t > 0.0 or gk.crouch_t > 0.0 or gk.head_anim > 0.0:
				saw_dive = true
			if m.is_finished() or m.state == 3:
				break
		if plan.get("on_target", false):
			on_target += 1
			if saw_dive:
				dived += 1
			if m.ball.scored:
				goals += 1
			elif plan.get("save", false):
				saves += 1
		m.free()
		Engine.time_scale = 1.0
	print("PORTERO tiros lejanos a puerta: %d | reaccionó (estirada/bloqueo): %d | paradas: %d | goles: %d" % [on_target, dived, saves, goals])


func _test_passes() -> void:
	for btn in ["b", "c"]:
		var ok := 0
		var tot := 0
		var moving := 0
		var dist_sum := 0.0
		for i in 40:
			var m = _new_match("contra" if i % 2 == 0 else "frontal")
			var passer = m.ball.carrier
			if passer == null or passer.team != 0:
				m.free()
				continue
			m.hud.joy_vec = Vector2(1, 0)
			m.simulate(1.0 / 60.0)
			tot += 1
			var start: Vector3 = m.ball.position
			m.hud.press(btn)
			m.simulate(1.0 / 60.0)
			var receiver = null
			for k in 300:
				m.simulate(1.0 / 60.0)
				if m.ball.carrier != null:
					receiver = m.ball.carrier
					break
			if receiver != null and receiver.team == 0 and receiver != passer:
				ok += 1
				dist_sum += start.distance_to(m.ball.position)
				m.hud.joy_vec = Vector2.ZERO
				for k in 15:
					m.simulate(1.0 / 60.0)
				if receiver.velocity.length() > 2.0:
					moving += 1
			m.free()
		print("PASE %s: recibidos %d/%d, distancia media %.1f m, sigue en carrera al recibir %d/%d" % ["normal" if btn == "b" else "al hueco", ok, tot, dist_sum / maxf(ok, 1), moving, ok])


func _test_press() -> void:
	var won := 0
	var tot := 0
	var times := 0.0
	for i in 30:
		var m = _new_match("def_frontal")
		if m.ball.carrier == null or m.ball.carrier.team != 1:
			m.free()
			continue
		tot += 1
		m.hud._buttons["c"].down = true
		var t := 0.0
		for k in 600:
			m.simulate(1.0 / 60.0)
			t += 1.0 / 60.0
			if m.ball.carrier != null and m.ball.carrier.team == 0:
				won += 1
				times += t
				break
			if m.is_finished():
				break
		m.free()
		Engine.time_scale = 1.0
	print("PRESIÓN en defensa: balón recuperado %d/%d (tiempo medio %.1f s)" % [won, tot, times / maxf(won, 1)])

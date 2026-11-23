extends Node3D
## Jugada clave en 3D. Modos: "attack", "defend", "corner", "freekick",
## "penalty_for" y "penalty_against". Tu equipo (HOME) siempre ataca hacia +X.
## Los atributos de cada jugador (con energía y ánimo) deciden velocidad, pases,
## tiros, robos y paradas.

const HALF_L := 52.5
const HALF_W := 34.0
const GOAL_HW := 3.66
const GOAL_H := 2.44
const HOME := 0
const AWAY := 1

enum State { INTRO, SETPIECE, PLAY, GOAL, ENDED }

var state := State.INTRO
var state_t := 0.0
var mode := "attack"
var moment: Dictionary
var jugada: Dictionary
var time_left := 20.0
var time_total := 20.0
var home: Array[Futbolista] = []
var away: Array[Futbolista] = []
var players: Array[Futbolista] = []
var ball: Balon
var cam: Camera3D
var hud: Hud
var controlled: Futbolista = null
var cam_focus := Vector3.ZERO
var cam_mode := "broadcast"
var cam_mode_t := 0.0
var charging := false
var charge := 0.0
var home_hold := 0.0
var away_hold := 0.0
var gk_hold := 0.0
var autoplay := false
var result: Dictionary = {}
var gk_plan: Dictionary = {}

var aim := Vector2(1.5, 1.6)  # (z, y) sobre la portería
var curve := 0.0
var taker: Futbolista = null
var takers: Array = []
var taker_idx := 0
var wall: Array[Futbolista] = []
var wall_jump_t := 0.0
var aim_marker: Node3D
var pen_choice := 99
var corner_done := false
var setpiece_kicked := false
var _keys_prev := {}
var _kits: Array


func _ready() -> void:
	randomize()
	moment = GameData.moment if not GameData.moment.is_empty() else _default_moment()
	jugada = moment.jugada
	mode = jugada.mode
	time_total = jugada.time * 1.5
	time_left = time_total
	Stadium.build(self, moment.user_team.name, moment.rival_team.name)
	_kits = GameData.kits_for(moment.user_team, moment.rival_team)
	_spawn()
	_setup_camera()
	_setup_hud()
	state = State.INTRO
	state_t = 0.0
	hud.show_message("¡JUGADA CLAVE!", 1.6)


func _default_moment() -> Dictionary:
	var ut: Dictionary = GameData.teams[int(GameData.training_team)]
	var rt: Dictionary = GameData.teams[(int(GameData.training_team) + 1 + randi() % 19) % GameData.teams.size()]
	var all := Jugadas.all()
	return GameData.build_moment(all[randi() % all.size()], ut, rt, "training")


# ---------------------------------------------------------------- Montaje

func _spawn() -> void:
	var home_pool: Array = moment.home_xi.duplicate()
	var away_pool: Array = moment.away_xi.duplicate()
	var ball_owner: Futbolista = null
	for e in jugada.home:
		var p := _make_player(_take(home_pool, e.role, e.get("taker", false)), HOME, e.pos)
		p.key_player = true
		p.lane_z = e.get("lane", e.pos.z)
		if e.get("ball", false):
			ball_owner = p
		if e.get("taker", false):
			taker = p
	for e in jugada.away:
		var p := _make_player(_take(away_pool, e.role, e.get("taker", false)), AWAY, e.pos)
		p.key_player = true
		p.lane_z = e.get("lane", e.pos.z)
		if e.get("ball", false):
			ball_owner = p
		if e.get("taker", false):
			taker = p
	ball = Balon.new()
	add_child(ball)

	match mode:
		"freekick", "penalty_for":
			var bp: Vector3 = jugada.ball_pos
			ball.place(bp + Vector3(0, Balon.R, 0))
			if mode == "freekick":
				_build_wall(away_pool, int(jugada.get("wall", 4)))
			_spawn_extras(home_pool, away_pool)
			takers = home.filter(func(x): return x.role != "GK")
			if mode == "freekick":
				takers.sort_custom(func(a, b): return a.tl > b.tl)
			else:
				takers.sort_custom(func(a, b): return a.sho + a.tl * 0.5 > b.sho + b.tl * 0.5)
			takers = takers.slice(0, 5)
			taker_idx = 0
			_place_taker(takers[0])
			var gk := _gk_of(AWAY)
			if gk:
				gk.position = Vector3(HALF_L - 0.4, 0, -signf(bp.z) * 0.9 if absf(bp.z) > 2 else 0.0)
				gk.face_towards(bp)
			aim = Vector2(-signf(bp.z) * 2.2 if absf(bp.z) > 2 else 2.2, 1.7)
			_make_aim_marker()
		"penalty_against":
			var bp2: Vector3 = jugada.ball_pos
			ball.place(bp2 + Vector3(0, Balon.R, 0))
			if taker:
				taker.face_towards(bp2)
			_spawn_extras(home_pool, away_pool)
			var mygk := _gk_of(HOME)
			if mygk:
				mygk.position = Vector3(-HALF_L + 0.3, 0, 0)
				mygk.face_towards(bp2)
		"corner":
			if taker:
				ball.place(taker.position + Vector3(-0.4, Balon.R, -0.4 * signf(taker.position.z)))
				taker.face_towards(Vector3(45, 0, 0))
			_spawn_extras(home_pool, away_pool)
		_:
			if jugada.has("loose_ball"):
				ball.place(jugada.loose_ball)
				ball.vel = jugada.loose_vel
				ball.kind = "loose"
				ball.last_touch = _gk_of(AWAY)
			elif ball_owner:
				ball.place(ball_owner.position + ball_owner.facing * 0.55 + Vector3(0, Balon.R, 0))
				_give_ball(ball_owner)
			_spawn_extras(home_pool, away_pool)
	for p in players:
		if p.role != "GK" and mode in ["attack", "defend", "corner"]:
			if p != ball_owner and p != taker:
				p.face_towards(ball.position)


func _take(pool: Array, role: String, is_taker := false) -> Dictionary:
	var order := {"GK": ["GK"], "FWD": ["FWD", "MID", "DEF"], "MID": ["MID", "FWD", "DEF"], "DEF": ["DEF", "MID", "FWD"]}
	for r in order.get(role, ["MID"]):
		var best = null
		var bv := -1.0
		for d in pool:
			if d.pos != r:
				continue
			var v: float = d.sho + d.spd if r == "FWD" else (d.pas + d.spd * 0.3 if r == "MID" else (d.dfn if r == "DEF" else d.gkp))
			if is_taker:
				v = d.tl + d.pas
			if v > bv:
				bv = v
				best = d
		if best != null:
			pool.erase(best)
			return best
	if pool.is_empty():
		return {"name": "Jugador", "number": 0, "pos": role, "spd": 60, "pas": 60, "sho": 60, "dfn": 60, "gkp": 40, "tl": 50}
	return pool.pop_back()


func _make_player(data: Dictionary, team: int, pos: Vector3) -> Futbolista:
	var p := Futbolista.new()
	add_child(p)
	var kit: Dictionary = _kits[0] if team == HOME else _kits[1]
	p.setup(data, team, kit)
	p.position = pos
	if team == AWAY:
		p.facing = Vector3.LEFT
	players.append(p)
	if team == HOME:
		home.append(p)
	else:
		away.append(p)
	return p


func _place_taker(new_taker: Futbolista) -> void:
	## Pone a un jugador como lanzador; el anterior ocupa el sitio del nuevo.
	var bp: Vector3 = jugada.ball_pos
	var dir := (Vector3(HALF_L, 0, 0) - bp).normalized()
	var side := Vector3(-dir.z, 0, dir.x)
	var spot := bp - dir * 1.8 + side * 1.3
	if taker and taker != new_taker:
		taker.position = new_taker.position
		taker.set_name_visible(true)
	taker = new_taker
	taker.position = spot
	taker.velocity = Vector3.ZERO
	taker.face_towards(bp)
	_set_controlled(taker)
	taker.set_name_visible(false)


func _spawn_extras(home_pool: Array, away_pool: Array) -> void:
	## Completa los once de cada equipo con el resto de jugadores.
	var behind: bool = jugada.group in ["contra", "1v1", "def_contra", "def_1v1"]
	for t in [HOME, AWAY]:
		var pool: Array = home_pool if t == HOME else away_pool
		while not pool.is_empty():
			var data: Dictionary = pool.pop_front()
			var pos := _extra_spot(t, data, behind)
			for _k in 6:
				var clash := false
				for o in players:
					if _hdist(o.position, pos) < 2.2:
						clash = true
						break
				if not clash:
					break
				pos.z = clampf(pos.z + 2.6, -32.0, 32.0)
			var p := _make_player(data, t, pos)
			p.lane_z = pos.z
			p.face_towards(ball.position)
			if behind and data.pos != "GK":
				var attacker := HOME if mode == "attack" else AWAY
				if t != attacker:
					p.stun = randf_range(0.6, 1.6)  # tardan en reaccionar al contraataque


func _extra_spot(t: int, data: Dictionary, behind: bool) -> Vector3:
	var d := dir_of(t)
	var sx: float = data.get("sx", 0.5)
	var sy: float = data.get("sy", 0.5)
	if data.pos == "GK":
		return Vector3(own_goal_x(t) + d * 0.6, 0, 0)
	var r := randf_range(-1.5, 1.5)
	match mode:
		"penalty_for", "penalty_against":
			var px := 32.0 if mode == "penalty_for" else -32.0
			return Vector3(px - signf(px) * randf_range(0.0, 5.0), 0, (sx - 0.5) * 34.0 + r)
		"freekick":
			if t == HOME:
				if sy > 0.7:
					return Vector3(-4.0 + r * 3.0, 0, (sx - 0.5) * 30.0)
				return Vector3(randf_range(39.0, 45.0), 0, (sx - 0.5) * 26.0 + r)
			return Vector3(randf_range(44.0, 49.5), 0, (sx - 0.5) * 22.0 + r)
		"corner":
			if t == HOME:
				if sy > 0.7:
					return Vector3(randf_range(-2.0, 8.0), 0, (sx - 0.5) * 30.0)
				return Vector3(randf_range(36.0, 44.0), 0, (sx - 0.5) * 24.0 + r)
			if sy < 0.3:
				return Vector3(randf_range(14.0, 22.0), 0, (sx - 0.5) * 20.0)
			return Vector3(randf_range(44.0, 50.0), 0, (sx - 0.5) * 20.0 + r)
	var pos := _shape_spot(t, Vector2(sx, sy))
	if behind:
		# En un contraataque, el equipo que defiende está descolocado: detrás del balón.
		var attacker := HOME if mode == "attack" else AWAY
		if t != attacker:
			var ad := dir_of(attacker)
			pos.x = ball.position.x - ad * randf_range(9.0, 30.0)
		elif sy > 0.6:
			pos.x = ball.position.x - dir_of(t) * randf_range(12.0, 30.0)
	pos.x = clampf(pos.x, -HALF_L + 2, HALF_L - 2)
	return pos


func _shape_spot(t: int, sl: Vector2) -> Vector3:
	## Posición de un jugador según su formación, el balón y quién tiene la posesión.
	var d := dir_of(t)
	var own := own_goal_x(t)
	var poss := -1
	if ball.carrier:
		poss = ball.carrier.team
	elif ball.last_touch:
		poss = ball.last_touch.team
	var attacking := poss == t
	var bx := (ball.position.x - own) * d
	var back_line := clampf(bx - (30.0 if attacking else 17.0), 9.0, 58.0)
	var depth := clampf((0.8 - sl.y) / 0.66, 0.0, 1.2)
	var span := 36.0 if attacking else 24.0
	var dist := minf(back_line + depth * span, 97.0)
	var width := 58.0 if attacking else 42.0
	var z := (sl.x - 0.5) * width + ball.position.z * 0.3
	return Vector3(own + d * dist, 0, clampf(z, -31.0, 31.0))


func _build_wall(pool: Array, n: int) -> void:
	var bp: Vector3 = jugada.ball_pos
	var near := Vector3(HALF_L, 0, signf(bp.z) * 1.6 if absf(bp.z) > 2 else 0.0)
	var dir := (near - bp).normalized()
	var center := bp + dir * 9.15
	var perp := Vector3(-dir.z, 0, dir.x)
	for i in n:
		var off := (i - (n - 1) / 2.0) * 0.62
		var w := _make_player(_take(pool, "DEF"), AWAY, center + perp * off)
		w.face_towards(bp)
		wall.append(w)


func _make_aim_marker() -> void:
	aim_marker = Node3D.new()
	var ring := MeshUtil.ring(0.28, 0.36, 0, TAU, 32, Color(1, 0.9, 0.15))
	ring.rotation_degrees.z = 90
	aim_marker.add_child(ring)
	var dot := MeshUtil.ring(0.0, 0.06, 0, TAU, 12, Color(1, 0.3, 0.2))
	dot.rotation_degrees.z = 90
	aim_marker.add_child(dot)
	add_child(aim_marker)
	_update_aim_marker()


func _update_aim_marker() -> void:
	if aim_marker:
		aim_marker.position = Vector3(HALF_L - 0.1, aim.y, aim.x)
		aim_marker.visible = state == State.SETPIECE or state == State.INTRO


func _setup_camera() -> void:
	cam = Camera3D.new()
	cam.fov = 48
	cam.far = 400
	add_child(cam)
	cam.current = true
	if mode in ["freekick", "penalty_for"]:
		cam_mode = "setpiece"
	elif mode == "penalty_against":
		cam_mode = "penalty_gk"
	cam_focus = Vector3(ball.position.x, 0, ball.position.z * 0.5)
	cam.global_transform = _camera_target()


func _setup_hud() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	hud = Hud.new()
	layer.add_child(hud)
	hud.time_total = time_total
	hud.info_text = jugada.name
	hud.set_mode("none")
	_update_hud()


# ---------------------------------------------------------------- Bucle

func _process(delta: float) -> void:
	var real_dt := delta / maxf(Engine.time_scale, 0.01)
	state_t += real_dt
	cam_mode_t += real_dt
	match state:
		State.INTRO:
			_idle_step(delta)
			if state_t > 1.6:
				state_t = 0.0
				if mode in ["freekick", "penalty_for", "penalty_against"]:
					state = State.SETPIECE
				else:
					state = State.PLAY
					hud.show_message("¡YA!", 0.6, true)
		State.SETPIECE:
			_setpiece_step(delta)
		State.PLAY:
			_play_step(delta)
		State.GOAL:
			_free_step(delta)
			if state_t > 2.2:
				Engine.time_scale = 1.0
				var scorer: String = result.get("scorer", "")
				if result.get("goal_for", false):
					_finish(true, "¡GOOOL!", "Gol de %s." % scorer)
				else:
					_finish(false, "Gol en contra", "Marcó %s." % scorer)
		State.ENDED:
			_free_step(delta)
	_update_hud_mode()
	_update_camera(real_dt)
	_update_aim_marker()
	_update_hud()
	hud.end_frame()


func simulate(dt: float) -> void:
	_process(dt)


func _idle_step(dt: float) -> void:
	for p in players:
		p.move_input = Vector3.ZERO
		p.step(dt, p == ball.carrier)
	ball.step(dt)


func _free_step(dt: float) -> void:
	for p in players:
		p.move_input = p.move_input.lerp(Vector3.ZERO, dt * 3.0)
		p.sprinting = false
		p.step(dt, p == ball.carrier)
	ball.step(dt)


func _play_step(dt: float) -> void:
	time_left -= dt
	wall_jump_t = maxf(0.0, wall_jump_t - dt)
	if mode == "corner" and not corner_done:
		_corner_step()
	_update_control_target()
	_compute_marks()
	_handle_input(dt)
	for p in players:
		if p == controlled and not autoplay:
			continue
		if mode == "corner" and not corner_done and p == taker:
			p.move_input = Vector3.ZERO
			continue
		if p.role == "GK":
			_ai_gk(p, dt)
		else:
			_ai_field(p, dt)
	for p in players:
		p.step(dt, p == ball.carrier)
	_separate()
	var ev := ball.step(dt)
	_check_wall()
	_check_aerial()
	_check_possession()
	_check_tackles()
	_check_gk_save()
	_check_end(ev, dt)


# ---------------------------------------------------------------- Balón parado

func _setpiece_step(dt: float) -> void:
	for p in players:
		if p != taker:
			p.move_input = Vector3.ZERO
		p.step(dt, false)
	ball.step(dt)
	if mode == "penalty_against":
		_penalty_against_step()
		return
	var inp := _input_vector()
	if autoplay:
		if state_t > 0.8:
			aim = Vector2(randf_range(-2.8, 2.8), randf_range(0.4, 2.0))
			curve = randf_range(-1, 1)
			_setpiece_shoot(randf_range(0.55, 0.85))
		return
	# Apuntar con el joystick: derecha de la pantalla = +Z, arriba = más alto.
	aim.x = clampf(aim.x + inp.x * 3.2 * dt, -5.0, 5.0)
	aim.y = clampf(aim.y - inp.z * 2.4 * dt, 0.15, 3.2)
	if hud.pressed("b") or _key_edge(KEY_Q) == 1:
		taker_idx = (taker_idx + 1) % takers.size()
		_place_taker(takers[taker_idx])
		hud.show_message("Lanzador: %s" % taker.pname, 1.0)
	if mode == "freekick":
		if hud.pressed("c") or _key_edge(KEY_Z) == 1:
			curve = clampf(curve - 0.25, -1.0, 1.0)
		if hud.pressed("d") or _key_edge(KEY_X) == 1:
			curve = clampf(curve + 0.25, -1.0, 1.0)
	var k := _key_edge(KEY_K)
	if hud.pressed("a") or k == 1:
		charging = true
		charge = 0.0
	if charging:
		charge = minf(charge + dt / 1.0, 1.1)
		hud.shot_power = minf(charge, 1.0)
		if hud.released("a") or k == -1 or (not hud.is_down("a") and not Input.is_key_pressed(KEY_K)):
			charging = false
			hud.shot_power = -1.0
			_setpiece_shoot(minf(charge, 1.0))


func _setpiece_shoot(power: float) -> void:
	var skill: float = taker.tl if mode == "freekick" else taker.sho * 0.6 + taker.tl * 0.4
	var tgt := Vector3(HALF_L, aim.y, aim.x)
	var sd := (100.0 - skill) / 100.0 * 1.1 + (0.35 if power < 0.3 else 0.0)
	tgt.z += randfn(0.0, sd * 0.8)
	tgt.y += randfn(0.0, sd * 0.4) + maxf(0.0, power - 0.85) * 4.5
	tgt.y = maxf(tgt.y, 0.12)
	var spd := lerpf(17.0, 31.0, power) * (0.9 + skill / 1000.0)
	var spin := Vector3(0, -curve * 7.0, 0) if mode == "freekick" else Vector3.ZERO
	var v := _solve_kick(ball.position, tgt, spd, spin)
	if mode == "freekick" and aim.y > 1.3 and not wall.is_empty():
		# Si apuntas alto, el balón toma la parábola necesaria para superar la barrera.
		var need := 2.3 - (skill - 70.0) / 200.0
		while spd > 15.0 and _height_at(ball.position, v, spin, 9.15) < need:
			spd -= 0.8
			v = _solve_kick(ball.position, tgt, spd, spin)
	taker.kick_anim = 0.3
	_kick(taker, v, "shot")
	ball.spin = spin
	_plan_save(taker)
	for w in wall:
		w.head_anim = 0.45
	wall_jump_t = 0.5
	setpiece_kicked = true
	state = State.PLAY
	state_t = 0.0
	time_left = 7.0
	time_total = 7.0
	cam_mode = "follow_shot"
	cam_mode_t = 0.0
	hud.show_message("¡Disparo!" if power < 0.85 else "¡Cañonazo!", 0.8)


func _height_at(from: Vector3, v: Vector3, spin: Vector3, dist: float) -> float:
	## Altura del balón cuando ha recorrido "dist" metros en horizontal.
	var p := from
	var dt := 1.0 / 120.0
	for _i in 600:
		v.y -= Balon.GRAVITY * dt
		v += spin.cross(v) * Balon.MAGNUS * dt
		p += v * dt
		if Vector2(p.x - from.x, p.z - from.z).length() >= dist:
			return p.y
	return p.y


func _solve_kick(from: Vector3, tgt: Vector3, spd: float, spin: Vector3) -> Vector3:
	var flat := tgt - from
	flat.y = 0.0
	var dist := flat.length()
	var t := dist / spd
	var v := flat / dist * spd + Vector3(0, (tgt.y - from.y + 0.5 * Balon.GRAVITY * t * t) / t, 0)
	for _i in 10:
		var pc := ball.predict_cross(tgt.x, from, v, spin)
		if pc.is_empty():
			v.y += 1.0
			continue
		var ez: float = tgt.z - pc.z
		var ey: float = tgt.y - pc.y
		if absf(ez) < 0.03 and absf(ey) < 0.03:
			break
		v.z += ez / pc.t * 0.9
		v.y += ey / pc.t * 0.9
		var h := Vector2(v.x, v.z).normalized() * spd
		v.x = h.x
		v.z = h.y
	return v


func _penalty_against_step() -> void:
	if taker == null:
		return
	if autoplay and pen_choice == 99 and state_t > 1.0:
		pen_choice = [-1, 0, 1][randi() % 3]
	if pen_choice == 99:
		if hud.pressed("b") or Input.is_key_pressed(KEY_A):
			pen_choice = -1
		elif hud.pressed("c") or Input.is_key_pressed(KEY_S):
			pen_choice = 0
		elif hud.pressed("d") or Input.is_key_pressed(KEY_D):
			pen_choice = 1
		if pen_choice != 99:
			hud.show_message(["¡A la izquierda!", "¡Te quedas en el centro!", "¡A la derecha!"][pen_choice + 1], 0.8)
	var bp := ball.position
	if state_t > 1.2:
		_run_to(taker, bp + Vector3(0.5, 0, 0.1), false)
	if state_t > 2.6 or (state_t > 1.2 and taker.position.distance_to(bp) < 0.7):
		_penalty_against_kick()


func _penalty_against_kick() -> void:
	var z := randf_range(1.6, 3.2) * (1.0 if randf() < 0.5 else -1.0)
	if randf() < 0.2:
		z = randf_range(-0.8, 0.8)
	var y := randf_range(0.25, 1.9)
	if randf() < 0.1 - taker.sho / 1500.0:
		z = 4.3 * signf(z + 0.01)
	var tgt := Vector3(-HALF_L, y, z)
	var v := _solve_kick(ball.position, tgt, 24.0 + taker.sho / 20.0, Vector3.ZERO)
	taker.kick_anim = 0.3
	_kick(taker, v, "shot")
	var gk := _gk_of(HOME)
	var choice: int = pen_choice if pen_choice != 99 else [-1, 0, 1][randi() % 3]
	var shot_side := 0 if absf(z) < 1.2 else int(signf(z))
	var p_save := 0.03
	if choice == shot_side:
		p_save = 0.85 if choice == 0 else 0.5 + gk.gkp / 100.0 * 0.35
		if absf(z) > 2.8 and (y > 1.5 or y < 0.4):
			p_save -= 0.25
	if pen_choice == 99:
		p_save *= 0.6
	var on_target := absf(z) < GOAL_HW and y < GOAL_H
	gk_plan = {"gk": gk, "save": on_target and randf() < p_save, "dive_z": choice * 2.7, "react": 0.03,
		"y": y, "t": 0.6, "dived": false, "resolved": false, "on_target": on_target}
	state = State.PLAY
	state_t = 0.0
	time_left = 4.0
	time_total = 4.0


func _corner_step() -> void:
	if state_t < 1.4 or taker == null:
		if controlled == null or controlled == taker:
			var c := _closest(home.filter(func(x): return x != taker and x.role != "GK"), jugada.target)
			if c:
				_set_controlled(c)
		return
	corner_done = true
	var tgt: Vector3 = jugada.target + Vector3(randf_range(-1.5, 1.5), 0, randf_range(-1.5, 1.5))
	var flat := tgt - ball.position
	flat.y = 0
	var t := flat.length() / 19.0
	var v := flat / t + Vector3(0, (1.7 - ball.position.y + 0.5 * Balon.GRAVITY * t * t) / t, 0)
	v *= 1.0 + (100.0 - taker.pas) / 100.0 * randf_range(-0.12, 0.12)
	_kick(taker, v, "cross")
	var recv := _closest(home.filter(func(x): return x != taker and x.role != "GK"), tgt)
	ball.pass_target = recv
	if recv:
		_set_controlled(recv)


# ---------------------------------------------------------------- Control del usuario

func _attacking() -> bool:
	if ball.carrier != null:
		return ball.carrier.team == HOME
	return ball.last_touch == null or ball.last_touch.team == HOME


func _update_hud_mode() -> void:
	if state == State.SETPIECE:
		hud.set_mode("penalty_gk" if mode == "penalty_against" else ("penalty_shot" if mode == "penalty_for" else "setpiece"))
		if mode == "penalty_against":
			hud.hint_text = "Elige hacia dónde te lanzas antes de que patee" if pen_choice == 99 else ""
		else:
			var c_txt := "apunta a un lado" if mode == "penalty_for" else "sin efecto" if absf(curve) < 0.01 else ("efecto %s %d%%" % ["a la derecha" if curve > 0 else "a la izquierda", int(absf(curve) * 100)])
			var skill: int = int(taker.tl) if mode == "freekick" else int(taker.sho)
			hud.hint_text = "Lanzador: %s (%s %d)  ·  %s  ·  Mantén TIRO para la potencia" % [taker.pname, "TL" if mode == "freekick" else "TIR", skill, c_txt]
	elif state == State.PLAY:
		if mode == "penalty_against":
			hud.set_mode("none")
		else:
			hud.set_mode("attack" if _attacking() else "defense")
		hud.hint_text = ""
	else:
		hud.set_mode("none")
		hud.hint_text = ""


func _set_controlled(p: Futbolista) -> void:
	if controlled == p:
		return
	if controlled and is_instance_valid(controlled):
		controlled.set_controlled(false)
	controlled = p
	if p:
		p.set_controlled(true)
	charging = false
	if hud:
		hud.shot_power = -1.0


func _update_control_target() -> void:
	if mode == "penalty_against":
		_set_controlled(null)
		return
	if mode == "corner" and not corner_done:
		return
	if ball.carrier and ball.carrier.team == HOME:
		_set_controlled(ball.carrier)
	elif ball.carrier == null and ball.pass_target and ball.pass_target.team == HOME:
		_set_controlled(ball.pass_target)
	elif controlled == null or controlled.role == "GK":
		_set_controlled(_closest(_field(home, false), ball.position))
	elif ball.carrier == null and not (ball.kind in ["pass", "through", "cross"]):
		var c := _closest(_field(home, false), ball.position)
		if c and c.position.distance_to(ball.position) + 3.0 < controlled.position.distance_to(ball.position):
			_set_controlled(c)


func _input_vector() -> Vector3:
	var v := Vector3(hud.joy_vec.x, 0, hud.joy_vec.y)
	var k := Vector3.ZERO
	if Input.is_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT):
		k.x -= 1
	if Input.is_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT):
		k.x += 1
	if Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP):
		k.z -= 1
	if Input.is_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN):
		k.z += 1
	if k != Vector3.ZERO:
		v = k.normalized()
	return v


func _key_edge(key: int) -> int:
	var now := Input.is_key_pressed(key)
	var before: bool = _keys_prev.get(key, false)
	_keys_prev[key] = now
	if now and not before:
		return 1
	if before and not now:
		return -1
	return 0


func _handle_input(dt: float) -> void:
	if autoplay or controlled == null:
		return
	var p := controlled
	var inp := _input_vector()
	var k_shot := _key_edge(KEY_K)
	var k_pass := _key_edge(KEY_J)
	var k_thr := _key_edge(KEY_L)
	var k_sw := _key_edge(KEY_Q)
	var a_down := hud.is_down("a") or Input.is_key_pressed(KEY_K)
	var a_press := hud.pressed("a") or k_shot == 1
	var a_rel := hud.released("a") or k_shot == -1
	var b_press := hud.pressed("b") or k_pass == 1 or k_sw == 1
	var c_press := hud.pressed("c") or k_thr == 1
	var c_down := hud.is_down("c") or Input.is_key_pressed(KEY_L)
	p.sprinting = hud.is_down("d") or Input.is_key_pressed(KEY_SHIFT)
	var attack := _attacking()

	if ball.carrier == null and ball.pass_target == p and ball.kind in ["pass", "through", "cross"]:
		# El receptor va solo a por el balón aunque sigas tocando el joystick.
		_run_to(p, _receive_point(p), true)
	elif not attack and c_down and ball.carrier:
		_run_to(p, ball.carrier.position, true)
	else:
		p.move_input = inp

	_update_pass_marker(p, inp, attack)
	if attack:
		if ball.carrier == p:
			if a_press:
				charging = true
				charge = 0.0
			if charging:
				charge = minf(charge + dt / 0.9, 1.15)
				hud.shot_power = minf(charge, 1.0)
				if a_rel or not a_down:
					_shoot(p, minf(charge, 1.0), _user_aim(p, inp))
					charging = false
					hud.shot_power = -1.0
			elif b_press:
				_pass(p, false, inp)
			elif c_press:
				_pass(p, true, inp)
		else:
			charging = false
			hud.shot_power = -1.0
			var d := _hdist(p.position, ball.position)
			var near := ball.carrier == null and d < 1.7 and ball.position.y < 2.8
			if near and a_press:
				if ball.position.y > 1.15:
					p.head_anim = 0.45
					_shoot(p, 0.6, _user_aim(p, inp), true)
				else:
					_shoot(p, 0.75, _user_aim(p, inp))
			elif near and b_press and ball.position.y < 1.4:
				_pass(p, false, inp)
	else:
		charging = false
		hud.shot_power = -1.0
		if a_press and p.slide_t <= 0.0 and p.stun <= 0.0:
			p.slide_t = 0.6
			p.slide_resolved = false
			p.slide_dir = inp.normalized() if inp.length() > 0.2 else p.facing
			p.facing = p.slide_dir
		elif b_press:
			var others := _field(home, false).filter(func(x): return x != p)
			var c := _closest(others, ball.position)
			if c:
				_set_controlled(c)


var _marked_target: Futbolista = null


func _update_pass_marker(p: Futbolista, inp: Vector3, attack: bool) -> void:
	var t: Futbolista = null
	if attack and ball.carrier == p:
		t = _select_pass_target(p, inp.normalized() if inp.length() > 0.2 else p.facing)
	if t != _marked_target:
		if _marked_target and is_instance_valid(_marked_target):
			_marked_target.set_pass_target(false)
		_marked_target = t
		if t:
			t.set_pass_target(true)


func _user_aim(p: Futbolista, inp: Vector3) -> float:
	if absf(inp.z) > 0.25:
		return signf(inp.z) * lerpf(1.2, 3.1, absf(inp.z))
	return -signf(p.position.z) * 1.9 if absf(p.position.z) > 1.0 else randf_range(-2.0, 2.0)


# ---------------------------------------------------------------- Acciones

func _give_ball(p: Futbolista) -> void:
	ball.carrier = p
	ball.last_touch = p
	ball.kind = ""
	ball.pass_target = null
	ball.spin = Vector3.ZERO
	ball.rolled.clear()
	p.hold_t = 0.0
	gk_plan = {}


func _kick(p: Futbolista, v: Vector3, kind: String) -> void:
	ball.carrier = null
	ball.vel = v
	ball.spin = Vector3.ZERO
	ball.last_touch = p
	ball.last_kicker = p
	ball.kicker_ban = 0.35
	ball.kind = kind
	ball.pass_target = null
	ball.rolled.clear()
	ball.shot_time = 0.0
	p.kick_anim = 0.3
	gk_plan = {}
	var d := Vector3(v.x, 0, v.z)
	if d.length() > 0.1:
		p.facing = d.normalized()


func _select_pass_target(p: Futbolista, dir: Vector3) -> Futbolista:
	## Compañero al que va el pase: el más alineado con la dirección del joystick,
	## penalizando la distancia y las líneas de pase tapadas.
	var best: Futbolista = null
	var best_score := -INF
	for m in _field(team_of(p.team), true, true):
		if m == p:
			continue
		var to: Vector3 = m.position - p.position
		to.y = 0
		var dist := to.length()
		if dist < 3.0 or dist > 45.0:
			continue
		var align := dir.dot(to / dist)
		if align < 0.2:
			continue
		var score := align * 3.0 - dist / 28.0
		if _lane_blocked(p.position, m.position, p.team, 0.9):
			score -= 1.2
		if score > best_score:
			best_score = score
			best = m
	return best


func _pass(p: Futbolista, through: bool, inp: Vector3) -> void:
	var dir := inp.normalized() if inp.length() > 0.2 else p.facing
	var best := _select_pass_target(p, dir)
	if best == null:
		_kick(p, dir * 12.0 + Vector3(0, 0.5, 0), "pass")
		return
	_pass_to(p, best, through)


func _pass_to(p: Futbolista, best: Futbolista, through: bool) -> void:
	var dsign := dir_of(p.team)
	var target := best.position
	var dist := p.position.distance_to(best.position)
	if through:
		var run := best.velocity.normalized() if best.velocity.length() > 1.0 else Vector3(dsign, 0, 0)
		target += run * clampf(dist * 0.4, 4.0, 12.0)
	else:
		target += best.velocity * (dist / 18.0)
	target.x = clampf(target.x, -HALF_L + 1, HALF_L - 1)
	target.z = clampf(target.z, -HALF_W + 1, HALF_W - 1)
	var flat := target - ball.position
	flat.y = 0
	var d2 := flat.length()
	var err := randf_range(-1.0, 1.0) * (1.0 - p.pas / 100.0) * 0.14
	var dirn := flat.normalized().rotated(Vector3.UP, err)
	var gx := goal_x(p.team)
	var is_cross := d2 > 14.0 and absf(p.position.z) > 13.0 and absf(target.x - gx) < 20.0 and absf(target.z) < 14.0
	if is_cross:
		var t := d2 / 18.0
		var v := dirn * 18.0 + Vector3(0, (1.6 - ball.position.y + 0.5 * Balon.GRAVITY * t * t) / t, 0)
		_kick(p, v, "cross")
	else:
		var v_end := 3.5 if through else 4.5
		var spd := sqrt(v_end * v_end + 2.0 * (Balon.ROLL_DECEL + 0.4) * 1.2 * d2)
		_kick(p, dirn * spd + Vector3(0, 0.6, 0), "through" if through else "pass")
	ball.pass_target = best


func _shoot(p: Futbolista, power: float, aim_z: float, header := false) -> void:
	var gx := goal_x(p.team)
	var aim_y := lerpf(0.35, 1.9, power * power) if not header else randf_range(0.3, 1.6)
	var target := Vector3(gx, aim_y, clampf(aim_z, -3.3, 3.3))
	var dist := _hdist(ball.position, target)
	var sd := (100.0 - p.sho) / 100.0 * (0.45 + dist / 24.0)
	if header:
		sd *= 1.3
	target.z += randfn(0.0, sd)
	target.y += randfn(0.0, sd * 0.5) + maxf(0.0, power - 0.85) * 5.0
	target.y = maxf(target.y, 0.12)
	var speed_h := lerpf(15.0, 32.0, power) * (0.82 + p.sho / 550.0)
	if header:
		speed_h = lerpf(11.0, 19.0, power) * (0.85 + p.sho / 600.0)
	var flat := target - ball.position
	flat.y = 0
	var t := flat.length() / speed_h
	var vy := (target.y - ball.position.y + 0.5 * Balon.GRAVITY * t * t) / maxf(t, 0.05)
	_kick(p, flat.normalized() * speed_h + Vector3(0, vy, 0), "shot")
	_plan_save(p)
	if p.team == HOME:
		hud.show_message("¡Cabezazo!" if header else ("¡Disparo!" if power < 0.85 else "¡Cañonazo!"), 0.8)


func _clear(p: Futbolista) -> void:
	var d := dir_of(p.team)
	var target := Vector3(p.position.x + d * 35.0, 0, randf_range(-28, 28))
	var flat := target - p.position
	flat.y = 0
	_kick(p, flat.normalized() * 24.0 + Vector3(0, 9.0, 0), "clear")


# ---------------------------------------------------------------- Portero

func _plan_save(shooter: Futbolista) -> void:
	## Decide al disparar si el portero llega, según su habilidad, la velocidad y la colocación.
	var def_team := AWAY if shooter.team == HOME else HOME
	var gk := _gk_of(def_team)
	if gk == null:
		return
	var gx := own_goal_x(def_team)
	var pc := ball.predict_cross(gx)
	if pc.is_empty():
		return
	var z: float = pc.z
	var y: float = pc.y
	var on_target := absf(z) < GOAL_HW - 0.05 and y < GOAL_H - 0.05
	var react := 0.12 + (100.0 - gk.gkp) / 100.0 * 0.22
	var t_avail := maxf(0.0, float(pc.t) - react)
	var dive_speed := 6.0 + gk.gkp / 100.0 * 3.0
	var reach := 0.6 + gk.gkp / 100.0 * 0.6
	var capacity := minf(t_avail * dive_speed, 2.2 + gk.gkp / 100.0 * 0.8) + maxf(0.0, t_avail - 0.6) * 4.0 + reach
	var d := absf(z - gk.position.z)
	if y > 2.0:
		capacity -= 0.35
	var spd := ball.vel.length()
	var p_save := 0.0
	if on_target and d <= capacity:
		p_save = 0.25 + gk.gkp / 100.0 * 0.45 - maxf(0.0, spd - 18.0) / 30.0
		p_save += clampf((capacity - d) / 2.5, 0.0, 0.5)
		if absf(z) > 2.7 and (y > 1.7 or y < 0.45):
			p_save -= 0.2
		p_save = clampf(p_save, 0.04, 0.97)
	elif on_target:
		p_save = 0.02
	var save := randf() < p_save
	var dive_z := z
	if not save:
		var dir := signf(z - gk.position.z)
		dive_z = gk.position.z + dir * maxf(0.0, minf(d, capacity) - randf_range(0.5, 1.0))
		if not on_target:
			dive_z = clampf(z, -GOAL_HW - 0.5, GOAL_HW + 0.5) if absf(z) < GOAL_HW + 2.0 else gk.position.z
	gk_plan = {"gk": gk, "save": save, "on_target": on_target, "t": pc.t, "z": z, "y": y,
		"dive_z": clampf(dive_z, -GOAL_HW - 0.6, GOAL_HW + 0.6), "react": react, "dived": false, "resolved": false}


func _ai_gk(p: Futbolista, dt: float) -> void:
	var gx := own_goal_x(p.team)
	var side := signf(gx)
	if ball.carrier == p:
		p.move_input = Vector3.ZERO
		p.face_towards(Vector3.ZERO)
		return
	if p.dive_t > 0.0:
		var to := p.dive_target - p.position
		to.y = 0
		var need := maxf(0.25, float(gk_plan.get("t", 0.6)) - float(gk_plan.get("react", 0.1)) - 0.05)
		var spd := clampf(to.length() / need, 3.5, 11.0)
		p.velocity = to.normalized() * spd if to.length() > 0.12 else p.velocity * 0.8
		return
	if gk_plan.get("gk") == p and not gk_plan.resolved:
		if ball.shot_time >= gk_plan.react and not gk_plan.dived:
			gk_plan.dived = true
			var dz: float = gk_plan.dive_z - p.position.z
			p.face_towards(ball.position)
			if absf(dz) > 0.4 or float(gk_plan.y) > 1.8:
				p.dive_t = 0.7
				p.dive_side = signf(dz) if absf(dz) > 0.05 else 0.0
				p.dive_target = Vector3(p.position.x, 0, gk_plan.dive_z)
				p.dive_high = clampf((float(gk_plan.y) - 0.9) / 1.4, 0.0, 1.0)
			else:
				p.head_anim = 0.4 if float(gk_plan.y) > 1.2 else 0.0
				p.move_input = Vector3.ZERO
		elif not gk_plan.dived:
			p.move_input = Vector3.ZERO
		return
	# Salir a por un balón suelto cerca del área chica
	if ball.carrier == null and ball.kind != "shot":
		var bd := _hdist(ball.position, Vector3(gx, 0, 0))
		var closest_any := _closest(players.filter(func(x): return x.role != "GK"), ball.position)
		var mine := closest_any == null or _hdist(p.position, ball.position) < _hdist(closest_any.position, ball.position)
		if bd < 11.0 and ball.vel.length() < 14.0 and absf(ball.position.z) < 14 and (mine or bd < 6.0) and ball.position.y < 2.5:
			_run_to(p, ball.position, true)
			return
	# Colocación entre el balón y el centro de la portería
	var goal_c := Vector3(gx, 0, 0)
	var to_ball := ball.position - goal_c
	to_ball.y = 0
	var dist := to_ball.length()
	var adv := clampf(dist * 0.1, 0.7, 3.0)
	var tgt := goal_c + to_ball.normalized() * adv
	tgt.z = clampf(tgt.z, -GOAL_HW + 0.4, GOAL_HW - 0.4)
	tgt.x = gx - side * maxf(absf(tgt.x - gx), 0.4)
	_run_to(p, tgt, false)
	if p.move_input.length() < 0.1:
		p.face_towards(ball.position)


func _check_gk_save() -> void:
	if gk_plan.is_empty() or gk_plan.resolved:
		return
	if ball.carrier != null or ball.kind != "shot" or ball.scored:
		gk_plan.resolved = true
		return
	var gk: Futbolista = gk_plan.gk
	var side := signf(own_goal_x(gk.team))
	var passed := (ball.position.x - gk.position.x) * side > -0.5
	if not passed:
		return
	gk_plan.resolved = true
	if not gk_plan.save:
		return
	var sp := ball.speed()
	if sp < 21.0 and randf() < 0.3 + gk.gkp / 250.0:
		_give_ball(gk)
		hud.show_message("¡Atajada de %s!" % gk.pname, 1.2)
	else:
		var zdir := signf(ball.position.z - gk.position.z)
		if zdir == 0.0:
			zdir = 1.0 if randf() < 0.5 else -1.0
		ball.position.x = gk.position.x - side * 0.3
		ball.vel = Vector3(-side * sp * randf_range(0.15, 0.3), randf_range(2.0, 5.0), zdir * sp * randf_range(0.2, 0.4))
		ball.spin = Vector3.ZERO
		ball.kind = "loose"
		ball.last_touch = gk
		ball.last_kicker = gk
		ball.kicker_ban = 0.6
		ball.rolled.clear()
		hud.show_message("¡Paradón de %s!" % gk.pname, 1.2)


# ---------------------------------------------------------------- IA de campo

func _ai_field(p: Futbolista, dt: float) -> void:
	var c := ball.carrier
	if c == p:
		_ai_carrier(p, dt)
		return
	if c == null:
		if ball.pass_target == p:
			_run_to(p, _receive_point(p), true)
			return
		var to_mate := ball.pass_target != null and ball.pass_target.team == p.team
		if not to_mate:
			var chaser := _closest(_field(team_of(p.team), true), ball.position + Vector3(ball.vel.x, 0, ball.vel.z) * 0.3)
			if chaser == p:
				_run_to(p, ball.position + Vector3(ball.vel.x, 0, ball.vel.z) * 0.3, true)
				return
		if ball.last_touch != null and ball.last_touch.team == p.team:
			_ai_support(p)
		else:
			_ai_defend(p, ball.position)
		return
	if c.team == p.team:
		_ai_support(p)
	else:
		_ai_defend(p, c.position)


func _receive_point(p: Futbolista) -> Vector3:
	var v := Vector3(ball.vel.x, 0, ball.vel.z)
	var to := p.position - ball.position
	to.y = 0
	var t := clampf(to.length() / maxf(v.length(), 1.0), 0.0, 1.2)
	var pt := ball.position + v * t * 0.8
	pt.y = 0
	return pt


func _ai_support(p: Futbolista) -> void:
	if not p.key_player and p.role != "FWD":
		_ai_shape(p)
		return
	var d := dir_of(p.team)
	var gx := goal_x(p.team)
	var ref := ball.position.x
	var near_box := (gx - ref) * d < 24.0
	var lane := p.lane_z * (0.5 if near_box else 1.0)
	var tx := ref + d * p.run_ahead
	if near_box:
		tx = gx - d * (7.5 + absf(lane) * 0.3)
	if (gx - tx) * d < 7.0:
		tx = gx - d * 7.0
	var tgt := Vector3(tx, 0, lane)
	_run_to(p, tgt, p.position.distance_to(tgt) > 4.0)


var _marks := {}
var _pressers := {}


func _compute_marks() -> void:
	## Para cada equipo que defiende: quién presiona y a quién marca cada defensor.
	_marks.clear()
	_pressers.clear()
	var focus := ball.carrier.position if ball.carrier else ball.position
	for t in [HOME, AWAY]:
		var field := _field(team_of(t), true)
		var presser := _closest(field, focus)
		_pressers[t] = presser
		var og := Vector3(own_goal_x(t), 0, 0)
		var attackers := _field(team_of(1 - t), false, true).filter(func(x):
			return x != ball.carrier and (_hdist(x.position, og) < 34.0 or _hdist(x.position, focus) < 22.0))
		attackers.sort_custom(func(a, b): return a.position.distance_to(og) < b.position.distance_to(og))
		var used := {}
		for atk in attackers:
			var best: Futbolista = null
			var bd := INF
			for df in field:
				if df == presser or used.has(df):
					continue
				var dd: float = df.position.distance_to(atk.position)
				if dd < bd:
					bd = dd
					best = df
			if best and bd < 30.0:
				used[best] = true
				_marks[best] = atk


func _ai_shape(p: Futbolista) -> void:
	var tgt := _shape_spot(p.team, p.slot)
	_run_to(p, tgt, p.position.distance_to(tgt) > 9.0)
	if p.move_input.length() < 0.1:
		p.face_towards(ball.position)


func _ai_defend(p: Futbolista, focus: Vector3) -> void:
	var og := Vector3(own_goal_x(p.team), 0, 0)
	if _pressers.get(p.team) == p:
		_run_to(p, focus + (og - focus).normalized() * 0.7, true)
		return
	if _marks.has(p):
		var atk2: Futbolista = _marks[p]
		var tgt := atk2.position + (og - atk2.position).normalized() * 1.8
		if absf(tgt.x) > HALF_L - 1.5:
			tgt.x = signf(tgt.x) * (HALF_L - 1.5)
		_run_to(p, tgt, p.position.distance_to(tgt) > 2.5)
		return
	_ai_shape(p)


func _ai_carrier(p: Futbolista, dt: float) -> void:
	p.hold_t += dt
	var d := dir_of(p.team)
	var goal := Vector3(goal_x(p.team), 0, 0)
	var dist := _hdist(p.position, goal)
	var opps := _field(team_of(1 - p.team), false, true)
	var pressure := _closest(opps, p.position)
	var pd := _hdist(pressure.position, p.position) if pressure else 99.0
	# El equipo que defiende en esta jugada despeja cuando recupera el balón
	var user_attacks := mode in ["attack", "corner", "freekick", "penalty_for"]
	var defending_side := (p.team == AWAY) == user_attacks
	if defending_side:
		if p.hold_t > 0.45 + randf() * 0.3:
			_clear(p)
			return
		_run_to(p, p.position + Vector3(d * 5, 0, signf(p.position.z) * 2.0), false)
		return
	var shoot_range := 13.0 + p.sho / 100.0 * 15.0
	if dist < shoot_range and p.hold_t > 0.3:
		var blocked := _lane_blocked(p.position, goal, p.team, 1.2)
		if (not blocked or dist < 14.0) and randf() < dt * (3.5 if dist < 18.0 else 1.4):
			var power := clampf(0.5 + dist / 55.0 + randf_range(-0.08, 0.12), 0.45, 0.92)
			_shoot(p, power, randf_range(1.6, 3.0) * (1.0 if randf() < 0.5 else -1.0))
			return
	# ¿La presión viene de frente o desde atrás?
	var pressure_front := false
	if pressure:
		pressure_front = (pressure.position.x - p.position.x) * d > -0.5
	var urgent := pd < 1.7 or (pressure_front and pd < 3.0)
	if p.hold_t > 0.45 and randf() < dt * (3.5 if urgent else 0.7):
		var best: Futbolista = null
		var bs := -INF
		for m in _field(team_of(p.team), false, true):
			if m == p:
				continue
			var progress: float = (m.position.x - p.position.x) * d
			if progress < (-4.0 if urgent else 1.0):
				continue
			if _lane_blocked(p.position, m.position, p.team, 1.0):
				continue
			var marker := _closest(opps, m.position)
			var open := _hdist(marker.position, m.position) if marker else 20.0
			if open < 2.0:
				continue
			var s := progress * 0.35 + minf(open, 8.0) - p.position.distance_to(m.position) * 0.04
			if s > bs:
				bs = s
				best = m
		if best and bs > 2.0:
			var ahead_of_defense := true
			for o in opps:
				if (o.position.x - best.position.x) * d > 0.0:
					ahead_of_defense = false
			_pass_to(p, best, not ahead_of_defense and randf() < 0.5)
			return
	var dirv := (goal - p.position).normalized()
	if absf(goal.x - p.position.x) < 12.0:
		dirv = (goal + Vector3(-d * 4.0, 0, 0) - p.position).normalized()
	if pressure and pd < 5.0 and pressure_front:
		var away_v := p.position - pressure.position
		away_v.y = 0
		var side := Vector3(-dirv.z, 0, dirv.x)
		if side.dot(away_v) < 0.0:
			side = -side
		dirv = (dirv + side * 0.9).normalized()
	_run_to(p, p.position + dirv * 5.0, true)


func _lane_blocked(from: Vector3, to: Vector3, team: int, width := 1.3) -> bool:
	for o in team_of(1 - team):
		if o.role == "GK":
			continue
		var seg := to - from
		seg.y = 0
		var t := clampf((o.position - from).dot(seg) / seg.length_squared(), 0.0, 1.0)
		var closest := from + seg * t
		if _hdist(closest, o.position) < width and t > 0.05:
			return true
	return false


func _run_to(p: Futbolista, target: Vector3, sprint := false) -> void:
	var d := target - p.position
	d.y = 0
	var dist := d.length()
	if dist < 0.4:
		p.move_input = Vector3.ZERO
		p.sprinting = false
		return
	p.move_input = d / dist * clampf(dist / 2.0, 0.0, 1.0)
	p.sprinting = sprint and dist > 2.0


# ---------------------------------------------------------------- Reglas

func _check_wall() -> void:
	if wall.is_empty() or ball.carrier != null or ball.kind != "shot":
		return
	var h := 1.85 + (0.28 if wall_jump_t > 0.0 else 0.0)
	for w in wall:
		if ball.position.y > h:
			continue
		var a := Vector2(ball.prev_pos.x, ball.prev_pos.z)
		var b := Vector2(ball.position.x, ball.position.z)
		var c := Vector2(w.position.x, w.position.z)
		var ab := b - a
		var t := clampf((c - a).dot(ab) / maxf(ab.length_squared(), 0.0001), 0.0, 1.0)
		if (a + ab * t).distance_to(c) < 0.4:
			ball.vel = Vector3(-ball.vel.x * 0.25, randf_range(2.0, 5.0), ball.vel.z * 0.3 + randf_range(-4, 4))
			ball.spin = Vector3.ZERO
			ball.kind = "loose"
			ball.last_touch = w
			gk_plan = {}
			wall.clear()
			hud.show_message("¡A la barrera!", 1.0)
			return


func _check_aerial() -> void:
	## Remates de cabeza y despejes aéreos de la IA.
	if ball.carrier != null or ball.position.y < 1.0 or ball.position.y > 2.7:
		return
	if not (ball.kind in ["cross", "loose", "clear"]):
		return
	for p in players:
		if p.role == "GK" or p.stun > 0.0 or (p == controlled and not autoplay):
			continue
		if p == ball.last_kicker and ball.kicker_ban > 0.0:
			continue
		if ball.rolled.has(p) or _hdist(p.position, ball.position) > 1.0:
			continue
		ball.rolled[p] = true
		var attacking := ball.last_touch != null and ball.last_touch.team == p.team and ball.kind == "cross"
		var win_p := (0.62 + p.sho / 500.0) if attacking else (0.42 + p.dfn / 400.0)
		if randf() > win_p:
			continue
		p.head_anim = 0.45
		if attacking:
			_shoot(p, 0.6, randf_range(-2.8, 2.8), true)
		else:
			var d := dir_of(p.team)
			_kick(p, Vector3(d * randf_range(8, 14), randf_range(4, 7), randf_range(-8, 8)), "clear")
			hud.show_message("Despeje de cabeza", 0.8)
		return


func _check_possession() -> void:
	if ball.carrier != null:
		return
	var best: Futbolista = null
	var bd := INF
	for p in players:
		if p == ball.last_kicker and ball.kicker_ban > 0.0:
			continue
		if p.stun > 0.0 or p.dive_t > 0.0:
			continue
		var reach := 0.8
		var max_h := 1.1
		if p.role == "GK":
			reach = 1.15
			max_h = 2.4
		var d := _hdist(p.position, ball.position)
		if d < reach and ball.position.y < max_h and d < bd:
			if ball.rolled.has(p):
				continue
			var sp := ball.speed()
			var chance := 1.0
			var same_team := ball.last_touch != null and ball.last_touch.team == p.team
			if p.role == "GK":
				chance = 1.0 if (sp < 15.0 or ball.kind != "shot") else 0.0
			elif same_team:
				chance = clampf(1.5 - sp / 28.0, 0.55, 1.0)
			else:
				chance = clampf(1.25 - sp / 24.0, 0.12, 1.0) * (0.8 + p.dfn / 500.0)
			ball.rolled[p] = true
			if randf() < chance:
				best = p
				bd = d
	if best:
		var was_shot := ball.kind == "shot"
		_give_ball(best)
		if best.team == AWAY and best.role != "GK" and mode != "defend":
			hud.show_message("¡Intercepción!" if not was_shot else "¡Bloqueo!", 1.0)


func _check_tackles() -> void:
	var c := ball.carrier
	if controlled and controlled.slide_t > 0.0 and not controlled.slide_resolved:
		var foot := controlled.position + controlled.slide_dir * 0.6
		if c and c.team == AWAY and _hdist(foot, c.position) < 1.2:
			controlled.slide_resolved = true
			if randf() < 0.45 + controlled.dfn / 250.0 - c.spd / 600.0:
				c.stun = 0.8
				_give_ball(controlled)
				ball.carrier = null
				ball.vel = controlled.slide_dir * 7.0
				ball.kind = "loose"
				hud.show_message("¡Barrida limpia!", 1.0)
			else:
				hud.show_message("Barrida fallida", 0.8)
		elif c == null and _hdist(foot, ball.position) < 1.1 and ball.position.y < 0.6:
			controlled.slide_resolved = true
			ball.vel = controlled.slide_dir * 8.0 + Vector3(0, 0.5, 0)
			ball.last_touch = controlled
			ball.kind = "loose"
			ball.pass_target = null
			gk_plan = {}
	if c == null:
		return
	for t in players:
		if t.team == c.team or t.role == "GK" or t.stun > 0.0 or t.slide_t > 0.0 or t.tackle_cd > 0.0:
			continue
		if _hdist(t.position, c.position) < 1.1:
			t.tackle_cd = 1.0
			var chance := 0.22 + (t.dfn - c.spd) * 0.005
			if c.sprinting:
				chance += 0.08
			if c.is_controlled:
				chance -= 0.05
			if t.is_controlled:
				chance += 0.05
			if randf() < chance:
				c.stun = 0.7
				_give_ball(t)
				if t.team == AWAY:
					hud.show_message("¡Te robaron el balón!", 1.0)
				else:
					hud.show_message("¡Balón recuperado!", 1.0)
				return


func _check_end(ev: String, dt: float) -> void:
	if ev == "post":
		hud.show_message("¡Al palo!", 1.0)
	if ev == "goal_home" or ev == "goal_away":
		_goal(ev == "goal_home")
		return
	var c := ball.carrier
	var attack_mode := mode in ["attack", "corner", "freekick", "penalty_for"]
	if attack_mode:
		if ev == "out":
			if ball.last_touch and ball.last_touch.team == AWAY and ball.position.x > HALF_L - 1:
				_finish(false, "Córner", "La defensa la mandó a córner. ¡Casi!", {"text": "Córner que no se aprovecha."})
			else:
				_finish(false, "Fuera", "El balón salió del campo.", {"text": "La jugada termina con el balón fuera."})
			return
		if c and c.team == AWAY:
			if c.role == "GK":
				gk_hold += dt
				if gk_hold > 0.6:
					_finish(false, "¡Atajada!", "%s se quedó con el balón." % c.pname, {"text": "El portero %s atrapa el balón." % c.pname})
					return
			else:
				away_hold += dt
				if away_hold > 1.4:
					_finish(false, "Balón perdido", "%s recuperó el balón." % c.pname, {"text": "%s corta la jugada." % c.pname})
					return
		else:
			gk_hold = 0.0
			away_hold = 0.0
		if c == null and ball.kind == "clear" and ball.last_touch and ball.last_touch.team == AWAY and ball.position.x < 25.0:
			_finish(false, "Despejada", "La defensa despejó el balón.", {"text": "La defensa despeja el peligro."})
			return
		if time_left <= 0.0:
			_finish(false, "Se acabó el tiempo", "No lograste definir la jugada.", {"text": "La jugada se diluye sin remate."})
	else:
		if ev == "out":
			_finish(true, "¡Defendiste!", "El balón salió del campo.", {"text": "Tu defensa aguanta y el balón sale fuera."})
			return
		if c and c.team == HOME:
			home_hold += dt
			if c.role == "GK" and home_hold > 0.4:
				_finish(true, "¡Atajada!", "Tu portero %s se quedó con el balón." % c.pname, {"text": "%s atrapa el balón." % c.pname})
				return
			if home_hold > 1.0:
				_finish(true, "¡Defendiste!", "%s recuperó el balón." % c.pname, {"text": "%s recupera el balón." % c.pname})
				return
		else:
			home_hold = 0.0
		if c == null and ball.kind == "clear" and ball.last_touch and ball.last_touch.team == HOME:
			_finish(true, "¡Defendiste!", "Despeje de %s." % ball.last_touch.pname, {"text": "Despeje de %s." % ball.last_touch.pname})
			return
		if time_left <= 0.0:
			_finish(true, "¡Defendiste!", "El rival no encontró el gol.", {"text": "Tu equipo resiste el ataque."})


func _goal(user_scored: bool) -> void:
	state = State.GOAL
	state_t = 0.0
	Engine.time_scale = 0.35
	hud.release_all()
	hud.controls_enabled = false
	var lt := ball.last_touch
	var team := HOME if user_scored else AWAY
	var scorer := lt.pname if lt and lt.team == team else ""
	if scorer == "":
		var c := _closest(team_of(team).filter(func(x): return x.role != "GK"), ball.position)
		scorer = c.pname if c else ""
	for p in team_of(team):
		if p.role != "GK":
			p.celebrate = 3.0
	if user_scored:
		hud.show_message("¡GOOOOL!", 2.2, true)
		GameData.stats.goals += 1
		result = {"goal_for": true, "scorer": scorer}
	else:
		hud.show_message("Gol del rival", 2.2, true)
		result = {"goal_against": true, "scorer": scorer}


func _finish(win: bool, title: String, reason: String, res: Dictionary = {}) -> void:
	if state == State.ENDED:
		return
	state = State.ENDED
	state_t = 0.0
	Engine.time_scale = 1.0
	if not res.is_empty():
		result = res
	if not result.has("text"):
		result["text"] = title
	GameData.moment_result = result
	if controlled and is_instance_valid(controlled):
		controlled.set_controlled(false)
	var ctx: String = moment.get("context", "training")
	var buttons: Array = []
	if ctx == "training":
		buttons = [["Otra jugada", _next_training], ["Repetir", _repeat], ["Menú", _go_menu]]
	else:
		buttons = [["Continuar", _return_to_sim]]
	hud.show_result(win, title, reason, buttons)


func _return_to_sim() -> void:
	Engine.time_scale = 1.0
	get_tree().change_scene_to_file("res://scenes/sim.tscn")


func _go_menu() -> void:
	Engine.time_scale = 1.0
	GameData.moment = {}
	get_tree().change_scene_to_file("res://scenes/menu.tscn")


func _repeat() -> void:
	Engine.time_scale = 1.0
	get_tree().reload_current_scene()


func _next_training() -> void:
	Engine.time_scale = 1.0
	var group: String = moment.get("training_group", "")
	var pool: Array = Jugadas.by_group(group) if group != "" else Jugadas.all()
	if pool.size() > 1:
		pool = pool.filter(func(j): return j.id != jugada.id)
	var ut: Dictionary = moment.user_team
	var rt: Dictionary = GameData.teams[(int(ut.id) + 1 + randi() % (GameData.teams.size() - 1)) % GameData.teams.size()]
	GameData.moment = GameData.build_moment(pool[randi() % pool.size()], ut, rt, "training")
	GameData.moment["training_group"] = group
	get_tree().reload_current_scene()


func is_finished() -> bool:
	return state == State.ENDED


# ---------------------------------------------------------------- Utilidades

func dir_of(t: int) -> float:
	return 1.0 if t == HOME else -1.0


func goal_x(t: int) -> float:
	## Portería que ataca el equipo t.
	return HALF_L * dir_of(t)


func own_goal_x(t: int) -> float:
	return -HALF_L * dir_of(t)


func team_of(t: int) -> Array[Futbolista]:
	return home if t == HOME else away


func _gk_of(t: int) -> Futbolista:
	for p in team_of(t):
		if p.role == "GK":
			return p
	return null


func _field(list: Array, exclude_controlled: bool, include_controlled_always := false) -> Array:
	return list.filter(func(x): return x.role != "GK" and (include_controlled_always or not exclude_controlled or x != controlled or autoplay))


func _separate() -> void:
	for i in players.size():
		for j in range(i + 1, players.size()):
			var a := players[i]
			var b := players[j]
			if a.dive_t > 0.0 or b.dive_t > 0.0:
				continue
			var d := b.position - a.position
			d.y = 0
			var l := d.length()
			if l < 0.75 and l > 0.001:
				var push := d / l * (0.75 - l) * 0.5
				a.position -= push
				b.position += push


func _hdist(a: Vector3, b: Vector3) -> float:
	return Vector2(a.x - b.x, a.z - b.z).length()


func _closest(list: Array, pos: Vector3) -> Futbolista:
	var best: Futbolista = null
	var bd := INF
	for p in list:
		var d := _hdist(p.position, pos)
		if d < bd:
			bd = d
			best = p
	return best


func _camera_target() -> Transform3D:
	var t := Transform3D()
	match cam_mode:
		"setpiece":
			var bp := ball.position
			var goal_c := Vector3(HALF_L, 1.3, aim.x * 0.3)
			var dir := (goal_c - bp)
			dir.y = 0
			dir = dir.normalized()
			var side := Vector3(-dir.z, 0, dir.x)
			t.origin = bp - dir * 3.6 - side * 0.7 + Vector3(0, 1.9, 0)
			return t.looking_at(goal_c, Vector3.UP)
		"follow_shot":
			var bp2 := ball.position
			t.origin = Vector3(bp2.x - 7.0, 3.0, bp2.z * 0.8)
			return t.looking_at(Vector3(HALF_L, 1.0, ball.position.z * 0.5), Vector3.UP)
		"penalty_gk":
			t.origin = Vector3(-59.5, 3.2, 0)
			return t.looking_at(Vector3(-40, 0.6, 0), Vector3.UP)
		_:
			t.origin = cam_focus + Vector3(0, 11.0, 16.0)
			return t.looking_at(cam_focus + Vector3(0, 0, -1.5), Vector3.UP)


func _update_camera(dt: float) -> void:
	cam.fov = 34.0 if cam_mode == "setpiece" else 48.0
	if cam_mode == "follow_shot" and (cam_mode_t > 1.6 or ball.carrier != null or ball.kind != "shot"):
		cam_mode = "broadcast"
	var target := Vector3(clampf(ball.position.x, -42, 42), 0, clampf(ball.position.z * 0.55, -16, 16))
	cam_focus = cam_focus.lerp(target, clampf(dt * 2.5, 0.0, 1.0))
	var want := _camera_target()
	cam.global_transform = cam.global_transform.interpolate_with(want, clampf(dt * (6.0 if cam_mode == "setpiece" else 3.5), 0.0, 1.0))


func _update_hud() -> void:
	var su: int = int(moment.score_user) + (1 if result.get("goal_for", false) else 0)
	var sr: int = int(moment.score_rival) + (1 if result.get("goal_against", false) else 0)
	var u: Dictionary = moment.user_team
	var r: Dictionary = moment.rival_team
	if moment.user_is_home:
		hud.score_text = "%s  %d - %d  %s" % [u.short, su, sr, r.short]
	else:
		hud.score_text = "%s  %d - %d  %s" % [r.short, sr, su, u.short]
	hud.minute_text = moment.minute
	hud.time_left = maxf(time_left, 0.0)
	hud.time_total = time_total

extends Node3D
## Jugada clave: estadio, jugadores, IA, controles y reglas de la jugada.

const HALF_L := 52.5
const HALF_W := 34.0
const GOAL_HW := 3.66
const GOAL_H := 2.44

enum State { INTRO, PLAY, GOAL, ENDED }

var state := State.INTRO
var state_t := 0.0
var time_left := 30.0
var scenario: Dictionary
var home: Array[Futbolista] = []
var away: Array[Futbolista] = []
var players: Array[Futbolista] = []
var ball: Balon
var cam: Camera3D
var hud: Hud
var controlled: Futbolista = null
var cam_focus := Vector3.ZERO
var charging := false
var charge := 0.0
var away_hold_t := 0.0
var gk_hold_t := 0.0
var autoplay := false  # lo usa la prueba automática


func _ready() -> void:
	randomize()
	scenario = GameData.scenarios[GameData.current_scenario]
	time_left = scenario.time
	_build_environment()
	_build_pitch()
	_build_goal(1.0)
	_build_goal(-1.0)
	_build_stadium()
	_spawn_players()
	_setup_camera()
	_setup_hud()
	state = State.INTRO
	state_t = 0.0
	hud.show_message(scenario.title, 2.4)


# ---------------------------------------------------------------- Escenario

func _build_environment() -> void:
	var we := WorldEnvironment.new()
	var env := Environment.new()
	var sky := Sky.new()
	var sm := ProceduralSkyMaterial.new()
	sm.sky_top_color = Color(0.25, 0.45, 0.8)
	sm.sky_horizon_color = Color(0.7, 0.8, 0.9)
	sm.ground_horizon_color = Color(0.4, 0.45, 0.4)
	sky.sky_material = sm
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.55, 0.6, 0.7)
	env.ambient_light_energy = 0.45
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	we.environment = env
	add_child(we)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-55, -35, 0)
	sun.light_energy = 0.95
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 70.0
	add_child(sun)


func _build_pitch() -> void:
	var base := MeshUtil.box(Vector3(130, 0.1, 92), Color(0.09, 0.26, 0.1))
	base.position.y = -0.05
	add_child(base)
	var stripes := 14
	var w := 2 * HALF_L / stripes
	for i in stripes:
		var c := Color(0.12, 0.34, 0.13) if i % 2 == 0 else Color(0.15, 0.39, 0.16)
		var s := MeshUtil.box(Vector3(w, 0.02, 2 * HALF_W + 6), c)
		s.position = Vector3(-HALF_L + w * (i + 0.5), 0.0, 0)
		s.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(s)
	var lw := 0.12
	var white := Color(0.95, 0.95, 0.95)
	var y := 0.02
	_line(Vector3(0, y, HALF_W), Vector3(2 * HALF_L + lw, 0.01, lw))
	_line(Vector3(0, y, -HALF_W), Vector3(2 * HALF_L + lw, 0.01, lw))
	_line(Vector3(HALF_L, y, 0), Vector3(lw, 0.01, 2 * HALF_W))
	_line(Vector3(-HALF_L, y, 0), Vector3(lw, 0.01, 2 * HALF_W))
	_line(Vector3(0, y, 0), Vector3(lw, 0.01, 2 * HALF_W))
	_add_ring(Vector3(0, y, 0), 9.15 - lw / 2, 9.15 + lw / 2, 0, TAU, white)
	_add_ring(Vector3(0, y, 0), 0, 0.2, 0, TAU, white)
	for side in [1.0, -1.0]:
		var gx: float = HALF_L * side
		# Área grande
		_line(Vector3(gx - 16.5 * side, y, 0), Vector3(lw, 0.01, 40.32))
		_line(Vector3(gx - 8.25 * side, y, 20.16), Vector3(16.5, 0.01, lw))
		_line(Vector3(gx - 8.25 * side, y, -20.16), Vector3(16.5, 0.01, lw))
		# Área chica
		_line(Vector3(gx - 5.5 * side, y, 0), Vector3(lw, 0.01, 18.32))
		_line(Vector3(gx - 2.75 * side, y, 9.16), Vector3(5.5, 0.01, lw))
		_line(Vector3(gx - 2.75 * side, y, -9.16), Vector3(5.5, 0.01, lw))
		# Punto penal y medialuna
		var spot := Vector3(gx - 11.0 * side, y, 0)
		_add_ring(spot, 0, 0.2, 0, TAU, white)
		var a := acos(5.5 / 9.15)
		if side > 0:
			_add_ring(spot, 9.15 - lw / 2, 9.15 + lw / 2, PI - a, PI + a, white)
		else:
			_add_ring(spot, 9.15 - lw / 2, 9.15 + lw / 2, -a, a, white)


func _line(pos: Vector3, size: Vector3) -> void:
	var m := MeshUtil.box(size, Color(0.95, 0.95, 0.95), true)
	m.position = pos
	m.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(m)


func _add_ring(pos: Vector3, r0: float, r1: float, a0: float, a1: float, c: Color) -> void:
	var r := MeshUtil.ring(r0, r1, a0, a1, 48, c)
	r.position = pos
	add_child(r)


func _build_goal(side: float) -> void:
	var gx := HALF_L * side
	var white := Color(0.97, 0.97, 0.97)
	for pz in [GOAL_HW, -GOAL_HW]:
		var post := MeshUtil.cylinder(0.06, GOAL_H, white)
		post.position = Vector3(gx, GOAL_H / 2, pz)
		add_child(post)
	var bar := MeshUtil.cylinder(0.06, GOAL_HW * 2, white)
	bar.rotation_degrees.x = 90
	bar.position = Vector3(gx, GOAL_H, 0)
	add_child(bar)
	var net_c := Color(1, 1, 1, 0.22)
	var depth := 2.0
	var back := MeshUtil.box(Vector3(0.02, GOAL_H, GOAL_HW * 2), net_c)
	back.position = Vector3(gx + depth * side, GOAL_H / 2, 0)
	add_child(back)
	var top := MeshUtil.box(Vector3(depth, 0.02, GOAL_HW * 2), net_c)
	top.position = Vector3(gx + depth / 2 * side, GOAL_H, 0)
	add_child(top)
	for pz in [GOAL_HW, -GOAL_HW]:
		var sidenet := MeshUtil.box(Vector3(depth, GOAL_H, 0.02), net_c)
		sidenet.position = Vector3(gx + depth / 2 * side, GOAL_H / 2, pz)
		add_child(sidenet)
	for i in range(1, 8):
		var vline := MeshUtil.box(Vector3(0.03, GOAL_H, 0.03), Color(1, 1, 1, 0.5))
		vline.position = Vector3(gx + depth * side, GOAL_H / 2, -GOAL_HW + i * GOAL_HW * 2 / 8)
		add_child(vline)


func _build_stadium() -> void:
	# Público: imagen con "personas" de colores sobre fondo oscuro.
	var img := Image.create(128, 64, false, Image.FORMAT_RGB8)
	var palette := [Color(0.75, 0.1, 0.12), Color(0.85, 0.85, 0.85), Color(0.15, 0.25, 0.7), Color(0.9, 0.75, 0.2), Color(0.3, 0.3, 0.35), Color(0.6, 0.45, 0.35)]
	for y in 64:
		for x in 128:
			var c: Color = Color(0.07, 0.07, 0.09)
			if y % 4 != 3 and randf() < 0.8:
				c = palette[randi() % palette.size()].darkened(randf() * 0.4)
			img.set_pixel(x, y, c)
	var tex := ImageTexture.create_from_image(img)
	var crowd := StandardMaterial3D.new()
	crowd.albedo_texture = tex
	crowd.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	crowd.uv1_scale = Vector3(6, 2, 1)
	crowd.roughness = 1.0
	# Gradas inclinadas en los cuatro lados.
	var specs := [
		[Vector3(0, 7, -HALF_W - 16), Vector3(140, 0.5, 26), Vector3(30, 0, 0)],
		[Vector3(0, 7, HALF_W + 16), Vector3(140, 0.5, 26), Vector3(-30, 0, 0)],
		[Vector3(HALF_L + 18, 7, 0), Vector3(26, 0.5, 100), Vector3(0, 0, 30)],
		[Vector3(-HALF_L - 18, 7, 0), Vector3(26, 0.5, 100), Vector3(0, 0, -30)],
	]
	for sp in specs:
		var mi := MeshInstance3D.new()
		var bm := BoxMesh.new()
		bm.size = sp[1]
		bm.material = crowd
		mi.mesh = bm
		mi.position = sp[0]
		mi.rotation_degrees = sp[2]
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(mi)
	# Vallas publicitarias
	var texts := ["HALCONES FC", "RAINROAD", "FÚTBOL MÁNAGER", "TORMENTA"]
	for side in [1.0, -1.0]:
		var board := MeshUtil.box(Vector3(2 * HALF_L + 10, 1.0, 0.15), Color(0.08, 0.12, 0.3))
		board.position = Vector3(0, 0.5, (HALF_W + 4) * side)
		add_child(board)
		for i in 6:
			var l := Label3D.new()
			l.text = texts[i % texts.size()]
			l.font_size = 90
			l.pixel_size = 0.01
			l.modulate = Color(1, 0.85, 0.2) if i % 2 == 0 else Color.WHITE
			l.position = Vector3(-50 + i * 20, 0.5, (HALF_W + 4) * side - 0.1 * side)
			if side > 0:
				l.rotation_degrees.y = 180
			add_child(l)


# ---------------------------------------------------------------- Jugadores

func _spawn_players() -> void:
	for d in scenario.home:
		var p := _make_player(GameData.home_players[d.idx], Futbolista.HOME, GameData.home_team.kit, d.pos)
		p.lane_z = d.get("lane", d.pos.z)
		home.append(p)
	for d in scenario.away:
		var p := _make_player(GameData.away_players[d.idx], Futbolista.AWAY, GameData.away_team.kit, d.pos)
		away.append(p)
	ball = Balon.new()
	add_child(ball)
	var starter: Futbolista = home[0]
	for i in scenario.home.size():
		if scenario.home[i].get("ball", false):
			starter = home[i]
	ball.position = starter.position + starter.facing * 0.55 + Vector3(0, Balon.R, 0)
	_give_ball(starter)


func _make_player(data: Dictionary, team: int, kit: Dictionary, pos: Vector3) -> Futbolista:
	var p := Futbolista.new()
	add_child(p)
	p.setup(data, team, kit)
	p.position = pos
	players.append(p)
	return p


func _setup_camera() -> void:
	cam = Camera3D.new()
	cam.fov = 48
	cam.far = 400
	add_child(cam)
	cam.current = true
	cam_focus = Vector3(ball.position.x, 0, ball.position.z * 0.5)
	_update_camera(1.0)


func _setup_hud() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	hud = Hud.new()
	layer.add_child(hud)
	hud.retry_pressed.connect(func(): get_tree().reload_current_scene())
	hud.next_pressed.connect(_next_scenario)
	hud.menu_pressed.connect(_go_menu)
	hud.time_total = scenario.time
	_update_hud()


func _go_menu() -> void:
	Engine.time_scale = 1.0
	get_tree().change_scene_to_file("res://scenes/menu.tscn")


func _next_scenario() -> void:
	Engine.time_scale = 1.0
	var order: Array = GameData.scenario_order
	var i := order.find(GameData.current_scenario)
	GameData.current_scenario = order[(i + 1) % order.size()]
	get_tree().reload_current_scene()


# ---------------------------------------------------------------- Bucle

func _process(delta: float) -> void:
	var real_dt := delta / maxf(Engine.time_scale, 0.01)
	state_t += real_dt
	match state:
		State.INTRO:
			if state_t > 0.6:
				var n := 3 - int((state_t - 0.6) / 0.6)
				if n > 0:
					hud.show_message(str(n), 0.5, true)
			if state_t > 2.4:
				state = State.PLAY
				state_t = 0.0
				hud.show_message("¡YA!", 0.6, true)
			_animate_idle(delta)
		State.PLAY:
			_play_step(delta)
		State.GOAL:
			_free_step(delta)
			if state_t > 2.2:
				Engine.time_scale = 1.0
				_finish(true, "¡GOLAZO!", _goal_reason())
		State.ENDED:
			_free_step(delta)
	_update_camera(delta)
	_update_hud()
	hud.end_frame()


func simulate(dt: float) -> void:
	## Paso manual usado por la prueba automática.
	_process(dt)


func _animate_idle(dt: float) -> void:
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
	_update_control_target()
	_handle_input(dt)
	for p in players:
		if p == controlled and not autoplay:
			continue
		if p.role == "GK":
			_ai_goalkeeper(p, dt)
		elif p.team == Futbolista.HOME:
			_ai_home(p, dt)
		else:
			_ai_away(p, dt)
	for p in players:
		p.step(dt, p == ball.carrier)
	_separate()
	var ev := ball.step(dt)
	_check_possession()
	_check_tackles()
	_check_gk_save()
	_check_end(ev, dt)


# ---------------------------------------------------------------- Control del usuario

func _attacking() -> bool:
	if ball.carrier != null:
		return ball.carrier.team == Futbolista.HOME
	return ball.last_touch == null or ball.last_touch.team == Futbolista.HOME


func _set_controlled(p: Futbolista) -> void:
	if controlled == p:
		return
	if controlled:
		controlled.set_controlled(false)
	controlled = p
	if p:
		p.set_controlled(true)
	charging = false
	hud.shot_power = -1.0


func _update_control_target() -> void:
	if ball.carrier and ball.carrier.team == Futbolista.HOME:
		_set_controlled(ball.carrier)
	elif ball.carrier == null and ball.pass_target and ball.pass_target.team == Futbolista.HOME:
		_set_controlled(ball.pass_target)
	elif controlled == null or (ball.carrier == null and ball.kind != "pass" and ball.kind != "through"):
		var c := _closest(home, ball.position)
		if c and (controlled == null or c.position.distance_to(ball.position) + 3.0 < controlled.position.distance_to(ball.position)):
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


var _keys_prev := {}


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
	if autoplay:
		return
	if controlled == null:
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
	hud.attack_mode = attack

	# Movimiento: si viene un pase hacia mí y no toco el joystick, corro solo a recibir.
	if ball.carrier == null and ball.pass_target == p and inp.length() < 0.2:
		_run_to(p, ball.position + Vector3(ball.vel.x, 0, ball.vel.z) * 0.35, true)
	elif not attack and c_down and ball.carrier:
		_run_to(p, ball.carrier.position, true)
	else:
		p.move_input = inp

	if attack:
		if ball.carrier == p:
			if a_press:
				charging = true
				charge = 0.0
			if charging:
				charge = minf(charge + dt / 0.9, 1.15)
				hud.shot_power = minf(charge, 1.0)
				if a_rel or not a_down:
					_shoot(p, minf(charge, 1.0), inp)
					charging = false
					hud.shot_power = -1.0
			elif b_press:
				_pass(p, false, inp)
			elif c_press:
				_pass(p, true, inp)
		else:
			charging = false
			hud.shot_power = -1.0
			var near := ball.carrier == null and _hdist(p.position, ball.position) < 1.4 and ball.position.y < 1.6
			if near and a_press:
				_shoot(p, 0.75, inp)  # remate de primera
			elif near and b_press:
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
			var others := home.filter(func(x): return x != p)
			var c := _closest(others, ball.position)
			if c:
				_set_controlled(c)


# ---------------------------------------------------------------- Acciones

func _give_ball(p: Futbolista) -> void:
	ball.carrier = p
	ball.last_touch = p
	ball.kind = ""
	ball.pass_target = null
	ball.rolled.clear()
	p.hold_t = 0.0


func _kick(p: Futbolista, v: Vector3, kind: String) -> void:
	ball.carrier = null
	ball.vel = v
	ball.last_touch = p
	ball.last_kicker = p
	ball.kicker_ban = 0.35
	ball.kind = kind
	ball.pass_target = null
	ball.rolled.clear()
	ball.shot_time = 0.0
	p.kick_anim = 0.3
	var d := Vector3(v.x, 0, v.z)
	if d.length() > 0.1:
		p.facing = d.normalized()


func _pass(p: Futbolista, through: bool, inp: Vector3) -> void:
	var mates := (home if p.team == Futbolista.HOME else away).filter(func(x): return x != p and x.role != "GK")
	var dir := inp.normalized() if inp.length() > 0.2 else p.facing
	var best: Futbolista = null
	var best_score := -INF
	for m in mates:
		var to: Vector3 = m.position - p.position
		var dist := to.length()
		if dist < 2.0:
			continue
		var score := dir.dot(to / dist) * 2.0 - dist / 35.0
		if score > best_score:
			best_score = score
			best = m
	var target: Vector3
	if best == null:
		target = p.position + dir * 15.0
	else:
		target = best.position
		var dist := p.position.distance_to(best.position)
		if through:
			var run := best.velocity.normalized() if best.velocity.length() > 1.0 else Vector3(1 if p.team == Futbolista.HOME else -1, 0, 0)
			target += run * clampf(dist * 0.4, 4.0, 12.0)
		else:
			target += best.velocity * (dist / 18.0)
	target.x = clampf(target.x, -HALF_L + 1, HALF_L - 1)
	target.z = clampf(target.z, -HALF_W + 1, HALF_W - 1)
	var flat := target - ball.position
	flat.y = 0
	var dist2 := flat.length()
	var v_end := 3.5 if through else 5.5
	var spd := sqrt(v_end * v_end + 2.0 * Balon.ROLL_DECEL * 1.25 * dist2)
	var err := randf_range(-1.0, 1.0) * (1.0 - p.pas / 100.0) * 0.14
	var d := flat.normalized().rotated(Vector3.UP, err)
	_kick(p, d * spd + Vector3(0, 0.6, 0), "through" if through else "pass")
	ball.pass_target = best


func _shoot(p: Futbolista, power: float, inp: Vector3) -> void:
	var goal_x := HALF_L if p.team == Futbolista.HOME else -HALF_L
	var aim_z: float
	if absf(inp.z) > 0.25:
		aim_z = signf(inp.z) * lerpf(1.2, 3.1, absf(inp.z))
	else:
		aim_z = -signf(p.position.z) * 1.6 if absf(p.position.z) > 1.0 else randf_range(-1.5, 1.5)
	var target := Vector3(goal_x, lerpf(0.35, 2.0, power * power), aim_z)
	var dist := Vector2(goal_x - ball.position.x, aim_z - ball.position.z).length()
	var sd := (1.05 - p.sho / 100.0) * 1.3 + dist / 45.0
	target.z += randfn(0.0, sd * 0.8)
	target.y += randfn(0.0, sd * 0.4) + maxf(0.0, power - 0.85) * 4.5
	target.y = maxf(target.y, 0.15)
	var speed_h := lerpf(13.0, 31.0, power) * (0.85 + p.sho / 700.0)
	var flat := target - ball.position
	flat.y = 0
	var t := flat.length() / speed_h
	var vy := (target.y - ball.position.y + 0.5 * Balon.GRAVITY * t * t) / maxf(t, 0.05)
	_kick(p, flat.normalized() * speed_h + Vector3(0, vy, 0), "shot")
	hud.show_message("¡Disparo!" if power < 0.85 else "¡Cañonazo!", 0.8)


func _clear(p: Futbolista) -> void:
	var target := Vector3(-45, 0, randf_range(-28, 28))
	var flat := target - p.position
	flat.y = 0
	_kick(p, flat.normalized() * 24.0 + Vector3(0, 9.0, 0), "clear")


# ---------------------------------------------------------------- IA

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


func _ai_home(p: Futbolista, dt: float) -> void:
	var c := ball.carrier
	if c == p:
		_ai_carrier_home(p, dt)
		return
	if ball.carrier == null and ball.pass_target == p:
		_run_to(p, ball.position + Vector3(ball.vel.x, 0, ball.vel.z) * 0.35, true)
		return
	if ball.carrier == null:
		var closest := _closest(home.filter(func(x): return x != controlled or autoplay), ball.position)
		if closest == p and _hdist(p.position, ball.position) < 15.0:
			_run_to(p, ball.position + Vector3(ball.vel.x, 0, ball.vel.z) * 0.3, true)
			return
	if c and c.team == Futbolista.AWAY:
		var closest2 := _closest(home.filter(func(x): return x != controlled or autoplay), c.position)
		if closest2 == p:
			_run_to(p, c.position, true)
			return
	# Desmarque: correr al espacio por su carril.
	var ref_x := ball.position.x
	var lane := p.lane_z * (0.55 if ref_x > 30 else 1.0)
	var tx := minf(ref_x + p.run_ahead, 44.0)
	if ref_x > 30:
		tx = clampf(ref_x + 6.0, 38.0, 46.0)
	_run_to(p, Vector3(tx, 0, lane), absf(tx - p.position.x) > 4.0)


func _ai_carrier_home(p: Futbolista, dt: float) -> void:
	## Solo se usa en la prueba automática: conduce, esquiva, pasa y dispara.
	p.hold_t += dt
	var goal := Vector3(HALF_L, 0, 0)
	var dist := p.position.distance_to(goal)
	if dist < 20.0 and p.hold_t > 0.3:
		_shoot(p, randf_range(0.55, 0.85), Vector3(0, 0, randf_range(-1, 1)))
		return
	var pressure := _closest(away.filter(func(x): return x.role != "GK"), p.position)
	var pd := pressure.position.distance_to(p.position) if pressure else 99.0
	if pd < 2.5 and p.hold_t > 0.5:
		for m in home:
			if m != p and m.position.x > p.position.x + 3.0 and randf() < 0.6:
				_pass(p, randf() < 0.5, (m.position - p.position).normalized())
				return
	var dir := (goal + Vector3(-6, 0, 0) - p.position).normalized()
	if pressure and pd < 5.0:
		var away_v := p.position - pressure.position
		away_v.y = 0
		dir = (dir + away_v.normalized() * 0.8).normalized()
	_run_to(p, p.position + dir * 5.0, true)


func _ai_away(p: Futbolista, dt: float) -> void:
	var own_goal := Vector3(HALF_L, 0, 0)
	var c := ball.carrier
	if c == p:
		p.hold_t += dt
		_run_to(p, p.position + Vector3(-5, 0, signf(p.position.z) * 2.0), false)
		if p.hold_t > 0.45 + randf() * 0.3:
			_clear(p)
		return
	var field := away.filter(func(x): return x.role != "GK")
	if c == null:
		var closest := _closest(field, ball.position)
		if closest == p:
			_run_to(p, ball.position + Vector3(ball.vel.x, 0, ball.vel.z) * 0.3, true)
			return
	if c and c.team == Futbolista.AWAY:
		_run_to(p, p.position + Vector3(-3, 0, 0))
		return
	var focus := c.position if c else ball.position
	var presser := _closest(field, focus)
	if p == presser:
		var goal_side := (own_goal - focus).normalized()
		_run_to(p, focus + goal_side * 0.7, true)
		return
	# Marcaje: asignar defensores a los atacantes más peligrosos.
	var attackers := home.filter(func(x): return x != c)
	attackers.sort_custom(func(a, b): return a.position.distance_to(own_goal) < b.position.distance_to(own_goal))
	var free_defs := field.filter(func(x): return x != presser)
	var assignment := {}
	for atk in attackers:
		var best: Futbolista = null
		var bd := INF
		for d in free_defs:
			if assignment.has(d):
				continue
			var dd: float = d.position.distance_to(atk.position)
			if dd < bd:
				bd = dd
				best = d
		if best:
			assignment[best] = atk
	if assignment.has(p):
		var atk2: Futbolista = assignment[p]
		var tgt := atk2.position + (own_goal - atk2.position).normalized() * 2.2
		tgt.x = minf(tgt.x, HALF_L - 2.0)
		_run_to(p, tgt, p.position.distance_to(tgt) > 3.0)
	else:
		var cover := focus.lerp(own_goal, 0.55)
		_run_to(p, cover, true)


func _ai_goalkeeper(p: Futbolista, dt: float) -> void:
	var gx := HALF_L if p.team == Futbolista.AWAY else -HALF_L
	var side := signf(gx)
	if ball.carrier == p:
		p.move_input = Vector3.ZERO
		return
	# Estirada ante un disparo
	if p.dive_t > 0.0:
		var to := p.dive_target - p.position
		to.y = 0
		var dive_speed := 5.5 + p.gkp / 100.0 * 2.5
		p.velocity = to.normalized() * dive_speed if to.length() > 0.15 else p.velocity * 0.85
		return
	var shot_incoming := ball.carrier == null and ball.kind == "shot" and ball.vel.x * side > 3.0
	var react := 0.1 + (100.0 - p.gkp) / 100.0 * 0.25
	if shot_incoming and ball.shot_time > react and p.stun <= 0.0:
		var t := (gx - ball.position.x) / ball.vel.x
		if t > 0.0 and t < 2.5:
			var zc := ball.position.z + ball.vel.z * t
			if absf(zc) < GOAL_HW + 1.2:
				var tz := clampf(zc, -GOAL_HW, GOAL_HW)
				if absf(tz - p.position.z) > 0.6:
					p.dive_t = 0.7
					p.dive_side = signf(tz - p.position.z)
					p.dive_target = Vector3(p.position.x, 0, tz)
					return
				_run_to(p, Vector3(p.position.x, 0, tz), true)
				return
	# Salir a por un balón suelto cerca del área chica
	if ball.carrier == null and ball.kind != "shot":
		var bd := _hdist(ball.position, Vector3(gx, 0, 0))
		if bd < 9.0 and ball.vel.length() < 12.0 and absf(ball.position.z) < 12:
			_run_to(p, ball.position, true)
			return
	# Colocación: en la línea entre el balón y el centro de la portería
	var goal_c := Vector3(gx, 0, 0)
	var to_ball := ball.position - goal_c
	to_ball.y = 0
	var dist := to_ball.length()
	var adv := clampf(dist * 0.12, 0.8, 5.0)
	var tgt := goal_c + to_ball.normalized() * adv
	tgt.z = clampf(tgt.z, -GOAL_HW + 0.3, GOAL_HW - 0.3)
	tgt.x = gx - side * maxf(absf(tgt.x - gx), 0.5)
	_run_to(p, tgt, false)


# ---------------------------------------------------------------- Reglas

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
			reach = 1.1
			max_h = 2.4
		var d := _hdist(p.position, ball.position)
		if d < reach and ball.position.y < max_h and d < bd:
			if ball.rolled.has(p):
				continue
			var sp := ball.speed()
			var chance := 1.0
			var same_team := ball.last_touch != null and ball.last_touch.team == p.team
			if p.role == "GK":
				chance = 1.0 if sp < 14.0 else 0.0  # los disparos fuertes se resuelven como atajada
			elif same_team:
				chance = clampf(1.5 - sp / 28.0, 0.55, 1.0)
			else:
				chance = clampf(1.25 - sp / 24.0, 0.15, 1.0)
			ball.rolled[p] = true
			if randf() < chance:
				best = p
				bd = d
	if best:
		_give_ball(best)
		if best.team == Futbolista.AWAY and best.role != "GK":
			hud.show_message("¡Intercepción!", 1.0)


func _check_tackles() -> void:
	var c := ball.carrier
	# Barrida del jugador controlado
	if controlled and controlled.slide_t > 0.0 and not controlled.slide_resolved:
		if c and c.team == Futbolista.AWAY and _hdist(controlled.position + controlled.slide_dir * 0.6, c.position) < 1.2:
			controlled.slide_resolved = true
			if randf() < 0.55 + controlled.dfn / 300.0:
				c.stun = 0.8
				_give_ball(controlled)
				ball.carrier = null
				ball.vel = controlled.slide_dir * 7.0
				ball.last_touch = controlled
				ball.kind = "loose"
				hud.show_message("¡Barrida limpia!", 1.0)
			else:
				hud.show_message("Barrida fallida", 0.8)
		elif c == null and _hdist(controlled.position + controlled.slide_dir * 0.6, ball.position) < 1.1 and ball.position.y < 0.6:
			controlled.slide_resolved = true
			ball.vel = controlled.slide_dir * 8.0 + Vector3(0, 0.5, 0)
			ball.last_touch = controlled
			ball.kind = "loose"
			ball.pass_target = null
	if c == null:
		return
	for t in players:
		if t.team == c.team or t.role == "GK" or t.stun > 0.0 or t.slide_t > 0.0:
			continue
		if t.tackle_cd > 0.0:
			continue
		if _hdist(t.position, c.position) < 1.1:
			t.tackle_cd = 1.0
			var chance := 0.22 + (t.dfn - c.spd) * 0.004
			if c.sprinting:
				chance += 0.08
			if c.is_controlled:
				chance -= 0.05
			if randf() < chance:
				c.stun = 0.7
				_give_ball(t)
				hud.show_message("¡Te robaron el balón!" if t.team == Futbolista.AWAY else "¡Recuperado!", 1.0)
				return


func _check_gk_save() -> void:
	if ball.carrier != null or ball.kind != "shot" or ball.scored:
		return
	for gk in players:
		if gk.role != "GK":
			continue
		if gk == ball.last_kicker:
			continue
		var reach_h := 2.35 if gk.dive_t > 0.0 else 2.2
		if ball.position.y > reach_h + 0.3:
			continue
		var hand := gk.position + Vector3(0, clampf(ball.position.y, 0.2, reach_h), 0)
		var radius := 0.32 + gk.gkp / 100.0 * 0.35 + (0.3 if gk.dive_t > 0.0 else 0.0)
		if hand.distance_to(ball.position) < radius:
			var sp := ball.speed()
			if sp < 19.0 and randf() < 0.75:
				_give_ball(gk)
				hud.show_message("¡Atajada del portero!", 1.2)
			else:
				var away_dir := Vector3(-signf(ball.vel.x), 0, signf(ball.position.z - gk.position.z + 0.01))
				ball.vel = Vector3(away_dir.x * sp * 0.25, 3.5, away_dir.z * sp * 0.35)
				ball.kind = "loose"
				ball.last_touch = gk
				ball.last_kicker = gk
				ball.kicker_ban = 0.5
				ball.rolled.clear()
				hud.show_message("¡Qué paradón!", 1.2)
			return


func _check_end(ev: String, _dt: float) -> void:
	if ev == "post":
		hud.show_message("¡Al palo!", 1.0)
	if ev == "goal_home":
		state = State.GOAL
		state_t = 0.0
		Engine.time_scale = 0.35
		hud.release_all()
		hud.controls_enabled = false
		hud.show_message("¡GOOOOL!", 2.2, true)
		GameData.stats.goals += 1
		return
	if ev == "goal_away":
		_finish(false, "Autogol...", "El balón terminó en tu propia portería.")
		return
	if ev == "out":
		if ball.last_touch and ball.last_touch.team == Futbolista.AWAY and ball.position.x > HALF_L - 1:
			_finish(false, "Córner", "Un defensor la mandó a córner. ¡Casi! La jugada termina aquí.")
		else:
			_finish(false, "Fuera", "El balón salió del campo.")
		return
	var c := ball.carrier
	if c and c.role == "GK" and c.team == Futbolista.AWAY:
		gk_hold_t += _dt
		if gk_hold_t > 0.8:
			_finish(false, "¡Atajada!", "El portero se quedó con el balón.")
			return
	else:
		gk_hold_t = 0.0
	if ball.carrier == null and ball.kind == "clear" and ball.position.x < -10.0:
		_finish(false, "Despejada", "La defensa despejó el balón lejos del área.")
		return
	if c and c.team == Futbolista.AWAY and c.role != "GK":
		away_hold_t += _dt
		if away_hold_t > 3.0:
			_finish(false, "Balón perdido", "El rival se quedó con la pelota.")
			return
	else:
		away_hold_t = 0.0
	if time_left <= 0.0:
		_finish(false, "Se acabó el tiempo", "No lograste definir la jugada a tiempo.")


func _finish(win: bool, title: String, reason: String) -> void:
	if state == State.ENDED:
		return
	state = State.ENDED
	state_t = 0.0
	Engine.time_scale = 1.0
	GameData.stats.played += 1
	if controlled:
		controlled.set_controlled(false)
	hud.shot_power = -1.0
	hud.show_result(win, title, reason)


func _goal_reason() -> String:
	var sc: Array = scenario.score
	var scorer := ball.last_touch.pname if ball.last_touch else ""
	return "Gol de %s. %s %d - %d %s" % [scorer, GameData.home_team.short, sc[0] + 1, sc[1], GameData.away_team.short]


func is_finished() -> bool:
	return state == State.ENDED


func won() -> bool:
	return ball.scored


# ---------------------------------------------------------------- Utilidades

func _separate() -> void:
	for i in players.size():
		for j in range(i + 1, players.size()):
			var a := players[i]
			var b := players[j]
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


func _update_camera(dt: float) -> void:
	var target := Vector3(clampf(ball.position.x, -42, 42), 0, clampf(ball.position.z * 0.55, -16, 16))
	cam_focus = cam_focus.lerp(target, clampf(dt * 2.5, 0.0, 1.0))
	cam.position = cam_focus + Vector3(0, 11.0, 16.0)
	cam.look_at(cam_focus + Vector3(0, 0, -1.5))


func _update_hud() -> void:
	var sc: Array = scenario.score
	var h: int = sc[0] + (1 if ball and ball.scored else 0)
	hud.score_text = "%s  %d - %d  %s" % [GameData.home_team.short, h, sc[1], GameData.away_team.short]
	var elapsed: float = scenario.time - maxf(time_left, 0.0)
	hud.minute_text = "%d'" % (int(scenario.minute) + int(elapsed / 20.0))
	hud.time_left = maxf(time_left, 0.0)

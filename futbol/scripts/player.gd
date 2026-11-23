class_name Futbolista
extends Node3D
## Un futbolista: modelo low-poly articulado (cadera, rodilla, hombro, codo) con
## animación procedural de carrera, tiro, barrida, cabezazo y estirada del portero.
## El movimiento tiene inercia (acelera y gira de forma progresiva) para que el
## juego se sienta más pausado y realista.

const HOME := 0
const AWAY := 1

var team := HOME
var role := "MID"  # GK, DEF, MID, FWD
var pname := ""
var number := 0
var spd := 70.0
var pas := 70.0
var sho := 70.0
var dfn := 60.0
var gkp := 50.0
var tl := 50.0
var data_id := -1
var slot := Vector2(0.5, 0.5)   # posición en la formación (x: ancho, y: profundidad)
var key_player := false         # forma parte de la jugada (los demás mantienen la forma del equipo)

var velocity := Vector3.ZERO
var move_input := Vector3.ZERO
var sprinting := false
var facing := Vector3.RIGHT
var stun := 0.0
var slide_t := 0.0
var slide_dir := Vector3.ZERO
var slide_resolved := false
var kick_anim := 0.0
var tackle_cd := 0.0
var dive_t := 0.0
var dive_target := Vector3.ZERO
var dive_side := 0.0
var dive_high := 0.0
var head_anim := 0.0
var celebrate := 0.0
var lane_z := 0.0
var run_ahead := 10.0
var hold_t := 0.0
var is_controlled := false

var _body: Node3D
var _torso: Node3D
var _leg_l: Node3D
var _leg_r: Node3D
var _shin_l: Node3D
var _shin_r: Node3D
var _arm_l: Node3D
var _arm_r: Node3D
var _fore_l: Node3D
var _fore_r: Node3D
var _ring: MeshInstance3D
var _target_ring: MeshInstance3D
var _name_lbl: Label3D
var _phase := 0.0
var _show_name := true
var _lean := 0.0


func setup(data: Dictionary, team_id: int, kit: Dictionary) -> void:
	team = team_id
	pname = data.name
	number = int(data.number)
	role = data.pos
	spd = data.spd
	pas = data.pas
	sho = data.sho
	dfn = data.dfn
	gkp = data.gkp
	tl = data.get("tl", 50.0)
	data_id = int(data.get("id", -1))
	slot = Vector2(data.get("sx", 0.5), data.get("sy", 0.5))
	facing = Vector3.RIGHT if team == HOME else Vector3.LEFT
	run_ahead = randf_range(7.0, 13.0)
	_phase = randf() * TAU
	_build(kit)


func _build(kit: Dictionary) -> void:
	var skins := [Color(0.96, 0.80, 0.66), Color(0.80, 0.60, 0.45), Color(0.58, 0.40, 0.27), Color(0.38, 0.25, 0.17)]
	var hairs := [Color(0.08, 0.06, 0.05), Color(0.35, 0.2, 0.1), Color(0.75, 0.6, 0.3), Color(0.15, 0.1, 0.08)]
	var h := absi(hash(pname))
	var skin: Color = skins[h % 4]
	var hair: Color = hairs[(h / 4) % 4]
	var shirt: Color = kit.shirt
	var shorts: Color = kit.shorts
	var socks: Color = kit.socks
	if role == "GK":
		shirt = kit.gk
		shorts = kit.gk.darkened(0.5)
		socks = kit.gk

	_body = Node3D.new()
	add_child(_body)
	var legs := _make_leg(-0.1, skin, socks)
	_leg_l = legs[0]
	_shin_l = legs[1]
	legs = _make_leg(0.1, skin, socks)
	_leg_r = legs[0]
	_shin_r = legs[1]

	_torso = Node3D.new()
	_torso.position = Vector3(0, 0.95, 0)
	_body.add_child(_torso)
	var hips := MeshUtil.box(Vector3(0.36, 0.22, 0.22), shorts)
	hips.position = Vector3(0, 0.02, 0)
	_torso.add_child(hips)
	var chest := MeshUtil.box(Vector3(0.42, 0.52, 0.24), shirt)
	chest.position = Vector3(0, 0.38, 0)
	_torso.add_child(chest)
	var shoulders := MeshUtil.box(Vector3(0.5, 0.12, 0.25), shirt)
	shoulders.position = Vector3(0, 0.6, 0)
	_torso.add_child(shoulders)
	var neck := MeshUtil.box(Vector3(0.1, 0.1, 0.1), skin)
	neck.position = Vector3(0, 0.7, 0)
	_torso.add_child(neck)
	var head := MeshUtil.sphere(0.12, skin)
	head.position = Vector3(0, 0.83, 0.01)
	head.scale = Vector3(0.92, 1.12, 1.0)
	_torso.add_child(head)
	var hair_m := MeshUtil.sphere(0.125, hair)
	hair_m.position = Vector3(0, 0.88, -0.015)
	hair_m.scale = Vector3(1.0, 0.72, 1.02)
	_torso.add_child(hair_m)

	var arms := _make_arm(-0.29, skin, shirt)
	_arm_l = arms[0]
	_fore_l = arms[1]
	arms = _make_arm(0.29, skin, shirt)
	_arm_r = arms[0]
	_fore_r = arms[1]

	var num := Label3D.new()
	num.text = str(number)
	num.font_size = 96
	num.pixel_size = 0.0026
	num.outline_size = 12
	num.modulate = kit.number
	num.outline_modulate = Color(0, 0, 0, 0.6)
	num.position = Vector3(0, 0.42, -0.125)
	num.rotation_degrees.y = 180
	_torso.add_child(num)
	var num_f := Label3D.new()
	num_f.text = str(number)
	num_f.font_size = 48
	num_f.pixel_size = 0.0026
	num_f.modulate = kit.number
	num_f.position = Vector3(0.1, 0.5, 0.125)
	_torso.add_child(num_f)

	_ring = MeshUtil.ring(0.5, 0.66, 0, TAU, 32, Color(1.0, 0.92, 0.15))
	_ring.position.y = 0.03
	_ring.visible = false
	add_child(_ring)
	_target_ring = MeshUtil.ring(0.45, 0.56, 0, TAU, 32, Color(0.3, 0.75, 1.0))
	_target_ring.position.y = 0.025
	_target_ring.visible = false
	add_child(_target_ring)

	_name_lbl = Label3D.new()
	_name_lbl.text = "%d %s" % [number, pname]
	_name_lbl.font_size = 40
	_name_lbl.pixel_size = 0.006
	_name_lbl.outline_size = 10
	_name_lbl.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	_name_lbl.no_depth_test = true
	_name_lbl.position = Vector3(0, 2.35, 0)
	_name_lbl.visible = false
	add_child(_name_lbl)


func _make_leg(x: float, skin: Color, socks: Color) -> Array:
	var hip := Node3D.new()
	hip.position = Vector3(x, 0.95, 0)
	_body.add_child(hip)
	var thigh := MeshUtil.box(Vector3(0.15, 0.46, 0.16), skin)
	thigh.position = Vector3(0, -0.23, 0)
	hip.add_child(thigh)
	var knee := Node3D.new()
	knee.position = Vector3(0, -0.46, 0)
	hip.add_child(knee)
	var shin := MeshUtil.box(Vector3(0.12, 0.42, 0.13), socks)
	shin.position = Vector3(0, -0.2, 0)
	knee.add_child(shin)
	var boot := MeshUtil.box(Vector3(0.12, 0.08, 0.26), Color(0.08, 0.08, 0.08))
	boot.position = Vector3(0, -0.45, 0.05)
	knee.add_child(boot)
	return [hip, knee]


func _make_arm(x: float, skin: Color, shirt: Color) -> Array:
	var shoulder := Node3D.new()
	shoulder.position = Vector3(x, 0.6, 0)
	_torso.add_child(shoulder)
	var sleeve := MeshUtil.box(Vector3(0.12, 0.28, 0.12), shirt)
	sleeve.position = Vector3(0, -0.13, 0)
	shoulder.add_child(sleeve)
	var elbow := Node3D.new()
	elbow.position = Vector3(0, -0.28, 0)
	shoulder.add_child(elbow)
	var fore := MeshUtil.box(Vector3(0.09, 0.27, 0.09), skin)
	fore.position = Vector3(0, -0.13, 0)
	elbow.add_child(fore)
	return [shoulder, elbow]


func set_controlled(v: bool) -> void:
	is_controlled = v
	_ring.visible = v
	_name_lbl.visible = v and _show_name


func set_name_visible(v: bool) -> void:
	_show_name = v
	_name_lbl.visible = is_controlled and v


func set_pass_target(v: bool) -> void:
	_target_ring.visible = v


func max_speed() -> float:
	var b := lerpf(4.3, 6.3, spd / 100.0)
	if sprinting:
		b *= 1.35
	if role == "GK":
		b *= 0.85
	return b


func step(dt: float, has_ball: bool) -> void:
	tackle_cd = maxf(0.0, tackle_cd - dt)
	var prev_speed := velocity.length()
	if slide_t > 0.0:
		slide_t -= dt
		velocity = slide_dir * (2.5 + 7.0 * clampf(slide_t / 0.6, 0.0, 1.0))
		if slide_t <= 0.0:
			stun = 0.45
	elif dive_t > 0.0:
		dive_t -= dt
		if dive_t <= 0.0:
			stun = 0.5
			velocity = Vector3.ZERO
	elif stun > 0.0:
		stun -= dt
		velocity = velocity.move_toward(Vector3.ZERO, 14.0 * dt)
	else:
		var mx := max_speed() * (0.88 if has_ball else 1.0)
		var want := move_input.limit_length(1.0)
		var tv := want * mx
		# Inercia: acelera menos de lo que frena y gira poco a poco a alta velocidad.
		var accel := lerpf(7.0, 11.0, spd / 100.0) * (1.15 if sprinting else 1.0)
		if tv.length() < velocity.length():
			accel = 13.0
		if velocity.length() > 2.0 and tv.length() > 0.5:
			var turn := velocity.normalized().angle_to(tv.normalized())
			if turn > 1.2:
				accel *= 0.6  # cambio brusco de dirección: frena antes de girar
		velocity = velocity.move_toward(tv, accel * dt)
	position += velocity * dt
	position.y = 0.0
	position.x = clampf(position.x, -56.0, 56.0)
	position.z = clampf(position.z, -37.0, 37.0)
	if velocity.length() > 0.3 and slide_t <= 0.0 and dive_t <= 0.0:
		var rate := lerpf(10.0, 5.0, clampf(velocity.length() / 8.0, 0.0, 1.0))
		facing = facing.slerp(velocity.normalized(), clampf(dt * rate, 0.0, 1.0))
		facing.y = 0
		facing = facing.normalized()
	var acc := (velocity.length() - prev_speed) / maxf(dt, 0.001)
	_lean = lerpf(_lean, clampf(acc * 0.04, -0.15, 0.2), clampf(dt * 6.0, 0.0, 1.0))
	_animate(dt)


func face_towards(p: Vector3) -> void:
	var d := p - position
	d.y = 0
	if d.length() > 0.01:
		facing = d.normalized()


func _animate(dt: float) -> void:
	_body.rotation.y = atan2(facing.x, facing.z)
	var s := Vector2(velocity.x, velocity.z).length()
	# Zancada: un ciclo son dos pasos; la longitud crece con la velocidad.
	var cycle := 1.3 + s * 0.16
	_phase = fmod(_phase + TAU * s / cycle * dt, TAU * 100.0)
	var run := clampf((s - 1.0) / 6.5, 0.0, 1.0)   # 0 = andar, 1 = sprint
	var moving := clampf(s / 1.2, 0.0, 1.0)
	var sn := sin(_phase)
	var thigh_amp := lerpf(0.32, 0.85, run) * moving
	var knee_amp := lerpf(0.45, 1.5, run) * moving
	_leg_l.rotation.x = -sn * thigh_amp
	_leg_r.rotation.x = sn * thigh_amp
	# La rodilla se dobla cuando la pierna va hacia delante (fase de vuelo).
	_shin_l.rotation.x = (maxf(0.0, sin(_phase + 1.3)) * knee_amp + 0.08) * moving + 0.04
	_shin_r.rotation.x = (maxf(0.0, sin(_phase + 1.3 + PI)) * knee_amp + 0.08) * moving + 0.04
	var arm_amp := lerpf(0.3, 0.75, run) * moving
	_arm_l.rotation.x = sn * arm_amp
	_arm_r.rotation.x = -sn * arm_amp
	_arm_l.rotation.z = -0.1
	_arm_r.rotation.z = 0.1
	var elbow := -lerpf(0.25, 1.35, run) * moving - 0.15
	_fore_l.rotation.x = elbow
	_fore_r.rotation.x = elbow
	_torso.rotation.x = lerpf(0.04, 0.22, run) * moving + _lean
	_torso.rotation.y = sn * 0.1 * moving
	_torso.rotation.z = 0.0
	_body.position.y = absf(cos(_phase)) * lerpf(0.02, 0.07, run) * moving
	_body.rotation.x = 0.0
	_body.rotation.z = 0.0
	if s < 0.3:
		# Respiración en reposo
		var b := sin(Time.get_ticks_msec() / 600.0 + float(number))
		_torso.rotation.x = 0.03 + b * 0.015
		_arm_l.rotation.z = -0.12 - b * 0.02
		_arm_r.rotation.z = 0.12 + b * 0.02

	if kick_anim > 0.0:
		kick_anim -= dt
		var k := 1.0 - clampf(kick_anim / 0.3, 0.0, 1.0)
		_leg_r.rotation.x = lerpf(0.8, -1.25, k)
		_shin_r.rotation.x = lerpf(1.4, 0.1, k)
		_leg_l.rotation.x = 0.1
		_shin_l.rotation.x = 0.25
		_arm_l.rotation.x = -0.5
		_arm_l.rotation.z = -0.8
		_arm_r.rotation.z = 0.5
		_torso.rotation.x = -0.12 + k * 0.2
	if slide_t > 0.0:
		_body.rotation.x = -1.15
		_body.position.y = 0.18
		_leg_l.rotation.x = -0.3
		_shin_l.rotation.x = 1.0
		_leg_r.rotation.x = -1.4
		_shin_r.rotation.x = 0.1
	elif stun > 0.0 and dive_t <= 0.0:
		_torso.rotation.x = -0.2
	if head_anim > 0.0:
		head_anim -= dt
		var hp := sin(clampf(1.0 - head_anim / 0.45, 0.0, 1.0) * PI)
		_body.position.y = hp * 0.55
		_torso.rotation.x = 0.35 * hp
		_arm_l.rotation.z = -0.9
		_arm_r.rotation.z = 0.9
		_shin_l.rotation.x = 0.9 * hp
		_shin_r.rotation.x = 0.6 * hp
	if celebrate > 0.0:
		celebrate -= dt
		_arm_l.rotation.z = -2.6
		_arm_r.rotation.z = 2.6
		_fore_l.rotation.x = 0.0
		_fore_r.rotation.x = 0.0
		_body.position.y = absf(sin(celebrate * 8.0)) * 0.3
	if dive_t > 0.0:
		var p := clampf(1.0 - dive_t / 0.7, 0.0, 1.0)
		var lift := sin(p * PI) * (1.0 + dive_high)
		var local_side := dive_side * (1.0 if facing.x < 0 else -1.0)
		_body.rotation.z = local_side * 1.35 * minf(p * 3.0, 1.0)
		_body.position.y = 0.25 + lift * 0.5
		_arm_l.rotation.z = -2.8
		_arm_r.rotation.z = 2.8
		_arm_l.rotation.x = 0.0
		_arm_r.rotation.x = 0.0
		_fore_l.rotation.x = 0.0
		_fore_r.rotation.x = 0.0
		_leg_l.rotation.x = 0.0
		_leg_r.rotation.x = 0.0
		_shin_l.rotation.x = 0.2
		_shin_r.rotation.x = 0.2

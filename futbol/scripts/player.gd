class_name Futbolista
extends Node3D
## Un futbolista: modelo low-poly hecho con piezas, animación procedural
## (correr, patear, barrida, estirada del portero) y movimiento.
## Más adelante se puede reemplazar el modelo por uno de Mixamo.

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
var _arm_l: Node3D
var _arm_r: Node3D
var _ring: MeshInstance3D
var _name_lbl: Label3D
var _phase := 0.0


func setup(data: Dictionary, team_id: int, kit: Dictionary) -> void:
	team = team_id
	pname = data.name
	number = data.number
	role = data.pos
	spd = data.spd
	pas = data.pas
	sho = data.sho
	dfn = data.dfn
	gkp = data.gkp
	tl = data.get("tl", 50.0)
	data_id = int(data.get("id", -1))
	facing = Vector3.RIGHT if team == HOME else Vector3.LEFT
	run_ahead = randf_range(7.0, 13.0)
	_build(kit)


func _build(kit: Dictionary) -> void:
	var skins := [Color(0.96, 0.80, 0.66), Color(0.80, 0.60, 0.45), Color(0.58, 0.40, 0.27), Color(0.38, 0.25, 0.17)]
	var hairs := [Color(0.08, 0.06, 0.05), Color(0.35, 0.2, 0.1), Color(0.75, 0.6, 0.3), Color(0.15, 0.1, 0.08)]
	var skin: Color = skins[(number * 7 + team * 3) % 4]
	var hair: Color = hairs[(number * 3 + team) % 4]
	var shirt: Color = kit.shirt
	var shorts: Color = kit.shorts
	var socks: Color = kit.socks
	if role == "GK":
		shirt = kit.gk
		shorts = kit.gk.darkened(0.5)
		socks = kit.gk

	_body = Node3D.new()
	add_child(_body)
	_leg_l = _make_leg(-0.11, skin, socks)
	_leg_r = _make_leg(0.11, skin, socks)

	_torso = Node3D.new()
	_torso.position = Vector3(0, 0.95, 0)
	_body.add_child(_torso)
	var shorts_m := MeshUtil.box(Vector3(0.38, 0.24, 0.24), shorts)
	shorts_m.position = Vector3(0, 0.0, 0)
	_torso.add_child(shorts_m)
	var chest := MeshUtil.box(Vector3(0.44, 0.56, 0.26), shirt)
	chest.position = Vector3(0, 0.38, 0)
	_torso.add_child(chest)
	var neck := MeshUtil.box(Vector3(0.1, 0.1, 0.1), skin)
	neck.position = Vector3(0, 0.7, 0)
	_torso.add_child(neck)
	var head := MeshUtil.sphere(0.13, skin)
	head.position = Vector3(0, 0.84, 0)
	head.scale = Vector3(0.95, 1.1, 1.0)
	_torso.add_child(head)
	var hair_m := MeshUtil.sphere(0.135, hair)
	hair_m.position = Vector3(0, 0.89, -0.02)
	hair_m.scale = Vector3(1.0, 0.75, 1.0)
	_torso.add_child(hair_m)

	_arm_l = _make_arm(-0.29, skin, shirt)
	_arm_r = _make_arm(0.29, skin, shirt)

	var num := Label3D.new()
	num.text = str(number)
	num.font_size = 96
	num.pixel_size = 0.0028
	num.outline_size = 12
	num.modulate = kit.number
	num.outline_modulate = Color(0, 0, 0, 0.6)
	num.position = Vector3(0, 0.42, -0.135)
	num.rotation_degrees.y = 180
	_torso.add_child(num)

	_ring = MeshUtil.ring(0.5, 0.66, 0, TAU, 32, Color(1.0, 0.92, 0.15))
	_ring.position.y = 0.03
	_ring.visible = false
	add_child(_ring)

	_name_lbl = Label3D.new()
	_name_lbl.text = pname
	_name_lbl.font_size = 40
	_name_lbl.pixel_size = 0.006
	_name_lbl.outline_size = 10
	_name_lbl.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	_name_lbl.no_depth_test = true
	_name_lbl.position = Vector3(0, 2.35, 0)
	_name_lbl.visible = false
	add_child(_name_lbl)


func _make_leg(x: float, skin: Color, socks: Color) -> Node3D:
	var pivot := Node3D.new()
	pivot.position = Vector3(x, 0.95, 0)
	_body.add_child(pivot)
	var thigh := MeshUtil.box(Vector3(0.14, 0.45, 0.15), skin)
	thigh.position = Vector3(0, -0.22, 0)
	pivot.add_child(thigh)
	var shin := MeshUtil.box(Vector3(0.12, 0.42, 0.13), socks)
	shin.position = Vector3(0, -0.64, 0)
	pivot.add_child(shin)
	var boot := MeshUtil.box(Vector3(0.12, 0.08, 0.25), Color(0.08, 0.08, 0.08))
	boot.position = Vector3(0, -0.9, 0.05)
	pivot.add_child(boot)
	return pivot


func _make_arm(x: float, skin: Color, shirt: Color) -> Node3D:
	var pivot := Node3D.new()
	pivot.position = Vector3(x, 0.6, 0)
	_torso.add_child(pivot)
	var sleeve := MeshUtil.box(Vector3(0.13, 0.24, 0.13), shirt)
	sleeve.position = Vector3(0, -0.1, 0)
	pivot.add_child(sleeve)
	var fore := MeshUtil.box(Vector3(0.09, 0.32, 0.09), skin)
	fore.position = Vector3(0, -0.36, 0)
	pivot.add_child(fore)
	return pivot


var _show_name := true


func set_controlled(v: bool) -> void:
	is_controlled = v
	_ring.visible = v
	_name_lbl.visible = v and _show_name


func set_name_visible(v: bool) -> void:
	_show_name = v
	_name_lbl.visible = is_controlled and v


func max_speed() -> float:
	var b := lerpf(5.6, 7.6, spd / 100.0)
	if sprinting:
		b *= 1.32
	if role == "GK":
		b *= 0.85
	return b


func step(dt: float, has_ball: bool) -> void:
	tackle_cd = maxf(0.0, tackle_cd - dt)
	if slide_t > 0.0:
		slide_t -= dt
		velocity = slide_dir * (3.0 + 8.0 * clampf(slide_t / 0.6, 0.0, 1.0))
		if slide_t <= 0.0:
			stun = 0.35
	elif dive_t > 0.0:
		# El partido decide la dirección de la estirada; aquí solo se agota el tiempo.
		dive_t -= dt
		if dive_t <= 0.0:
			stun = 0.5
			velocity = Vector3.ZERO
	elif stun > 0.0:
		stun -= dt
		velocity = velocity.move_toward(Vector3.ZERO, 20.0 * dt)
	else:
		var mx := max_speed() * (0.92 if has_ball else 1.0)
		var tv := move_input.limit_length(1.0) * mx
		var acc := 24.0 if tv.length() > velocity.length() else 32.0
		velocity = velocity.move_toward(tv, acc * dt)
	position += velocity * dt
	position.y = 0.0
	position.x = clampf(position.x, -56.0, 56.0)
	position.z = clampf(position.z, -37.0, 37.0)
	if velocity.length() > 0.4 and slide_t <= 0.0 and dive_t <= 0.0:
		facing = facing.lerp(velocity.normalized(), clampf(dt * 12.0, 0.0, 1.0)).normalized()
	_animate(dt)


func face_towards(p: Vector3) -> void:
	var d := p - position
	d.y = 0
	if d.length() > 0.01:
		facing = d.normalized()


func _animate(dt: float) -> void:
	_body.rotation.y = atan2(facing.x, facing.z)
	var s := Vector2(velocity.x, velocity.z).length()
	_phase += dt * (3.0 + s * 1.45)
	var amp := clampf(s / 7.0, 0.0, 1.0) * 0.85
	var sn := sin(_phase)
	_leg_l.rotation.x = sn * amp
	_leg_r.rotation.x = -sn * amp
	_arm_l.rotation.x = -sn * amp * 0.8
	_arm_r.rotation.x = sn * amp * 0.8
	_arm_l.rotation.z = -0.12
	_arm_r.rotation.z = 0.12
	_torso.rotation.x = amp * 0.2
	_body.position.y = absf(sn) * 0.05 * amp
	_body.rotation.x = 0.0
	_body.rotation.z = 0.0

	if kick_anim > 0.0:
		kick_anim -= dt
		var k := 1.0 - clampf(kick_anim / 0.3, 0.0, 1.0)
		_leg_r.rotation.x = lerpf(0.9, -1.3, k)
		_arm_l.rotation.x = -0.6
		_arm_l.rotation.z = -0.7
	if slide_t > 0.0:
		_body.rotation.x = -1.15
		_body.position.y = 0.18
		_leg_l.rotation.x = -0.4
		_leg_r.rotation.x = -1.4
	elif stun > 0.0:
		_torso.rotation.x = -0.25
	if head_anim > 0.0:
		head_anim -= dt
		var hp := sin(clampf(1.0 - head_anim / 0.45, 0.0, 1.0) * PI)
		_body.position.y = hp * 0.55
		_torso.rotation.x = 0.35 * hp
		_arm_l.rotation.z = -0.9
		_arm_r.rotation.z = 0.9
		_leg_l.rotation.x = 0.3
		_leg_r.rotation.x = 0.5
	if celebrate > 0.0:
		celebrate -= dt
		_arm_l.rotation.z = -2.6
		_arm_r.rotation.z = 2.6
		_body.position.y = absf(sin(celebrate * 9.0)) * 0.3
	if dive_t > 0.0:
		var p := clampf(1.0 - dive_t / 0.7, 0.0, 1.0)
		var lift := sin(p * PI) * (1.0 + dive_high)
		# El cuerpo gira hacia el lado de la estirada (en espacio local).
		var local_side := dive_side * (1.0 if facing.x < 0 else -1.0)
		_body.rotation.z = local_side * 1.35 * minf(p * 3.0, 1.0)
		_body.position.y = 0.25 + lift * 0.5
		_arm_l.rotation.z = -2.8
		_arm_r.rotation.z = 2.8
		_arm_l.rotation.x = 0.0
		_arm_r.rotation.x = 0.0

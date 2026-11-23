class_name Balon
extends Node3D
## Balón con física propia (gravedad, bote, rodado, postes y red).
## Se hace a mano en vez de con RigidBody para que pases y tiros sean predecibles.

const R := 0.11
const GRAVITY := 9.8
const ROLL_DECEL := 2.6
const HALF_L := 52.5
const HALF_W := 34.0
const GOAL_HW := 3.66
const GOAL_H := 2.44
const POST_R := 0.06
const NET_DEPTH := 2.0

var vel := Vector3.ZERO
var carrier: Futbolista = null
var last_touch: Futbolista = null
var last_kicker: Futbolista = null
var kicker_ban := 0.0
var kind := ""  # "pass", "through", "shot", "clear", "loose"
var pass_target: Futbolista = null
var shot_time := 0.0
var rolled := {}
var scored := false

var _mesh: MeshInstance3D
var _shadow: MeshInstance3D


func _ready() -> void:
	_mesh = MeshInstance3D.new()
	var sm := SphereMesh.new()
	sm.radius = R
	sm.height = R * 2.0
	sm.radial_segments = 16
	sm.rings = 8
	var m := StandardMaterial3D.new()
	m.albedo_texture = _make_texture()
	m.roughness = 0.6
	sm.material = m
	_mesh.mesh = sm
	add_child(_mesh)

	_shadow = MeshInstance3D.new()
	var qm := PlaneMesh.new()
	qm.size = Vector2(0.32, 0.32)
	var sh := StandardMaterial3D.new()
	sh.albedo_color = Color(0, 0, 0, 0.45)
	sh.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	sh.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	qm.material = sh
	_shadow.mesh = qm
	_shadow.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_shadow)


func _make_texture() -> ImageTexture:
	var img := Image.create(64, 32, false, Image.FORMAT_RGB8)
	for y in 32:
		for x in 64:
			var cx := int(x / 8.0)
			var cy := int(y / 8.0)
			var dark := (cx + cy) % 2 == 0 and (x % 8 > 1 and y % 8 > 1)
			img.set_pixel(x, y, Color(0.1, 0.1, 0.1) if dark else Color(0.97, 0.97, 0.97))
	return ImageTexture.create_from_image(img)


func is_loose() -> bool:
	return carrier == null


func speed() -> float:
	return vel.length()


## Avanza la física. Devuelve un evento: "", "goal_home", "goal_away", "out", "post".
func step(dt: float) -> String:
	kicker_ban = maxf(0.0, kicker_ban - dt)
	shot_time += dt
	var event := ""
	if carrier != null:
		var ahead := 0.55 + (0.35 if carrier.sprinting else 0.0)
		var target := carrier.position + carrier.facing * ahead
		target.y = R
		position = position.lerp(target, clampf(dt * 18.0, 0.0, 1.0))
		vel = carrier.velocity
		_spin_visual(dt)
		_update_shadow()
		return ""

	var prev := position
	vel.y -= GRAVITY * dt
	position += vel * dt

	if position.y <= R:
		position.y = R
		if vel.y < 0.0:
			vel.y = -vel.y * 0.5
			if vel.y < 1.2:
				vel.y = 0.0
			vel.x *= 0.85
			vel.z *= 0.85
	if position.y <= R + 0.01 and vel.y == 0.0:
		var h := Vector3(vel.x, 0, vel.z)
		var hl := h.length()
		if hl > 0.0:
			var nl := maxf(0.0, hl - (ROLL_DECEL + hl * 0.08) * dt)
			h = h * (nl / hl)
			vel.x = h.x
			vel.z = h.z
	else:
		vel.x *= 1.0 - 0.012 * dt * 10.0
		vel.z *= 1.0 - 0.012 * dt * 10.0

	# Postes y travesaño de ambas porterías.
	for side in [1.0, -1.0]:
		var gx: float = HALF_L * side
		for pz in [GOAL_HW, -GOAL_HW]:
			if position.y < GOAL_H + R:
				var d := Vector2(position.x - gx, position.z - pz)
				if d.length() < R + POST_R:
					var n := Vector3(d.x, 0, d.y).normalized()
					_bounce(n, 0.6)
					position = Vector3(gx + n.x * (R + POST_R), position.y, pz + n.z * (R + POST_R))
					event = "post"
		if absf(position.z) < GOAL_HW:
			var d2 := Vector2(position.x - gx, position.y - GOAL_H)
			if d2.length() < R + POST_R:
				var n2 := Vector3(d2.x, d2.y, 0).normalized()
				_bounce(n2, 0.6)
				position = Vector3(gx + n2.x * (R + POST_R), GOAL_H + n2.y * (R + POST_R), position.z)
				event = "post"

	# Gol o fuera por la línea de fondo.
	if not scored:
		for side2 in [1.0, -1.0]:
			var line: float = (HALF_L + R) * side2
			var crossed: bool = (prev.x - line) * side2 <= 0.0 and (position.x - line) * side2 > 0.0
			if crossed:
				if absf(position.z) < GOAL_HW and position.y < GOAL_H:
					scored = true
					event = "goal_home" if side2 > 0 else "goal_away"
				else:
					event = "out"
		if absf(position.z) > HALF_W + R:
			event = "out"

	# Red: mantener el balón dentro de la portería después de un gol.
	if scored:
		var sx := signf(position.x)
		var back := HALF_L + NET_DEPTH
		if absf(position.x) > back - R:
			position.x = (back - R) * sx
			vel.x *= -0.15
			vel.z *= 0.4
		if absf(position.z) > GOAL_HW - R:
			position.z = (GOAL_HW - R) * signf(position.z)
			vel.z *= -0.2
		if position.y > GOAL_H - R:
			position.y = GOAL_H - R
			vel.y = -absf(vel.y) * 0.2

	_spin_visual(dt)
	_update_shadow()
	return event


func _bounce(n: Vector3, restitution: float) -> void:
	var vn := vel.dot(n)
	if vn < 0.0:
		vel -= (1.0 + restitution) * vn * n


func _spin_visual(dt: float) -> void:
	var h := Vector3(vel.x, 0, vel.z)
	if h.length() > 0.05:
		var axis := Vector3.UP.cross(h.normalized())
		_mesh.rotate(axis.normalized(), h.length() / R * dt)


func _update_shadow() -> void:
	_shadow.global_position = Vector3(position.x, 0.02, position.z)
	var s := clampf(1.0 - position.y / 8.0, 0.35, 1.0)
	_shadow.scale = Vector3(s, 1, s)

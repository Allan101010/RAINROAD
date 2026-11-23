class_name Balon
extends Node3D
## Balón con física propia: gravedad, bote, rodado, efecto (Magnus), postes y red.
## Se hace a mano en vez de con RigidBody para que pases y tiros sean predecibles.

const R := 0.11
const GRAVITY := 9.8
const ROLL_DECEL := 2.6
const MAGNUS := 0.034
const HALF_L := 52.5
const HALF_W := 34.0
const GOAL_HW := 3.66
const GOAL_H := 2.44
const POST_R := 0.06
const NET_DEPTH := 2.0

var vel := Vector3.ZERO
var spin := Vector3.ZERO
var prev_pos := Vector3.ZERO
var carrier: Futbolista = null
var last_touch: Futbolista = null
var last_kicker: Futbolista = null
var kicker_ban := 0.0
var kind := ""  # "pass", "through", "cross", "shot", "clear", "loose"
var pass_target: Futbolista = null
var pass_point := Vector3.ZERO
var shield := Vector3.ZERO  # hacia dónde se aparta el balón para protegerlo
var shot_time := 0.0
var rolled := {}
var scored := false
var scored_side := 0

var _mesh: MeshInstance3D
var _shadow: MeshInstance3D
var _trail: Array[MeshInstance3D] = []
var _trail_pos: Array[Vector3] = []


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
	_shadow.top_level = true
	add_child(_shadow)

	for i in 8:
		var t := MeshInstance3D.new()
		var ts := SphereMesh.new()
		ts.radius = R * (0.9 - i * 0.08)
		ts.height = ts.radius * 2.0
		ts.radial_segments = 8
		ts.rings = 4
		var tm := StandardMaterial3D.new()
		tm.albedo_color = Color(1, 1, 1, 0.35 - i * 0.04)
		tm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		tm.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		ts.material = tm
		t.mesh = ts
		t.top_level = true
		t.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		t.visible = false
		add_child(t)
		_trail.append(t)


func _make_texture() -> ImageTexture:
	var img := Image.create(64, 32, false, Image.FORMAT_RGB8)
	for y in 32:
		for x in 64:
			var cx := int(x / 8.0)
			var cy := int(y / 8.0)
			var dark := (cx + cy) % 2 == 0 and (x % 8 > 1 and y % 8 > 1)
			img.set_pixel(x, y, Color(0.1, 0.1, 0.1) if dark else Color(0.97, 0.97, 0.97))
	return ImageTexture.create_from_image(img)


func speed() -> float:
	return vel.length()


func place(p: Vector3) -> void:
	position = p
	prev_pos = p
	vel = Vector3.ZERO
	spin = Vector3.ZERO
	_trail_pos.clear()


## Avanza la física. Devuelve un evento: "", "goal_home", "goal_away", "out", "post".
func step(dt: float) -> String:
	kicker_ban = maxf(0.0, kicker_ban - dt)
	shot_time += dt
	prev_pos = position
	if carrier != null:
		# Conducción pegada al pie; al esprintar el balón va algo más adelantado.
		var ahead := 0.42 + (0.3 if carrier.sprinting else 0.0)
		var target := carrier.position + carrier.facing * ahead + shield * 0.22
		target.y = R
		position = position.lerp(target, clampf(dt * 18.0, 0.0, 1.0))
		vel = carrier.velocity
		spin = Vector3.ZERO
		_spin_visual(dt)
		_update_extras()
		return ""
	var event := _integrate(dt)
	_spin_visual(dt)
	_update_extras()
	return event


func _integrate(dt: float) -> String:
	var event := ""
	var prev := position
	vel.y -= GRAVITY * dt
	if spin != Vector3.ZERO and position.y > R + 0.02:
		vel += spin.cross(vel) * MAGNUS * dt
		spin *= 1.0 - 0.35 * dt
	position += vel * dt

	if position.y <= R:
		position.y = R
		if vel.y < -1.5:
			# Bote real: pierde algo de velocidad.
			vel.y = -vel.y * 0.5
			if vel.y < 1.2:
				vel.y = 0.0
			vel.x *= 0.88
			vel.z *= 0.88
			spin *= 0.5
		elif vel.y < 0.0:
			vel.y = 0.0
	if position.y <= R + 0.01 and vel.y == 0.0:
		var h := Vector3(vel.x, 0, vel.z)
		var hl := h.length()
		if hl > 0.0:
			var nl := maxf(0.0, hl - (ROLL_DECEL + hl * 0.06) * dt)
			h = h * (nl / hl)
			vel.x = h.x
			vel.z = h.z
	else:
		vel.x *= 1.0 - 0.1 * dt
		vel.z *= 1.0 - 0.1 * dt

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

	if not scored:
		for side2 in [1.0, -1.0]:
			var line: float = (HALF_L + R) * side2
			var crossed: bool = (prev.x - line) * side2 <= 0.0 and (position.x - line) * side2 > 0.0
			if crossed:
				if absf(position.z) < GOAL_HW and position.y < GOAL_H:
					scored = true
					scored_side = int(side2)
					event = "goal_home" if side2 > 0 else "goal_away"
				else:
					event = "out"
		if absf(position.z) > HALF_W + R:
			event = "out"

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
		spin = Vector3.ZERO
	return event


## Predice dónde cruzará el balón el plano x = gx (sin contar jugadores).
## Devuelve {"t", "z", "y"} o un diccionario vacío si no llega.
func predict_cross(gx: float, from_pos := Vector3.INF, from_vel := Vector3.INF, from_spin := Vector3.INF) -> Dictionary:
	var p := position if from_pos == Vector3.INF else from_pos
	var v := vel if from_vel == Vector3.INF else from_vel
	var s := spin if from_spin == Vector3.INF else from_spin
	var dt := 1.0 / 120.0
	var t := 0.0
	var side := signf(gx - p.x)
	while t < 4.0:
		var prev := p
		v.y -= GRAVITY * dt
		if s != Vector3.ZERO and p.y > R + 0.02:
			v += s.cross(v) * MAGNUS * dt
			s *= 1.0 - 0.35 * dt
		p += v * dt
		if p.y <= R:
			p.y = R
			if v.y < -1.5:
				v.y = -v.y * 0.5
				if v.y < 1.2:
					v.y = 0.0
				v.x *= 0.88
				v.z *= 0.88
			elif v.y < 0.0:
				v.y = 0.0
		if p.y <= R + 0.01 and v.y == 0.0:
			var h := Vector3(v.x, 0, v.z)
			var hl := h.length()
			if hl < 0.3:
				return {}
			var nl := maxf(0.0, hl - (ROLL_DECEL + hl * 0.06) * dt)
			v.x = h.x * nl / hl
			v.z = h.z * nl / hl
		else:
			v.x *= 1.0 - 0.1 * dt
			v.z *= 1.0 - 0.1 * dt
		t += dt
		if (prev.x - gx) * side < 0.0 and (p.x - gx) * side >= 0.0:
			return {"t": t, "z": p.z, "y": p.y}
	return {}


func _bounce(n: Vector3, restitution: float) -> void:
	var vn := vel.dot(n)
	if vn < 0.0:
		vel -= (1.0 + restitution) * vn * n


func _spin_visual(dt: float) -> void:
	var h := Vector3(vel.x, 0, vel.z)
	if h.length() > 0.05:
		var axis := Vector3.UP.cross(h.normalized())
		_mesh.rotate(axis.normalized(), h.length() / R * dt)


func _update_extras() -> void:
	_shadow.global_position = Vector3(global_position.x, 0.02, global_position.z)
	var s := clampf(1.0 - position.y / 8.0, 0.35, 1.0)
	_shadow.scale = Vector3(s, 1, s)
	var fast := carrier == null and vel.length() > 17.0
	_trail_pos.push_front(global_position)
	if _trail_pos.size() > _trail.size() * 2:
		_trail_pos.pop_back()
	for i in _trail.size():
		var idx := (i + 1) * 2 - 1
		_trail[i].visible = fast and idx < _trail_pos.size()
		if _trail[i].visible:
			_trail[i].global_position = _trail_pos[idx]

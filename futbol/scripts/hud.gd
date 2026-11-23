class_name Hud
extends Control
## Interfaz del partido: joystick virtual, botones táctiles multitáctiles,
## marcador, mensajes y pantalla de resultado.

signal retry_pressed
signal next_pressed
signal menu_pressed

const JOY_R := 85.0

var joy_vec := Vector2.ZERO
var joy_index := -1
var joy_base := Vector2.ZERO
var joy_pos := Vector2.ZERO
var controls_enabled := true
var attack_mode := true
var shot_power := -1.0

var score_text := ""
var minute_text := ""
var time_left := 0.0
var time_total := 1.0

var event_log: Array[String] = []
var _buttons := {}
var _just_pressed := {}
var _just_released := {}
var _msg := ""
var _msg_t := 0.0
var _msg_big := false
var _result_panel: Control
var _result_root: Control
var _menu_btn: Button

const LABELS_ATTACK := {"a": "TIRO", "b": "PASE", "c": "AL HUECO", "d": "SPRINT"}
const LABELS_DEFENSE := {"a": "BARRIDA", "b": "CAMBIAR", "c": "PRESIÓN", "d": "SPRINT"}
const COLORS := {"a": Color(0.9, 0.2, 0.2), "b": Color(0.2, 0.7, 0.3), "c": Color(0.25, 0.5, 0.95), "d": Color(0.95, 0.75, 0.15)}


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	for id in ["a", "b", "c", "d"]:
		_buttons[id] = {"pos": Vector2.ZERO, "r": 50.0, "down": false, "idx": -1}
	_menu_btn = Button.new()
	_menu_btn.text = "MENÚ"
	_menu_btn.add_theme_font_size_override("font_size", 22)
	_menu_btn.custom_minimum_size = Vector2(110, 48)
	_menu_btn.set_anchors_preset(Control.PRESET_TOP_RIGHT)
	_menu_btn.position = Vector2(-126, 14)
	_menu_btn.pressed.connect(func(): menu_pressed.emit())
	add_child(_menu_btn)
	resized.connect(_layout)
	_layout()


func _layout() -> void:
	var s := size
	if s.x < 10:
		s = get_viewport_rect().size
	_buttons.a.pos = Vector2(s.x - 115, s.y - 125)
	_buttons.a.r = 68.0
	_buttons.b.pos = Vector2(s.x - 265, s.y - 80)
	_buttons.b.r = 54.0
	_buttons.c.pos = Vector2(s.x - 235, s.y - 230)
	_buttons.c.r = 50.0
	_buttons.d.pos = Vector2(s.x - 85, s.y - 285)
	_buttons.d.r = 44.0
	_menu_btn.position = Vector2(s.x - 126, 14)
	queue_redraw()


func _default_joy_base() -> Vector2:
	return Vector2(175, size.y - 165)


func _input(event: InputEvent) -> void:
	if event is InputEventScreenTouch:
		var st := event as InputEventScreenTouch
		if st.pressed:
			if not controls_enabled:
				return
			var hit := false
			for id in _buttons:
				var b: Dictionary = _buttons[id]
				if st.position.distance_to(b.pos) < b.r * 1.3 and b.idx == -1:
					b.down = true
					b.idx = st.index
					_just_pressed[id] = true
					hit = true
					break
			if not hit and joy_index == -1 and st.position.x < size.x * 0.5 and st.position.y > 90:
				joy_index = st.index
				joy_base = st.position
				joy_pos = st.position
				joy_vec = Vector2.ZERO
		else:
			if st.index == joy_index:
				joy_index = -1
				joy_vec = Vector2.ZERO
			for id in _buttons:
				var b2: Dictionary = _buttons[id]
				if b2.idx == st.index:
					b2.down = false
					b2.idx = -1
					_just_released[id] = true
		queue_redraw()
	elif event is InputEventScreenDrag:
		var sd := event as InputEventScreenDrag
		if sd.index == joy_index:
			joy_pos = sd.position
			var d := joy_pos - joy_base
			if d.length() > JOY_R:
				joy_base = joy_pos - d.normalized() * JOY_R
				d = joy_pos - joy_base
			joy_vec = d / JOY_R
			if joy_vec.length() < 0.12:
				joy_vec = Vector2.ZERO
			queue_redraw()


func is_down(id: String) -> bool:
	return _buttons[id].down


func pressed(id: String) -> bool:
	return _just_pressed.has(id)


func released(id: String) -> bool:
	return _just_released.has(id)


func end_frame() -> void:
	_just_pressed.clear()
	_just_released.clear()


func release_all() -> void:
	for id in _buttons:
		_buttons[id].down = false
		_buttons[id].idx = -1
	joy_index = -1
	joy_vec = Vector2.ZERO


func show_message(text: String, duration := 1.5, big := false) -> void:
	event_log.append(text)
	_msg = text
	_msg_t = duration
	_msg_big = big


func _process(delta: float) -> void:
	var real_dt := delta / maxf(Engine.time_scale, 0.01)
	if _msg_t > 0.0:
		_msg_t -= real_dt
		if _msg_t <= 0.0:
			_msg = ""
	queue_redraw()


func _draw() -> void:
	var font := ThemeDB.fallback_font
	# Marcador
	var box := Rect2(16, 14, 330, 52)
	draw_rect(box, Color(0.05, 0.07, 0.12, 0.85))
	draw_rect(Rect2(16, 14, 6, 52), Color(0.82, 0.08, 0.14))
	draw_string(font, Vector2(34, 50), score_text, HORIZONTAL_ALIGNMENT_LEFT, -1, 28, Color.WHITE)
	draw_rect(Rect2(266, 14, 80, 52), Color(0.95, 0.95, 0.95, 0.95))
	draw_string(font, Vector2(266, 50), minute_text, HORIZONTAL_ALIGNMENT_CENTER, 80, 26, Color(0.05, 0.07, 0.12))
	# Tiempo restante de la jugada
	var frac := clampf(time_left / maxf(time_total, 0.01), 0.0, 1.0)
	draw_rect(Rect2(16, 70, 330, 8), Color(0, 0, 0, 0.5))
	draw_rect(Rect2(16, 70, 330 * frac, 8), Color(1.0, 0.85, 0.2) if frac > 0.25 else Color(1.0, 0.3, 0.2))

	if controls_enabled:
		# Joystick
		var base := joy_base if joy_index != -1 else _default_joy_base()
		var knob := base + joy_vec * JOY_R
		draw_circle(base, JOY_R, Color(1, 1, 1, 0.12))
		draw_arc(base, JOY_R, 0, TAU, 48, Color(1, 1, 1, 0.45), 3.0, true)
		draw_circle(knob, 38, Color(1, 1, 1, 0.55 if joy_index != -1 else 0.3))
		# Botones
		var labels: Dictionary = LABELS_ATTACK if attack_mode else LABELS_DEFENSE
		for id in _buttons:
			var b: Dictionary = _buttons[id]
			var c: Color = COLORS[id]
			c.a = 0.85 if b.down else 0.5
			draw_circle(b.pos, b.r, c)
			draw_arc(b.pos, b.r, 0, TAU, 48, Color(1, 1, 1, 0.8), 3.0, true)
			var fs := 22 if id == "a" else 17
			draw_string_outline(font, b.pos + Vector2(-b.r, fs * 0.35), labels[id], HORIZONTAL_ALIGNMENT_CENTER, b.r * 2, fs, 4, Color(0, 0, 0, 0.6))
			draw_string(font, b.pos + Vector2(-b.r, fs * 0.35), labels[id], HORIZONTAL_ALIGNMENT_CENTER, b.r * 2, fs, Color.WHITE)
		# Barra de potencia del tiro
		if shot_power >= 0.0:
			var pb := Rect2(_buttons.a.pos + Vector2(-80, -_buttons.a.r - 34), Vector2(160, 16))
			draw_rect(pb, Color(0, 0, 0, 0.6))
			var pc := Color(0.3, 0.9, 0.3).lerp(Color(1, 0.2, 0.1), clampf(shot_power, 0, 1))
			draw_rect(Rect2(pb.position, Vector2(160 * clampf(shot_power, 0, 1), 16)), pc)
			draw_rect(pb, Color.WHITE, false, 2.0)

	if _msg != "":
		var fs2 := 96 if _msg_big else 44
		var y := size.y * (0.35 if _msg_big else 0.25)
		draw_string_outline(font, Vector2(0, y), _msg, HORIZONTAL_ALIGNMENT_CENTER, size.x, fs2, 10, Color(0, 0, 0, 0.75))
		draw_string(font, Vector2(0, y), _msg, HORIZONTAL_ALIGNMENT_CENTER, size.x, fs2, Color(1, 0.95, 0.4) if _msg_big else Color.WHITE)


func show_result(win: bool, title: String, reason: String) -> void:
	hide_result()
	release_all()
	controls_enabled = false
	_result_panel = PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.05, 0.08, 0.12, 0.92)
	sb.border_color = Color(0.3, 0.9, 0.4) if win else Color(0.9, 0.3, 0.3)
	sb.set_border_width_all(4)
	sb.set_corner_radius_all(16)
	sb.set_content_margin_all(28)
	_result_panel.add_theme_stylebox_override("panel", sb)
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 14)
	_result_panel.add_child(vb)
	var t := Label.new()
	t.text = title
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	t.add_theme_font_size_override("font_size", 48)
	t.add_theme_color_override("font_color", Color(0.4, 1, 0.5) if win else Color(1, 0.45, 0.4))
	vb.add_child(t)
	var r := Label.new()
	r.text = reason
	r.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	r.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	r.custom_minimum_size = Vector2(460, 0)
	r.add_theme_font_size_override("font_size", 24)
	vb.add_child(r)
	var hb := HBoxContainer.new()
	hb.add_theme_constant_override("separation", 14)
	hb.alignment = BoxContainer.ALIGNMENT_CENTER
	vb.add_child(hb)
	hb.add_child(_mk_btn("Reintentar", func(): retry_pressed.emit()))
	hb.add_child(_mk_btn("Siguiente", func(): next_pressed.emit()))
	hb.add_child(_mk_btn("Menú", func(): menu_pressed.emit()))
	var center := CenterContainer.new()
	center.add_child(_result_panel)
	add_child(center)
	center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_result_root = center


func hide_result() -> void:
	if _result_root and is_instance_valid(_result_root):
		_result_root.queue_free()
	_result_root = null
	_result_panel = null


func _mk_btn(text: String, cb: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(150, 60)
	b.add_theme_font_size_override("font_size", 24)
	b.pressed.connect(cb)
	return b

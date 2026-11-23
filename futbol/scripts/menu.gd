extends Control
## Menú principal: elegir jugada clave o ver la plantilla (inicio del modo mánager).

var _main: Control
var _roster: Control


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var bg := ColorRect.new()
	bg.color = Color(0.06, 0.2, 0.1)
	add_child(bg)
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	# Franjas de césped decorativas
	for i in 10:
		var s := ColorRect.new()
		s.color = Color(1, 1, 1, 0.03 if i % 2 == 0 else 0.0)
		s.anchor_left = i / 10.0
		s.anchor_right = (i + 1) / 10.0
		s.anchor_bottom = 1.0
		add_child(s)
		s.offset_left = 0
		s.offset_right = 0
		s.offset_top = 0
		s.offset_bottom = 0
	_build_main()
	_build_roster()
	_show(_main)


func _build_main() -> void:
	_main = MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		_main.add_theme_constant_override("margin_" + side, 40)
	add_child(_main)
	_main.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var hb := HBoxContainer.new()
	hb.add_theme_constant_override("separation", 40)
	_main.add_child(hb)

	var left := VBoxContainer.new()
	left.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	left.alignment = BoxContainer.ALIGNMENT_CENTER
	left.add_theme_constant_override("separation", 10)
	hb.add_child(left)
	left.add_child(_label("FÚTBOL MÁNAGER", 64, Color(1, 0.9, 0.3)))
	left.add_child(_label(GameData.home_team.name + "  ·  Temporada 2026", 28, Color(0.9, 0.95, 0.9)))
	var st: Dictionary = GameData.stats
	left.add_child(_label("Jugadas: %d   ·   Goles: %d" % [st.played, st.goals], 22, Color(0.7, 0.85, 0.7)))
	left.add_child(_label("\nControles: joystick a la izquierda; Tiro (mantén para cargar), Pase, Al hueco y Sprint a la derecha.", 20, Color(0.75, 0.8, 0.75)))

	var right := VBoxContainer.new()
	right.custom_minimum_size = Vector2(440, 0)
	right.alignment = BoxContainer.ALIGNMENT_CENTER
	right.add_theme_constant_override("separation", 14)
	hb.add_child(right)
	right.add_child(_label("JUGADAS CLAVE", 26, Color.WHITE))
	for key in GameData.scenario_order:
		var sc: Dictionary = GameData.scenarios[key]
		right.add_child(_button(sc.title, _start.bind(key), Color(0.85, 0.12, 0.18)))
	right.add_child(_button("Mi plantilla", func(): _show(_roster), Color(0.15, 0.35, 0.75)))
	right.add_child(_button("Salir", func(): get_tree().quit(), Color(0.25, 0.25, 0.3)))


func _build_roster() -> void:
	_roster = MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		_roster.add_theme_constant_override("margin_" + side, 30)
	add_child(_roster)
	_roster.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 10)
	_roster.add_child(vb)
	var top := HBoxContainer.new()
	vb.add_child(top)
	var title := _label("PLANTILLA · " + GameData.home_team.name, 36, Color(1, 0.9, 0.3))
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
	top.add_child(title)
	top.add_child(_button("Volver", func(): _show(_main), Color(0.25, 0.25, 0.3), Vector2(160, 56)))

	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vb.add_child(scroll)
	var grid := GridContainer.new()
	grid.columns = 8
	grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	grid.add_theme_constant_override("h_separation", 26)
	grid.add_theme_constant_override("v_separation", 8)
	scroll.add_child(grid)
	for h in ["#", "Nombre", "Pos", "VEL", "PAS", "TIR", "DEF", "MEDIA"]:
		grid.add_child(_label(h, 22, Color(1, 0.9, 0.3)))
	var pos_es := {"GK": "POR", "DEF": "DEF", "MID": "MED", "FWD": "DEL"}
	for p in GameData.home_players:
		var rating := GameData.player_rating(p)
		var cells := [str(p.number), p.name, pos_es[p.pos], str(p.spd), str(p.pas), str(p.sho), str(p.dfn), str(rating)]
		for i in cells.size():
			var c := Color.WHITE
			if i == 7:
				c = Color(0.4, 1, 0.5) if rating >= 75 else (Color(1, 0.85, 0.3) if rating >= 65 else Color(1, 0.5, 0.4))
			var l := _label(cells[i], 22, c)
			if i == 1:
				l.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
			grid.add_child(l)
	vb.add_child(_label("Próximamente: alineación, tácticas, entrenamientos, fichajes y liga.", 20, Color(0.7, 0.8, 0.7)))


func _show(panel: Control) -> void:
	_main.visible = panel == _main
	_roster.visible = panel == _roster


func _start(key: String) -> void:
	GameData.current_scenario = key
	get_tree().change_scene_to_file("res://scenes/match.tscn")


func _label(text: String, size: int, color: Color) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART if size <= 22 and text.length() > 40 else TextServer.AUTOWRAP_OFF
	return l


func _button(text: String, cb: Callable, color: Color, min_size := Vector2(0, 68)) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = min_size
	b.add_theme_font_size_override("font_size", 28)
	for state in ["normal", "hover", "pressed", "focus"]:
		var sb := StyleBoxFlat.new()
		sb.bg_color = color.lightened(0.15) if state == "hover" else (color.darkened(0.25) if state == "pressed" else color)
		if state == "focus":
			sb.bg_color = Color(0, 0, 0, 0)
			sb.border_color = Color(1, 1, 1, 0.6)
			sb.set_border_width_all(2)
		sb.set_corner_radius_all(14)
		sb.set_content_margin_all(12)
		b.add_theme_stylebox_override(state, sb)
	b.pressed.connect(cb)
	return b

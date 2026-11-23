extends Node3D
## Menú principal con el estadio en 3D de fondo: Partido rápido, Modo carrera
## y Entrenamiento (practicar cualquier tipo de jugada).

var _ui: Control
var _screen: Control
var _cam: Camera3D
var _t := 0.0
var _ball: Balon
var _players: Array[Futbolista] = []


func _ready() -> void:
	Engine.time_scale = 1.0
	Stadium.build(self)
	_cam = Camera3D.new()
	_cam.fov = 50
	add_child(_cam)
	_cam.current = true
	_spawn_decor()
	var layer := CanvasLayer.new()
	add_child(layer)
	_ui = Control.new()
	layer.add_child(_ui)
	UI.fill(_ui)
	var shade := TextureRect.new()
	var gt := GradientTexture2D.new()
	var g := Gradient.new()
	g.colors = PackedColorArray([Color(0.02, 0.03, 0.07, 0.25), Color(0.02, 0.03, 0.07, 0.9)])
	gt.gradient = g
	gt.fill_from = Vector2(0, 0)
	gt.fill_to = Vector2(0, 1)
	shade.texture = gt
	shade.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	shade.stretch_mode = TextureRect.STRETCH_SCALE
	shade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_ui.add_child(shade)
	UI.fill(shade)
	_show_main()


func _spawn_decor() -> void:
	var t1: Dictionary = GameData.teams[0]
	var t2: Dictionary = GameData.teams[1]
	var kits := GameData.kits_for(t1, t2)
	var spots := [Vector3(-3, 0, 2), Vector3(2, 0, -3), Vector3(5, 0, 4), Vector3(-6, 0, -5)]
	for i in spots.size():
		var team := 0 if i % 2 == 0 else 1
		var src: Dictionary = (t1 if team == 0 else t2).players[12 + i]
		var p := Futbolista.new()
		add_child(p)
		p.setup(GameData.effective(src), team, kits[team])
		p.position = spots[i]
		_players.append(p)
	_ball = Balon.new()
	add_child(_ball)
	_ball.place(Vector3(0, 0.11, 0))


func _process(delta: float) -> void:
	_t += delta
	var a := _t * 0.08
	_cam.position = Vector3(cos(a) * 22.0, 6.5 + sin(_t * 0.2) * 0.8, sin(a) * 22.0)
	_cam.look_at(Vector3(0, 1.0, 0))
	# Pases entre los jugadores decorativos
	var target: Futbolista = _players[int(_t / 1.6) % _players.size()]
	for p in _players:
		var d := target.position - p.position if p != target else _ball.position - p.position
		d.y = 0
		p.move_input = Vector3.ZERO
		p.face_towards(_ball.position)
		p.step(delta, false)
	var to := target.position + target.facing * 0.5 - _ball.position
	to.y = 0
	_ball.position += to * clampf(delta * 1.4, 0, 1)
	_ball.position.y = 0.11


# ---------------------------------------------------------------- Pantallas

func _set_screen(c: Control) -> void:
	if _screen and is_instance_valid(_screen):
		_screen.queue_free()
	_screen = c
	_ui.add_child(c)
	UI.fill(c)


func _show_main() -> void:
	var root := UI.margin(30)
	_set_screen(root)
	var vb := UI.vbox(18)
	root.add_child(vb)
	var title := UI.label("FÚTBOL MÁNAGER", 72, UI.GOLD, HORIZONTAL_ALIGNMENT_CENTER)
	title.add_theme_constant_override("outline_size", 14)
	title.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.7))
	vb.add_child(title)
	vb.add_child(UI.label("LaLiga  ·  Temporada 2026/27", 24, UI.TEXT, HORIZONTAL_ALIGNMENT_CENTER))
	var spacer := Control.new()
	UI.expand(spacer, true, true)
	vb.add_child(spacer)

	var cards := UI.hbox(22)
	cards.alignment = BoxContainer.ALIGNMENT_CENTER
	vb.add_child(cards)
	cards.add_child(_card("PARTIDO RÁPIDO", "Elige dos equipos y juega un partido con jugadas clave.", Color(0.85, 0.2, 0.25), "ball", _show_quick))
	var career_sub := "Lleva a tu club en LaLiga: 38 jornadas, alineaciones y clasificación."
	if GameData.has_career():
		career_sub = "Continuar: %s, jornada %d." % [GameData.user_team().name, mini(int(GameData.career.round) + 1, 38)]
	cards.add_child(_card("MODO CARRERA", career_sub, Color(0.95, 0.7, 0.15), "trophy", _show_career))
	cards.add_child(_card("ENTRENAMIENTO", "Practica cualquiera de las %d jugadas: tiros libres, penales, contras..." % Jugadas.all().size(), Color(0.2, 0.6, 0.95), "cone", _show_training))
	var spacer2 := Control.new()
	UI.expand(spacer2, true, true)
	vb.add_child(spacer2)
	var foot := UI.label("Jugadas: %d  ·  Goles en jugadas clave: %d" % [int(GameData.stats.played), int(GameData.stats.goals)], 18, UI.TEXT_DIM, HORIZONTAL_ALIGNMENT_CENTER)
	vb.add_child(foot)


func _card(title: String, sub: String, color: Color, icon: String, cb: Callable) -> Control:
	var b := Button.new()
	b.custom_minimum_size = Vector2(340, 300)
	b.add_theme_stylebox_override("normal", UI.style(Color(0.05, 0.08, 0.13, 0.88), 22, color, 3, 18))
	b.add_theme_stylebox_override("hover", UI.style(Color(0.08, 0.12, 0.2, 0.95), 22, color.lightened(0.2), 4, 18))
	b.add_theme_stylebox_override("pressed", UI.style(color.darkened(0.6), 22, color, 4, 18))
	b.add_theme_stylebox_override("focus", UI.style(Color(0, 0, 0, 0), 22, Color(1, 1, 1, 0.4), 2, 18))
	b.pressed.connect(cb)
	var vb := UI.vbox(10)
	vb.mouse_filter = Control.MOUSE_FILTER_IGNORE
	b.add_child(vb)
	UI.fill(vb)
	vb.offset_left = 18
	vb.offset_right = -18
	vb.offset_top = 18
	vb.offset_bottom = -18
	var ic := Control.new()
	ic.custom_minimum_size = Vector2(0, 120)
	ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ic.draw.connect(_draw_icon.bind(ic, icon, color))
	vb.add_child(ic)
	var t := UI.label(title, 30, Color.WHITE, HORIZONTAL_ALIGNMENT_CENTER)
	t.mouse_filter = Control.MOUSE_FILTER_IGNORE
	vb.add_child(t)
	var s := UI.label(sub, 17, UI.TEXT_DIM, HORIZONTAL_ALIGNMENT_CENTER)
	s.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	s.mouse_filter = Control.MOUSE_FILTER_IGNORE
	vb.add_child(s)
	return b


func _draw_icon(c: Control, icon: String, color: Color) -> void:
	var ctr := Vector2(c.size.x / 2, c.size.y / 2)
	match icon:
		"ball":
			c.draw_circle(ctr, 48, Color.WHITE)
			c.draw_arc(ctr, 48, 0, TAU, 48, Color(0.1, 0.1, 0.1), 4, true)
			var pts := PackedVector2Array()
			for i in 5:
				var a := -PI / 2 + i * TAU / 5
				pts.append(ctr + Vector2(cos(a), sin(a)) * 18)
			c.draw_colored_polygon(pts, Color(0.1, 0.1, 0.1))
			for i in 5:
				var a2 := -PI / 2 + i * TAU / 5
				c.draw_line(ctr + Vector2(cos(a2), sin(a2)) * 18, ctr + Vector2(cos(a2), sin(a2)) * 46, Color(0.1, 0.1, 0.1), 4)
		"trophy":
			var cup := PackedVector2Array([ctr + Vector2(-36, -44), ctr + Vector2(36, -44), ctr + Vector2(28, -6), ctr + Vector2(10, 10),
				ctr + Vector2(-10, 10), ctr + Vector2(-28, -6)])
			c.draw_colored_polygon(cup, color)
			c.draw_arc(ctr + Vector2(-36, -28), 14, PI / 2, PI * 1.5, 16, color, 6)
			c.draw_arc(ctr + Vector2(36, -28), 14, -PI / 2, PI / 2, 16, color, 6)
			c.draw_rect(Rect2(ctr + Vector2(-6, 10), Vector2(12, 22)), color)
			c.draw_rect(Rect2(ctr + Vector2(-28, 32), Vector2(56, 12)), color.darkened(0.2))
		"cone":
			var cone := PackedVector2Array([ctr + Vector2(0, -50), ctr + Vector2(30, 36), ctr + Vector2(-30, 36)])
			c.draw_colored_polygon(cone, Color(1, 0.5, 0.1))
			c.draw_rect(Rect2(ctr + Vector2(-17, -8), Vector2(34, 10)), Color.WHITE)
			c.draw_rect(Rect2(ctr + Vector2(-40, 36), Vector2(80, 10)), Color(1, 0.5, 0.1).darkened(0.3))
			c.draw_circle(ctr + Vector2(52, 30), 14, Color.WHITE)


func _header(text: String, back: Callable) -> HBoxContainer:
	var h := UI.hbox(14)
	h.add_child(UI.button("< Volver", back, UI.GREY, Vector2(150, 56), 20))
	var t := UI.title(text, 38)
	UI.expand(t)
	h.add_child(t)
	return h


# ---------------------------------------------------------------- Selector de equipo

func _team_picker(state: Dictionary, key: String, label: String) -> Control:
	var p := UI.panel(Color(0.05, 0.08, 0.13, 0.9), 18, 16)
	p.custom_minimum_size = Vector2(400, 0)
	var vb := UI.vbox(10)
	p.add_child(vb)
	vb.add_child(UI.label(label, 20, UI.GOLD, HORIZONTAL_ALIGNMENT_CENTER))
	var row := UI.hbox(10)
	vb.add_child(row)
	var info := UI.vbox(6)
	UI.expand(info)
	var refresh := func():
		UI.clear(info)
		var t: Dictionary = GameData.teams[int(state[key])]
		var k := GameData.kit_colors(t)
		var chip := UI.color_chip(k.shirt, k.shorts, Vector2(70, 70))
		chip.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
		info.add_child(chip)
		info.add_child(UI.label(t.name, 26, UI.TEXT, HORIZONTAL_ALIGNMENT_CENTER))
		var r := GameData.team_rating(t)
		info.add_child(UI.label("Media del once: %d" % r, 18, UI.rating_color(r), HORIZONTAL_ALIGNMENT_CENTER))
		var stars := ""
		for i in 5:
			stars += "*" if r >= 66 + i * 4 else "·"
		info.add_child(UI.label(stars, 26, UI.GOLD, HORIZONTAL_ALIGNMENT_CENTER))
	row.add_child(UI.button("<", func():
		state[key] = (int(state[key]) - 1 + GameData.teams.size()) % GameData.teams.size()
		refresh.call(), UI.GREY, Vector2(60, 90), 30))
	row.add_child(info)
	row.add_child(UI.button(">", func():
		state[key] = (int(state[key]) + 1) % GameData.teams.size()
		refresh.call(), UI.GREY, Vector2(60, 90), 30))
	refresh.call()
	return p


# ---------------------------------------------------------------- Partido rápido

func _show_quick() -> void:
	var root := UI.margin(26)
	_set_screen(root)
	var vb := UI.vbox(16)
	root.add_child(vb)
	vb.add_child(_header("PARTIDO RÁPIDO", _show_main))
	var sp := Control.new()
	UI.expand(sp, true, true)
	vb.add_child(sp)
	var row := UI.hbox(30)
	row.alignment = BoxContainer.ALIGNMENT_CENTER
	vb.add_child(row)
	row.add_child(_team_picker(GameData.quick, "user", "TU EQUIPO (LOCAL)"))
	row.add_child(UI.label("VS", 40, UI.TEXT_DIM))
	row.add_child(_team_picker(GameData.quick, "rival", "RIVAL (VISITANTE)"))
	var sp2 := Control.new()
	UI.expand(sp2, true, true)
	vb.add_child(sp2)
	var go := UI.button("Elegir alineación", _quick_lineup, UI.GREEN, Vector2(360, 70), 26)
	go.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	vb.add_child(go)


func _quick_lineup() -> void:
	if int(GameData.quick.user) == int(GameData.quick.rival):
		GameData.quick.rival = (int(GameData.quick.user) + 1) % GameData.teams.size()
	_quick_team = GameData.teams[int(GameData.quick.user)].duplicate(true)
	var team: Dictionary = _quick_team
	for p in team.players:
		p.energy = 100.0
	GameData.auto_lineup(team)
	var bg := Panel.new()
	bg.add_theme_stylebox_override("panel", UI.style(Color(0.03, 0.05, 0.09, 0.96), 0, Color(0, 0, 0, 0), 0, 0))
	_set_screen(bg)
	var lp := LineupPanel.new()
	lp.setup(team, null, 0, "¡A jugar!")
	bg.add_child(lp)
	lp.done.connect(_start_quick)


var _quick_team: Dictionary = {}


func _start_quick() -> void:
	var ut: Dictionary = _quick_team
	var rt: Dictionary = GameData.teams[int(GameData.quick.rival)].duplicate(true)
	for p in rt.players:
		p.energy = 100.0
	var s := MatchSim.new()
	s.setup(ut, rt, true, "quick")
	GameData.sim = s
	get_tree().change_scene_to_file("res://scenes/sim.tscn")


# ---------------------------------------------------------------- Modo carrera

var _career_pick := {"team": 0}


func _show_career() -> void:
	var root := UI.margin(26)
	_set_screen(root)
	var vb := UI.vbox(16)
	root.add_child(vb)
	vb.add_child(_header("MODO CARRERA", _show_main))
	var sp := Control.new()
	UI.expand(sp, true, true)
	vb.add_child(sp)
	var row := UI.hbox(30)
	row.alignment = BoxContainer.ALIGNMENT_CENTER
	vb.add_child(row)
	if GameData.has_career():
		var cont := UI.panel(Color(0.05, 0.08, 0.13, 0.9), 18, 22)
		cont.custom_minimum_size = Vector2(420, 0)
		row.add_child(cont)
		var cv := UI.vbox(12)
		cont.add_child(cv)
		var t := GameData.user_team()
		cv.add_child(UI.label("PARTIDA GUARDADA", 20, UI.GOLD, HORIZONTAL_ALIGNMENT_CENTER))
		cv.add_child(UI.label(t.name, 30, UI.TEXT, HORIZONTAL_ALIGNMENT_CENTER))
		cv.add_child(UI.label("Jornada %d · %dº en la tabla" % [mini(int(GameData.career.round) + 1, 38), GameData.table_position(int(t.id))], 20, UI.TEXT_DIM, HORIZONTAL_ALIGNMENT_CENTER))
		cv.add_child(UI.button("Continuar carrera", func(): get_tree().change_scene_to_file("res://scenes/career.tscn"), UI.GREEN, Vector2(0, 66), 24))
	var newp := UI.vbox(12)
	row.add_child(newp)
	newp.add_child(_team_picker(_career_pick, "team", "NUEVA CARRERA: ELIGE TU CLUB"))
	var warn := "Empezar una nueva carrera borrará la partida guardada." if GameData.has_career() else "Se crearán plantillas nuevas para los 20 equipos."
	newp.add_child(UI.label(warn, 16, UI.TEXT_DIM, HORIZONTAL_ALIGNMENT_CENTER))
	newp.add_child(UI.button("Empezar carrera", _new_career, UI.GOLD.darkened(0.25), Vector2(0, 62), 24))
	var sp2 := Control.new()
	UI.expand(sp2, true, true)
	vb.add_child(sp2)


func _new_career() -> void:
	GameData.new_career(int(_career_pick.team))
	get_tree().change_scene_to_file("res://scenes/career.tscn")


# ---------------------------------------------------------------- Entrenamiento

var _train := {"team": 0}


func _show_training() -> void:
	if GameData.has_career():
		_train.team = int(GameData.career.team_id)
	var root := UI.margin(22)
	_set_screen(root)
	var vb := UI.vbox(12)
	root.add_child(vb)
	vb.add_child(_header("ENTRENAMIENTO", _show_main))
	var row := UI.hbox(20)
	UI.expand(row, true, true)
	vb.add_child(row)
	row.add_child(_team_picker(_train, "team", "ENTRENA CON"))
	var right := UI.panel(Color(0.05, 0.08, 0.13, 0.9), 18, 16)
	UI.expand(right, true, true)
	row.add_child(right)
	var rv := UI.vbox(10)
	right.add_child(rv)
	rv.add_child(UI.label("ELIGE QUÉ PRACTICAR", 20, UI.GOLD))
	var grid := GridContainer.new()
	grid.columns = 3
	grid.add_theme_constant_override("h_separation", 10)
	grid.add_theme_constant_override("v_separation", 10)
	UI.expand(grid, true, true)
	rv.add_child(grid)
	for g in Jugadas.GROUP_NAMES:
		var n := Jugadas.by_group(g).size()
		var col := UI.BLUE if g in Jugadas.DEFEND_GROUPS or g == "penal_contra" else (UI.GOLD.darkened(0.35) if g in ["falta", "penal", "corner"] else UI.RED.darkened(0.1))
		var b := UI.button("%s (%d)" % [Jugadas.GROUP_NAMES[g], n], _start_training.bind(g), col, Vector2(0, 62), 18)
		UI.expand(b)
		grid.add_child(b)
	var all_b := UI.button("Jugada al azar (%d en total)" % Jugadas.all().size(), _start_training.bind(""), UI.GREEN, Vector2(0, 58), 20)
	rv.add_child(all_b)


func _start_training(group: String) -> void:
	var ut: Dictionary = GameData.teams[int(_train.team)].duplicate(true)
	for p in ut.players:
		p.energy = maxf(float(p.energy), 90.0)
	var rt: Dictionary = GameData.teams[(int(ut.id) + 1 + randi() % (GameData.teams.size() - 1)) % GameData.teams.size()].duplicate(true)
	var pool: Array = Jugadas.by_group(group) if group != "" else Jugadas.all()
	GameData.training_team = int(ut.id)
	GameData.moment = GameData.build_moment(pool[randi() % pool.size()], ut, rt, "training")
	GameData.moment["training_group"] = group
	get_tree().change_scene_to_file("res://scenes/match.tscn")

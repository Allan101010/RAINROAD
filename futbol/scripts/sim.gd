extends Control
## Pantalla del partido simulado: marcador, minuto, comentarios, estadísticas,
## energía de tus jugadores, cambios y aviso de jugadas clave (jugar o simular).

const SPEEDS := [0.9, 0.45, 0.18]
const SPEED_NAMES := ["x1", "x2", "x4"]

var sim: MatchSim
var speed_i := 1
var paused := false
var _acc := 0.0
var _score_lbl: Label
var _minute_lbl: Label
var _progress: ProgressBar
var _feed: VBoxContainer
var _stats_box: VBoxContainer
var _team_box: VBoxContainer
var _speed_btn: Button
var _pause_btn: Button
var _overlay: Control
var _last_event_count := 0
var _scorers_lbl: Label


func _ready() -> void:
	sim = GameData.sim
	if sim == null:
		get_tree().change_scene_to_file.call_deferred("res://scenes/menu.tscn")
		return
	UI.fill(self)
	UI.background(self, Color(0.05, 0.12, 0.1), Color(0.02, 0.03, 0.07))
	_build()
	if not GameData.moment_result.is_empty() and not sim.pending.is_empty():
		sim.apply_result(GameData.moment_result)
		GameData.moment_result = {}
		GameData.moment = {}
	_refresh(true)


func _build() -> void:
	var root := UI.margin(14)
	add_child(root)
	UI.fill(root)
	var vb := UI.vbox(10)
	root.add_child(vb)

	# Marcador
	var board := UI.panel(Color(0.04, 0.06, 0.1, 0.95), 16, 12)
	vb.add_child(board)
	var bh := UI.hbox(16)
	board.add_child(bh)
	var home_t: Dictionary = sim.teams[0]
	var away_t: Dictionary = sim.teams[1]
	var hk := GameData.kit_colors(home_t)
	var ak: Dictionary = GameData.kits_for(home_t, away_t)[1]
	var hn := UI.hbox(10)
	UI.expand(hn)
	hn.alignment = BoxContainer.ALIGNMENT_END
	hn.add_child(UI.label(home_t.name + (" (Tú)" if sim.user_side == 0 else ""), 28, UI.TEXT))
	hn.add_child(UI.color_chip(hk.shirt, hk.shorts, Vector2(30, 30)))
	bh.add_child(hn)
	_score_lbl = UI.label("0 - 0", 44, UI.GOLD, HORIZONTAL_ALIGNMENT_CENTER)
	_score_lbl.custom_minimum_size = Vector2(150, 0)
	bh.add_child(_score_lbl)
	var an := UI.hbox(10)
	UI.expand(an)
	an.add_child(UI.color_chip(ak.shirt, ak.shorts, Vector2(30, 30)))
	an.add_child(UI.label(away_t.name + (" (Tú)" if sim.user_side == 1 else ""), 28, UI.TEXT))
	bh.add_child(an)
	_minute_lbl = UI.label("0'", 30, UI.TEXT, HORIZONTAL_ALIGNMENT_CENTER)
	_minute_lbl.custom_minimum_size = Vector2(110, 0)
	bh.add_child(_minute_lbl)

	_progress = ProgressBar.new()
	_progress.max_value = 95
	_progress.show_percentage = false
	_progress.custom_minimum_size = Vector2(0, 8)
	_progress.add_theme_stylebox_override("background", UI.style(Color(0, 0, 0, 0.5), 4, Color(0, 0, 0, 0), 0, 0))
	_progress.add_theme_stylebox_override("fill", UI.style(UI.GOLD, 4, Color(0, 0, 0, 0), 0, 0))
	vb.add_child(_progress)
	_scorers_lbl = UI.label("", 16, UI.TEXT_DIM, HORIZONTAL_ALIGNMENT_CENTER)
	vb.add_child(_scorers_lbl)

	# Cuerpo: comentarios | estadísticas y equipo
	var body := UI.hbox(12)
	UI.expand(body, true, true)
	vb.add_child(body)
	var feed_panel := UI.panel(UI.PANEL, 14, 12)
	UI.expand(feed_panel, true, true)
	body.add_child(feed_panel)
	var fv := UI.vbox(6)
	feed_panel.add_child(fv)
	fv.add_child(UI.label("EN DIRECTO", 18, UI.GOLD))
	var scroll := ScrollContainer.new()
	UI.expand(scroll, true, true)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	fv.add_child(scroll)
	_feed = UI.vbox(6)
	UI.expand(_feed)
	scroll.add_child(_feed)

	var side := UI.vbox(10)
	side.custom_minimum_size = Vector2(380, 0)
	body.add_child(side)
	var sp := UI.panel(UI.PANEL, 14, 12)
	side.add_child(sp)
	_stats_box = UI.vbox(4)
	sp.add_child(_stats_box)
	var tp := UI.panel(UI.PANEL, 14, 12)
	UI.expand(tp, false, true)
	side.add_child(tp)
	var tv := UI.vbox(4)
	tp.add_child(tv)
	tv.add_child(UI.label("TU EQUIPO · ENERGÍA", 16, UI.GOLD))
	var ts := ScrollContainer.new()
	UI.expand(ts, true, true)
	tv.add_child(ts)
	_team_box = UI.vbox(3)
	UI.expand(_team_box)
	ts.add_child(_team_box)

	# Botones
	var bar := UI.hbox(12)
	vb.add_child(bar)
	_speed_btn = UI.button("Velocidad x2", _toggle_speed, UI.GREY, Vector2(200, 58), 22)
	bar.add_child(_speed_btn)
	_pause_btn = UI.button("Pausa", _toggle_pause, UI.GREY, Vector2(160, 58), 22)
	bar.add_child(_pause_btn)
	bar.add_child(UI.button("Cambios", _open_subs, UI.BLUE, Vector2(160, 58), 22))
	var spacer := Control.new()
	UI.expand(spacer)
	bar.add_child(spacer)
	bar.add_child(UI.button("Abandonar", _abandon, Color(0.4, 0.15, 0.15), Vector2(160, 58), 20))


func _process(delta: float) -> void:
	if sim == null or _overlay != null:
		return
	if not sim.pending.is_empty():
		_show_moment()
		return
	if sim.halftime_pending:
		_show_halftime()
		return
	if sim.finished:
		_show_final()
		return
	if paused:
		return
	_acc += delta
	if _acc >= SPEEDS[speed_i]:
		_acc = 0.0
		sim.step()
		_refresh()


func _refresh(full := false) -> void:
	_score_lbl.text = "%d - %d" % [sim.score[0], sim.score[1]]
	_minute_lbl.text = sim.minute_label()
	_progress.value = sim.minute if sim.half == 2 or sim.minute <= 45 else 45
	var parts: PackedStringArray = []
	for s in sim.scorers:
		parts.append("%s %d'" % [s.name, s.min])
	_scorers_lbl.text = "Goles: " + ", ".join(parts) if parts.size() > 0 else ""
	# Comentarios nuevos arriba
	if full:
		UI.clear(_feed)
		_last_event_count = 0
	for i in range(_last_event_count, sim.events.size()):
		var e: Dictionary = sim.events[i]
		_feed.add_child(_event_row(e))
		_feed.move_child(_feed.get_child(_feed.get_child_count() - 1), 0)
	_last_event_count = sim.events.size()
	# Estadísticas
	UI.clear(_stats_box)
	_stats_box.add_child(UI.label("ESTADÍSTICAS", 16, UI.GOLD))
	var poss := sim.possession()
	var st: Dictionary = sim.stats
	for row in [["Posesión", "%d%%" % poss[0], "%d%%" % poss[1]], ["Tiros", str(st.shots[0]), str(st.shots[1])],
			["A puerta", str(st.on_target[0]), str(st.on_target[1])], ["Córners", str(st.corners[0]), str(st.corners[1])],
			["Faltas", str(st.fouls[0]), str(st.fouls[1])]]:
		var h := UI.hbox(6)
		var l1 := UI.label(row[1], 17, UI.TEXT, HORIZONTAL_ALIGNMENT_LEFT)
		l1.custom_minimum_size = Vector2(60, 0)
		var lm := UI.label(row[0], 15, UI.TEXT_DIM, HORIZONTAL_ALIGNMENT_CENTER)
		UI.expand(lm)
		var l2 := UI.label(row[2], 17, UI.TEXT, HORIZONTAL_ALIGNMENT_RIGHT)
		l2.custom_minimum_size = Vector2(60, 0)
		h.add_child(l1)
		h.add_child(lm)
		h.add_child(l2)
		_stats_box.add_child(h)
	# Energía del equipo del usuario
	UI.clear(_team_box)
	var u := sim.user_side
	for i in sim.xi[u].size():
		var p: Dictionary = sim.xi[u][i]
		var h2 := UI.hbox(6)
		var pl := UI.label(sim.slots[u][i], 13, UI.GOLD)
		pl.custom_minimum_size = Vector2(40, 0)
		h2.add_child(pl)
		var nl := UI.label(p.name, 14, UI.TEXT)
		nl.clip_text = true
		UI.expand(nl)
		h2.add_child(nl)
		var b := UI.bar(float(p.energy), 90, 9)
		b.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		h2.add_child(b)
		_team_box.add_child(h2)


func _event_row(e: Dictionary) -> Control:
	var col := UI.TEXT
	var size := 18
	match e.type:
		"goal":
			col = UI.GOLD
			size = 21
		"moment":
			col = Color(0.5, 0.85, 1.0)
		"half", "end":
			col = Color(0.6, 1.0, 0.6)
		"sub":
			col = UI.TEXT_DIM
		"info":
			col = UI.TEXT_DIM
	var l := UI.label("%s'  %s" % [str(e.min), e.text], size, col)
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	return l


func _toggle_speed() -> void:
	speed_i = (speed_i + 1) % SPEEDS.size()
	_speed_btn.text = "Velocidad " + SPEED_NAMES[speed_i]


func _toggle_pause() -> void:
	paused = not paused
	_pause_btn.text = "Seguir" if paused else "Pausa"


func _open_subs() -> void:
	var was_paused := paused
	paused = true
	var layer := _make_overlay(0.75)
	var lp := LineupPanel.new()
	lp.setup(sim.user_team(), sim, sim.user_side, "Volver")
	layer.add_child(lp)
	lp.done.connect(func():
		_close_overlay()
		paused = was_paused
		_refresh())


func _make_overlay(alpha := 0.8) -> Control:
	_close_overlay()
	var o := Control.new()
	add_child(o)
	UI.fill(o)
	var dim := ColorRect.new()
	dim.color = Color(0, 0, 0, alpha)
	o.add_child(dim)
	UI.fill(dim)
	_overlay = o
	return o


func _close_overlay() -> void:
	if _overlay and is_instance_valid(_overlay):
		_overlay.queue_free()
	_overlay = null


func _center_card(o: Control, color: Color) -> VBoxContainer:
	var cc := CenterContainer.new()
	o.add_child(cc)
	UI.fill(cc)
	var p := UI.panel(Color(0.05, 0.08, 0.13, 0.97), 20, 26)
	p.add_theme_stylebox_override("panel", UI.style(Color(0.05, 0.08, 0.13, 0.97), 20, color, 4, 26))
	cc.add_child(p)
	var vb := UI.vbox(14)
	vb.custom_minimum_size = Vector2(620, 0)
	p.add_child(vb)
	return vb


func _show_moment() -> void:
	var o := _make_overlay(0.6)
	var pend: Dictionary = sim.pending
	var attack: bool = pend.kind in ["attack", "freekick", "penalty_for", "corner"]
	var vb := _center_card(o, UI.GOLD if attack else UI.RED)
	vb.add_child(UI.label("¡JUGADA CLAVE!  ·  " + sim.minute_label(), 34, UI.GOLD, HORIZONTAL_ALIGNMENT_CENTER))
	var t := UI.label(pend.text, 22, UI.TEXT, HORIZONTAL_ALIGNMENT_CENTER)
	t.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	vb.add_child(t)
	var j := UI.label(pend.jugada.name, 24, Color(0.5, 0.85, 1.0) if attack else Color(1, 0.6, 0.5), HORIZONTAL_ALIGNMENT_CENTER)
	j.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	vb.add_child(j)
	var hint := {"attack": "Ataca y marca", "corner": "Remata el córner de cabeza (TIRO cuando llegue el balón)",
		"defend": "Defiende: presiona, barre y recupera el balón", "freekick": "Apunta, elige el efecto y patea",
		"penalty_for": "Apunta y patea el penal", "penalty_against": "Eres el portero: elige hacia dónde lanzarte"}
	vb.add_child(UI.label(hint.get(pend.kind, ""), 18, UI.TEXT_DIM, HORIZONTAL_ALIGNMENT_CENTER))
	var hb := UI.hbox(14)
	hb.alignment = BoxContainer.ALIGNMENT_CENTER
	vb.add_child(hb)
	hb.add_child(UI.button("JUGAR", _play_moment, UI.GREEN, Vector2(220, 70), 28))
	hb.add_child(UI.button("Simular", _simulate_moment, UI.GREY, Vector2(180, 70), 22))


func _play_moment() -> void:
	GameData.moment = sim.moment_payload()
	GameData.moment_result = {}
	get_tree().change_scene_to_file("res://scenes/match.tscn")


func _simulate_moment() -> void:
	sim.auto_resolve()
	_close_overlay()
	_refresh()


func _show_halftime() -> void:
	var o := _make_overlay(0.6)
	var vb := _center_card(o, UI.GREEN)
	vb.add_child(UI.label("DESCANSO", 40, UI.GOLD, HORIZONTAL_ALIGNMENT_CENTER))
	vb.add_child(UI.label("%s %d - %d %s" % [sim.teams[0].name, sim.score[0], sim.score[1], sim.teams[1].name], 26, UI.TEXT, HORIZONTAL_ALIGNMENT_CENTER))
	vb.add_child(UI.label("Revisa la energía de tus jugadores y haz cambios si hace falta.", 18, UI.TEXT_DIM, HORIZONTAL_ALIGNMENT_CENTER))
	var hb := UI.hbox(14)
	hb.alignment = BoxContainer.ALIGNMENT_CENTER
	vb.add_child(hb)
	hb.add_child(UI.button("Segundo tiempo", func():
		sim.halftime_pending = false
		_close_overlay()
		_refresh(), UI.GREEN, Vector2(240, 66), 24))
	hb.add_child(UI.button("Cambios", func():
		sim.halftime_pending = false
		_close_overlay()
		paused = true
		_pause_btn.text = "Seguir"
		_open_subs(), UI.BLUE, Vector2(180, 66), 22))


func _show_final() -> void:
	var o := _make_overlay(0.6)
	var u := sim.user_side
	var res := signi(sim.score[u] - sim.score[1 - u])
	var col: Color = [UI.RED, UI.GOLD, UI.GREEN][res + 1]
	var vb := _center_card(o, col)
	vb.add_child(UI.label("FINAL DEL PARTIDO", 36, UI.GOLD, HORIZONTAL_ALIGNMENT_CENTER))
	vb.add_child(UI.label("%s %d - %d %s" % [sim.teams[0].name, sim.score[0], sim.score[1], sim.teams[1].name], 28, UI.TEXT, HORIZONTAL_ALIGNMENT_CENTER))
	vb.add_child(UI.label(["Derrota · 0 puntos", "Empate · 1 punto", "¡Victoria! · 3 puntos"][res + 1], 26, col, HORIZONTAL_ALIGNMENT_CENTER))
	var parts: PackedStringArray = []
	for s in sim.scorers:
		parts.append("%s (%s) %d'" % [s.name, sim.teams[s.side].short, s.min])
	if parts.size() > 0:
		var g := UI.label("Goles: " + ", ".join(parts), 17, UI.TEXT_DIM, HORIZONTAL_ALIGNMENT_CENTER)
		g.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		vb.add_child(g)
	vb.add_child(UI.label("Jugadas clave jugadas: %d" % sim.moments_played, 16, UI.TEXT_DIM, HORIZONTAL_ALIGNMENT_CENTER))
	vb.add_child(UI.button("Continuar", _after_match, UI.GREEN, Vector2(240, 66), 24))


func _after_match() -> void:
	if sim.context == "career":
		GameData.finish_round(sim.score[0], sim.score[1])
		GameData.sim = null
		get_tree().change_scene_to_file("res://scenes/career.tscn")
	else:
		GameData.sim = null
		get_tree().change_scene_to_file("res://scenes/menu.tscn")


func _abandon() -> void:
	var o := _make_overlay(0.6)
	var vb := _center_card(o, UI.RED)
	vb.add_child(UI.label("¿Abandonar el partido?", 30, UI.TEXT, HORIZONTAL_ALIGNMENT_CENTER))
	var msg := "Se simulará el resto del partido sin jugadas clave." if sim.context == "career" else "Volverás al menú principal."
	vb.add_child(UI.label(msg, 18, UI.TEXT_DIM, HORIZONTAL_ALIGNMENT_CENTER))
	var hb := UI.hbox(14)
	hb.alignment = BoxContainer.ALIGNMENT_CENTER
	vb.add_child(hb)
	hb.add_child(UI.button("Sí", func():
		_close_overlay()
		if sim.context == "career":
			while not sim.finished:
				if not sim.pending.is_empty():
					sim.auto_resolve()
				sim.halftime_pending = false
				sim.step()
			_refresh()
		else:
			GameData.sim = null
			get_tree().change_scene_to_file("res://scenes/menu.tscn"), UI.RED, Vector2(140, 60)))
	hb.add_child(UI.button("No", _close_overlay, UI.GREY, Vector2(140, 60)))

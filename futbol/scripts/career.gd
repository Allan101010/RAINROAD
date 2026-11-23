extends Control
## Centro del modo carrera: próximo partido, clasificación, calendario, alineación,
## entrenamiento semanal y guardado.

var _content: Control
var _tab := "inicio"


func _ready() -> void:
	if not GameData.has_career():
		get_tree().change_scene_to_file.call_deferred("res://scenes/menu.tscn")
		return
	UI.fill(self)
	UI.background(self, Color(0.06, 0.14, 0.2), Color(0.02, 0.03, 0.07))
	var root := UI.margin(14)
	add_child(root)
	UI.fill(root)
	var vb := UI.vbox(10)
	root.add_child(vb)

	var team := GameData.user_team()
	var head := UI.hbox(12)
	vb.add_child(head)
	var k := GameData.kit_colors(team)
	head.add_child(UI.color_chip(k.shirt, k.shorts, Vector2(44, 44)))
	var tv := UI.vbox(0)
	UI.expand(tv)
	head.add_child(tv)
	tv.add_child(UI.title(team.name, 34))
	var pos := GameData.table_position(int(team.id))
	var row: Dictionary = GameData.career.table[str(team.id)]
	var pos_txt := "%dº con %d puntos" % [pos, int(row.pts)] if int(row.pj) > 0 else "la liga está por empezar"
	tv.add_child(UI.label("LaLiga %d/%d  ·  Jornada %d de 38  ·  %s" % [int(GameData.career.season), int(GameData.career.season) + 1,
		mini(int(GameData.career.round) + 1, 38), pos_txt], 18, UI.TEXT_DIM))
	head.add_child(UI.button("Guardar y salir", _save_exit, UI.GREY, Vector2(200, 56), 20))

	var tabs := UI.hbox(8)
	vb.add_child(tabs)
	for t in [["inicio", "Inicio"], ["alineacion", "Alineación"], ["tabla", "Clasificación"], ["calendario", "Calendario"], ["entreno", "Entrenamiento"]]:
		var b := UI.button(t[1], _set_tab.bind(t[0]), UI.BLUE if _tab == t[0] else UI.GREY, Vector2(0, 52), 20)
		UI.expand(b)
		tabs.add_child(b)

	_content = Control.new()
	UI.expand(_content, true, true)
	vb.add_child(_content)
	_show_tab()


func _set_tab(t: String) -> void:
	_tab = t
	GameData.save_career()
	get_tree().reload_current_scene.call_deferred()
	_pending_tab = t


static var _pending_tab := ""


func _enter_tree() -> void:
	if _pending_tab != "":
		_tab = _pending_tab
		_pending_tab = ""


func _show_tab() -> void:
	UI.clear(_content)
	match _tab:
		"inicio":
			_tab_home()
		"alineacion":
			var lp := LineupPanel.new()
			lp.setup(GameData.user_team(), null, 0, "Guardar")
			_content.add_child(lp)
			lp.done.connect(func():
				GameData.save_career()
				_set_tab("inicio"))
		"tabla":
			_tab_table()
		"calendario":
			_tab_calendar()
		"entreno":
			_tab_training()


func _tab_home() -> void:
	var hb := UI.hbox(14)
	_content.add_child(hb)
	UI.fill(hb)
	var left := UI.panel(UI.PANEL, 18, 22)
	UI.expand(left, true, true)
	hb.add_child(left)
	var lv := UI.vbox(14)
	left.add_child(lv)
	if GameData.season_over():
		var rows := GameData.sorted_table()
		var champ := GameData.team_by_id(rows[0].id)
		lv.add_child(UI.title("¡FIN DE LA TEMPORADA!", 36))
		lv.add_child(UI.label("Campeón: %s" % champ.name, 28, UI.TEXT))
		lv.add_child(UI.label("Tu equipo terminó en la posición %d." % GameData.table_position(int(GameData.career.team_id)), 24, UI.TEXT_DIM))
		lv.add_child(UI.button("Empezar nueva temporada", func():
			GameData.new_season()
			get_tree().reload_current_scene(), UI.GREEN, Vector2(0, 70), 26))
	else:
		var fx := GameData.current_fixture()
		var ht := GameData.team_by_id(fx[0])
		var at := GameData.team_by_id(fx[1])
		var me := GameData.user_team()
		var rival := at if int(ht.id) == int(me.id) else ht
		lv.add_child(UI.label("PRÓXIMO PARTIDO · JORNADA %d" % (int(GameData.career.round) + 1), 20, UI.GOLD))
		var vs := UI.hbox(16)
		vs.alignment = BoxContainer.ALIGNMENT_CENTER
		lv.add_child(vs)
		vs.add_child(_team_badge(ht))
		vs.add_child(UI.label("vs", 30, UI.TEXT_DIM))
		vs.add_child(_team_badge(at))
		lv.add_child(UI.label("Juegas de %s. Rival: %dº en la tabla." % ["local" if int(ht.id) == int(me.id) else "visitante",
			GameData.table_position(int(rival.id))], 20, UI.TEXT_DIM, HORIZONTAL_ALIGNMENT_CENTER))
		var tired := GameData.lineup_players(me).filter(func(p): return float(p.energy) < 60).size()
		if tired > 0:
			lv.add_child(UI.label("Ojo: %d titulares con poca energía. Revisa la alineación." % tired, 18, UI.GOLD, HORIZONTAL_ALIGNMENT_CENTER))
		lv.add_child(UI.button("JUGAR PARTIDO", _play_match, UI.GREEN, Vector2(0, 76), 30))
		lv.add_child(UI.button("Simular partido completo", _sim_full, UI.GREY, Vector2(0, 56), 20))
	# Resultados de la última jornada
	var right := UI.panel(UI.PANEL, 18, 16)
	right.custom_minimum_size = Vector2(440, 0)
	UI.expand(right, false, true)
	hb.add_child(right)
	var rv := UI.vbox(6)
	right.add_child(rv)
	rv.add_child(UI.label("ÚLTIMA JORNADA", 18, UI.GOLD))
	var last: Array = GameData.career.get("last_round", [])
	if last.is_empty():
		rv.add_child(UI.label("Aún no se ha jugado ninguna jornada.", 17, UI.TEXT_DIM))
	for r in last:
		var mine := int(r[0]) == int(GameData.career.team_id) or int(r[1]) == int(GameData.career.team_id)
		var l := UI.label("%s  %d - %d  %s" % [GameData.team_by_id(r[0]).short, int(r[2]), int(r[3]), GameData.team_by_id(r[1]).short], 18, UI.GOLD if mine else UI.TEXT)
		rv.add_child(l)
	rv.add_child(UI.label("", 8))
	rv.add_child(UI.label("MÁXIMOS GOLEADORES DE TU EQUIPO", 16, UI.GOLD))
	var squad: Array = GameData.user_team().players.duplicate()
	squad.sort_custom(func(a, b): return int(a.goals) > int(b.goals))
	for p in squad.slice(0, 4):
		if int(p.goals) > 0:
			rv.add_child(UI.label("%s · %d goles" % [p.name, int(p.goals)], 16, UI.TEXT))


func _team_badge(t: Dictionary) -> Control:
	var vb := UI.vbox(6)
	vb.custom_minimum_size = Vector2(240, 0)
	var k := GameData.kit_colors(t)
	var chip := UI.color_chip(k.shirt, k.shorts, Vector2(64, 64))
	chip.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	vb.add_child(chip)
	vb.add_child(UI.label(t.name, 24, UI.TEXT, HORIZONTAL_ALIGNMENT_CENTER))
	vb.add_child(UI.label("Media %d" % GameData.team_rating(t), 18, UI.rating_color(GameData.team_rating(t)), HORIZONTAL_ALIGNMENT_CENTER))
	return vb


func _tab_table() -> void:
	var p := UI.panel(UI.PANEL, 16, 12)
	_content.add_child(p)
	UI.fill(p)
	var scroll := ScrollContainer.new()
	p.add_child(scroll)
	var grid := GridContainer.new()
	grid.columns = 10
	grid.add_theme_constant_override("h_separation", 22)
	grid.add_theme_constant_override("v_separation", 6)
	UI.expand(grid)
	scroll.add_child(grid)
	for h in ["#", "Equipo", "PJ", "G", "E", "P", "GF", "GC", "DG", "PTS"]:
		grid.add_child(UI.label(h, 18, UI.GOLD))
	var rows := GameData.sorted_table()
	for i in rows.size():
		var r: Dictionary = rows[i]
		var mine := int(r.id) == int(GameData.career.team_id)
		var col := UI.GOLD if mine else UI.TEXT
		if not mine and i < 4:
			col = Color(0.5, 0.85, 1.0)
		elif not mine and i >= 17:
			col = Color(1, 0.55, 0.5)
		var cells := [str(i + 1), GameData.team_by_id(r.id).name, str(int(r.pj)), str(int(r.g)), str(int(r.e)), str(int(r.p)),
			str(int(r.gf)), str(int(r.gc)), str(int(r.gf) - int(r.gc)), str(int(r.pts))]
		for c in cells:
			grid.add_child(UI.label(c, 18, col))


func _tab_calendar() -> void:
	var p := UI.panel(UI.PANEL, 16, 12)
	_content.add_child(p)
	UI.fill(p)
	var scroll := ScrollContainer.new()
	p.add_child(scroll)
	var vb := UI.vbox(4)
	UI.expand(vb)
	scroll.add_child(vb)
	var me := int(GameData.career.team_id)
	for r in GameData.career.fixtures.size():
		var line := ""
		for m in GameData.career.fixtures[r]:
			if int(m[0]) == me or int(m[1]) == me:
				var h := GameData.team_by_id(m[0])
				var a := GameData.team_by_id(m[1])
				var res := "  -  "
				if r < GameData.career.results.size():
					for x in GameData.career.results[r]:
						if int(x[0]) == int(m[0]) and int(x[1]) == int(m[1]):
							res = "%d - %d" % [int(x[2]), int(x[3])]
				line = "Jornada %2d:   %s   %s   %s" % [r + 1, h.name, res, a.name]
		var col := UI.GOLD if r == int(GameData.career.round) else (UI.TEXT if r < int(GameData.career.round) else UI.TEXT_DIM)
		vb.add_child(UI.label(line, 18, col))


func _tab_training() -> void:
	var p := UI.panel(UI.PANEL, 18, 22)
	_content.add_child(p)
	UI.fill(p)
	var vb := UI.vbox(14)
	p.add_child(vb)
	vb.add_child(UI.label("ENTRENAMIENTO SEMANAL", 22, UI.GOLD))
	vb.add_child(UI.label("Decide cómo entrena tu plantilla entre jornada y jornada.", 18, UI.TEXT_DIM))
	var opts := [["suave", "Suave", "Recuperan mucha energía (+34) y mejora el ánimo."],
		["normal", "Normal", "Recuperación equilibrada (+26)."],
		["intenso", "Intenso", "Recuperan menos (+16) pero algunos jugadores mejoran sus atributos."]]
	for o in opts:
		var hb := UI.hbox(14)
		vb.add_child(hb)
		var sel: bool = GameData.career.training == o[0]
		hb.add_child(UI.button(("● " if sel else "") + o[1], func():
			GameData.career.training = o[0]
			GameData.save_career()
			_show_tab(), UI.GREEN if sel else UI.GREY, Vector2(200, 60), 22))
		var l := UI.label(o[2], 18, UI.TEXT)
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		UI.expand(l)
		hb.add_child(l)
	vb.add_child(UI.label("Para practicar jugadas usa «Entrenamiento» en el menú principal.", 16, UI.TEXT_DIM))


func _play_match() -> void:
	var fx := GameData.current_fixture()
	var me := int(GameData.career.team_id)
	var s := MatchSim.new()
	s.setup(GameData.team_by_id(fx[0]), GameData.team_by_id(fx[1]), int(fx[0]) == me, "career")
	GameData.sim = s
	GameData.save_career()
	get_tree().change_scene_to_file("res://scenes/sim.tscn")


func _sim_full() -> void:
	var fx := GameData.current_fixture()
	var me := int(GameData.career.team_id)
	var s := MatchSim.new()
	s.setup(GameData.team_by_id(fx[0]), GameData.team_by_id(fx[1]), int(fx[0]) == me, "career")
	while not s.finished:
		if not s.pending.is_empty():
			s.auto_resolve()
		s.halftime_pending = false
		s.step()
	GameData.finish_round(s.score[0], s.score[1])
	_set_tab("inicio")


func _save_exit() -> void:
	GameData.save_career()
	get_tree().change_scene_to_file("res://scenes/menu.tscn")

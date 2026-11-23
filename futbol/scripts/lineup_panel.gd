class_name LineupPanel
extends Control
## Editor de alineación: formación, once titular sobre el campo y suplentes.
## Toca un jugador y luego otro para intercambiarlos.
## En modo "subs" (durante el partido) solo se puede cambiar un titular por un suplente.

signal done

var team: Dictionary
var sim: MatchSim = null       # si no es null, estamos en modo cambios
var side := 0
var done_text := "Listo"
var _selected := {}            # {"where": "xi"/"bench", "i": índice}
var _pitch: Control
var _bench_box: VBoxContainer
var _info: Label
var _form_label: Label
var _subs_label: Label


func setup(t: Dictionary, match_sim: MatchSim = null, sim_side := 0, button_text := "Listo") -> void:
	team = t
	sim = match_sim
	side = sim_side
	done_text = button_text


func _ready() -> void:
	UI.fill(self)
	var root := UI.margin(16)
	add_child(root)
	UI.fill(root)
	var vb := UI.vbox(10)
	root.add_child(vb)

	var top := UI.hbox(10)
	vb.add_child(top)
	var title := UI.title(("CAMBIOS · " if sim else "ALINEACIÓN · ") + team.name, 30)
	UI.expand(title)
	top.add_child(title)
	if sim == null:
		top.add_child(UI.button("<", _prev_form, UI.GREY, Vector2(56, 52)))
		_form_label = UI.label(team.formation, 26, UI.TEXT, HORIZONTAL_ALIGNMENT_CENTER)
		_form_label.custom_minimum_size = Vector2(110, 0)
		top.add_child(_form_label)
		top.add_child(UI.button(">", _next_form, UI.GREY, Vector2(56, 52)))
		top.add_child(UI.button("Mejor XI", _best, UI.BLUE, Vector2(130, 52), 20))
	else:
		_subs_label = UI.label("", 22, UI.GOLD)
		top.add_child(_subs_label)
	top.add_child(UI.button(done_text, func(): done.emit(), UI.GREEN, Vector2(150, 52), 22))

	var body := UI.hbox(14)
	UI.expand(body, true, true)
	vb.add_child(body)
	_pitch = Control.new()
	_pitch.custom_minimum_size = Vector2(560, 0)
	UI.expand(_pitch, true, true)
	_pitch.draw.connect(_draw_pitch)
	_pitch.resized.connect(_refresh)
	body.add_child(_pitch)

	var right := UI.panel(UI.PANEL, 14, 10)
	right.custom_minimum_size = Vector2(420, 0)
	UI.expand(right, false, true)
	body.add_child(right)
	var rv := UI.vbox(6)
	right.add_child(rv)
	rv.add_child(UI.label("SUPLENTES", 20, UI.GOLD))
	var hdr := UI.label("POS   NOMBRE                         MED  ENE  ÁNIMO", 14, UI.TEXT_DIM)
	rv.add_child(hdr)
	var scroll := ScrollContainer.new()
	UI.expand(scroll, true, true)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	rv.add_child(scroll)
	_bench_box = UI.vbox(4)
	UI.expand(_bench_box)
	scroll.add_child(_bench_box)

	_info = UI.label("Toca un jugador para ver sus datos. Toca dos para intercambiarlos.", 17, UI.TEXT_DIM)
	_info.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	vb.add_child(_info)
	_refresh()


func _xi() -> Array:
	return sim.xi[side] if sim else GameData.lineup_players(team)


func _slots() -> Array:
	var out: Array = []
	for s in GameData.FORMATIONS[team.formation]:
		out.append(s)
	return out


func _bench() -> Array:
	return sim.bench(side) if sim else GameData.bench_players(team)


func _refresh() -> void:
	if _pitch == null or _bench_box == null:
		return
	UI.clear(_pitch)
	var xi := _xi()
	var slots := _slots()
	var sz := _pitch.size
	for i in xi.size():
		var p: Dictionary = xi[i]
		var sl: Array = slots[i]
		var card := _player_card(p, sl[0], _selected.get("where") == "xi" and _selected.get("i") == i)
		card.position = Vector2(sl[1] * sz.x - 66, sl[2] * sz.y - 36)
		card.gui_input.connect(_on_card_input.bind("xi", i))
		_pitch.add_child(card)
	UI.clear(_bench_box)
	var bench := _bench()
	bench.sort_custom(func(a, b): return ["POR", "DFC", "LD", "LI", "MCD", "MC", "MCO", "ED", "EI", "DC"].find(a.pos) < ["POR", "DFC", "LD", "LI", "MCD", "MC", "MCO", "ED", "EI", "DC"].find(b.pos))
	for i in bench.size():
		var row := _bench_row(bench[i], _selected.get("where") == "bench" and _selected.get("id") == bench[i].id)
		row.gui_input.connect(_on_card_input.bind("bench", bench[i].id))
		_bench_box.add_child(row)
	if _form_label:
		_form_label.text = team.formation
	if _subs_label:
		_subs_label.text = "Cambios disponibles: %d" % sim.subs_left[side]
	_pitch.queue_redraw()


func _draw_pitch() -> void:
	var s := _pitch.size
	_pitch.draw_rect(Rect2(Vector2.ZERO, s), Color(0.12, 0.36, 0.16))
	for i in 8:
		if i % 2 == 0:
			_pitch.draw_rect(Rect2(0, s.y * i / 8.0, s.x, s.y / 8.0), Color(0.14, 0.4, 0.18))
	var c := Color(1, 1, 1, 0.5)
	_pitch.draw_rect(Rect2(Vector2(6, 6), s - Vector2(12, 12)), c, false, 2.0)
	_pitch.draw_line(Vector2(6, s.y * 0.02), Vector2(s.x - 6, s.y * 0.02), c, 2.0)
	_pitch.draw_arc(Vector2(s.x / 2, 6), s.x * 0.12, 0, PI, 32, c, 2.0)
	_pitch.draw_rect(Rect2(s.x * 0.25, s.y - 6 - s.y * 0.17, s.x * 0.5, s.y * 0.17), c, false, 2.0)
	_pitch.draw_rect(Rect2(s.x * 0.38, s.y - 6 - s.y * 0.06, s.x * 0.24, s.y * 0.06), c, false, 2.0)


func _player_card(p: Dictionary, slot_pos: String, selected: bool) -> Control:
	var panel := PanelContainer.new()
	var fit := GameData.slot_factor(p, slot_pos)
	var border := UI.GOLD if selected else (Color(1, 0.4, 0.3) if fit < 0.9 else Color(1, 1, 1, 0.25))
	panel.add_theme_stylebox_override("panel", UI.style(Color(0.05, 0.08, 0.13, 0.9), 10, border, 3 if selected else 2, 5))
	panel.custom_minimum_size = Vector2(132, 0)
	panel.mouse_filter = Control.MOUSE_FILTER_STOP
	var vb := UI.vbox(1)
	vb.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.add_child(vb)
	var top := UI.hbox(4)
	top.mouse_filter = Control.MOUSE_FILTER_IGNORE
	vb.add_child(top)
	var pos := UI.label(slot_pos, 13, UI.GOLD)
	top.add_child(pos)
	var r := GameData.rating(p)
	var rl := UI.label(str(int(r * fit)), 15, UI.rating_color(r * fit))
	UI.expand(rl)
	rl.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	top.add_child(rl)
	var parts: PackedStringArray = str(p.name).split(" ")
	var short_name: String = parts[parts.size() - 1] if parts.size() > 1 else str(p.name)
	if short_name in ["Júnior", "Junior", "Jr."] or short_name.length() > 12:
		short_name = parts[0]
	var nm := UI.label("%d %s" % [int(p.number), short_name], 15, UI.TEXT, HORIZONTAL_ALIGNMENT_CENTER)
	nm.clip_text = true
	vb.add_child(nm)
	var b := UI.bar(float(p.energy), 120, 6)
	vb.add_child(b)
	for c in [pos, rl, nm, b]:
		c.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return panel


func _bench_row(p: Dictionary, selected: bool) -> Control:
	var panel := PanelContainer.new()
	panel.add_theme_stylebox_override("panel", UI.style(UI.PANEL_LIGHT if not selected else Color(0.35, 0.3, 0.1), 8, UI.GOLD if selected else Color(0, 0, 0, 0), 2 if selected else 0, 6))
	panel.mouse_filter = Control.MOUSE_FILTER_STOP
	var hb := UI.hbox(8)
	hb.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.add_child(hb)
	var cells: Array = [
		[p.pos, 15, UI.GOLD, 42], ["%d  %s" % [int(p.number), p.name], 15, UI.TEXT, 180],
		[str(GameData.rating(p)), 16, UI.rating_color(GameData.rating(p)), 36],
		[str(int(p.energy)), 15, UI.GREEN if p.energy >= 70 else (UI.GOLD if p.energy >= 45 else UI.RED), 36],
		[UI.morale_text(p.morale), 14, UI.morale_color(p.morale), 70],
	]
	for c in cells:
		var l := UI.label(c[0], c[1], c[2])
		l.custom_minimum_size = Vector2(c[3], 0)
		l.clip_text = true
		l.mouse_filter = Control.MOUSE_FILTER_IGNORE
		hb.add_child(l)
	return panel


func _on_card_input(event: InputEvent, where: String, key) -> void:
	var tap: bool = (event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT)
	if not tap:
		return
	var p := _get_player(where, key)
	_show_info(p)
	if _selected.is_empty():
		_selected = {"where": where, "i": key if where == "xi" else -1, "id": key if where == "bench" else -1}
		_refresh()
		return
	var a := _selected
	_selected = {}
	if a.where == where and (a.i == key or a.id == key):
		_refresh()
		return
	_swap(a, {"where": where, "i": key if where == "xi" else -1, "id": key if where == "bench" else -1})
	_refresh()


func _get_player(where: String, key) -> Dictionary:
	if where == "xi":
		return _xi()[int(key)]
	if sim:
		for p in sim.bench(side):
			if int(p.id) == int(key):
				return p
	return GameData.find_player(team, key)


func _swap(a: Dictionary, b: Dictionary) -> void:
	if sim:
		# Durante el partido: solo titular <-> suplente.
		var xi_i := -1
		var bench_id := -1
		for s in [a, b]:
			if s.where == "xi":
				xi_i = s.i
			else:
				bench_id = s.id
		if xi_i < 0 or bench_id < 0:
			_info.text = "Durante el partido solo puedes cambiar un titular por un suplente."
			return
		if sim.subs_left[side] <= 0:
			_info.text = "Ya no te quedan cambios."
			return
		var incoming := _get_player("bench", bench_id)
		sim.substitute(side, xi_i, incoming)
		_info.text = "Cambio hecho: entra %s." % incoming.name
		return
	var xi: Array = team.xi
	if a.where == "xi" and b.where == "xi":
		var tmp = xi[a.i]
		xi[a.i] = xi[b.i]
		xi[b.i] = tmp
	elif a.where == "xi" or b.where == "xi":
		var xs: Dictionary = a if a.where == "xi" else b
		var bs: Dictionary = b if a.where == "xi" else a
		xi[xs.i] = int(bs.id)
	team.xi = xi


func _show_info(p: Dictionary) -> void:
	if p.is_empty():
		return
	var s := "%d · %s · %s · MED %d   VEL %d  PAS %d  TIR %d  DEF %d  TL %d  RES %d" % [p.number, p.name, p.pos, GameData.rating(p), p.spd, p.pas, p.sho, p.dfn, p.tl, p.res]
	if p.pos == "POR":
		s += "  POR %d" % p.gkp
	s += "   ·   Energía %d%%  ·  Ánimo: %s" % [int(p.energy), UI.morale_text(p.morale)]
	_info.text = s


func _next_form() -> void:
	_change_form(1)


func _prev_form() -> void:
	_change_form(-1)


func _change_form(d: int) -> void:
	var order: Array = GameData.FORMATION_ORDER
	var i := order.find(team.formation)
	team.formation = order[(i + d + order.size()) % order.size()]
	_refresh()


func _best() -> void:
	GameData.auto_lineup(team)
	_refresh()

extends Node
## Datos globales: equipos de LaLiga, jugadores, alineaciones, liga (modo carrera),
## guardado y el paso de información entre la simulación y las jugadas en 3D.

const SAVE_PATH := "user://carrera.json"
const DATA_VERSION := 2  # 2 = plantillas reales 2026/27

# Plantillas reales: data/laliga_2026_27.json (se genera con tools/build_squads.py).

const POS_ROLE := {"POR": "GK", "DFC": "DEF", "LD": "DEF", "LI": "DEF", "MCD": "MID", "MC": "MID",
	"MCO": "MID", "ED": "FWD", "EI": "FWD", "DC": "FWD"}

const FORMATIONS := {
	"4-3-3": [["POR", 0.5, 0.92], ["LI", 0.12, 0.72], ["DFC", 0.37, 0.77], ["DFC", 0.63, 0.77], ["LD", 0.88, 0.72],
		["MC", 0.25, 0.5], ["MCD", 0.5, 0.57], ["MC", 0.75, 0.5], ["EI", 0.15, 0.24], ["DC", 0.5, 0.16], ["ED", 0.85, 0.24]],
	"4-4-2": [["POR", 0.5, 0.92], ["LI", 0.12, 0.72], ["DFC", 0.37, 0.77], ["DFC", 0.63, 0.77], ["LD", 0.88, 0.72],
		["EI", 0.12, 0.45], ["MC", 0.37, 0.5], ["MC", 0.63, 0.5], ["ED", 0.88, 0.45], ["DC", 0.37, 0.18], ["DC", 0.63, 0.18]],
	"4-2-3-1": [["POR", 0.5, 0.92], ["LI", 0.12, 0.72], ["DFC", 0.37, 0.77], ["DFC", 0.63, 0.77], ["LD", 0.88, 0.72],
		["MCD", 0.37, 0.58], ["MCD", 0.63, 0.58], ["EI", 0.15, 0.34], ["MCO", 0.5, 0.36], ["ED", 0.85, 0.34], ["DC", 0.5, 0.14]],
	"3-5-2": [["POR", 0.5, 0.92], ["DFC", 0.25, 0.76], ["DFC", 0.5, 0.79], ["DFC", 0.75, 0.76], ["LI", 0.08, 0.48],
		["MC", 0.3, 0.52], ["MCD", 0.5, 0.58], ["MC", 0.7, 0.52], ["LD", 0.92, 0.48], ["DC", 0.37, 0.18], ["DC", 0.63, 0.18]],
	"5-3-2": [["POR", 0.5, 0.92], ["LI", 0.08, 0.64], ["DFC", 0.3, 0.77], ["DFC", 0.5, 0.79], ["DFC", 0.7, 0.77],
		["LD", 0.92, 0.64], ["MC", 0.25, 0.48], ["MCD", 0.5, 0.53], ["MC", 0.75, 0.48], ["DC", 0.37, 0.18], ["DC", 0.63, 0.18]],
}
const FORMATION_ORDER := ["4-3-3", "4-4-2", "4-2-3-1", "3-5-2", "5-3-2"]

var teams: Array = []           # equipos con sus jugadores
var career: Dictionary = {}     # estado del modo carrera (vacío si no hay)
var quick := {"user": 0, "rival": 1}
var training_team := 0
var sim: MatchSim = null        # partido en curso (sobrevive a los cambios de escena)
var moment: Dictionary = {}     # jugada clave que se va a jugar en 3D
var moment_result: Dictionary = {}
var stats := {"played": 0, "goals": 0}
var _next_id := 1


func _ready() -> void:
	if not load_career():
		teams = generate_teams(randi())


# ------------------------------------------------------------------ Generación

const DATA_PATH := "res://data/laliga_2026_27.json"


func generate_teams(_seed_value: int = 0) -> Array:
	## Carga las plantillas reales de LaLiga 2026/27 (data/laliga_2026_27.json).
	var f := FileAccess.open(DATA_PATH, FileAccess.READ)
	var data = JSON.parse_string(f.get_as_text()) if f else null
	var out: Array = []
	_next_id = 1
	if typeof(data) != TYPE_DICTIONARY:
		push_error("No se pudo leer " + DATA_PATH)
		return out
	var rng := RandomNumberGenerator.new()
	rng.randomize()
	for i in data.teams.size():
		var t: Dictionary = data.teams[i]
		var team := {"id": i, "name": t.name, "short": t.short, "strength": 75, "kit": t.kit,
			"formation": t.formation, "xi": [], "players": []}
		for src in t.players:
			var p: Dictionary = src.duplicate()
			p["id"] = _next_id
			_next_id += 1
			p["role"] = POS_ROLE[p.pos]
			p["energy"] = 100.0
			p["morale"] = rng.randf_range(60, 78)
			p["goals"] = 0
			p["apps"] = 0
			p["age"] = 0
			for k in ["number", "spd", "pas", "sho", "dfn", "gkp", "tl", "res", "ovr"]:
				p[k] = int(p[k])
			team.players.append(p)
		auto_lineup(team)
		team.strength = team_rating(team)
		out.append(team)
	return out


# ------------------------------------------------------------------ Jugadores

func rating(p: Dictionary) -> int:
	if p.has("ovr"):
		return int(p.ovr)
	var w := {"POR": {"gkp": 1.0}, "DFC": {"dfn": 0.6, "spd": 0.2, "pas": 0.2},
		"LD": {"dfn": 0.4, "spd": 0.35, "pas": 0.25}, "LI": {"dfn": 0.4, "spd": 0.35, "pas": 0.25},
		"MCD": {"dfn": 0.45, "pas": 0.35, "spd": 0.2}, "MC": {"pas": 0.5, "dfn": 0.2, "sho": 0.15, "spd": 0.15},
		"MCO": {"pas": 0.45, "sho": 0.3, "spd": 0.25}, "ED": {"spd": 0.4, "sho": 0.3, "pas": 0.3},
		"EI": {"spd": 0.4, "sho": 0.3, "pas": 0.3}, "DC": {"sho": 0.55, "spd": 0.3, "pas": 0.15}}
	var ww: Dictionary = w[p.pos]
	var r := 0.0
	for k in ww:
		r += float(p[k]) * ww[k]
	return int(round(r))


func form_factor(p: Dictionary) -> float:
	## Energía y ánimo afectan al rendimiento.
	return (0.78 + 0.22 * float(p.energy) / 100.0) * (0.95 + 0.1 * float(p.morale) / 100.0)


const NEAR_POS := {
	"DFC": {"LD": 0.9, "LI": 0.9, "MCD": 0.88}, "LD": {"LI": 0.9, "DFC": 0.88, "ED": 0.85}, "LI": {"LD": 0.9, "DFC": 0.88, "EI": 0.85},
	"MCD": {"MC": 0.97, "DFC": 0.88, "MCO": 0.88}, "MC": {"MCD": 0.96, "MCO": 0.97}, "MCO": {"MC": 0.97, "ED": 0.9, "EI": 0.9, "DC": 0.88, "MCD": 0.86},
	"ED": {"EI": 0.95, "DC": 0.9, "MCO": 0.9}, "EI": {"ED": 0.95, "DC": 0.9, "MCO": 0.9}, "DC": {"ED": 0.9, "EI": 0.9, "MCO": 0.88},
}


func slot_factor(p: Dictionary, slot_pos: String) -> float:
	## Cuánto rinde un jugador en un puesto que no es el suyo.
	if p.pos == slot_pos:
		return 1.0
	var near: Dictionary = NEAR_POS.get(slot_pos, {})
	if near.has(p.pos):
		return near[p.pos]
	var r1: String = POS_ROLE[p.pos]
	var r2: String = POS_ROLE[slot_pos]
	if r1 == "GK" or r2 == "GK":
		return 0.35
	if r1 == r2:
		return 0.9
	return 0.75


func with_slots(list: Array, formation: String) -> Array:
	## Añade a cada jugador (efectivo) su posición en la formación (sx, sy).
	var slots: Array = FORMATIONS[formation]
	for i in list.size():
		list[i]["sx"] = slots[i][1]
		list[i]["sy"] = slots[i][2]
	return list


func effective(p: Dictionary, slot_pos := "") -> Dictionary:
	## Copia del jugador con los atributos que rinde hoy (para la jugada en 3D).
	var f := form_factor(p) * (slot_factor(p, slot_pos) if slot_pos != "" else 1.0)
	var role: String = POS_ROLE[slot_pos] if slot_pos != "" else p.role
	return {"name": p.name, "number": p.number, "pos": role, "id": p.id,
		"spd": p.spd * f, "pas": p.pas * f, "sho": p.sho * f, "dfn": p.dfn * f, "gkp": p.gkp * f, "tl": p.tl * f,
		"energy": p.energy}


func find_player(team: Dictionary, id) -> Dictionary:
	for p in team.players:
		if int(p.id) == int(id):
			return p
	return {}


func team_by_id(id) -> Dictionary:
	return teams[int(id)]


func auto_lineup(team: Dictionary) -> void:
	## Elige el mejor once disponible: asigna cada vez la mejor pareja jugador-puesto.
	var slots: Array = FORMATIONS[team.formation]
	var pairs: Array = []
	for si in slots.size():
		for p in team.players:
			pairs.append([rating(p) * form_factor(p) * slot_factor(p, slots[si][0]), si, int(p.id)])
	pairs.sort_custom(func(a, b): return a[0] > b[0])
	var xi: Array = []
	xi.resize(slots.size())
	var used := {}
	var filled := 0
	for pr in pairs:
		if xi[pr[1]] != null or used.has(pr[2]):
			continue
		xi[pr[1]] = pr[2]
		used[pr[2]] = true
		filled += 1
		if filled == slots.size():
			break
	team.xi = xi


func lineup_players(team: Dictionary) -> Array:
	var out: Array = []
	for id in team.xi:
		out.append(find_player(team, id))
	return out


func bench_players(team: Dictionary) -> Array:
	var ids := {}
	for id in team.xi:
		ids[int(id)] = true
	return team.players.filter(func(p): return not ids.has(int(p.id)))


func team_power(team: Dictionary, xi: Array = [], slots: Array = []) -> Dictionary:
	## Fuerza de ataque y defensa del once (con energía, ánimo y posiciones).
	if xi.is_empty():
		xi = lineup_players(team)
	if slots.is_empty():
		for s in FORMATIONS[team.formation]:
			slots.append(s[0])
	var att := 0.0
	var att_w := 0.0
	var dfn := 0.0
	var dfn_w := 0.0
	var mid := 0.0
	var pace := 0.0
	for i in xi.size():
		var p: Dictionary = xi[i]
		var sp: String = slots[i] if i < slots.size() else p.pos
		var f := form_factor(p) * slot_factor(p, sp)
		match POS_ROLE[sp]:
			"GK":
				dfn += p.gkp * f * 2.5
				dfn_w += 2.5
			"DEF":
				dfn += (p.dfn * 0.7 + p.spd * 0.3) * f
				dfn_w += 1.0
				att += (p.pas * 0.5 + p.spd * 0.5) * f * 0.3
				att_w += 0.3
			"MID":
				mid += p.pas * f
				att += (p.pas * 0.5 + p.sho * 0.25 + p.spd * 0.25) * f
				att_w += 1.0
				dfn += p.dfn * f * 0.4
				dfn_w += 0.4
			"FWD":
				att += (p.sho * 0.5 + p.spd * 0.3 + p.pas * 0.2) * f * 1.4
				att_w += 1.4
				pace += p.spd * f
	var form_bonus := {"4-3-3": [1.03, 0.99], "4-4-2": [1.0, 1.0], "4-2-3-1": [1.01, 1.01], "3-5-2": [1.04, 0.97], "5-3-2": [0.96, 1.05]}
	var fb: Array = form_bonus.get(team.formation, [1.0, 1.0])
	return {"att": att / maxf(att_w, 1.0) * fb[0], "def": dfn / maxf(dfn_w, 1.0) * fb[1], "mid": mid / 3.0, "pace": pace / 3.0}


func team_rating(team: Dictionary) -> int:
	var s := 0.0
	for p in lineup_players(team):
		s += rating(p)
	return int(round(s / 11.0))


func kit_colors(team: Dictionary, use_alt := false) -> Dictionary:
	var k: Dictionary = team.kit
	var shirt := Color(k.alt) if use_alt else Color(k.shirt)
	var shorts := Color(k.alt).darkened(0.3) if use_alt else Color(k.shorts)
	var socks := Color(k.alt) if use_alt else Color(k.socks)
	var lum := shirt.r * 0.3 + shirt.g * 0.59 + shirt.b * 0.11
	var number := Color(0.08, 0.08, 0.1) if lum > 0.6 else Color(1, 1, 1)
	var gk_opts := [Color(0.15, 0.85, 0.35), Color(0.95, 0.6, 0.1), Color(0.6, 0.2, 0.8), Color(0.1, 0.1, 0.1)]
	return {"shirt": shirt, "shorts": shorts, "socks": socks, "number": number, "gk": gk_opts[int(team.id) % gk_opts.size()]}


func kits_for(home_team: Dictionary, away_team: Dictionary) -> Array:
	## Si las camisetas se parecen, el segundo equipo usa la alternativa.
	var a := kit_colors(home_team)
	var b := kit_colors(away_team)
	var ca: Color = a.shirt
	var cb: Color = b.shirt
	var dist := Vector3(ca.r - cb.r, ca.g - cb.g, ca.b - cb.b).length()
	if dist < 0.45:
		b = kit_colors(away_team, true)
	if a.gk == b.gk:
		b.gk = Color(0.1, 0.1, 0.1)
	return [a, b]


func build_moment(j: Dictionary, ut: Dictionary, rt: Dictionary, ctx: String) -> Dictionary:
	## Jugada suelta (entrenamiento) con los onces de ambos equipos.
	if ut.xi.is_empty():
		auto_lineup(ut)
	auto_lineup(rt)
	var hx: Array = []
	var ax: Array = []
	var us: Array = FORMATIONS[ut.formation]
	var rs: Array = FORMATIONS[rt.formation]
	var ul := lineup_players(ut)
	var rl := lineup_players(rt)
	for i in ul.size():
		hx.append(effective(ul[i], us[i][0]))
	for i in rl.size():
		ax.append(effective(rl[i], rs[i][0]))
	with_slots(hx, ut.formation)
	with_slots(ax, rt.formation)
	return {"jugada": j, "user_team": ut, "rival_team": rt, "home_xi": hx, "away_xi": ax, "minute": "ENT",
		"score_user": 0, "score_rival": 0, "user_is_home": true, "context": ctx, "minute_short": true}


# ------------------------------------------------------------------ Modo carrera

func new_career(team_id: int) -> void:
	teams = generate_teams(randi())
	career = {"team_id": team_id, "season": 2026, "round": 0, "training": "normal",
		"fixtures": _make_fixtures(teams.size()), "results": [], "table": {}, "last_round": []}
	for t in teams:
		career.table[str(t.id)] = {"pj": 0, "g": 0, "e": 0, "p": 0, "gf": 0, "gc": 0, "pts": 0}
	save_career()


func has_career() -> bool:
	return not career.is_empty()


func user_team() -> Dictionary:
	return teams[int(career.team_id)] if has_career() else teams[int(quick.user)]


func _make_fixtures(n: int) -> Array:
	## Liga a doble vuelta (método del círculo).
	var ids: Array = range(n)
	var rounds: Array = []
	for r in n - 1:
		var games: Array = []
		for i in n / 2:
			var a: int = ids[i]
			var b: int = ids[n - 1 - i]
			if (r + i) % 2 == 0:
				games.append([a, b])
			else:
				games.append([b, a])
		rounds.append(games)
		var last: int = ids.pop_back()
		ids.insert(1, last)
	var second: Array = []
	for g in rounds:
		var rg: Array = []
		for m in g:
			rg.append([m[1], m[0]])
		second.append(rg)
	rounds.shuffle()
	second.shuffle()
	return rounds + second


func current_fixture() -> Array:
	## [local, visitante] del partido del usuario en la jornada actual.
	if not has_career() or int(career.round) >= career.fixtures.size():
		return []
	for m in career.fixtures[int(career.round)]:
		if int(m[0]) == int(career.team_id) or int(m[1]) == int(career.team_id):
			return [int(m[0]), int(m[1])]
	return []


func season_over() -> bool:
	return has_career() and int(career.round) >= career.fixtures.size()


func record_result(h: int, a: int, hg: int, ag: int) -> void:
	var th: Dictionary = career.table[str(h)]
	var ta: Dictionary = career.table[str(a)]
	th.pj += 1
	ta.pj += 1
	th.gf += hg
	th.gc += ag
	ta.gf += ag
	ta.gc += hg
	if hg > ag:
		th.g += 1
		th.pts += 3
		ta.p += 1
	elif hg < ag:
		ta.g += 1
		ta.pts += 3
		th.p += 1
	else:
		th.e += 1
		ta.e += 1
		th.pts += 1
		ta.pts += 1


func quick_score(home_team: Dictionary, away_team: Dictionary) -> Array:
	## Resultado rápido para los partidos que no juega el usuario.
	var ph := team_power(home_team)
	var pa := team_power(away_team)
	var lh := 1.45 * pow(ph.att / pa.def, 1.6) * 1.06
	var la := 1.15 * pow(pa.att / ph.def, 1.6)
	return [_poisson(lh), _poisson(la)]


func _poisson(l: float) -> int:
	var L := exp(-l)
	var k := 0
	var p := 1.0
	while true:
		p *= randf()
		if p <= L:
			break
		k += 1
	return k


func finish_round(user_hg: int, user_ag: int) -> void:
	## Registra el partido del usuario, simula el resto de la jornada y avanza.
	var rnd: Array = career.fixtures[int(career.round)]
	var results: Array = []
	for m in rnd:
		var h := int(m[0])
		var a := int(m[1])
		var sc: Array
		if h == int(career.team_id) or a == int(career.team_id):
			sc = [user_hg, user_ag]
		else:
			var th := team_by_id(h)
			var ta := team_by_id(a)
			auto_lineup(th)
			auto_lineup(ta)
			sc = quick_score(th, ta)
			_age_ai_team(th)
			_age_ai_team(ta)
		record_result(h, a, sc[0], sc[1])
		results.append([h, a, sc[0], sc[1]])
	career.results.append(results)
	career.last_round = results
	career.round = int(career.round) + 1
	_recover_user_team()
	save_career()


func _age_ai_team(t: Dictionary) -> void:
	for p in t.players:
		p.energy = clampf(p.energy - randf_range(0, 15) + 20.0, 40, 100)


func _recover_user_team() -> void:
	var t := user_team()
	var rec := {"suave": 34.0, "normal": 26.0, "intenso": 16.0}
	var r: float = rec.get(career.training, 26.0)
	for p in t.players:
		p.energy = clampf(float(p.energy) + r, 0, 100)
		if career.training == "intenso" and randf() < 0.12:
			var k: String = ["spd", "pas", "sho", "dfn", "tl", "res"][randi() % 6]
			if p.role == "GK":
				k = "gkp"
			p[k] = mini(int(p[k]) + 1, 97)
		if career.training == "suave":
			p.morale = clampf(float(p.morale) + 1.5, 0, 100)


func sorted_table() -> Array:
	var rows: Array = []
	for k in career.table:
		var r: Dictionary = career.table[k].duplicate()
		r["id"] = int(k)
		rows.append(r)
	rows.sort_custom(func(a, b):
		if a.pts != b.pts:
			return a.pts > b.pts
		var da: int = a.gf - a.gc
		var db: int = b.gf - b.gc
		if da != db:
			return da > db
		if a.gf != b.gf:
			return a.gf > b.gf
		return str(teams[a.id].name) < str(teams[b.id].name))
	return rows


func table_position(team_id: int) -> int:
	var rows := sorted_table()
	for i in rows.size():
		if int(rows[i].id) == team_id:
			return i + 1
	return 0


func new_season() -> void:
	career.season = int(career.season) + 1
	career.round = 0
	career.results = []
	career.last_round = []
	career.fixtures = _make_fixtures(teams.size())
	for t in teams:
		career.table[str(t.id)] = {"pj": 0, "g": 0, "e": 0, "p": 0, "gf": 0, "gc": 0, "pts": 0}
		for p in t.players:
			p.age = int(p.age) + 1
			p.energy = 100.0
			p.goals = 0
			p.apps = 0
	save_career()


func save_career() -> void:
	if not has_career():
		return
	var data := {"career": career, "teams": teams, "stats": stats, "next_id": _next_id, "data_version": DATA_VERSION}
	var f := FileAccess.open(SAVE_PATH, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(data))


func load_career() -> bool:
	if not FileAccess.file_exists(SAVE_PATH):
		return false
	var f := FileAccess.open(SAVE_PATH, FileAccess.READ)
	if f == null:
		return false
	var data = JSON.parse_string(f.get_as_text())
	if typeof(data) != TYPE_DICTIONARY or not data.has("career"):
		return false
	if int(data.get("data_version", 1)) != DATA_VERSION:
		return false  # partida de una versión con jugadores inventados
	career = data.career
	teams = data.teams
	stats = data.get("stats", stats)
	_next_id = int(data.get("next_id", 5000))
	return true


func delete_career() -> void:
	career = {}
	if FileAccess.file_exists(SAVE_PATH):
		DirAccess.remove_absolute(SAVE_PATH)

class_name MatchSim
extends RefCounted
## Simulación de un partido minuto a minuto. Cada minuto puede haber ocasiones,
## faltas, córners o penales según la fuerza de cada once (con energía y ánimo).
## Algunas de esas situaciones se convierten en jugadas clave que juega el usuario.

var teams: Array = []          # [local, visitante] (diccionarios de equipo)
var user_side := 0             # 0 = el usuario es local, 1 = visitante
var context := "quick"         # "quick" o "career"
var minute := 0
var half := 1
var added := [0, 0]
var score := [0, 0]
var events: Array = []         # {"min", "text", "type", "side"}
var stats := {"shots": [0, 0], "on_target": [0, 0], "corners": [0, 0], "fouls": [0, 0], "poss": [0.0, 0.0]}
var xi: Array = [[], []]       # jugadores en el campo por lado
var slots: Array = [[], []]    # posición de cada hueco de la formación
var subs_left := [5, 5]
var subbed_off: Dictionary = {}
var finished := false
var halftime_pending := false
var pending: Dictionary = {}   # jugada clave esperando decisión
var used_jugadas: Dictionary = {}
var scorers: Array = []        # {"side", "name", "min"}
var minutes_played: Dictionary = {}
var moments_played := 0


func setup(home_team: Dictionary, away_team: Dictionary, user_is_home: bool, ctx: String) -> void:
	teams = [home_team, away_team]
	user_side = 0 if user_is_home else 1
	context = ctx
	added = [randi_range(1, 3), randi_range(2, 5)]
	for s in 2:
		var t: Dictionary = teams[s]
		if s != user_side:
			GameData.auto_lineup(t)
		xi[s] = GameData.lineup_players(t)
		slots[s] = []
		for sl in GameData.FORMATIONS[t.formation]:
			slots[s].append(sl[0])
		for p in xi[s]:
			minutes_played[int(p.id)] = 0
	_event(0, "¡Comienza el partido! %s recibe a %s." % [home_team.name, away_team.name], "info", -1)


func user_team() -> Dictionary:
	return teams[user_side]


func rival_team() -> Dictionary:
	return teams[1 - user_side]


func _event(m: int, text: String, type: String, side: int) -> void:
	events.append({"min": m, "text": text, "type": type, "side": side})


func minute_label() -> String:
	var base := 45 if half == 1 else 90
	if minute > base:
		return "%d+%d'" % [base, minute - base]
	return "%d'" % minute


func power(side: int) -> Dictionary:
	return GameData.team_power(teams[side], xi[side], slots[side])


# ------------------------------------------------------------------ Paso de un minuto

func step() -> void:
	if finished or not pending.is_empty() or halftime_pending:
		return
	minute += 1
	var end_first := 45 + int(added[0])
	var end_second := 90 + int(added[1])
	if half == 1 and minute > end_first:
		half = 2
		minute = 45
		halftime_pending = true
		_event(45, "Descanso. %s %d - %d %s" % [teams[0].short, score[0], score[1], teams[1].short], "half", -1)
		for s in 2:
			for p in xi[s]:
				p.energy = clampf(float(p.energy) + 6.0, 0, 100)
		return
	if half == 2 and minute > end_second:
		_finish()
		return
	if minute == 45 and half == 1:
		_event(45, "El árbitro añade %d minutos." % added[0], "info", -1)
	if minute == 90:
		_event(90, "Se añaden %d minutos." % added[1], "info", -1)

	_drain_energy()
	_ai_subs()
	for p in xi[0] + xi[1]:
		minutes_played[int(p.id)] = int(minutes_played.get(int(p.id), 0)) + 1

	var pw := [power(0), power(1)]
	var mid_total: float = pw[0].mid + pw[1].mid
	stats.poss[0] += pw[0].mid / mid_total * 1.06
	stats.poss[1] += pw[1].mid / mid_total
	var order := [0, 1]
	order.shuffle()
	for s in order:
		if not pending.is_empty():
			return
		_minute_side(s, pw[s], pw[1 - s])


func _minute_side(s: int, me: Dictionary, opp: Dictionary) -> void:
	var ratio: float = me.att / maxf(opp.def, 1.0)
	var home_adv := 1.08 if s == 0 else 1.0
	var late_push := 1.25 if (minute > 75 and score[s] < score[1 - s]) else 1.0
	var p_chance := 0.062 * pow(ratio, 1.8) * home_adv * late_push
	var user := s == user_side

	# Penal
	if randf() < 0.0017:
		stats.fouls[1 - s] += 1
		if user:
			_offer("penalty_for", s, "¡PENAL a favor de %s!" % teams[s].name)
		else:
			_offer("penalty_against", s, "¡PENAL para %s! Te toca ir bajo los palos." % teams[s].name)
		return
	# Falta peligrosa
	if randf() < 0.02:
		stats.fouls[1 - s] += 1
		var dangerous := randf() < 0.35
		if dangerous:
			if user and randf() < 0.75:
				_offer("freekick", s, "Falta peligrosa sobre %s. ¡Tiro libre en buena posición!" % _random_player(s, ["FWD", "MID"]).name)
			else:
				_auto_freekick(s)
		elif randf() < 0.25:
			_event(minute, "Falta de %s en el centro del campo." % _random_player(1 - s, ["DEF", "MID"]).name, "info", s)
		return
	if randf() < p_chance:
		if user and randf() < 0.42:
			_offer("attack", s, _attack_intro(s))
			return
		if not user and randf() < 0.42:
			_offer("defend", s, "¡Cuidado! %s ataca con peligro..." % teams[s].name)
			return
		_auto_chance(s, ratio)


func _attack_intro(s: int) -> String:
	var lines := ["¡Oportunidad para %s!", "%s sale rápido al ataque...", "¡Se abre el espacio para %s!", "%s llega con peligro al área rival..."]
	return lines[randi() % lines.size()] % teams[s].name


func _offer(kind: String, side: int, text: String) -> void:
	var ctx := {"pace_for": power(user_side).pace, "pace_against": power(1 - user_side).pace,
		"losing": score[user_side] < score[1 - user_side]}
	var j := Jugadas.pick(kind, ctx, used_jugadas)
	if j.is_empty():
		return
	used_jugadas[j.id] = true
	pending = {"kind": kind, "side": side, "jugada": j, "text": text, "minute": minute}
	_event(minute, text, "moment", side)


func _auto_chance(s: int, ratio: float) -> void:
	stats.shots[s] += 1
	var shooter := _pick_shooter(s)
	var conv := clampf(0.095 * pow(ratio, 1.2) * (0.75 + shooter.sho / 200.0), 0.03, 0.35)
	var gk := _goalkeeper(1 - s)
	var r := randf()
	if r < conv:
		stats.on_target[s] += 1
		_goal(s, shooter, ["¡GOOOL de %s! Remate imparable.", "¡GOL! %s define con frialdad.", "¡GOLAZO de %s desde fuera del área!", "¡Gol! %s empuja el balón a la red."][randi() % 4] % shooter.name)
	elif r < conv + 0.3:
		stats.on_target[s] += 1
		_event(minute, ["Disparo de %s... ¡paradón de %s!", "%s prueba fortuna, pero %s atrapa el balón.", "Remate de %s, %s despeja a córner."][randi() % 3] % [shooter.name, gk.name], "chance", s)
		if randf() < 0.4:
			_corner(s)
	else:
		_event(minute, ["%s dispara desviado.", "El tiro de %s se va por encima del larguero.", "%s no llega a rematar el centro.", "Ocasión clara para %s, pero la manda fuera."][randi() % 4] % shooter.name, "chance", s)


func _corner(s: int) -> void:
	stats.corners[s] += 1
	if s == user_side and randf() < 0.3 and pending.is_empty():
		_offer("corner", s, "Córner a favor de %s." % teams[s].name)
	elif randf() < 0.05:
		var head := _pick_shooter(s, true)
		_goal(s, head, "¡GOL de cabeza de %s tras el córner!" % head.name)
	else:
		_event(minute, "Córner para %s... despeja la defensa." % teams[s].name, "info", s)


func _auto_freekick(s: int) -> void:
	var taker := _best_taker(s)
	stats.shots[s] += 1
	if randf() < 0.05 + taker.tl / 1200.0:
		stats.on_target[s] += 1
		_goal(s, taker, "¡GOLAZO de tiro libre de %s!" % taker.name)
	else:
		_event(minute, "Tiro libre de %s... %s." % [taker.name, ["a la barrera", "por encima", "atrapa el portero", "rozando el palo"][randi() % 4]], "chance", s)


func _goal(s: int, scorer: Dictionary, text: String) -> void:
	score[s] += 1
	scorers.append({"side": s, "name": scorer.name, "min": minute})
	if scorer.has("goals"):
		scorer.goals = int(scorer.goals) + 1
		scorer.morale = clampf(float(scorer.morale) + 4.0, 0, 100)
	_event(minute, text + "  (%s %d - %d %s)" % [teams[0].short, score[0], score[1], teams[1].short], "goal", s)


func _drain_energy() -> void:
	for s in 2:
		for p in xi[s]:
			if p.role == "GK":
				p.energy = clampf(float(p.energy) - 0.05, 0, 100)
			else:
				p.energy = clampf(float(p.energy) - 0.42 * (1.32 - float(p.res) / 100.0), 0, 100)


func _ai_subs() -> void:
	var s := 1 - user_side
	if minute < 58 or subs_left[s] <= 0 or randf() > 0.25:
		return
	var tired = null
	var lowest := 60.0
	for p in xi[s]:
		if p.role != "GK" and float(p.energy) < lowest:
			lowest = p.energy
			tired = p
	if tired == null:
		return
	var slot_i: int = xi[s].find(tired)
	var best = null
	var bv := -1.0
	for b in bench(s):
		var v := GameData.rating(b) * GameData.slot_factor(b, slots[s][slot_i]) * GameData.form_factor(b)
		if v > bv:
			bv = v
			best = b
	if best:
		substitute(s, slot_i, best)


func bench(s: int) -> Array:
	var on := {}
	for p in xi[s]:
		on[int(p.id)] = true
	return teams[s].players.filter(func(p): return not on.has(int(p.id)) and not subbed_off.has(int(p.id)))


func substitute(s: int, slot_i: int, incoming: Dictionary) -> bool:
	if subs_left[s] <= 0:
		return false
	var out: Dictionary = xi[s][slot_i]
	subbed_off[int(out.id)] = true
	xi[s][slot_i] = incoming
	minutes_played[int(incoming.id)] = 0
	subs_left[s] -= 1
	_event(minute, "Cambio en %s: entra %s, sale %s." % [teams[s].short, incoming.name, out.name], "sub", s)
	return true


func _finish() -> void:
	finished = true
	_event(minute, "¡FINAL! %s %d - %d %s" % [teams[0].name, score[0], score[1], teams[1].name], "end", -1)
	# Ánimo y partidos jugados del equipo del usuario
	var u := user_side
	var res := signi(score[u] - score[1 - u])
	for p in teams[u].players:
		var played := minutes_played.has(int(p.id))
		if played:
			p.apps = int(p.apps) + 1
			p.morale = clampf(float(p.morale) + [-6.0, 1.5, 7.0][res + 1], 5, 100)
		else:
			p.morale = clampf(float(p.morale) - 1.5 + (1.0 if res > 0 else 0.0), 5, 100)
	GameData.stats.played += 1


# ------------------------------------------------------------------ Jugadas clave

func moment_payload() -> Dictionary:
	## Datos que necesita la escena 3D para montar la jugada.
	var u := user_side
	var home_xi: Array = []
	var away_xi: Array = []
	for i in xi[u].size():
		home_xi.append(GameData.effective(xi[u][i], slots[u][i]))
	for i in xi[1 - u].size():
		away_xi.append(GameData.effective(xi[1 - u][i], slots[1 - u][i]))
	return {"jugada": pending.jugada, "user_team": teams[u], "rival_team": teams[1 - u], "home_xi": home_xi,
		"away_xi": away_xi, "minute": minute_label(), "score_user": score[u], "score_rival": score[1 - u],
		"user_is_home": u == 0, "context": context}


func apply_result(result: Dictionary) -> void:
	## Resultado de la jugada jugada en 3D.
	var side: int = pending.side
	moments_played += 1
	var kind: String = pending.kind
	if result.get("goal_for", false):
		stats.shots[user_side] += 1
		stats.on_target[user_side] += 1
		var scorer := _player_by_name(user_side, result.get("scorer", ""))
		_goal(user_side, scorer, "¡GOOOL de %s en la jugada clave!" % scorer.name)
	elif result.get("goal_against", false):
		stats.shots[1 - user_side] += 1
		stats.on_target[1 - user_side] += 1
		var sc := _player_by_name(1 - user_side, result.get("scorer", ""))
		_goal(1 - user_side, sc, "Gol de %s. No pudiste evitarlo." % sc.name)
	else:
		if kind in ["attack", "freekick", "penalty_for", "corner"]:
			stats.shots[user_side] += 1
		_event(minute, result.get("text", "La jugada termina sin gol."), "chance", side)
	pending = {}


func auto_resolve() -> void:
	## El usuario decide no jugar la jugada: se resuelve con probabilidades.
	var kind: String = pending.kind
	var u := user_side
	var me := power(u)
	var op := power(1 - u)
	var res := {}
	match kind:
		"attack", "corner":
			var p := clampf(0.24 * pow(me.att / op.def, 1.5), 0.06, 0.5)
			if randf() < p:
				res = {"goal_for": true, "scorer": _pick_shooter(u).name}
			else:
				res = {"text": "Llegaron al área, pero la ocasión se perdió."}
		"defend":
			var p2 := clampf(0.24 * pow(op.att / me.def, 1.5), 0.06, 0.5)
			if randf() < p2:
				res = {"goal_against": true, "scorer": _pick_shooter(1 - u).name}
			else:
				res = {"text": "Tu defensa resolvió el peligro."}
		"freekick":
			var t := _best_taker(u)
			if randf() < 0.08 + t.tl / 800.0:
				res = {"goal_for": true, "scorer": t.name}
			else:
				res = {"text": "El tiro libre de %s no entró." % t.name}
		"penalty_for":
			var t2 := _pick_shooter(u)
			if randf() < 0.72 + t2.sho / 1000.0:
				res = {"goal_for": true, "scorer": t2.name}
			else:
				res = {"text": "¡%s falla el penal!" % t2.name}
		"penalty_against":
			if randf() < 0.75:
				res = {"goal_against": true, "scorer": _pick_shooter(1 - u).name}
			else:
				res = {"text": "¡Tu portero detiene el penal!"}
	apply_result(res)


# ------------------------------------------------------------------ Utilidades

func _random_player(s: int, roles: Array) -> Dictionary:
	var pool: Array = xi[s].filter(func(p): return GameData.POS_ROLE[p.pos] in roles)
	if pool.is_empty():
		pool = xi[s]
	return pool[randi() % pool.size()]


func _pick_shooter(s: int, header := false) -> Dictionary:
	var best = xi[s][0]
	var bv := -1.0
	for i in xi[s].size():
		var p: Dictionary = xi[s][i]
		var role: String = GameData.POS_ROLE[slots[s][i]]
		var w := {"GK": 0.0, "DEF": 0.25, "MID": 0.8, "FWD": 2.2}[role] as float
		if header and role == "DEF":
			w = 1.2
		var v := w * float(p.sho) * randf()
		if v > bv:
			bv = v
			best = p
	return best


func _best_taker(s: int) -> Dictionary:
	var best = xi[s][0]
	for p in xi[s]:
		if p.tl > best.tl:
			best = p
	return best


func _goalkeeper(s: int) -> Dictionary:
	for i in xi[s].size():
		if slots[s][i] == "POR":
			return xi[s][i]
	return xi[s][0]


func _player_by_name(s: int, name: String) -> Dictionary:
	for p in xi[s]:
		if p.name == name:
			return p
	return _pick_shooter(s)


func possession() -> Array:
	var t: float = stats.poss[0] + stats.poss[1]
	if t <= 0.0:
		return [50, 50]
	var h := int(round(stats.poss[0] / t * 100.0))
	return [h, 100 - h]

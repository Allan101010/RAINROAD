class_name Jugadas
extends RefCounted
## Catálogo de jugadas clave (más de 100) generado a partir de plantillas con variantes
## (lado, zona, número de jugadores, distancia...). El simulador elige una según el
## contexto del partido y evita repetir dentro del mismo partido.
##
## Convención: tu equipo (HOME) siempre ataca hacia +X. En las jugadas defensivas
## el rival ataca hacia -X, donde está tu portería.

const GROUP_NAMES := {
	"contra": "Contraataques", "frontal": "Ataque en la frontal", "1v1": "Mano a mano",
	"banda": "Juego por banda", "rechace": "Rechaces en el área", "corner": "Córners a favor",
	"falta": "Tiros libres", "penal": "Penales a favor", "penal_contra": "Penales en contra",
	"def_contra": "Defender contraataques", "def_frontal": "Defender la frontal",
	"def_banda": "Defender centros", "def_1v1": "Defender mano a mano",
}
const ATTACK_GROUPS := ["contra", "frontal", "1v1", "banda", "rechace"]
const DEFEND_GROUPS := ["def_contra", "def_frontal", "def_banda", "def_1v1"]

static var _catalog: Array = []


static func all() -> Array:
	if _catalog.is_empty():
		_build()
	return _catalog


static func by_group(group: String) -> Array:
	return all().filter(func(j): return j.group == group)


static func get_by_id(id: int) -> Dictionary:
	for j in all():
		if j.id == id:
			return j
	return {}


static func _add(j: Dictionary) -> void:
	j["id"] = _catalog.size() + 1
	_catalog.append(j)


static func _side_name(z: float) -> String:
	if z < -4:
		return "por la izquierda"
	if z > 4:
		return "por la derecha"
	return "por el centro"


static func _build() -> void:
	_catalog.clear()
	var gk_away := {"role": "GK", "pos": Vector3(51, 0, 0)}
	var gk_home := {"role": "GK", "pos": Vector3(-51, 0, 0)}

	# --- Contraataques: 3 superioridades x 3 carriles x 2 zonas de inicio = 18
	for n in [[2, 1], [3, 2], [4, 3]]:
		for z in [-14.0, 0.0, 14.0]:
			for x0 in [-12.0, 4.0]:
				var home: Array = [{"role": "FWD", "pos": Vector3(x0, 0, z), "ball": true}]
				var lanes := [-16.0, 16.0, 0.0] if z == 0.0 else ([0.0, 18.0 * -signf(z), -8.0 * signf(z)])
				for k in n[0] - 1:
					var lane: float = lanes[k]
					home.append({"role": "FWD" if k == 0 else "MID", "pos": Vector3(x0 - 3 - k * 2, 0, lane), "lane": lane})
				var away: Array = [gk_away]
				for k in n[1]:
					var dz: float = (k - (n[1] - 1) / 2.0) * 11.0
					away.append({"role": "DEF", "pos": Vector3(x0 + 26 + k * 2, 0, dz + z * 0.3)})
				away.append({"role": "MID", "pos": Vector3(x0 - 5, 0, z + 5)})
				_add({"name": "Contraataque %d contra %d %s%s" % [n[0], n[1], _side_name(z), " desde tu campo" if x0 < 0 else ""],
					"group": "contra", "mode": "attack", "time": 32.0 if x0 < 0 else 25.0, "home": home, "away": away})

	# --- Ataque en la frontal: 3 posiciones x 3 densidades = 9
	for z in [-9.0, 0.0, 9.0]:
		for nd in [4, 5, 6]:
			var home2: Array = [{"role": "MID", "pos": Vector3(30, 0, z), "ball": true},
				{"role": "FWD", "pos": Vector3(37, 0, -z * 0.5 + 4), "lane": 4.0},
				{"role": "FWD", "pos": Vector3(35, 0, -16), "lane": -12.0},
				{"role": "FWD", "pos": Vector3(33, 0, 16), "lane": 12.0}]
			var away2: Array = [gk_away]
			var spots := [Vector3(41, 0, -3), Vector3(41, 0, 4), Vector3(38, 0, -12), Vector3(38, 0, 12), Vector3(34, 0, z + 2), Vector3(44, 0, 0)]
			for k in nd:
				away2.append({"role": "DEF" if k < 4 else "MID", "pos": spots[k]})
			_add({"name": "Ataque en la frontal %s contra %d defensas" % [_side_name(z), nd], "group": "frontal",
				"mode": "attack", "time": 24.0, "home": home2, "away": away2})

	# --- Mano a mano: 2 distancias x 3 ángulos = 6
	for x in [18.0, 26.0]:
		for z in [-10.0, 0.0, 10.0]:
			_add({"name": "Mano a mano %s desde %d metros" % [_side_name(z), int(52.5 - x)], "group": "1v1",
				"mode": "attack", "time": 12.0,
				"home": [{"role": "FWD", "pos": Vector3(x, 0, z), "ball": true}],
				"away": [gk_away, {"role": "DEF", "pos": Vector3(x - 4, 0, z + 3)}]})

	# --- Juego por banda (desborde y centro): 2 lados x 2 alturas x 2 rematadores = 8
	for side in [-1.0, 1.0]:
		for x in [28.0, 38.0]:
			for nb in [2, 3]:
				var home3: Array = [{"role": "FWD", "pos": Vector3(x, 0, 24 * side), "ball": true},
					{"role": "FWD", "pos": Vector3(40, 0, -2 * side), "lane": -2.0 * side},
					{"role": "MID", "pos": Vector3(34, 0, 6 * side), "lane": 6.0 * side}]
				if nb == 3:
					home3.append({"role": "FWD", "pos": Vector3(42, 0, -9 * side), "lane": -8.0 * side})
				var away3: Array = [gk_away, {"role": "DEF", "pos": Vector3(x + 3, 0, 21 * side)},
					{"role": "DEF", "pos": Vector3(45, 0, 0)}, {"role": "DEF", "pos": Vector3(44, 0, -6 * side)},
					{"role": "DEF", "pos": Vector3(44, 0, 5 * side)}]
				_add({"name": "Desborde por la banda %s, %d rematadores en el área" % ["izquierda" if side < 0 else "derecha", nb],
					"group": "banda", "mode": "attack", "time": 22.0, "home": home3, "away": away3})

	# --- Rechaces: 2 lados x 2 = 4
	for z in [-4.0, 4.0]:
		for strong in [false, true]:
			_add({"name": "Rechace del portero %s%s" % [_side_name(z * 3), " con el área llena" if strong else ""],
				"group": "rechace", "mode": "attack", "time": 10.0, "loose_ball": Vector3(44, 0.3, z),
				"loose_vel": Vector3(-4, 2, z * 0.6),
				"home": [{"role": "FWD", "pos": Vector3(39, 0, z * 2), "ball": false}, {"role": "FWD", "pos": Vector3(41, 0, -z * 2), "lane": -z * 2}],
				"away": [{"role": "GK", "pos": Vector3(51.5, 0, z * 0.5)}, {"role": "DEF", "pos": Vector3(46, 0, -z)},
					{"role": "DEF", "pos": Vector3(42, 0, z * 2.5)}] + ([{"role": "DEF", "pos": Vector3(40, 0, 0)}] if strong else [])})

	# --- Córners a favor: 2 lados x 3 zonas = 6
	for side in [-1.0, 1.0]:
		for t in [[Vector3(47.5, 0, 2.5 * side), "primer palo"], [Vector3(41.5, 0, 0), "punto de penal"], [Vector3(47, 0, -3.5 * side), "segundo palo"]]:
			var tgt: Vector3 = t[0]
			_add({"name": "Córner desde la %s al %s" % ["izquierda" if side < 0 else "derecha", t[1]], "group": "corner",
				"mode": "corner", "time": 9.0, "corner_side": side, "target": tgt,
				"home": [{"role": "MID", "pos": Vector3(52.3, 0, 33.6 * side), "taker": true},
					{"role": "DEF", "pos": tgt + Vector3(-6, 0, 1)}, {"role": "FWD", "pos": Vector3(44, 0, -5 * side)},
					{"role": "FWD", "pos": Vector3(43, 0, 5 * side)}, {"role": "DEF", "pos": Vector3(40, 0, 0)}],
				"away": [gk_away, {"role": "DEF", "pos": tgt + Vector3(0.8, 0, 0.6)}, {"role": "DEF", "pos": Vector3(46, 0, 0)},
					{"role": "DEF", "pos": Vector3(45, 0, -5 * side)}, {"role": "DEF", "pos": Vector3(48, 0, 3.6 * side)}]})

	# --- Tiros libres directos: 5 distancias x 5 ángulos = 25
	for d in [18.0, 21.0, 24.0, 27.0, 30.0]:
		for ang in [-28.0, -14.0, 0.0, 14.0, 28.0]:
			var a := deg_to_rad(ang)
			var bp := Vector3(52.5 - d * cos(a), 0, d * sin(a))
			var desc := "frontal" if ang == 0.0 else ("escorado a la %s" % ("izquierda" if ang < 0 else "derecha"))
			_add({"name": "Tiro libre %s a %d metros" % [desc, int(d)], "group": "falta", "mode": "freekick",
				"time": 8.0, "ball_pos": bp, "wall": 3 if d > 26 else (4 if d > 21 else 5) - (1 if absf(ang) > 20 else 0),
				"home": [{"role": "FWD", "pos": Vector3(46, 0, -3)}, {"role": "FWD", "pos": Vector3(45, 0, 5)}],
				"away": [gk_away, {"role": "DEF", "pos": Vector3(47, 0, -2)}, {"role": "DEF", "pos": Vector3(47, 0, 4)}]})

	# --- Penales
	_add({"name": "Penal a favor", "group": "penal", "mode": "penalty_for", "time": 8.0, "ball_pos": Vector3(41.5, 0, 0),
		"home": [], "away": [gk_away]})
	_add({"name": "Penal a favor en un momento decisivo", "group": "penal", "mode": "penalty_for", "time": 8.0,
		"ball_pos": Vector3(41.5, 0, 0), "home": [], "away": [gk_away]})
	_add({"name": "Penal en contra: ¡adivina el lado!", "group": "penal_contra", "mode": "penalty_against", "time": 8.0,
		"ball_pos": Vector3(-41.5, 0, 0), "home": [gk_home], "away": [{"role": "FWD", "pos": Vector3(-38.5, 0, 1.5), "taker": true}]})

	# --- Defender contraataques: 3 situaciones x 3 carriles x 2 zonas = 18
	for n in [[2, 1], [3, 2], [3, 3]]:
		for z in [-14.0, 0.0, 14.0]:
			for x0 in [8.0, -6.0]:
				var away4: Array = [{"role": "FWD", "pos": Vector3(x0, 0, z), "ball": true}]
				var lanes2 := [-16.0, 16.0] if z == 0.0 else [0.0, 18.0 * -signf(z)]
				for k in n[0] - 1:
					var lane2: float = lanes2[k]
					away4.append({"role": "FWD" if k == 0 else "MID", "pos": Vector3(x0 + 3 + k * 2, 0, lane2), "lane": lane2})
				var home4: Array = [gk_home]
				for k in n[1]:
					var dz2: float = (k - (n[1] - 1) / 2.0) * 11.0
					home4.append({"role": "DEF", "pos": Vector3(x0 - 24 - k * 2, 0, dz2 + z * 0.3)})
				home4.append({"role": "MID", "pos": Vector3(x0 + 5, 0, z - 4)})
				_add({"name": "Defender contraataque rival %d contra %d %s" % [n[0], n[1], _side_name(z)],
					"group": "def_contra", "mode": "defend", "time": 22.0 if x0 > 0 else 18.0, "home": home4, "away": away4})

	# --- Defender la frontal: 3 posiciones x 2 = 6
	for z in [-9.0, 0.0, 9.0]:
		for extra in [false, true]:
			var away5: Array = [{"role": "MID", "pos": Vector3(-30, 0, z), "ball": true},
				{"role": "FWD", "pos": Vector3(-37, 0, 4), "lane": 4.0}, {"role": "FWD", "pos": Vector3(-35, 0, -14), "lane": -12.0}]
			if extra:
				away5.append({"role": "FWD", "pos": Vector3(-33, 0, 15), "lane": 12.0})
			var home5: Array = [gk_home, {"role": "DEF", "pos": Vector3(-41, 0, -3)}, {"role": "DEF", "pos": Vector3(-41, 0, 4)},
				{"role": "DEF", "pos": Vector3(-38, 0, -12)}, {"role": "DEF", "pos": Vector3(-38, 0, 12)}, {"role": "MID", "pos": Vector3(-27, 0, z + 3)}]
			_add({"name": "Defender un ataque en la frontal %s%s" % [_side_name(z), " con 4 atacantes" if extra else ""],
				"group": "def_frontal", "mode": "defend", "time": 18.0, "home": home5, "away": away5})

	# --- Defender centros por banda: 2 lados x 2 = 4
	for side in [-1.0, 1.0]:
		for x in [-30.0, -40.0]:
			_add({"name": "Defender un desborde por la %s" % ("izquierda" if side < 0 else "derecha"), "group": "def_banda",
				"mode": "defend", "time": 16.0,
				"away": [{"role": "FWD", "pos": Vector3(x, 0, 24 * side), "ball": true},
					{"role": "FWD", "pos": Vector3(-40, 0, -2 * side), "lane": -2.0 * side},
					{"role": "MID", "pos": Vector3(-35, 0, 7 * side), "lane": 6.0 * side}],
				"home": [gk_home, {"role": "DEF", "pos": Vector3(x - 3, 0, 21 * side)}, {"role": "DEF", "pos": Vector3(-45, 0, 0)},
					{"role": "DEF", "pos": Vector3(-44, 0, -6 * side)}, {"role": "DEF", "pos": Vector3(-44, 0, 5 * side)}]})

	# --- Defender un mano a mano (persigues al delantero): 3
	for z in [-8.0, 0.0, 8.0]:
		_add({"name": "Defender un mano a mano %s" % _side_name(z), "group": "def_1v1", "mode": "defend", "time": 12.0,
			"away": [{"role": "FWD", "pos": Vector3(-20, 0, z), "ball": true}],
			"home": [gk_home, {"role": "DEF", "pos": Vector3(-16, 0, z + 2.5)}]})


## Elige una jugada para la situación. "kind" puede ser "attack", "defend", "freekick",
## "penalty_for", "penalty_against" o "corner". "ctx" lleva datos del partido para decidir.
static func pick(kind: String, ctx: Dictionary, used: Dictionary) -> Dictionary:
	var groups: Dictionary = {}
	var pace_for: float = ctx.get("pace_for", 70.0)
	var pace_against: float = ctx.get("pace_against", 70.0)
	var losing: bool = ctx.get("losing", false)
	match kind:
		"attack":
			groups = {"contra": 1.0 + maxf(0, pace_for - 70) / 15.0 + (0.5 if not losing else 0.0),
				"frontal": 1.2 + (0.8 if losing else 0.0), "1v1": 0.5 + maxf(0, pace_for - 75) / 15.0,
				"banda": 1.0, "rechace": 0.5}
		"defend":
			groups = {"def_contra": 1.0 + maxf(0, pace_against - 70) / 12.0 + (0.6 if losing else 0.0),
				"def_frontal": 1.2, "def_banda": 0.9, "def_1v1": 0.4 + maxf(0, pace_against - 78) / 12.0}
		"freekick":
			groups = {"falta": 1.0}
		"penalty_for":
			groups = {"penal": 1.0}
		"penalty_against":
			groups = {"penal_contra": 1.0}
		"corner":
			groups = {"corner": 1.0}
	var candidates: Array = []
	var weights: Array = []
	for j in all():
		if not groups.has(j.group):
			continue
		var w: float = groups[j.group]
		if used.has(j.id):
			w *= 0.05  # casi nunca se repite en el mismo partido
		candidates.append(j)
		weights.append(w)
	if candidates.is_empty():
		return {}
	var total := 0.0
	for w in weights:
		total += w
	var r := randf() * total
	for i in candidates.size():
		r -= weights[i]
		if r <= 0.0:
			return candidates[i]
	return candidates.back()

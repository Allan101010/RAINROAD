extends Node
## Datos globales del juego: equipos, jugadores y jugadas clave.
## Es la base del futuro modo mánager (plantilla, fichajes, liga...).

var home_team := {
	"name": "Halcones FC", "short": "HAL",
	"kit": {"shirt": Color(0.82, 0.08, 0.14), "shorts": Color(0.95, 0.95, 0.95),
		"socks": Color(0.82, 0.08, 0.14), "number": Color(1, 1, 1), "gk": Color(0.15, 0.85, 0.35)},
}

var away_team := {
	"name": "Atlético Tormenta", "short": "TOR",
	"kit": {"shirt": Color(0.12, 0.32, 0.85), "shorts": Color(0.08, 0.1, 0.25),
		"socks": Color(0.12, 0.32, 0.85), "number": Color(1, 0.9, 0.2), "gk": Color(0.95, 0.6, 0.1)},
}

# Atributos de 0 a 100: spd = velocidad/regate, pas = pase, sho = tiro,
# dfn = defensa, gkp = portería.
var home_players: Array = [
	{"name": "Rubén Saldaña", "number": 1, "pos": "GK", "spd": 45, "pas": 55, "sho": 30, "dfn": 40, "gkp": 78},
	{"name": "Iván Prieto", "number": 2, "pos": "DEF", "spd": 72, "pas": 64, "sho": 45, "dfn": 74, "gkp": 10},
	{"name": "Mateo Ríos", "number": 4, "pos": "DEF", "spd": 62, "pas": 60, "sho": 40, "dfn": 79, "gkp": 10},
	{"name": "Óscar Lema", "number": 5, "pos": "DEF", "spd": 60, "pas": 63, "sho": 42, "dfn": 77, "gkp": 10},
	{"name": "Bruno Gallardo", "number": 3, "pos": "DEF", "spd": 75, "pas": 66, "sho": 48, "dfn": 71, "gkp": 10},
	{"name": "Diego Ferraz", "number": 6, "pos": "MID", "spd": 66, "pas": 76, "sho": 58, "dfn": 72, "gkp": 10},
	{"name": "Tomás Aguirre", "number": 8, "pos": "MID", "spd": 74, "pas": 80, "sho": 70, "dfn": 60, "gkp": 10},
	{"name": "Lucas Benítez", "number": 10, "pos": "MID", "spd": 80, "pas": 86, "sho": 78, "dfn": 45, "gkp": 10},
	{"name": "Julián Morales", "number": 7, "pos": "FWD", "spd": 88, "pas": 72, "sho": 76, "dfn": 35, "gkp": 10},
	{"name": "Andrés Castillo", "number": 9, "pos": "FWD", "spd": 82, "pas": 68, "sho": 85, "dfn": 38, "gkp": 10},
	{"name": "Samuel Ortega", "number": 11, "pos": "FWD", "spd": 86, "pas": 70, "sho": 74, "dfn": 36, "gkp": 10},
]

var away_players: Array = [
	{"name": "Fabián Cordero", "number": 1, "pos": "GK", "spd": 45, "pas": 50, "sho": 30, "dfn": 40, "gkp": 74},
	{"name": "Néstor Vidal", "number": 2, "pos": "DEF", "spd": 70, "pas": 58, "sho": 40, "dfn": 72, "gkp": 10},
	{"name": "Raúl Quesada", "number": 4, "pos": "DEF", "spd": 64, "pas": 55, "sho": 38, "dfn": 76, "gkp": 10},
	{"name": "Esteban Mora", "number": 5, "pos": "DEF", "spd": 61, "pas": 57, "sho": 40, "dfn": 75, "gkp": 10},
	{"name": "Hugo Alfaro", "number": 3, "pos": "DEF", "spd": 73, "pas": 60, "sho": 42, "dfn": 70, "gkp": 10},
	{"name": "Marco Villalobos", "number": 6, "pos": "MID", "spd": 68, "pas": 70, "sho": 55, "dfn": 70, "gkp": 10},
	{"name": "Kevin Solís", "number": 8, "pos": "MID", "spd": 72, "pas": 74, "sho": 64, "dfn": 62, "gkp": 10},
	{"name": "Adrián Rojas", "number": 10, "pos": "MID", "spd": 78, "pas": 80, "sho": 72, "dfn": 48, "gkp": 10},
	{"name": "Felipe Arce", "number": 7, "pos": "FWD", "spd": 84, "pas": 66, "sho": 72, "dfn": 34, "gkp": 10},
	{"name": "Gerardo Brenes", "number": 9, "pos": "FWD", "spd": 78, "pas": 62, "sho": 80, "dfn": 36, "gkp": 10},
	{"name": "Pablo Jiménez", "number": 11, "pos": "FWD", "spd": 83, "pas": 65, "sho": 70, "dfn": 35, "gkp": 10},
]

# Jugadas clave. "idx" es el índice del jugador en la plantilla.
# El equipo local siempre ataca hacia +X (a la derecha de la pantalla).
var scenarios := {
	"contraataque": {
		"title": "Contraataque",
		"desc": "Minuto 78, empate 1-1. Robaste el balón en el medio campo. ¡Define la jugada!",
		"minute": 78, "score": [1, 1], "time": 35.0,
		"home": [
			{"idx": 9, "pos": Vector3(-6, 0, 3), "ball": true},
			{"idx": 8, "pos": Vector3(-10, 0, -15), "lane": -13.0},
			{"idx": 10, "pos": Vector3(-9, 0, 16), "lane": 13.0},
			{"idx": 7, "pos": Vector3(-16, 0, -2), "lane": 2.0},
		],
		"away": [
			{"idx": 0, "pos": Vector3(51, 0, 0)},
			{"idx": 2, "pos": Vector3(26, 0, -9)},
			{"idx": 3, "pos": Vector3(29, 0, 4)},
			{"idx": 4, "pos": Vector3(24, 0, 15)},
			{"idx": 5, "pos": Vector3(-12, 0, 7)},
		],
	},
	"area": {
		"title": "Ataque en el área",
		"desc": "Minuto 89, pierden 1-2. Tienen el balón en la frontal del área. ¡Hay que empatar!",
		"minute": 89, "score": [1, 2], "time": 25.0,
		"home": [
			{"idx": 7, "pos": Vector3(29, 0, -3), "ball": true},
			{"idx": 9, "pos": Vector3(36, 0, 6), "lane": 4.0},
			{"idx": 8, "pos": Vector3(34, 0, -16), "lane": -12.0},
			{"idx": 10, "pos": Vector3(25, 0, 14), "lane": 12.0},
		],
		"away": [
			{"idx": 0, "pos": Vector3(51, 0, 0)},
			{"idx": 2, "pos": Vector3(40, 0, -3)},
			{"idx": 3, "pos": Vector3(41, 0, 5)},
			{"idx": 1, "pos": Vector3(38, 0, -12)},
			{"idx": 4, "pos": Vector3(37, 0, 12)},
			{"idx": 6, "pos": Vector3(26, 0, 2)},
		],
	},
	"mano_a_mano": {
		"title": "Mano a mano",
		"desc": "Minuto 64, 0-0. Te escapaste solo contra el portero... pero te persiguen.",
		"minute": 64, "score": [0, 0], "time": 12.0,
		"home": [
			{"idx": 9, "pos": Vector3(20, 0, 0), "ball": true},
		],
		"away": [
			{"idx": 0, "pos": Vector3(51, 0, 0)},
			{"idx": 3, "pos": Vector3(16, 0, 3)},
		],
	},
}

var scenario_order := ["contraataque", "area", "mano_a_mano"]
var current_scenario := "contraataque"
var stats := {"played": 0, "goals": 0}


func player_rating(p: Dictionary) -> int:
	if p.pos == "GK":
		return int(p.gkp)
	var weights := {"DEF": [0.25, 0.15, 0.05, 0.55], "MID": [0.25, 0.4, 0.2, 0.15], "FWD": [0.35, 0.2, 0.4, 0.05]}
	var w: Array = weights[p.pos]
	return int(round(p.spd * w[0] + p.pas * w[1] + p.sho * w[2] + p.dfn * w[3]))

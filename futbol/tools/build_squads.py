#!/usr/bin/env python3
"""Genera data/laliga_2026_27.json para el juego.

Entrada: data/plantillas_wikipedia_2026_27.json (plantillas, dorsales y posiciones
de Wikipedia, actualizadas entre septiembre y noviembre de 2026).
Las valoraciones son aproximadas, al estilo de los videojuegos de fútbol, y se
pueden ajustar en la tabla RATINGS de abajo.

Formato de RATINGS: "Nombre": "POS MEDIA [VEL TIR PAS DEF] [tl=NN]"
Si solo se da POS y MEDIA, los atributos se calculan según la posición.
Los jugadores que no aparecen reciben la posición de Wikipedia y una media
según el nivel del equipo.
"""
import json
import os
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Wikipedia, nombre, abreviatura, nivel base, camiseta, pantalón, medias, alternativa, formación
TEAMS = [
    ("Real_Madrid_CF", "Real Madrid", "RMA", 82, "#f2f2f2", "#f2f2f2", "#f2f2f2", "#1d2a5c", "4-3-3"),
    ("FC_Barcelona", "FC Barcelona", "BAR", 81, "#a50044", "#0a2a6e", "#0a2a6e", "#f2c94c", "4-3-3"),
    ("Atlético_Madrid", "Atlético de Madrid", "ATM", 79, "#cb3524", "#1b3a8c", "#cb3524", "#1d2a3a", "4-4-2"),
    ("Athletic_Bilbao", "Athletic Club", "ATH", 76, "#e30613", "#111111", "#111111", "#2e7d32", "4-2-3-1"),
    ("Villarreal_CF", "Villarreal CF", "VIL", 76, "#ffe14d", "#ffe14d", "#ffe14d", "#1b3a8c", "4-4-2"),
    ("Real_Betis", "Real Betis", "BET", 75, "#0bb363", "#f2f2f2", "#0bb363", "#5b2a86", "4-2-3-1"),
    ("Real_Sociedad", "Real Sociedad", "RSO", 75, "#0067b1", "#f2f2f2", "#0067b1", "#e6c229", "4-3-3"),
    ("Sevilla_FC", "Sevilla FC", "SEV", 72, "#f2f2f2", "#f2f2f2", "#d71920", "#d71920", "4-2-3-1"),
    ("Valencia_CF", "Valencia CF", "VAL", 73, "#f2f2f2", "#111111", "#111111", "#f39200", "4-4-2"),
    ("RC_Celta_de_Vigo", "RC Celta", "CEL", 73, "#8ac3ee", "#f2f2f2", "#8ac3ee", "#b22234", "3-5-2"),
    ("CA_Osasuna", "CA Osasuna", "OSA", 72, "#d91a21", "#0a2240", "#0a2240", "#f2f2f2", "4-4-2"),
    ("Rayo_Vallecano", "Rayo Vallecano", "RAY", 73, "#f2f2f2", "#f2f2f2", "#e30613", "#111111", "4-2-3-1"),
    ("Getafe_CF", "Getafe CF", "GET", 72, "#005999", "#005999", "#005999", "#e30613", "5-3-2"),
    ("RCD_Espanyol", "RCD Espanyol", "ESP", 71, "#007fc8", "#f2f2f2", "#007fc8", "#f39200", "4-2-3-1"),
    ("Deportivo_Alavés", "Deportivo Alavés", "ALA", 71, "#0057b8", "#f2f2f2", "#0057b8", "#f2c94c", "4-4-2"),
    ("Levante_UD", "Levante UD", "LEV", 70, "#b4053f", "#004b9b", "#b4053f", "#f2f2f2", "4-4-2"),
    ("Elche_CF", "Elche CF", "ELC", 70, "#f2f2f2", "#f2f2f2", "#05642c", "#05642c", "4-3-3"),
    ("Racing_de_Santander", "Racing de Santander", "RAC", 69, "#f2f2f2", "#111111", "#0a8a3a", "#0a8a3a", "4-2-3-1"),
    ("Deportivo_de_A_Coruña", "Deportivo de La Coruña", "DEP", 70, "#1f5fbf", "#f2f2f2", "#1f5fbf", "#111111", "4-2-3-1"),
    ("Málaga_CF", "Málaga CF", "MAL", 69, "#4f8fe0", "#f2f2f2", "#4f8fe0", "#111111", "4-4-2"),
]

RATINGS = {
    # Real Madrid
    "Thibaut Courtois": "POR 89", "Andriy Lunin": "POR 80",
    "Raúl Asencio": "DFC 79 76 40 60 79", "Éder Militão": "DFC 84 82 55 68 84", "Dean Huijsen": "DFC 83 70 50 74 83",
    "Jude Bellingham": "MCO 89 80 85 84 74", "Eduardo Camavinga": "MC 84 80 66 80 80",
    "Vinícius Júnior": "EI 89 94 84 82 30", "Federico Valverde": "MC 89 88 84 85 80", "Endrick": "DC 78 85 80 65 30",
    "Kylian Mbappé": "DC 91 96 92 82 35", "Rodrygo": "ED 84 88 82 80 35",
    "Trent Alexander-Arnold": "LD 85 75 72 90 74 tl=88", "Aurélien Tchouaméni": "MCD 85 70 72 80 84",
    "Arda Güler": "MCO 83 75 80 86 50 tl=85", "Ibrahima Konaté": "DFC 85 80 45 65 85",
    "Marc Cucurella": "LI 84 80 60 78 82", "Álvaro Carreras": "LI 81 84 55 74 78", "Carlos Espí": "DC 72 72 74 55 30",
    "Bernardo Silva": "MC 86 74 78 88 64", "Brahim Díaz": "MCO 81 85 77 80 38", "Antonio Rüdiger": "DFC 84 78 50 68 86",
    "Ferland Mendy": "LI 79 84 50 72 79", "Denzel Dumfries": "LD 82 85 70 74 76", "Yan Diomande": "ED 79 90 74 74 30",
    "Thiago Pitarch": "MC 70 72 60 70 60",
    # FC Barcelona
    "Joan Garcia": "POR 85", "Wojciech Szczęsny": "POR 82", "Dominik Livaković": "POR 80",
    "João Cancelo": "LD 84 82 72 84 74", "Alejandro Balde": "LI 82 92 58 76 74", "Brian Fariñas": "MCD 68 68 55 70 66",
    "Pau Cubarsí": "DFC 84 74 45 78 85", "Gavi": "MC 82 78 70 82 70", "Fermín López": "MCO 84 80 82 82 60",
    "Pedri": "MC 90 78 78 92 72", "Gabriel Jesus": "DC 80 82 79 76 40", "Lamine Yamal": "ED 91 90 84 89 35 tl=83",
    "Raphinha": "EI 88 89 86 84 45 tl=84", "Xavi Espart": "LD 70 76 50 66 66", "Karim Adeyemi": "ED 81 94 78 74 35",
    "Andreas Christensen": "DFC 81 66 50 76 82", "Rodri": "MCD 88 62 75 88 85", "Anthony Gordon": "EI 84 91 79 78 45",
    "Gerard Martín": "LI 76 80 50 70 74", "Roony Bardghji": "ED 74 85 72 72 30", "Dani Olmo": "MCO 85 78 82 86 50 tl=83",
    "Frenkie de Jong": "MC 87 78 70 88 78", "Marc Bernal": "MCD 74 66 60 76 72", "Jules Koundé": "LD 86 84 55 74 85",
    "Eric Garcia": "DFC 80 68 50 78 79",
    # Atlético de Madrid
    "Juan Musso": "POR 80", "Jan Oblak": "POR 87", "Salvi Esquivel": "POR 66",
    "Obed Vargas": "MC 72 70 62 72 68", "Rodrigo Mendoza": "MC 74 70 64 76 66", "Johnny Cardoso": "MCD 80 70 60 76 80",
    "Koke": "MC 81 55 70 84 74", "Lee Kang-in": "MCO 82 78 78 85 45 tl=82", "Pablo Barrios": "MC 82 74 70 80 76",
    "Alexander Sørloth": "DC 82 74 84 68 40", "Álex Baena": "MCO 84 74 80 86 50 tl=86", "Ademola Lookman": "EI 85 88 82 80 40",
    "Marcos Llorente": "LD 82 85 75 78 76", "Jonathan David": "DC 83 85 84 74 35", "Dávid Hancko": "DFC 83 76 55 72 83",
    "Marc Pubill": "LD 77 78 50 66 76", "Julián Alvarez": "DC 88 85 87 82 55 tl=80", "Giuliano Simeone": "ED 80 86 72 74 60",
    "Cristian Romero": "DFC 86 74 55 70 87", "Alejandro Grimaldo": "LI 85 82 76 86 72 tl=87",
    "Morten Hjulmand": "MCD 82 66 66 78 82", "Robin Le Normand": "DFC 81 66 50 66 82",
    # Athletic Club
    "Unai Simón": "POR 85", "Álex Padilla": "POR 74", "Dani Vivian": "DFC 81 74 45 62 81", "Aitor Paredes": "DFC 77 74 45 60 77",
    "Yeray Álvarez": "DFC 76 66 40 60 77", "Beñat Prados": "MC 77 70 62 76 72", "Álex Berenguer": "EI 77 80 74 74 45",
    "Oihan Sancet": "MCO 83 72 80 80 50", "Iñaki Williams": "ED 80 90 76 70 40", "Nico Williams": "EI 86 93 78 80 38",
    "Gorka Guruzeta": "DC 78 74 78 66 35", "Jesús Areso": "LD 77 82 55 68 74", "Aymeric Laporte": "DFC 81 62 50 74 82",
    "Hugo Rincón": "LD 70 78 45 62 66", "Iñigo Ruiz de Galarreta": "MCD 79 58 64 80 74", "Yuri Berchiche": "LI 77 74 60 74 72",
    "Mikel Jauregizar": "MC 78 70 62 76 74", "Alejandro Rego": "MC 72 70 62 72 60", "Maroan Sannadi": "DC 73 72 72 60 35",
    "Nico Serrano": "ED 70 80 66 66 30", "Robert Navarro": "EI 77 80 74 74 35", "Álvaro Djaló": "ED 74 88 70 68 30",
    "Peio Canales": "MCO 70 72 64 72 50",
    # Villarreal
    "Luiz Júnior": "POR 79", "Péter Gulácsi": "POR 78", "Rubén Gómez": "POR 66",
    "Logan Costa": "DFC 79 72 45 64 79", "Alex Freeman": "LD 74 82 55 66 70", "Pau Navarro": "DFC 74 72 45 62 74",
    "Gerard Moreno": "DC 80 66 84 78 40 tl=80", "Juan Foyth": "DFC 80 74 50 68 80", "Georges Mikautadze": "DC 80 82 80 72 35",
    "Alberto Moleiro": "MCO 81 78 76 82 45 tl=78", "Ilias Akhomach": "ED 75 86 70 72 30", "Renato Veiga": "DFC 80 72 55 72 79",
    "Santi Comesaña": "MC 78 70 66 76 74", "Santiago Mouriño": "DFC 77 70 45 62 77", "Tajon Buchanan": "ED 78 90 70 72 55",
    "Pape Gueye": "MCD 80 70 66 74 80", "Nicolas Pépé": "ED 81 86 80 80 35 tl=80", "Carlos Romero": "LI 76 80 55 70 72",
    "Tani Oluwaseyi": "DC 76 84 74 64 35", "Ayoze Pérez": "DC 81 76 82 78 40", "Sergi Cardona": "LI 78 80 55 72 75",
    "Nathan Saliba": "MC 72 72 62 72 66",
    # Real Betis
    "Álvaro Valles": "POR 78", "Diego Conde": "POR 72", "Héctor Bellerín": "LD 77 82 55 72 72",
    "Diego Llorente": "DFC 79 70 50 68 79", "Natan": "DFC 80 76 45 64 80", "Marc Bartra": "DFC 77 60 50 66 77",
    "Antony": "ED 83 86 80 80 40 tl=78", "Pablo Fornals": "MC 80 70 74 82 64", "Cucho Hernández": "DC 81 80 82 72 40",
    "Abde Ezzalzouli": "EI 81 92 74 74 35", "Fran García": "LI 78 86 55 70 72", "Ángel Ortiz": "LD 70 80 45 60 66",
    "Iker Losada": "MCO 72", "Álvaro Fidalgo": "MC 79 66 70 82 64", "Valentín Gómez": "DFC 76 72 45 62 76",
    "Rodrigo Riquelme": "EI 78 82 72 76 50", "Nelson Deossa": "MC 77 76 68 74 70", "Troy Parrott": "DC 78 76 80 68 35",
    "Giovanni Lo Celso": "MCO 82 70 80 85 55 tl=84", "Marc Roca": "MCD 79 58 64 80 76", "Isco": "MCO 83 60 78 88 50 tl=82",
    "Junior Firpo": "LI 76 78 55 70 72", "Aitor Ruibal": "ED 76 76 66 72 66", "Dani Ceballos": "MC 80 66 68 84 64",
    # Real Sociedad
    "Álex Remiro": "POR 83", "Unai Marrero": "POR 70", "Jon Aramburu": "LD 77 84 50 66 74", "Aihen Muñoz": "LI 74 76 50 68 70",
    "Jon Gorrotxategi": "MCD 76 68 60 74 74", "Igor Zubeldia": "DFC 79 64 45 66 80", "Jon Martín": "DFC 76 70 40 60 77",
    "Ander Barrenetxea": "EI 78 84 74 76 40", "Beñat Turrientes": "MC 77 66 64 78 70", "Orri Óskarsson": "DC 77 78 76 62 35",
    "Mikel Oyarzabal": "DC 84 76 84 82 45 tl=82", "Gonçalo Guedes": "ED 78 82 76 74 35", "Takefusa Kubo": "ED 84 86 78 84 40 tl=80",
    "Pablo Marín": "MC 74 70 62 74 62", "Jon Pacheco": "DFC 77 70 45 66 77", "Sergio Gómez": "LI 78 76 70 80 64 tl=80",
    "Carlos Soler": "MC 80 66 76 82 60 tl=82", "Mamadou Sarr": "DFC 74 76 40 58 74", "Álvaro Odriozola": "LD 74 84 55 68 68",
    "Yangel Herrera": "MC 80 72 72 76 76", "Héctor Fort": "LD 75 80 50 66 70", "Arsen Zakharyan": "MCO 77 76 70 78 50",
    "Luka Sučić": "MC 79 70 74 80 62",
    # Sevilla
    "Odysseas Vlachodimos": "POR 76", "Fran González": "POR 68", "Juan Iglesias": "LD 75 76 55 66 72",
    "Kike Salas": "DFC 75 72 45 60 75", "Andrés Castrín": "DFC 72 68 40 58 72", "Lucien Agoumé": "MCD 77 66 60 74 76",
    "Alfon González": "EI 76 82 70 72 40", "Giorgi Kochorashvili": "MC 72", "Robbie Ure": "DC 70 72 70 58 30",
    "Peque Fernández": "MCO 75 76 68 76 45", "Rubén Vargas": "EI 79 86 74 76 40", "Arouna Sangante": "DFC 72 72 40 55 72",
    "Manu Bueno": "MC 74 66 66 76 60", "Fábio Cardoso": "DFC 75 66 45 60 76", "Isaac Romero": "DC 77 78 76 62 35",
    "Gabriel Suazo": "LI 76 76 55 70 72", "Jon Guridi": "MC 75 66 66 76 62", "Lucas Stassin": "DC 74",
    "Félix Correia": "ED 75 84 70 72 35", "Chidera Ejuke": "EI 77 86 70 74 35", "José Ángel Carmona": "LD 76 76 55 68 74",
    "Marcão": "DFC 77 70 45 60 78", "Youssouf Fofana": "MC 79 74 66 76 78",
    # Valencia
    "Stole Dimitrievski": "POR 77", "Guido Rodríguez": "MCD 79 58 64 76 79", "José Copete": "DFC 74 68 40 60 74",
    "Mouctar Diakhaby": "DFC 77 72 45 55 77", "César Tárrega": "DFC 77 72 45 60 77", "Umar Sadiq": "DC 75 80 74 60 35",
    "Arnaut Danjuma": "EI 78 86 76 72 35", "Javi Guerra": "MC 80 74 74 78 66", "Hugo Duro": "DC 77 74 78 64 40",
    "Harvey Elliott": "MCO 80 76 76 82 45 tl=78", "Luis Rioja": "ED 77 82 70 74 50", "Justin de Haas": "DFC 72",
    "José Gayà": "LI 79 72 60 78 74 tl=78", "Diego López": "ED 77 84 72 74 40", "Pepelu": "MCD 78 58 70 80 70 tl=80",
    "Dani Raba": "MCO 75 72 70 74 45", "Dimitri Foulquier": "LD 74 78 50 64 70", "Jesús Vázquez": "LI 74 74 50 68 70",
    "Arnau Martínez": "LD 75 76 50 66 72", "Filip Ugrinić": "MC 76 68 70 76 62", "Pablo Maffeo": "LD 76 76 55 70 72",
    # Celta
    "Altay Bayındır": "POR 76", "Ionuț Radu": "POR 75", "Iván Villar": "POR 70", "Carl Starfelt": "DFC 76 68 40 58 77",
    "Marcos Alonso": "LI 76 62 64 76 72 tl=82", "Sergio Carreira": "LD 74 76 55 68 70", "Ilaix Moriba": "MC 77 74 66 74 72",
    "Borja Iglesias": "DC 78 64 80 68 35", "Miguel Román": "MC 74 66 60 74 70", "Ferran Jutglà": "DC 76 76 76 66 40",
    "Iago Aspas": "MCO 80 58 82 82 35 tl=84", "Pablo Durán": "DC 74 76 74 62 35", "Aleix Febas": "MC 74 66 64 76 64",
    "Álvaro Núñez": "LD 74 78 50 66 70", "Javi Rueda": "LD 72 80 50 62 66", "Yoel Lago": "DFC 72 68 40 56 72",
    "Williot Swedberg": "ED 75 80 72 72 45", "Javi Rodríguez": "DFC 76 72 45 64 76", "Sebastián Cáceres": "DFC 76 70 40 58 76",
    "Javi Galán": "LI 77 82 55 72 72", "Hugo Álvarez": "EI 76 82 70 72 45", "Couhaib Driouech": "ED 77 84 76 72 35",
    # Osasuna
    "Sergio Herrera": "POR 79", "Aitor Fernández": "POR 74", "Jorge Herrando": "DFC 74 68 40 56 74",
    "Lucas Torró": "MCD 77 58 62 72 77", "Jon Moncayola": "MC 77 72 66 72 72", "Iker Muñoz": "MC 74 68 62 72 70",
    "Raúl García": "DC 76 70 76 66 40", "Aimar Oroz": "MCO 78 72 72 80 55", "Kike Barja": "EI 72 76 66 70 40",
    "Rubén García": "ED 76 72 72 78 45", "Diego Rico": "LI 74 72 55 70 70", "Moi Gómez": "MCO 76 68 72 78 50",
    "Ante Budimir": "DC 80 58 82 66 40", "Raúl Moro": "ED 72 84 66 66 30", "Valentin Rosier": "LD 75 76 50 66 72",
    "Romain Del Castillo": "ED 75 78 72 76 40 tl=78", "Jonathan Dubasin": "EI 72", "Enzo Boyomo": "DFC 77 72 40 58 77",
    "Abel Bretones": "LI 75 80 55 66 70", "Alejandro Catena": "DFC 78 62 45 60 79",
    # Rayo Vallecano
    "Dani Cárdenas": "POR 74", "Augusto Batalla": "POR 76", "Emil Audero": "POR 75", "Andrei Rațiu": "LD 78 82 55 70 74",
    "Marash Kumbulla": "DFC 75 66 40 58 75", "Pedro Díaz": "MC 74 66 64 76 62", "Luiz Felipe": "DFC 76 64 45 60 76",
    "Pathé Ciss": "MCD 77 68 60 70 77", "Isi Palazón": "ED 79 78 74 80 50 tl=80", "Unai López": "MC 77 66 66 80 62",
    "Alemão": "DC 75 74 76 60 40", "Sergio Camello": "DC 76 82 74 66 35", "Randy Nteka": "DC 74 70 72 66 40",
    "Giorgi Tsitaishvili": "EI 72", "Mujaid Sadick": "DFC 72", "Adrià Pedrosa": "LI 74", "Álvaro García": "EI 78 86 72 74 50",
    "Jorge de Frutos": "ED 78 86 74 72 50", "Iván Balliu": "LD 75 72 50 66 72", "Fran Pérez": "ED 74 82 68 70 40",
    "Óscar Valentín": "MCD 77 64 50 70 78", "Florian Lejeune": "DFC 78 56 50 62 79",
    # Getafe
    "Jiří Letáček": "POR 74", "David Soria": "POR 78", "Dakonam Djené": "DFC 79 68 40 58 81", "Davinchi": "LI 72 76 45 60 70",
    "Abdel Abqar": "DFC 76 66 40 55 77", "Mario Martín": "MC 74 68 62 74 70", "Juanmi": "DC 76 76 76 70 40",
    "Nemanja Gudelj": "MCD 77 56 64 72 77", "Borja Mayoral": "DC 77 72 78 66 40", "Martín Satriano": "DC 74 76 72 62 40",
    "Ramon Terrats": "MC 74 68 64 74 64", "Dani Carvajal": "LD 82 74 60 78 80", "Kiko Femenía": "LD 72 76 50 66 68",
    "Christantus Uche": "MCO 76 74 70 72 60", "Enes Ünal": "DC 76 62 78 66 40", "Iván Azón": "DC 74 78 70 60 40",
    "Johan Mojica": "LI 75 78 55 70 70", "Orel Mangala": "MC 77 70 62 72 74", "Sebastián Boselli": "DFC 72",
    # Espanyol
    "Marko Dmitrović": "POR 77", "Ángel Fortuño": "POR 68", "Andoni Gorosabel": "LD 74", "Quilindschy Hartman": "LI 74",
    "Urko González de Zárate": "MCD 75", "Clemens Riedel": "DFC 74", "Leandro Cabrera": "DFC 76", "Javi Puado": "DC 78 76 76 70 40",
    "Edu Expósito": "MC 77 66 68 80 60 tl=78", "Roberto Fernández": "DC 74", "Pol Lozano": "MC 74", "Pere Milla": "ED 76 72 74 72 45",
    "Unai Nuñez": "DFC 75", "Bryan Zaragoza": "EI 76 88 70 70 30", "Jofre Carreras": "ED 74 82 66 70 45",
    "Kike García": "DC 75 58 76 64 40", "Omar El Hilali": "LD 76 78 55 64 72", "Tyrhys Dolan": "ED 74",
    # Alavés
    "Antonio Sivera": "POR 77", "Nicolás Valentini": "DFC 74", "Youssef Enríquez": "LI 72", "Denis Suárez": "MC 75",
    "Facundo Garcés": "DFC 76", "Ander Guevara": "MCD 76", "Antonio Blanco": "MC 76", "Mariano Díaz": "DC 73",
    "Carles Aleñá": "MC 75", "Toni Martínez": "DC 76 70 76 64 40", "Nahuel Tenaglia": "DFC 76", "Lucas Boyé": "DC 77 72 76 66 45",
    "Jonny Otto": "LD 74", "Pablo Ibáñez": "MC 74", "Abde Rebbach": "EI 74 86 68 68 30", "Carlos Protesoni": "MCD 73",
    # Levante
    "Mathew Ryan": "POR 76", "Pablo Campos": "POR 70", "Aïssa Mandi": "DFC 75", "Adrián Dela": "DFC 72",
    "Roger Brugué": "ED 74 84 70 68 40", "Jon Ander Olasagasti": "MC 72", "Iván Romero": "DC 74 80 72 62 35", "Petar Ratkov": "DC 74",
    "Jorge Cabello": "DFC 70", "Oriol Rey": "MCD 72", "Karl Etta Eyong": "DC 75 86 72 64 35", "Jeremy Toljan": "LD 74",
    "Manu Sánchez": "LI 74",
    # Elche
    "Matías Dituro": "POR 74", "Pedro Bigas": "DFC 73", "Marc Aguado": "MCD 74", "Federico Redondo": "MCD 75",
    "Germán Valera": "ED 74", "Gonzalo Villar": "MC 75", "Thomas Lemar": "MCO 78 72 72 80 55 tl=78", "Grady Diangana": "ED 74",
    "Tete Morente": "ED 73", "Víctor Chust": "DFC 74", "Ezequiel Ponce": "DC 73", "Facundo Buonanotte": "MCO 76",
    "Martim Neto": "MC 72", "Josan": "ED 73 tl=78", "Yago Santiago": "EI 72", "Bambo Diaby": "DFC 72",
    # Racing de Santander
    "Julen Agirrezabala": "POR 74", "Andrés Martín": "EI 74", "Iñigo Vicente": "MCO 75 tl=78", "Sergio Canales": "MCO 77 tl=80",
    "Juan Carlos Arana": "DC 73", "Aarón Martín": "LI 73", "Matteo Prati": "MC 72", "Maguette Gueye": "MCD 71",
    "Manu Hernando": "DFC 71", "Facundo González": "DFC 72", "Giorgi Guliashvili": "EI 72", "Yassir Zabiri": "DC 72",
    # Deportivo de La Coruña
    "Germán Parreño": "POR 72", "Álvaro Fernández": "POR 73", "Yeremay Hernández": "EI 79 88 74 78 35",
    "Pierre-Emerick Aubameyang": "DC 78 82 80 70 35", "Zakaria Eddahchouri": "DC 72", "David Mella": "ED 74", "Luismi Cruz": "ED 73",
    "Adama Traoré": "ED 76 92 66 70 40", "Angeliño": "LI 77", "Marc Casadó": "MCD 76", "Diego Villares": "MC 72",
    "Mario Soriano": "MCO 75", "Riki Rodríguez": "MC 72", "José María Giménez": "DFC 80", "Ximo Navarro": "LD 72",
    "Adrià Altimira": "LD 74", "Lucas Noubi": "DFC 72", "Arnau Comas": "DFC 72",
    # Málaga
    "Alfonso Herrero": "POR 72", "Jens Cajuste": "MC 75", "Chupete": "DC 72", "David Larrubia": "MCO 73", "Joaquín Muñoz": "ED 71",
    "Carlos Dotor": "MC 72", "Julen Lobete": "EI 72", "Izan Merino": "MC 70", "Adam Aznou": "LI 72", "Juan Berrocal": "DFC 72",
    "Fernando Calero": "DFC 72", "Carlos Puga": "LD 70", "Adrián Niño": "DC 70",
}

# Desplazamientos de cada atributo respecto a la media según la posición
PROFILE = {
    "DFC": (-6, -25, -10, 2), "LD": (3, -20, -5, -2), "LI": (3, -20, -5, -2),
    "MCD": (-6, -14, -2, 0), "MC": (-3, -8, 2, -10), "MCO": (0, -3, 3, -30),
    "ED": (6, -4, -3, -40), "EI": (6, -4, -3, -40), "DC": (2, 2, -10, -42),
}
WIKI_POS = {"GK": "POR", "DF": "DFC", "MF": "MC", "FW": "DC"}


def det(name, lo, hi):
    """Número pseudoaleatorio estable por jugador."""
    return lo + zlib.crc32(name.encode("utf-8")) % (hi - lo + 1)


def build_player(p, base):
    name = p["name"]
    spec = RATINGS.get(name)
    tl = None
    if spec:
        parts = spec.split()
        tl_parts = [x for x in parts if x.startswith("tl=")]
        if tl_parts:
            tl = int(tl_parts[0][3:])
        parts = [x for x in parts if not x.startswith("tl=")]
        pos = parts[0]
        ovr = int(parts[1])
        vals = [int(x) for x in parts[2:6]] if len(parts) >= 6 else None
    else:
        pos = WIKI_POS.get(p["pos"], "MC")
        ovr = base - 7 + det(name, -3, 3)
        vals = None
    out = {"name": name, "number": int(p["no"]) if p["no"] else 0, "pos": pos, "ovr": ovr}
    if pos == "POR":
        out.update({"spd": max(30, ovr - 35), "sho": 25, "pas": max(40, ovr - 25), "dfn": 30, "gkp": ovr, "tl": 25})
    else:
        if vals is None:
            off = PROFILE[pos]
            vals = [ovr + off[i] + det(name + str(i), -3, 3) for i in range(4)]
        spd, sho, pas, dfn = vals
        out.update({"spd": spd, "sho": sho, "pas": pas, "dfn": dfn, "gkp": det(name, 8, 18)})
        if tl is None:
            tl = int(sho * 0.55 + pas * 0.35) - det(name + "tl", 2, 12)
        out["tl"] = tl
    out["res"] = det(name + "res", 62, 90)
    for k in ("spd", "sho", "pas", "dfn", "gkp", "tl", "res", "ovr"):
        out[k] = max(20, min(97, int(out[k])))
    return out


def main():
    raw = json.load(open(os.path.join(ROOT, "data", "plantillas_wikipedia_2026_27.json"), encoding="utf-8"))
    teams = []
    missing = 0
    for wiki, name, short, base, shirt, shorts, socks, alt, form in TEAMS:
        src = [p for p in raw[wiki]["players"]]
        src.sort(key=lambda p: int(p["no"]) if p["no"] else 99)
        src = src[:26]
        used = {int(p["no"]) for p in src if p["no"]}
        players = []
        for p in src:
            if p["name"] not in RATINGS:
                missing += 1
            pl = build_player(p, base)
            if pl["number"] == 0:
                n = 2
                while n in used:
                    n += 1
                used.add(n)
                pl["number"] = n
            players.append(pl)
        teams.append({"name": name, "short": short, "kit": {"shirt": shirt, "shorts": shorts, "socks": socks, "alt": alt},
                      "formation": form, "updated": raw[wiki]["updated"].split("|")[0], "players": players})
    out = os.path.join(ROOT, "data", "laliga_2026_27.json")
    json.dump({"season": "2026/27", "source": "Plantillas y dorsales: Wikipedia (sept.-nov. 2026). Valoraciones aproximadas.",
               "teams": teams}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    total = sum(len(t["players"]) for t in teams)
    print("Equipos: %d  Jugadores: %d  Con valoración propia: %d" % (len(teams), total, total - missing))


if __name__ == "__main__":
    main()

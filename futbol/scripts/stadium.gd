class_name Stadium
extends RefCounted
## Construye el estadio: luz, cielo, césped con franjas, líneas, porterías, gradas y vallas.

const HALF_L := 52.5
const HALF_W := 34.0
const GOAL_HW := 3.66
const GOAL_H := 2.44


static func build(parent: Node3D, home_name := "", away_name := "") -> void:
	_environment(parent)
	_pitch(parent)
	_goal(parent, 1.0)
	_goal(parent, -1.0)
	_stands(parent, home_name, away_name)


static func _environment(parent: Node3D) -> void:
	var we := WorldEnvironment.new()
	var env := Environment.new()
	var sky := Sky.new()
	var sm := ProceduralSkyMaterial.new()
	sm.sky_top_color = Color(0.2, 0.38, 0.72)
	sm.sky_horizon_color = Color(0.65, 0.75, 0.88)
	sm.ground_horizon_color = Color(0.4, 0.45, 0.4)
	sky.sky_material = sm
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.55, 0.6, 0.7)
	env.ambient_light_energy = 0.45
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	we.environment = env
	parent.add_child(we)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-55, -35, 0)
	sun.light_energy = 0.95
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 70.0
	parent.add_child(sun)


static func _pitch(parent: Node3D) -> void:
	var base := MeshUtil.box(Vector3(130, 0.1, 92), Color(0.09, 0.26, 0.1))
	base.position.y = -0.05
	parent.add_child(base)
	var stripes := 14
	var w := 2 * HALF_L / stripes
	for i in stripes:
		var c := Color(0.12, 0.34, 0.13) if i % 2 == 0 else Color(0.15, 0.39, 0.16)
		var s := MeshUtil.box(Vector3(w, 0.02, 2 * HALF_W + 6), c)
		s.position = Vector3(-HALF_L + w * (i + 0.5), 0.0, 0)
		s.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		parent.add_child(s)
	var lw := 0.12
	var white := Color(0.95, 0.95, 0.95)
	var y := 0.02
	_line(parent, Vector3(0, y, HALF_W), Vector3(2 * HALF_L + lw, 0.01, lw))
	_line(parent, Vector3(0, y, -HALF_W), Vector3(2 * HALF_L + lw, 0.01, lw))
	_line(parent, Vector3(HALF_L, y, 0), Vector3(lw, 0.01, 2 * HALF_W))
	_line(parent, Vector3(-HALF_L, y, 0), Vector3(lw, 0.01, 2 * HALF_W))
	_line(parent, Vector3(0, y, 0), Vector3(lw, 0.01, 2 * HALF_W))
	_ring(parent, Vector3(0, y, 0), 9.15 - lw / 2, 9.15 + lw / 2, 0, TAU, white)
	_ring(parent, Vector3(0, y, 0), 0, 0.2, 0, TAU, white)
	for side in [1.0, -1.0]:
		var gx: float = HALF_L * side
		_line(parent, Vector3(gx - 16.5 * side, y, 0), Vector3(lw, 0.01, 40.32))
		_line(parent, Vector3(gx - 8.25 * side, y, 20.16), Vector3(16.5, 0.01, lw))
		_line(parent, Vector3(gx - 8.25 * side, y, -20.16), Vector3(16.5, 0.01, lw))
		_line(parent, Vector3(gx - 5.5 * side, y, 0), Vector3(lw, 0.01, 18.32))
		_line(parent, Vector3(gx - 2.75 * side, y, 9.16), Vector3(5.5, 0.01, lw))
		_line(parent, Vector3(gx - 2.75 * side, y, -9.16), Vector3(5.5, 0.01, lw))
		var spot := Vector3(gx - 11.0 * side, y, 0)
		_ring(parent, spot, 0, 0.2, 0, TAU, white)
		var a := acos(5.5 / 9.15)
		if side > 0:
			_ring(parent, spot, 9.15 - lw / 2, 9.15 + lw / 2, PI - a, PI + a, white)
		else:
			_ring(parent, spot, 9.15 - lw / 2, 9.15 + lw / 2, -a, a, white)
		# Banderines de córner
		for cz in [HALF_W, -HALF_W]:
			var pole := MeshUtil.cylinder(0.03, 1.5, Color(0.95, 0.95, 0.95))
			pole.position = Vector3(gx, 0.75, cz)
			parent.add_child(pole)
			var flag := MeshUtil.box(Vector3(0.02, 0.3, 0.4), Color(1, 0.85, 0.1))
			flag.position = Vector3(gx, 1.35, cz - 0.2 * signf(cz))
			parent.add_child(flag)


static func _line(parent: Node3D, pos: Vector3, size: Vector3) -> void:
	var m := MeshUtil.box(size, Color(0.95, 0.95, 0.95), true)
	m.position = pos
	m.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	parent.add_child(m)


static func _ring(parent: Node3D, pos: Vector3, r0: float, r1: float, a0: float, a1: float, c: Color) -> void:
	var r := MeshUtil.ring(r0, r1, a0, a1, 48, c)
	r.position = pos
	parent.add_child(r)


static func _goal(parent: Node3D, side: float) -> void:
	var gx := HALF_L * side
	var white := Color(0.97, 0.97, 0.97)
	for pz in [GOAL_HW, -GOAL_HW]:
		var post := MeshUtil.cylinder(0.06, GOAL_H, white)
		post.position = Vector3(gx, GOAL_H / 2, pz)
		parent.add_child(post)
	var bar := MeshUtil.cylinder(0.06, GOAL_HW * 2, white)
	bar.rotation_degrees.x = 90
	bar.position = Vector3(gx, GOAL_H, 0)
	parent.add_child(bar)
	var net_c := Color(1, 1, 1, 0.22)
	var depth := 2.0
	var back := MeshUtil.box(Vector3(0.02, GOAL_H, GOAL_HW * 2), net_c)
	back.position = Vector3(gx + depth * side, GOAL_H / 2, 0)
	parent.add_child(back)
	var top := MeshUtil.box(Vector3(depth, 0.02, GOAL_HW * 2), net_c)
	top.position = Vector3(gx + depth / 2 * side, GOAL_H, 0)
	parent.add_child(top)
	for pz in [GOAL_HW, -GOAL_HW]:
		var sidenet := MeshUtil.box(Vector3(depth, GOAL_H, 0.02), net_c)
		sidenet.position = Vector3(gx + depth / 2 * side, GOAL_H / 2, pz)
		parent.add_child(sidenet)
	for i in range(1, 8):
		var vline := MeshUtil.box(Vector3(0.03, GOAL_H, 0.03), Color(1, 1, 1, 0.5))
		vline.position = Vector3(gx + depth * side, GOAL_H / 2, -GOAL_HW + i * GOAL_HW * 2 / 8)
		parent.add_child(vline)


static func _stands(parent: Node3D, home_name: String, away_name: String) -> void:
	var img := Image.create(128, 64, false, Image.FORMAT_RGB8)
	var palette := [Color(0.75, 0.1, 0.12), Color(0.85, 0.85, 0.85), Color(0.15, 0.25, 0.7), Color(0.9, 0.75, 0.2), Color(0.3, 0.3, 0.35), Color(0.6, 0.45, 0.35)]
	for y in 64:
		for x in 128:
			var c: Color = Color(0.07, 0.07, 0.09)
			if y % 4 != 3 and randf() < 0.8:
				c = palette[randi() % palette.size()].darkened(randf() * 0.4)
			img.set_pixel(x, y, c)
	var crowd := StandardMaterial3D.new()
	crowd.albedo_texture = ImageTexture.create_from_image(img)
	crowd.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
	crowd.uv1_scale = Vector3(6, 2, 1)
	crowd.roughness = 1.0
	var specs := [
		[Vector3(0, 7, -HALF_W - 16), Vector3(140, 0.5, 26), Vector3(30, 0, 0)],
		[Vector3(0, 7, HALF_W + 16), Vector3(140, 0.5, 26), Vector3(-30, 0, 0)],
		[Vector3(HALF_L + 18, 7, 0), Vector3(26, 0.5, 100), Vector3(0, 0, 30)],
		[Vector3(-HALF_L - 18, 7, 0), Vector3(26, 0.5, 100), Vector3(0, 0, -30)],
	]
	for sp in specs:
		var mi := MeshInstance3D.new()
		var bm := BoxMesh.new()
		bm.size = sp[1]
		bm.material = crowd
		mi.mesh = bm
		mi.position = sp[0]
		mi.rotation_degrees = sp[2]
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		parent.add_child(mi)
	var texts := ["LALIGA", "FÚTBOL MÁNAGER", home_name.to_upper() if home_name != "" else "HALCONES", away_name.to_upper() if away_name != "" else "RAINROAD"]
	for side in [1.0, -1.0]:
		var board := MeshUtil.box(Vector3(2 * HALF_L + 10, 1.0, 0.15), Color(0.08, 0.12, 0.3))
		board.position = Vector3(0, 0.5, (HALF_W + 4) * side)
		parent.add_child(board)
		for i in 6:
			var l := Label3D.new()
			l.text = texts[i % texts.size()]
			l.font_size = 90
			l.pixel_size = 0.01
			l.modulate = Color(1, 0.85, 0.2) if i % 2 == 0 else Color.WHITE
			l.position = Vector3(-50 + i * 20, 0.5, (HALF_W + 4) * side - 0.1 * side)
			if side > 0:
				l.rotation_degrees.y = 180
			parent.add_child(l)
	# Vallas detrás de las porterías
	for side in [1.0, -1.0]:
		var board2 := MeshUtil.box(Vector3(0.15, 1.0, 40), Color(0.08, 0.12, 0.3))
		board2.position = Vector3((HALF_L + 5) * side, 0.5, 0)
		parent.add_child(board2)

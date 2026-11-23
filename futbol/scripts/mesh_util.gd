class_name MeshUtil
extends RefCounted
## Utilidades para crear geometría sencilla (low-poly) desde código.


static func mat(color: Color, unshaded := false) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = color
	if unshaded:
		m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	if color.a < 1.0:
		m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		m.cull_mode = BaseMaterial3D.CULL_DISABLED
	return m


static func box(size: Vector3, color: Color, unshaded := false) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = size
	bm.material = mat(color, unshaded)
	mi.mesh = bm
	return mi


static func sphere(radius: float, color: Color) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var sm := SphereMesh.new()
	sm.radius = radius
	sm.height = radius * 2.0
	sm.radial_segments = 16
	sm.rings = 8
	sm.material = mat(color)
	mi.mesh = sm
	return mi


static func cylinder(radius: float, height: float, color: Color) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var cm := CylinderMesh.new()
	cm.top_radius = radius
	cm.bottom_radius = radius
	cm.height = height
	cm.radial_segments = 12
	cm.material = mat(color)
	mi.mesh = cm
	return mi


## Anillo plano en el plano XZ (para líneas del campo y el indicador del jugador).
static func ring(r_in: float, r_out: float, a0: float, a1: float, segments: int, color: Color) -> MeshInstance3D:
	var verts := PackedVector3Array()
	var normals := PackedVector3Array()
	for i in segments:
		var t0 := a0 + (a1 - a0) * float(i) / segments
		var t1 := a0 + (a1 - a0) * float(i + 1) / segments
		var p0i := Vector3(cos(t0) * r_in, 0, sin(t0) * r_in)
		var p0o := Vector3(cos(t0) * r_out, 0, sin(t0) * r_out)
		var p1i := Vector3(cos(t1) * r_in, 0, sin(t1) * r_in)
		var p1o := Vector3(cos(t1) * r_out, 0, sin(t1) * r_out)
		verts.append_array([p0i, p0o, p1o, p0i, p1o, p1i])
		for _k in 6:
			normals.append(Vector3.UP)
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = verts
	arrays[Mesh.ARRAY_NORMAL] = normals
	var am := ArrayMesh.new()
	am.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	var m := mat(color, true)
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	am.surface_set_material(0, m)
	var mi := MeshInstance3D.new()
	mi.mesh = am
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	return mi

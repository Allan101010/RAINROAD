class_name UI
extends RefCounted
## Utilidades de interfaz: colores, botones, paneles y etiquetas con estilo.

const BG := Color(0.04, 0.06, 0.11)
const PANEL := Color(0.08, 0.11, 0.18, 0.92)
const PANEL_LIGHT := Color(0.13, 0.17, 0.26, 0.95)
const GOLD := Color(1.0, 0.8, 0.22)
const GREEN := Color(0.18, 0.75, 0.38)
const RED := Color(0.86, 0.2, 0.24)
const BLUE := Color(0.2, 0.45, 0.9)
const GREY := Color(0.28, 0.3, 0.38)
const TEXT := Color(0.93, 0.95, 0.98)
const TEXT_DIM := Color(0.65, 0.7, 0.8)


static func style(color: Color, radius := 14, border := Color(0, 0, 0, 0), border_w := 0, margin := 12) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = color
	sb.set_corner_radius_all(radius)
	if border_w > 0:
		sb.border_color = border
		sb.set_border_width_all(border_w)
	sb.set_content_margin_all(margin)
	sb.anti_aliasing = true
	return sb


static func label(text: String, size := 22, color := TEXT, align := HORIZONTAL_ALIGNMENT_LEFT) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	l.horizontal_alignment = align
	l.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	return l


static func title(text: String, size := 40) -> Label:
	var l := label(text, size, GOLD)
	l.add_theme_constant_override("outline_size", 8)
	l.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.6))
	return l


static func button(text: String, cb: Callable, color := BLUE, min_size := Vector2(0, 60), font := 24) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = min_size
	b.add_theme_font_size_override("font_size", font)
	b.add_theme_color_override("font_color", TEXT)
	b.add_theme_color_override("font_hover_color", Color.WHITE)
	b.add_theme_color_override("font_pressed_color", Color.WHITE)
	b.add_theme_stylebox_override("normal", style(color, 14))
	b.add_theme_stylebox_override("hover", style(color.lightened(0.12), 14))
	b.add_theme_stylebox_override("pressed", style(color.darkened(0.25), 14))
	b.add_theme_stylebox_override("disabled", style(color.darkened(0.5), 14))
	b.add_theme_stylebox_override("focus", style(Color(0, 0, 0, 0), 14, Color(1, 1, 1, 0.5), 2))
	b.pressed.connect(cb)
	return b


static func panel(color := PANEL, radius := 18, margin := 18) -> PanelContainer:
	var p := PanelContainer.new()
	p.add_theme_stylebox_override("panel", style(color, radius, Color(1, 1, 1, 0.06), 1, margin))
	return p


static func vbox(sep := 10) -> VBoxContainer:
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", sep)
	return v


static func hbox(sep := 10) -> HBoxContainer:
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", sep)
	return h


static func margin(m := 24) -> MarginContainer:
	var mc := MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		mc.add_theme_constant_override("margin_" + side, m)
	return mc


static func fill(c: Control) -> void:
	c.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)


static func expand(c: Control, h := true, v := false) -> Control:
	if h:
		c.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	if v:
		c.size_flags_vertical = Control.SIZE_EXPAND_FILL
	return c


static func background(parent: Control, top := Color(0.06, 0.16, 0.12), bottom := Color(0.02, 0.04, 0.08)) -> void:
	var tr := TextureRect.new()
	var gt := GradientTexture2D.new()
	var g := Gradient.new()
	g.colors = PackedColorArray([top, bottom])
	gt.gradient = g
	gt.fill_from = Vector2(0, 0)
	gt.fill_to = Vector2(0, 1)
	gt.width = 4
	gt.height = 256
	tr.texture = gt
	tr.stretch_mode = TextureRect.STRETCH_SCALE
	tr.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	tr.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(tr)
	fill(tr)


static func color_chip(c: Color, c2: Color, size := Vector2(26, 26)) -> Control:
	var p := Panel.new()
	p.custom_minimum_size = size
	var sb := StyleBoxFlat.new()
	sb.bg_color = c
	sb.set_corner_radius_all(int(size.x / 2))
	sb.border_color = c2
	sb.set_border_width_all(4)
	p.add_theme_stylebox_override("panel", sb)
	return p


static func bar(value: float, width := 80.0, height := 10.0) -> Control:
	## Barra de 0 a 100 con color según el valor (energía).
	var bg := Panel.new()
	bg.custom_minimum_size = Vector2(width, height)
	bg.add_theme_stylebox_override("panel", style(Color(0, 0, 0, 0.45), 4, Color(0, 0, 0, 0), 0, 0))
	var fg := Panel.new()
	var c := GREEN if value >= 70 else (GOLD if value >= 45 else RED)
	fg.add_theme_stylebox_override("panel", style(c, 4, Color(0, 0, 0, 0), 0, 0))
	fg.size = Vector2(width * clampf(value / 100.0, 0.0, 1.0), height)
	fg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	bg.add_child(fg)
	return bg


static func rating_color(r: float) -> Color:
	if r >= 80:
		return Color(0.35, 0.95, 0.5)
	if r >= 72:
		return Color(0.75, 0.95, 0.35)
	if r >= 64:
		return GOLD
	return Color(1, 0.5, 0.4)


static func morale_text(m: float) -> String:
	if m >= 80:
		return "Eufórico"
	if m >= 65:
		return "Contento"
	if m >= 45:
		return "Normal"
	if m >= 30:
		return "Molesto"
	return "Hundido"


static func morale_color(m: float) -> Color:
	if m >= 65:
		return Color(0.4, 0.95, 0.5)
	if m >= 45:
		return TEXT_DIM
	return Color(1, 0.5, 0.4)


static func clear(node: Node) -> void:
	for c in node.get_children():
		node.remove_child(c)
		c.queue_free()

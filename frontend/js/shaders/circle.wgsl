// Instanced SDF circle rendering
// Each circle = 6-vertex quad (2 triangles) expanded in vertex shader
// Fragment shader: smoothstep anti-aliased fill + stroke ring

struct ViewUniforms {
  transform: mat3x3f,   // 2D affine from d3-zoom: [[k,0,tx],[0,k,ty],[0,0,1]]
  resolution: vec2f,
  pixel_ratio: f32,
  _pad: f32,
};

@group(0) @binding(0) var<uniform> view: ViewUniforms;

struct CircleInstance {
  @location(0) center: vec2f,     // world-space center (cx, cy)
  @location(1) radius: f32,       // world-space radius
  @location(2) fill_color: vec3f, // RGB fill
  @location(3) fill_alpha: f32,
  @location(4) stroke_color: vec3f,
  @location(5) stroke_alpha: f32,
  @location(6) stroke_width: f32,
};

struct VertexOutput {
  @builtin(position) position: vec4f,
  @location(0) local_pos: vec2f,     // [-1,1] within quad
  @location(1) fill_color: vec3f,
  @location(2) fill_alpha: f32,
  @location(3) stroke_color: vec3f,
  @location(4) stroke_alpha: f32,
  @location(5) radius_px: f32,       // radius in screen pixels
  @location(6) stroke_width_px: f32, // stroke width in screen pixels
};

// 6 vertices for a quad: 2 triangles
const QUAD_VERTS = array<vec2f, 6>(
  vec2f(-1.0, -1.0),
  vec2f( 1.0, -1.0),
  vec2f(-1.0,  1.0),
  vec2f(-1.0,  1.0),
  vec2f( 1.0, -1.0),
  vec2f( 1.0,  1.0),
);

@vertex
fn vs_main(
  @builtin(vertex_index) vertex_index: u32,
  instance: CircleInstance,
) -> VertexOutput {
  let local = QUAD_VERTS[vertex_index];

  // Transform center to screen space
  let world_pos = vec3f(instance.center, 1.0);
  let screen_pos = view.transform * world_pos;

  // Scale radius by zoom level (transform[0][0] = k)
  let k = view.transform[0][0];
  let radius_px = instance.radius * k;

  // Expand quad: radius + stroke + 1px AA margin
  let expand = radius_px + instance.stroke_width * k + 1.5;
  let pos_px = screen_pos.xy + local * expand;

  // Convert to clip space: px -> NDC
  let ndc = (pos_px / view.resolution) * 2.0 - 1.0;

  var out: VertexOutput;
  out.position = vec4f(ndc.x, -ndc.y, 0.0, 1.0);
  out.local_pos = local * expand;
  out.fill_color = instance.fill_color;
  out.fill_alpha = instance.fill_alpha;
  out.stroke_color = instance.stroke_color;
  out.stroke_alpha = instance.stroke_alpha;
  out.radius_px = radius_px;
  out.stroke_width_px = instance.stroke_width * k;
  return out;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4f {
  let dist = length(in.local_pos);

  // Anti-aliasing width in pixels
  let aa = 1.0;

  // Fill: from center to radius
  let fill_edge = smoothstep(in.radius_px + aa, in.radius_px - aa, dist);

  // Stroke ring: between (radius - stroke_width) and radius
  let inner_edge = in.radius_px - in.stroke_width_px;
  let stroke_mask = smoothstep(inner_edge - aa, inner_edge + aa, dist)
                  * smoothstep(in.radius_px + aa, in.radius_px - aa, dist);

  // Composite: fill underneath, stroke on top
  let fill = vec4f(in.fill_color, in.fill_alpha * fill_edge);
  let stroke = vec4f(in.stroke_color, in.stroke_alpha * stroke_mask);

  // Alpha composite (stroke over fill)
  let out_alpha = stroke.a + fill.a * (1.0 - stroke.a);
  if (out_alpha < 0.001) {
    discard;
  }
  let out_rgb = (stroke.rgb * stroke.a + fill.rgb * fill.a * (1.0 - stroke.a)) / out_alpha;

  return vec4f(out_rgb, out_alpha);
}

// Line-as-quad rendering
// Each line = 6-vertex quad expanded perpendicular to line direction
// Fragment shader: 1px anti-aliased edges

struct ViewUniforms {
  transform: mat3x3f,
  resolution: vec2f,
  pixel_ratio: f32,
  _pad: f32,
};

@group(0) @binding(0) var<uniform> view: ViewUniforms;

struct LineInstance {
  @location(0) pos_a: vec2f,   // world-space start
  @location(1) pos_b: vec2f,   // world-space end
  @location(2) color: vec3f,   // RGB
  @location(3) alpha: f32,
  @location(4) width: f32,     // world-space width
};

struct VertexOutput {
  @builtin(position) position: vec4f,
  @location(0) edge_dist: f32,   // distance from center line in px
  @location(1) color: vec3f,
  @location(2) alpha: f32,
  @location(3) half_width_px: f32,
};

// 6 vertices for a quad
// x: 0=start, 1=end
// y: -1=left, +1=right
const QUAD_VERTS = array<vec2f, 6>(
  vec2f(0.0, -1.0),
  vec2f(1.0, -1.0),
  vec2f(0.0,  1.0),
  vec2f(0.0,  1.0),
  vec2f(1.0, -1.0),
  vec2f(1.0,  1.0),
);

@vertex
fn vs_main(
  @builtin(vertex_index) vertex_index: u32,
  instance: LineInstance,
) -> VertexOutput {
  let vert = QUAD_VERTS[vertex_index];

  // Transform endpoints to screen space
  let a_world = vec3f(instance.pos_a, 1.0);
  let b_world = vec3f(instance.pos_b, 1.0);
  let a_screen = (view.transform * a_world).xy;
  let b_screen = (view.transform * b_world).xy;

  // Direction and perpendicular
  let dir = b_screen - a_screen;
  let len = length(dir);

  // Handle degenerate lines
  var normal: vec2f;
  if (len < 0.001) {
    normal = vec2f(0.0, 1.0);
  } else {
    let d = dir / len;
    normal = vec2f(-d.y, d.x);
  }

  // Width in screen pixels
  let k = view.transform[0][0];
  let half_width = max(instance.width * k * 0.5, 0.5);
  let expand = half_width + 1.0; // +1px for AA

  // Interpolate along line and expand perpendicular
  let pos_on_line = mix(a_screen, b_screen, vert.x);
  let pos_px = pos_on_line + normal * vert.y * expand;

  // Convert to clip space
  let ndc = (pos_px / view.resolution) * 2.0 - 1.0;

  var out: VertexOutput;
  out.position = vec4f(ndc.x, -ndc.y, 0.0, 1.0);
  out.edge_dist = vert.y * expand;
  out.color = instance.color;
  out.alpha = instance.alpha;
  out.half_width_px = half_width;
  return out;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4f {
  // Anti-aliased edges
  let dist = abs(in.edge_dist);
  let aa = smoothstep(in.half_width_px + 1.0, in.half_width_px - 0.5, dist);

  let a = in.alpha * aa;
  if (a < 0.001) {
    discard;
  }

  return vec4f(in.color, a);
}

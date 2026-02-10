/**
 * renderer.js — WebGPU instanced renderer for BookGraph.
 *
 * Renders circles (author enclosures + book dots) and lines (citation edges)
 * using two instanced draw calls per frame.
 */

// WGSL shaders as inline strings (avoids fetch for no-build-step setup)
const CIRCLE_WGSL = `
struct ViewUniforms {
  transform: mat3x3f,
  resolution: vec2f,
  pixel_ratio: f32,
  _pad: f32,
};

@group(0) @binding(0) var<uniform> view: ViewUniforms;

struct CircleInstance {
  @location(0) center: vec2f,
  @location(1) radius: f32,
  @location(2) fill_color: vec3f,
  @location(3) fill_alpha: f32,
  @location(4) stroke_color: vec3f,
  @location(5) stroke_alpha: f32,
  @location(6) stroke_width: f32,
};

struct VertexOutput {
  @builtin(position) position: vec4f,
  @location(0) local_pos: vec2f,
  @location(1) fill_color: vec3f,
  @location(2) fill_alpha: f32,
  @location(3) stroke_color: vec3f,
  @location(4) stroke_alpha: f32,
  @location(5) radius_px: f32,
  @location(6) stroke_width_px: f32,
};

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
  let world_pos = vec3f(instance.center, 1.0);
  let screen_pos = view.transform * world_pos;
  let k = view.transform[0][0];
  let radius_px = instance.radius * k;
  let expand = radius_px + instance.stroke_width * k + 1.5;
  let pos_px = screen_pos.xy + local * expand;
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
  let aa = 1.0;
  let fill_edge = smoothstep(in.radius_px + aa, in.radius_px - aa, dist);
  let inner_edge = in.radius_px - in.stroke_width_px;
  let stroke_mask = smoothstep(inner_edge - aa, inner_edge + aa, dist)
                  * smoothstep(in.radius_px + aa, in.radius_px - aa, dist);

  let fill = vec4f(in.fill_color, in.fill_alpha * fill_edge);
  let stroke = vec4f(in.stroke_color, in.stroke_alpha * stroke_mask);

  let out_alpha = stroke.a + fill.a * (1.0 - stroke.a);
  if (out_alpha < 0.001) {
    discard;
  }
  let out_rgb = (stroke.rgb * stroke.a + fill.rgb * fill.a * (1.0 - stroke.a)) / out_alpha;
  return vec4f(out_rgb, out_alpha);
}
`;

const LINE_WGSL = `
struct ViewUniforms {
  transform: mat3x3f,
  resolution: vec2f,
  pixel_ratio: f32,
  _pad: f32,
};

@group(0) @binding(0) var<uniform> view: ViewUniforms;

struct LineInstance {
  @location(0) pos_a: vec2f,
  @location(1) pos_b: vec2f,
  @location(2) color: vec3f,
  @location(3) alpha: f32,
  @location(4) width: f32,
};

struct VertexOutput {
  @builtin(position) position: vec4f,
  @location(0) edge_dist: f32,
  @location(1) color: vec3f,
  @location(2) alpha: f32,
  @location(3) half_width_px: f32,
};

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
  let a_world = vec3f(instance.pos_a, 1.0);
  let b_world = vec3f(instance.pos_b, 1.0);
  let a_screen = (view.transform * a_world).xy;
  let b_screen = (view.transform * b_world).xy;

  let dir = b_screen - a_screen;
  let len = length(dir);
  var normal: vec2f;
  if (len < 0.001) {
    normal = vec2f(0.0, 1.0);
  } else {
    let d = dir / len;
    normal = vec2f(-d.y, d.x);
  }

  let k = view.transform[0][0];
  let half_width = max(instance.width * k * 0.5, 0.5);
  let expand = half_width + 1.0;
  let pos_on_line = mix(a_screen, b_screen, vert.x);
  let pos_px = pos_on_line + normal * vert.y * expand;
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
  let dist = abs(in.edge_dist);
  let aa = smoothstep(in.half_width_px + 1.0, in.half_width_px - 0.5, dist);
  let a = in.alpha * aa;
  if (a < 0.001) {
    discard;
  }
  return vec4f(in.color, a);
}
`;

// Circle instance layout: center(2f) + radius(1f) + fillColor(3f) + fillAlpha(1f)
//                        + strokeColor(3f) + strokeAlpha(1f) + strokeWidth(1f) = 12 floats = 48 bytes
const CIRCLE_FLOATS = 12;
const CIRCLE_BYTES = CIRCLE_FLOATS * 4;

// Line instance layout: posA(2f) + posB(2f) + color(3f) + alpha(1f) + width(1f) = 9 floats = 36 bytes
const LINE_FLOATS = 9;
const LINE_BYTES = LINE_FLOATS * 4;

// Colors (matching CSS variables)
const COLORS = {
  bookSource: [0.769, 0.361, 0.290],    // #c45c4a
  bookCited: [0.290, 0.435, 0.647],     // #4a6fa5
  authorFill: [0.831, 0.647, 0.455],    // gold-ish, very low alpha
  authorStroke: [0.831, 0.647, 0.455],   // gold-ish
  edge: [0.165, 0.165, 0.184],          // #2a2a2f
  edgeHighlight: [0.831, 0.647, 0.455], // --accent
  bg: [0.039, 0.039, 0.047],            // #0a0a0c
};

export class GraphRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.device = null;
    this.context = null;
    this.format = null;

    // Pipelines
    this.circlePipeline = null;
    this.linePipeline = null;

    // Buffers
    this.viewUniformBuffer = null;
    this.circleBuffer = null;
    this.lineBuffer = null;
    this.bindGroup = null;

    // Instance counts
    this.circleCount = 0;
    this.lineCount = 0;

    // CPU-side data arrays (for partial updates)
    this.circleData = null;
    this.lineData = null;

    // View transform (from d3-zoom)
    this.transform = { x: 0, y: 0, k: 1 };

    // Dirty flag — only submit GPU work when needed
    this.dirty = true;
  }

  async init() {
    if (!navigator.gpu) {
      throw new Error('WebGPU not supported');
    }

    const adapter = await navigator.gpu.requestAdapter();
    if (!adapter) {
      throw new Error('No WebGPU adapter found');
    }

    this.device = await adapter.requestDevice();
    this.context = this.canvas.getContext('webgpu');
    this.format = navigator.gpu.getPreferredCanvasFormat();

    this.context.configure({
      device: this.device,
      format: this.format,
      alphaMode: 'premultiplied',
    });

    this._resize();
    this._createPipelines();
    this._createViewBuffer();
  }

  _resize() {
    const dpr = window.devicePixelRatio || 1;
    const w = this.canvas.clientWidth;
    const h = this.canvas.clientHeight;
    this.canvas.width = w * dpr;
    this.canvas.height = h * dpr;
    this.width = w * dpr;
    this.height = h * dpr;
    this.dpr = dpr;
    this.dirty = true;
  }

  handleResize() {
    this._resize();
    this._updateViewUniforms();
  }

  _createPipelines() {
    // Circle pipeline
    const circleModule = this.device.createShaderModule({ code: CIRCLE_WGSL });
    this.circlePipeline = this.device.createRenderPipeline({
      layout: 'auto',
      vertex: {
        module: circleModule,
        entryPoint: 'vs_main',
        buffers: [{
          arrayStride: CIRCLE_BYTES,
          stepMode: 'instance',
          attributes: [
            { shaderLocation: 0, offset: 0,  format: 'float32x2' },  // center
            { shaderLocation: 1, offset: 8,  format: 'float32' },    // radius
            { shaderLocation: 2, offset: 12, format: 'float32x3' },  // fillColor
            { shaderLocation: 3, offset: 24, format: 'float32' },    // fillAlpha
            { shaderLocation: 4, offset: 28, format: 'float32x3' },  // strokeColor
            { shaderLocation: 5, offset: 40, format: 'float32' },    // strokeAlpha
            { shaderLocation: 6, offset: 44, format: 'float32' },    // strokeWidth
          ],
        }],
      },
      fragment: {
        module: circleModule,
        entryPoint: 'fs_main',
        targets: [{
          format: this.format,
          blend: {
            color: { srcFactor: 'src-alpha', dstFactor: 'one-minus-src-alpha', operation: 'add' },
            alpha: { srcFactor: 'one', dstFactor: 'one-minus-src-alpha', operation: 'add' },
          },
        }],
      },
      primitive: { topology: 'triangle-list' },
    });

    // Line pipeline
    const lineModule = this.device.createShaderModule({ code: LINE_WGSL });
    this.linePipeline = this.device.createRenderPipeline({
      layout: 'auto',
      vertex: {
        module: lineModule,
        entryPoint: 'vs_main',
        buffers: [{
          arrayStride: LINE_BYTES,
          stepMode: 'instance',
          attributes: [
            { shaderLocation: 0, offset: 0,  format: 'float32x2' },  // posA
            { shaderLocation: 1, offset: 8,  format: 'float32x2' },  // posB
            { shaderLocation: 2, offset: 16, format: 'float32x3' },  // color
            { shaderLocation: 3, offset: 28, format: 'float32' },    // alpha
            { shaderLocation: 4, offset: 32, format: 'float32' },    // width
          ],
        }],
      },
      fragment: {
        module: lineModule,
        entryPoint: 'fs_main',
        targets: [{
          format: this.format,
          blend: {
            color: { srcFactor: 'src-alpha', dstFactor: 'one-minus-src-alpha', operation: 'add' },
            alpha: { srcFactor: 'one', dstFactor: 'one-minus-src-alpha', operation: 'add' },
          },
        }],
      },
      primitive: { topology: 'triangle-list' },
    });
  }

  _createViewBuffer() {
    // mat3x3f in WebGPU = 3 × vec3f = 48 bytes (each column is vec3f padded to 16 bytes)
    // + resolution(2f) + pixelRatio(1f) + pad(1f) = 16 bytes
    // Total = 48 + 16 = 64 bytes
    this.viewUniformBuffer = this.device.createBuffer({
      size: 64,
      usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST,
    });

    // Create bind groups for both pipelines (they share the same uniform layout)
    this.circleBindGroup = this.device.createBindGroup({
      layout: this.circlePipeline.getBindGroupLayout(0),
      entries: [{ binding: 0, resource: { buffer: this.viewUniformBuffer } }],
    });
    this.lineBindGroup = this.device.createBindGroup({
      layout: this.linePipeline.getBindGroupLayout(0),
      entries: [{ binding: 0, resource: { buffer: this.viewUniformBuffer } }],
    });
  }

  _updateViewUniforms() {
    const { x, y, k } = this.transform;
    // mat3x3f stored as 3 columns, each padded to 16 bytes (vec4 alignment)
    // Column 0: [k, 0, 0, pad]
    // Column 1: [0, k, 0, pad]
    // Column 2: [tx, ty, 1, pad]
    const data = new Float32Array(16); // 64 bytes
    // Scale must be in device pixels to match u_resolution
    const kd = k * this.dpr;
    // Column 0
    data[0] = kd;
    data[1] = 0;
    data[2] = 0;
    data[3] = 0; // padding
    // Column 1
    data[4] = 0;
    data[5] = kd;
    data[6] = 0;
    data[7] = 0; // padding
    // Column 2
    data[8] = x * this.dpr;
    data[9] = y * this.dpr;
    data[10] = 1;
    data[11] = 0; // padding
    // resolution + pixelRatio
    data[12] = this.width;
    data[13] = this.height;
    data[14] = this.dpr;
    data[15] = 0;

    this.device.queue.writeBuffer(this.viewUniformBuffer, 0, data);
    this.dirty = true;
  }

  setTransform(transform) {
    this.transform = transform;
    this._updateViewUniforms();
  }

  /**
   * Build circle instance buffer from graph data.
   * @param {Array} authors - Author nodes with x, y, r, books[], isSource
   * @param {Object} highlightState - { dimmedIds: Set, highlightedIds: Set }
   */
  updateCircles(authors, highlightState = null) {
    // Count total circles: 1 enclosure + N books per author
    let totalCircles = 0;
    for (const a of authors) {
      totalCircles++; // author enclosure
      totalCircles += a.books ? a.books.length : 0; // book circles
    }

    // Allocate or reallocate CPU buffer
    if (!this.circleData || this.circleData.length < totalCircles * CIRCLE_FLOATS) {
      this.circleData = new Float32Array(totalCircles * CIRCLE_FLOATS);
    }

    const hasDim = highlightState && highlightState.dimmedIds && highlightState.dimmedIds.size > 0;

    let offset = 0;
    for (const a of authors) {
      const isDimmed = hasDim && highlightState.dimmedIds.has(a.id);
      const isHighlighted = highlightState && highlightState.highlightedIds && highlightState.highlightedIds.has(a.id);
      const alphaMultiplier = isDimmed ? 0.15 : 1.0;

      // Author enclosure circle
      const i = offset * CIRCLE_FLOATS;
      this.circleData[i + 0] = a.x;                    // center x
      this.circleData[i + 1] = a.y;                    // center y
      this.circleData[i + 2] = a.r;                    // radius
      this.circleData[i + 3] = COLORS.authorFill[0];   // fill R
      this.circleData[i + 4] = COLORS.authorFill[1];   // fill G
      this.circleData[i + 5] = COLORS.authorFill[2];   // fill B
      this.circleData[i + 6] = 0.03 * alphaMultiplier; // fill alpha
      this.circleData[i + 7] = COLORS.authorStroke[0]; // stroke R
      this.circleData[i + 8] = COLORS.authorStroke[1]; // stroke G
      this.circleData[i + 9] = COLORS.authorStroke[2]; // stroke B
      this.circleData[i + 10] = (isHighlighted ? 1.0 : 0.15) * alphaMultiplier; // stroke alpha
      this.circleData[i + 11] = isHighlighted ? 2 : 1; // stroke width
      offset++;

      // Book circles within this author
      if (a.books) {
        for (const b of a.books) {
          const j = offset * CIRCLE_FLOATS;
          const color = b.data.isSource ? COLORS.bookSource : COLORS.bookCited;
          this.circleData[j + 0] = a.x + b.x;            // center x (world = author pos + packed offset)
          this.circleData[j + 1] = a.y + b.y;            // center y
          this.circleData[j + 2] = b.r;                   // radius
          this.circleData[j + 3] = color[0];              // fill R
          this.circleData[j + 4] = color[1];              // fill G
          this.circleData[j + 5] = color[2];              // fill B
          this.circleData[j + 6] = 1.0 * alphaMultiplier; // fill alpha
          this.circleData[j + 7] = 0;                     // stroke R (no stroke)
          this.circleData[j + 8] = 0;                     // stroke G
          this.circleData[j + 9] = 0;                     // stroke B
          this.circleData[j + 10] = 0;                    // stroke alpha
          this.circleData[j + 11] = 0;                    // stroke width
          offset++;
        }
      }
    }

    this.circleCount = offset;

    // Create or update GPU buffer
    const byteLength = offset * CIRCLE_BYTES;
    if (!this.circleBuffer || this.circleBuffer.size < byteLength) {
      if (this.circleBuffer) this.circleBuffer.destroy();
      this.circleBuffer = this.device.createBuffer({
        size: Math.max(byteLength, 64),
        usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST,
      });
    }
    this.device.queue.writeBuffer(this.circleBuffer, 0, this.circleData, 0, offset * CIRCLE_FLOATS);
    this.dirty = true;
  }

  /**
   * Build line instance buffer from graph links.
   * @param {Array} links - Array of { source, target } with x,y positions
   * @param {Object} highlightState - { dimmedLinkIndices: Set, highlightedLinkIndices: Set }
   */
  updateLines(links, highlightState = null) {
    if (!this.lineData || this.lineData.length < links.length * LINE_FLOATS) {
      this.lineData = new Float32Array(links.length * LINE_FLOATS);
    }

    const hasDim = highlightState && highlightState.dimmedLinkIndices && highlightState.dimmedLinkIndices.size > 0;

    for (let idx = 0; idx < links.length; idx++) {
      const l = links[idx];
      const i = idx * LINE_FLOATS;
      const isDimmed = hasDim && highlightState.dimmedLinkIndices.has(idx);
      const isHighlighted = highlightState && highlightState.highlightedLinkIndices && highlightState.highlightedLinkIndices.has(idx);

      const color = isHighlighted ? COLORS.edgeHighlight : COLORS.edge;
      const alpha = isDimmed ? 0.08 : (isHighlighted ? 0.9 : 0.4);
      const width = isHighlighted ? 2 : 1;

      this.lineData[i + 0] = l.source.x;
      this.lineData[i + 1] = l.source.y;
      this.lineData[i + 2] = l.target.x;
      this.lineData[i + 3] = l.target.y;
      this.lineData[i + 4] = color[0];
      this.lineData[i + 5] = color[1];
      this.lineData[i + 6] = color[2];
      this.lineData[i + 7] = alpha;
      this.lineData[i + 8] = width;
    }

    this.lineCount = links.length;

    const byteLength = links.length * LINE_BYTES;
    if (!this.lineBuffer || this.lineBuffer.size < byteLength) {
      if (this.lineBuffer) this.lineBuffer.destroy();
      this.lineBuffer = this.device.createBuffer({
        size: Math.max(byteLength, 64),
        usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST,
      });
    }
    if (links.length > 0) {
      this.device.queue.writeBuffer(this.lineBuffer, 0, this.lineData, 0, links.length * LINE_FLOATS);
    }
    this.dirty = true;
  }

  /**
   * Update axis gridlines as line instances.
   * @param {Array} gridlines - Array of { y, width } in world coords, spanning the viewport
   */
  updateGridlines(gridlines, worldWidth) {
    if (!gridlines || gridlines.length === 0) {
      this.gridlineCount = 0;
      return;
    }

    if (!this.gridlineData || this.gridlineData.length < gridlines.length * LINE_FLOATS) {
      this.gridlineData = new Float32Array(gridlines.length * LINE_FLOATS);
    }

    for (let idx = 0; idx < gridlines.length; idx++) {
      const g = gridlines[idx];
      const i = idx * LINE_FLOATS;
      this.gridlineData[i + 0] = 0;            // posA.x
      this.gridlineData[i + 1] = g.y;          // posA.y
      this.gridlineData[i + 2] = worldWidth;    // posB.x
      this.gridlineData[i + 3] = g.y;          // posB.y
      this.gridlineData[i + 4] = 0.42;         // color R (--text-muted)
      this.gridlineData[i + 5] = 0.42;         // color G
      this.gridlineData[i + 6] = 0.42;         // color B
      this.gridlineData[i + 7] = 0.07;         // alpha
      this.gridlineData[i + 8] = 0.5;          // width
    }

    this.gridlineCount = gridlines.length;

    const byteLength = gridlines.length * LINE_BYTES;
    if (!this.gridlineBuffer || this.gridlineBuffer.size < byteLength) {
      if (this.gridlineBuffer) this.gridlineBuffer.destroy();
      this.gridlineBuffer = this.device.createBuffer({
        size: Math.max(byteLength, 64),
        usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST,
      });
    }
    this.device.queue.writeBuffer(this.gridlineBuffer, 0, this.gridlineData, 0, gridlines.length * LINE_FLOATS);
    this.dirty = true;
  }

  render() {
    if (!this.device || !this.context) return;

    const textureView = this.context.getCurrentTexture().createView();
    const encoder = this.device.createCommandEncoder();

    const pass = encoder.beginRenderPass({
      colorAttachments: [{
        view: textureView,
        clearValue: { r: COLORS.bg[0], g: COLORS.bg[1], b: COLORS.bg[2], a: 1 },
        loadOp: 'clear',
        storeOp: 'store',
      }],
    });

    // Draw gridlines first (behind everything)
    if (this.gridlineCount > 0 && this.gridlineBuffer) {
      pass.setPipeline(this.linePipeline);
      pass.setBindGroup(0, this.lineBindGroup);
      pass.setVertexBuffer(0, this.gridlineBuffer);
      pass.draw(6, this.gridlineCount);
    }

    // Draw lines (edges)
    if (this.lineCount > 0 && this.lineBuffer) {
      pass.setPipeline(this.linePipeline);
      pass.setBindGroup(0, this.lineBindGroup);
      pass.setVertexBuffer(0, this.lineBuffer);
      pass.draw(6, this.lineCount);
    }

    // Draw circles (nodes)
    if (this.circleCount > 0 && this.circleBuffer) {
      pass.setPipeline(this.circlePipeline);
      pass.setBindGroup(0, this.circleBindGroup);
      pass.setVertexBuffer(0, this.circleBuffer);
      pass.draw(6, this.circleCount);
    }

    pass.end();
    this.device.queue.submit([encoder.finish()]);
    this.dirty = false;
  }

  destroy() {
    if (this.circleBuffer) this.circleBuffer.destroy();
    if (this.lineBuffer) this.lineBuffer.destroy();
    if (this.gridlineBuffer) this.gridlineBuffer.destroy();
    if (this.viewUniformBuffer) this.viewUniformBuffer.destroy();
    if (this.device) this.device.destroy();
  }
}

export { COLORS };

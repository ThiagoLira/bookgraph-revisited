/**
 * fallback.js — WebGL2 fallback renderer.
 * Same interface as GraphRenderer but uses WebGL2 instead of WebGPU.
 */

const CIRCLE_VS = `#version 300 es
precision highp float;

// Per-instance attributes
layout(location = 0) in vec2 a_center;
layout(location = 1) in float a_radius;
layout(location = 2) in vec3 a_fillColor;
layout(location = 3) in float a_fillAlpha;
layout(location = 4) in vec3 a_strokeColor;
layout(location = 5) in float a_strokeAlpha;
layout(location = 6) in float a_strokeWidth;

uniform mat3 u_transform;
uniform vec2 u_resolution;

out vec2 v_localPos;
out vec3 v_fillColor;
out float v_fillAlpha;
out vec3 v_strokeColor;
out float v_strokeAlpha;
out float v_radiusPx;
out float v_strokeWidthPx;

const vec2 QUAD[6] = vec2[6](
  vec2(-1.0, -1.0),
  vec2( 1.0, -1.0),
  vec2(-1.0,  1.0),
  vec2(-1.0,  1.0),
  vec2( 1.0, -1.0),
  vec2( 1.0,  1.0)
);

void main() {
  vec2 local = QUAD[gl_VertexID];
  vec3 screenPos = u_transform * vec3(a_center, 1.0);
  float k = u_transform[0][0];
  float radiusPx = a_radius * k;
  float expand = radiusPx + a_strokeWidth * k + 1.5;
  vec2 posPx = screenPos.xy + local * expand;
  vec2 ndc = (posPx / u_resolution) * 2.0 - 1.0;

  gl_Position = vec4(ndc.x, -ndc.y, 0.0, 1.0);
  v_localPos = local * expand;
  v_fillColor = a_fillColor;
  v_fillAlpha = a_fillAlpha;
  v_strokeColor = a_strokeColor;
  v_strokeAlpha = a_strokeAlpha;
  v_radiusPx = radiusPx;
  v_strokeWidthPx = a_strokeWidth * k;
}
`;

const CIRCLE_FS = `#version 300 es
precision highp float;

in vec2 v_localPos;
in vec3 v_fillColor;
in float v_fillAlpha;
in vec3 v_strokeColor;
in float v_strokeAlpha;
in float v_radiusPx;
in float v_strokeWidthPx;

out vec4 fragColor;

void main() {
  float dist = length(v_localPos);
  float aa = 1.0;
  float fillEdge = smoothstep(v_radiusPx + aa, v_radiusPx - aa, dist);
  float innerEdge = v_radiusPx - v_strokeWidthPx;
  float strokeMask = smoothstep(innerEdge - aa, innerEdge + aa, dist)
                   * smoothstep(v_radiusPx + aa, v_radiusPx - aa, dist);

  vec4 fill = vec4(v_fillColor, v_fillAlpha * fillEdge);
  vec4 stroke = vec4(v_strokeColor, v_strokeAlpha * strokeMask);

  float outAlpha = stroke.a + fill.a * (1.0 - stroke.a);
  if (outAlpha < 0.001) discard;
  vec3 outRgb = (stroke.rgb * stroke.a + fill.rgb * fill.a * (1.0 - stroke.a)) / outAlpha;
  fragColor = vec4(outRgb, outAlpha);
}
`;

const LINE_VS = `#version 300 es
precision highp float;

layout(location = 0) in vec2 a_posA;
layout(location = 1) in vec2 a_posB;
layout(location = 2) in vec3 a_color;
layout(location = 3) in float a_alpha;
layout(location = 4) in float a_width;

uniform mat3 u_transform;
uniform vec2 u_resolution;

out float v_edgeDist;
out vec3 v_color;
out float v_alpha;
out float v_halfWidthPx;

const vec2 QUAD[6] = vec2[6](
  vec2(0.0, -1.0),
  vec2(1.0, -1.0),
  vec2(0.0,  1.0),
  vec2(0.0,  1.0),
  vec2(1.0, -1.0),
  vec2(1.0,  1.0)
);

void main() {
  vec2 vert = QUAD[gl_VertexID];
  vec2 aScreen = (u_transform * vec3(a_posA, 1.0)).xy;
  vec2 bScreen = (u_transform * vec3(a_posB, 1.0)).xy;

  vec2 dir = bScreen - aScreen;
  float len = length(dir);
  vec2 normal;
  if (len < 0.001) {
    normal = vec2(0.0, 1.0);
  } else {
    vec2 d = dir / len;
    normal = vec2(-d.y, d.x);
  }

  float k = u_transform[0][0];
  float halfWidth = max(a_width * k * 0.5, 0.5);
  float expand = halfWidth + 1.0;
  vec2 posOnLine = mix(aScreen, bScreen, vert.x);
  vec2 posPx = posOnLine + normal * vert.y * expand;
  vec2 ndc = (posPx / u_resolution) * 2.0 - 1.0;

  gl_Position = vec4(ndc.x, -ndc.y, 0.0, 1.0);
  v_edgeDist = vert.y * expand;
  v_color = a_color;
  v_alpha = a_alpha;
  v_halfWidthPx = halfWidth;
}
`;

const LINE_FS = `#version 300 es
precision highp float;

in float v_edgeDist;
in vec3 v_color;
in float v_alpha;
in float v_halfWidthPx;

out vec4 fragColor;

void main() {
  float dist = abs(v_edgeDist);
  float aa = smoothstep(v_halfWidthPx + 1.0, v_halfWidthPx - 0.5, dist);
  float a = v_alpha * aa;
  if (a < 0.001) discard;
  fragColor = vec4(v_color, a);
}
`;

// Same constants as renderer.js
const CIRCLE_FLOATS = 12;
const CIRCLE_BYTES = CIRCLE_FLOATS * 4;
const LINE_FLOATS = 9;
const LINE_BYTES = LINE_FLOATS * 4;

const COLORS = {
  bookSource: [0.769, 0.361, 0.290],
  bookCited: [0.290, 0.435, 0.647],
  authorFill: [0.831, 0.647, 0.455],
  authorStroke: [0.831, 0.647, 0.455],
  edge: [0.165, 0.165, 0.184],
  edgeHighlight: [0.831, 0.647, 0.455],
  bg: [0.039, 0.039, 0.047],
};

function compileShader(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    console.error('Shader compile error:', gl.getShaderInfoLog(shader));
    gl.deleteShader(shader);
    return null;
  }
  return shader;
}

function createProgram(gl, vsSource, fsSource) {
  const vs = compileShader(gl, gl.VERTEX_SHADER, vsSource);
  const fs = compileShader(gl, gl.FRAGMENT_SHADER, fsSource);
  const program = gl.createProgram();
  gl.attachShader(program, vs);
  gl.attachShader(program, fs);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    console.error('Program link error:', gl.getProgramInfoLog(program));
    return null;
  }
  return program;
}

export class FallbackRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.gl = null;
    this.circleProgram = null;
    this.lineProgram = null;
    this.circleCount = 0;
    this.lineCount = 0;
    this.gridlineCount = 0;
    this.transform = { x: 0, y: 0, k: 1 };
    this.dirty = true;
    this.circleData = null;
    this.lineData = null;
    this.gridlineData = null;
  }

  async init() {
    this.gl = this.canvas.getContext('webgl2', { alpha: false, antialias: false });
    if (!this.gl) {
      throw new Error('WebGL2 not supported');
    }

    const gl = this.gl;
    this._resize();

    gl.enable(gl.BLEND);
    gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);

    // Create programs
    this.circleProgram = createProgram(gl, CIRCLE_VS, CIRCLE_FS);
    this.lineProgram = createProgram(gl, LINE_VS, LINE_FS);

    // Get uniform locations
    this.circleUniforms = {
      transform: gl.getUniformLocation(this.circleProgram, 'u_transform'),
      resolution: gl.getUniformLocation(this.circleProgram, 'u_resolution'),
    };
    this.lineUniforms = {
      transform: gl.getUniformLocation(this.lineProgram, 'u_transform'),
      resolution: gl.getUniformLocation(this.lineProgram, 'u_resolution'),
    };

    // Create VAOs and buffers
    this.circleVAO = gl.createVertexArray();
    this.circleBuffer = gl.createBuffer();
    this._setupCircleVAO();

    this.lineVAO = gl.createVertexArray();
    this.lineBuffer = gl.createBuffer();
    this._setupLineVAO();

    this.gridlineVAO = gl.createVertexArray();
    this.gridlineBuffer = gl.createBuffer();
    this._setupGridlineVAO();
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
    this.gl.viewport(0, 0, this.width, this.height);
  }

  _setupCircleVAO() {
    const gl = this.gl;
    gl.bindVertexArray(this.circleVAO);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.circleBuffer);

    const stride = CIRCLE_BYTES;
    // center (vec2)
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, stride, 0);
    gl.vertexAttribDivisor(0, 1);
    // radius (float)
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 1, gl.FLOAT, false, stride, 8);
    gl.vertexAttribDivisor(1, 1);
    // fillColor (vec3)
    gl.enableVertexAttribArray(2);
    gl.vertexAttribPointer(2, 3, gl.FLOAT, false, stride, 12);
    gl.vertexAttribDivisor(2, 1);
    // fillAlpha (float)
    gl.enableVertexAttribArray(3);
    gl.vertexAttribPointer(3, 1, gl.FLOAT, false, stride, 24);
    gl.vertexAttribDivisor(3, 1);
    // strokeColor (vec3)
    gl.enableVertexAttribArray(4);
    gl.vertexAttribPointer(4, 3, gl.FLOAT, false, stride, 28);
    gl.vertexAttribDivisor(4, 1);
    // strokeAlpha (float)
    gl.enableVertexAttribArray(5);
    gl.vertexAttribPointer(5, 1, gl.FLOAT, false, stride, 40);
    gl.vertexAttribDivisor(5, 1);
    // strokeWidth (float)
    gl.enableVertexAttribArray(6);
    gl.vertexAttribPointer(6, 1, gl.FLOAT, false, stride, 44);
    gl.vertexAttribDivisor(6, 1);

    gl.bindVertexArray(null);
  }

  _setupLineVAO() {
    const gl = this.gl;
    gl.bindVertexArray(this.lineVAO);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.lineBuffer);

    const stride = LINE_BYTES;
    // posA (vec2)
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, stride, 0);
    gl.vertexAttribDivisor(0, 1);
    // posB (vec2)
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 2, gl.FLOAT, false, stride, 8);
    gl.vertexAttribDivisor(1, 1);
    // color (vec3)
    gl.enableVertexAttribArray(2);
    gl.vertexAttribPointer(2, 3, gl.FLOAT, false, stride, 16);
    gl.vertexAttribDivisor(2, 1);
    // alpha (float)
    gl.enableVertexAttribArray(3);
    gl.vertexAttribPointer(3, 1, gl.FLOAT, false, stride, 28);
    gl.vertexAttribDivisor(3, 1);
    // width (float)
    gl.enableVertexAttribArray(4);
    gl.vertexAttribPointer(4, 1, gl.FLOAT, false, stride, 32);
    gl.vertexAttribDivisor(4, 1);

    gl.bindVertexArray(null);
  }

  _setupGridlineVAO() {
    const gl = this.gl;
    gl.bindVertexArray(this.gridlineVAO);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.gridlineBuffer);

    const stride = LINE_BYTES;
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, stride, 0);
    gl.vertexAttribDivisor(0, 1);
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 2, gl.FLOAT, false, stride, 8);
    gl.vertexAttribDivisor(1, 1);
    gl.enableVertexAttribArray(2);
    gl.vertexAttribPointer(2, 3, gl.FLOAT, false, stride, 16);
    gl.vertexAttribDivisor(2, 1);
    gl.enableVertexAttribArray(3);
    gl.vertexAttribPointer(3, 1, gl.FLOAT, false, stride, 28);
    gl.vertexAttribDivisor(3, 1);
    gl.enableVertexAttribArray(4);
    gl.vertexAttribPointer(4, 1, gl.FLOAT, false, stride, 32);
    gl.vertexAttribDivisor(4, 1);

    gl.bindVertexArray(null);
  }

  setTransform(transform) {
    this.transform = transform;
    this.dirty = true;
  }

  _setUniforms(program, uniforms) {
    const gl = this.gl;
    const { x, y, k } = this.transform;
    gl.useProgram(program);

    // mat3 column-major: [[k,0,0], [0,k,0], [tx,ty,1]]
    // Scale and translate must both be in device pixels for consistency with u_resolution
    const kd = k * this.dpr;
    const mat = new Float32Array([
      kd, 0, 0,
      0, kd, 0,
      x * this.dpr, y * this.dpr, 1,
    ]);
    gl.uniformMatrix3fv(uniforms.transform, false, mat);
    gl.uniform2f(uniforms.resolution, this.width, this.height);
  }

  updateCircles(authors, highlightState = null) {
    const hasDim = highlightState && highlightState.dimmedIds && highlightState.dimmedIds.size > 0;

    let totalCircles = 0;
    for (const a of authors) {
      totalCircles++;
      totalCircles += a.books ? a.books.length : 0;
    }

    if (!this.circleData || this.circleData.length < totalCircles * CIRCLE_FLOATS) {
      this.circleData = new Float32Array(totalCircles * CIRCLE_FLOATS);
    }

    let offset = 0;
    for (const a of authors) {
      const isDimmed = hasDim && highlightState.dimmedIds.has(a.id);
      const isHighlighted = highlightState && highlightState.highlightedIds && highlightState.highlightedIds.has(a.id);
      const alphaMultiplier = isDimmed ? 0.15 : 1.0;

      const i = offset * CIRCLE_FLOATS;
      this.circleData[i + 0] = a.x;
      this.circleData[i + 1] = a.y;
      this.circleData[i + 2] = a.r;
      this.circleData[i + 3] = COLORS.authorFill[0];
      this.circleData[i + 4] = COLORS.authorFill[1];
      this.circleData[i + 5] = COLORS.authorFill[2];
      this.circleData[i + 6] = 0.03 * alphaMultiplier;
      this.circleData[i + 7] = COLORS.authorStroke[0];
      this.circleData[i + 8] = COLORS.authorStroke[1];
      this.circleData[i + 9] = COLORS.authorStroke[2];
      this.circleData[i + 10] = (isHighlighted ? 1.0 : 0.15) * alphaMultiplier;
      this.circleData[i + 11] = isHighlighted ? 2 : 1;
      offset++;

      if (a.books) {
        for (const b of a.books) {
          const j = offset * CIRCLE_FLOATS;
          const color = b.data.isSource ? COLORS.bookSource : COLORS.bookCited;
          this.circleData[j + 0] = a.x + b.x;
          this.circleData[j + 1] = a.y + b.y;
          this.circleData[j + 2] = b.r;
          this.circleData[j + 3] = color[0];
          this.circleData[j + 4] = color[1];
          this.circleData[j + 5] = color[2];
          this.circleData[j + 6] = 1.0 * alphaMultiplier;
          this.circleData[j + 7] = 0;
          this.circleData[j + 8] = 0;
          this.circleData[j + 9] = 0;
          this.circleData[j + 10] = 0;
          this.circleData[j + 11] = 0;
          offset++;
        }
      }
    }

    this.circleCount = offset;

    const gl = this.gl;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.circleBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, this.circleData.subarray(0, offset * CIRCLE_FLOATS), gl.DYNAMIC_DRAW);
    this.dirty = true;
  }

  updateLines(links, highlightState = null) {
    const hasDim = highlightState && highlightState.dimmedLinkIndices && highlightState.dimmedLinkIndices.size > 0;

    if (!this.lineData || this.lineData.length < links.length * LINE_FLOATS) {
      this.lineData = new Float32Array(links.length * LINE_FLOATS);
    }

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

    const gl = this.gl;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.lineBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, this.lineData.subarray(0, links.length * LINE_FLOATS), gl.DYNAMIC_DRAW);
    this.dirty = true;
  }

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
      this.gridlineData[i + 0] = 0;
      this.gridlineData[i + 1] = g.y;
      this.gridlineData[i + 2] = worldWidth;
      this.gridlineData[i + 3] = g.y;
      this.gridlineData[i + 4] = 0.42;
      this.gridlineData[i + 5] = 0.42;
      this.gridlineData[i + 6] = 0.42;
      this.gridlineData[i + 7] = 0.07;
      this.gridlineData[i + 8] = 0.5;
    }

    this.gridlineCount = gridlines.length;

    const gl = this.gl;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.gridlineBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, this.gridlineData.subarray(0, gridlines.length * LINE_FLOATS), gl.DYNAMIC_DRAW);
    this.dirty = true;
  }

  render() {
    const gl = this.gl;
    if (!gl) return;

    gl.viewport(0, 0, this.width, this.height);
    gl.clearColor(COLORS.bg[0], COLORS.bg[1], COLORS.bg[2], 1.0);
    gl.clear(gl.COLOR_BUFFER_BIT);

    // Draw gridlines
    if (this.gridlineCount > 0) {
      this._setUniforms(this.lineProgram, this.lineUniforms);
      gl.bindVertexArray(this.gridlineVAO);
      gl.drawArraysInstanced(gl.TRIANGLES, 0, 6, this.gridlineCount);
    }

    // Draw lines
    if (this.lineCount > 0) {
      this._setUniforms(this.lineProgram, this.lineUniforms);
      gl.bindVertexArray(this.lineVAO);
      gl.drawArraysInstanced(gl.TRIANGLES, 0, 6, this.lineCount);
    }

    // Draw circles
    if (this.circleCount > 0) {
      this._setUniforms(this.circleProgram, this.circleUniforms);
      gl.bindVertexArray(this.circleVAO);
      gl.drawArraysInstanced(gl.TRIANGLES, 0, 6, this.circleCount);
    }

    gl.bindVertexArray(null);
    this.dirty = false;
  }

  destroy() {
    // Cleanup GL resources
    const gl = this.gl;
    if (gl) {
      gl.deleteProgram(this.circleProgram);
      gl.deleteProgram(this.lineProgram);
      gl.deleteBuffer(this.circleBuffer);
      gl.deleteBuffer(this.lineBuffer);
      gl.deleteBuffer(this.gridlineBuffer);
      gl.deleteVertexArray(this.circleVAO);
      gl.deleteVertexArray(this.lineVAO);
      gl.deleteVertexArray(this.gridlineVAO);
    }
  }
}

export { COLORS };

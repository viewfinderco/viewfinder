// Copyright 2012 ViewFinder. All rights reserved.
// Author: Peter Mattis.

precision mediump float;

uniform sampler2D u_texture;

varying vec2 v_tex_coord;
varying float v_alpha;

void main() {
  // Multiplying the texture color by v_alpha is equivalent to alpha blending
  // the texture color with (0, 0, 0, 0).
  gl_FragColor = texture2D(u_texture, v_tex_coord) * v_alpha;
}

// local variables:
// mode: c++
// end:

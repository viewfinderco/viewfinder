// Copyright 2012 ViewFinder. All rights reserved.
// Author: Peter Mattis.

precision mediump float;

attribute highp vec4 a_position;
attribute vec2 a_tex_coord;

uniform highp mat4 u_MVP;

#ifdef EDGE_DETECT
uniform vec2 u_edge_step;
varying vec2 v_edge_coord[9];
#elif defined(GAUSSIAN_BLUR)
uniform vec2 u_blur_step;
varying vec2 v_blur_coord[9];
#else  // !GAUSSIAN_BLUR
varying vec2 v_tex_coord;
#endif // !GAUSSIAN_BLUR

#ifdef VIGNETTE
varying vec2 v_vignette_coord;
#endif // VIGNETTE

void main() {
  gl_Position = u_MVP * a_position;

#ifdef EDGE_DETECT
  v_edge_coord[0] = a_tex_coord + u_edge_step * vec2(-1.0, -1.0);
  v_edge_coord[1] = a_tex_coord + u_edge_step * vec2( 0.0, -1.0);
  v_edge_coord[2] = a_tex_coord + u_edge_step * vec2( 1.0, -1.0);
  v_edge_coord[3] = a_tex_coord + u_edge_step * vec2(-1.0,  0.0);
  v_edge_coord[4] = a_tex_coord + u_edge_step * vec2( 0.0,  0.0);
  v_edge_coord[5] = a_tex_coord + u_edge_step * vec2( 1.0,  0.0);
  v_edge_coord[6] = a_tex_coord + u_edge_step * vec2(-1.0,  1.0);
  v_edge_coord[7] = a_tex_coord + u_edge_step * vec2( 0.0,  1.0);
  v_edge_coord[8] = a_tex_coord + u_edge_step * vec2( 1.0,  1.0);
#elif defined(GAUSSIAN_BLUR)
  v_blur_coord[0] = a_tex_coord;
  v_blur_coord[1] = a_tex_coord - 1.0 * u_blur_step;
  v_blur_coord[2] = a_tex_coord + 1.0 * u_blur_step;
  v_blur_coord[3] = a_tex_coord - 2.0 * u_blur_step;
  v_blur_coord[4] = a_tex_coord + 2.0 * u_blur_step;
  v_blur_coord[5] = a_tex_coord - 3.0 * u_blur_step;
  v_blur_coord[6] = a_tex_coord + 3.0 * u_blur_step;
  v_blur_coord[7] = a_tex_coord - 4.0 * u_blur_step;
  v_blur_coord[8] = a_tex_coord + 4.0 * u_blur_step;
#else  // !GAUSSIAN_BLUR
  v_tex_coord = a_tex_coord;
#endif // !GAUSSIAN_BLUR

#ifdef VIGNETTE
  // TODO(pmattis): Adjust to handle filtering an image in parts.
  v_vignette_coord = a_tex_coord;
#endif // VIGNETTE
}

// local variables:
// mode: c++
// end:

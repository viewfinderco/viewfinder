// Copyright 2012 ViewFinder. All rights reserved.
// Author: Peter Mattis.

precision mediump float;

attribute highp vec4 a_position;
attribute vec2 a_tex_coord;
attribute float a_alpha;

// Model-view-projection matrix.
uniform highp mat4 u_MVP;

varying vec2 v_tex_coord;
varying float v_alpha;

void main() {
  gl_Position = u_MVP * a_position;
  v_tex_coord = a_tex_coord;
  v_alpha = a_alpha;
}

// local variables:
// mode: c++
// end:

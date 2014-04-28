// Copyright 2012 ViewFinder. All rights reserved.
// Author: Peter Mattis.

precision mediump float;

attribute highp vec4 a_position;
attribute highp vec2 a_tex_coord;

// Model-view-projection matrix.
uniform highp mat4 u_MVP;

varying highp vec2 v_tex_coord;

void main() {
  gl_Position = u_MVP * a_position;
  v_tex_coord = a_tex_coord;
}

// local variables:
// mode: c++
// end:

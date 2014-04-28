// Copyright 2012 ViewFinder. All rights reserved.
// Author: Peter Mattis.

precision mediump float;

attribute highp vec4 a_position;
attribute lowp vec4 a_color;

// Model-view-projection matrix.
uniform highp mat4 u_MVP;

varying lowp vec4 v_color;

void main() {
  gl_Position = u_MVP * a_position;
  v_color = a_color;
}

// local variables:
// mode: c++
// end:

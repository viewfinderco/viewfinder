// Copyright 2012 ViewFinder. All rights reserved.
// Author: Peter Mattis.
//
// TODO(pmattis): Explore whether performing lookup into a 1xN texture would be
// faster and more flexible.
//
// TODO(pmattis): We could also build the radial gradient out of lots of
// triangles. Each gradient step (blend between 2 gradient colors) is an arc
// segment. If the arc is drawn using triangles oriented towards the center of
// the arc, then we can use a varying to interpolate the color between the
// outer and inner edges of the arc. Simple fragment shader (no sqrt), but more
// work in the vertex shader.

precision mediump float;

varying highp vec2 v_tex_coord;

uniform highp vec4 u_radius1[2];
uniform highp vec4 u_radius2[2];
uniform lowp vec4 u_color[9];

void main() {
  // A simple gradient with start and end colors can be computed using:
  //
  //   mix(start_color, end_color, smoothstep(start_dist, end_dist, dist))
  //
  // In order to have multiple steps to the gradient, we could just cascade a
  // series of these mix(..., smoothstep(...)) operations, using the output
  // from the previous step as the input to the next. But we get better
  // parallelism (instruction-level) if we mix and smoothstep using vec4's and
  // vec3's.
  highp vec4 dist = vec4(length(v_tex_coord));
  // Compute the smoothsteps between r0-r1, r2-r3, r4-r5 and r6-r7.
  vec4 s_01_23_45_67 = smoothstep(u_radius1[0], u_radius1[1], dist);
  // Compute the smoothsteps between r1-r2, r3-r4, r5-r6 and r7-r8
  vec4 s_12_34_56_78 = smoothstep(u_radius2[0], u_radius2[1], dist);
  // Compute the mixed colors for r0-r1, r2-r3, r4-r5 and r6-r7.
  vec4 c_01 = mix(u_color[0], u_color[1], s_01_23_45_67.x);
  vec4 c_23 = mix(u_color[2], u_color[3], s_01_23_45_67.y);
  vec4 c_45 = mix(u_color[4], u_color[5], s_01_23_45_67.z);
  vec4 c_67 = mix(u_color[6], u_color[7], s_01_23_45_67.w);
  // Compute the mixed colors for r0-r3 and r4-r7.
  vec4 c_0123 = mix(c_01, c_23, s_12_34_56_78.x);
  vec4 c_4567 = mix(c_45, c_67, s_12_34_56_78.z);
  // Compute the final mixed color.
  gl_FragColor = mix(mix(c_0123, c_4567, s_12_34_56_78.y),
                     u_color[8], s_12_34_56_78.w);
}

// local variables:
// mode: c++
// end:

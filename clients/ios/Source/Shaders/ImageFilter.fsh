// Copyright 2012 ViewFinder. All rights reserved.
// Author: Peter Mattis.

#ifdef YUV_INPUT
#define COLOR_MATRIX
#endif // YUV_INPUT

#if defined(LINEAR_TILT_SHIFT) || defined(RADIAL_TILT_SHIFT)
#define GAUSSIAN_BLUR
#endif // defined(LINEAR_TILT_SHIFT) || defined(RADIAL_TILT_SHIFT)

precision mediump float;
precision mediump sampler2D;

#ifdef EDGE_DETECT
varying vec2 v_edge_coord[9];
#elif defined(GAUSSIAN_BLUR)
varying vec2 v_blur_coord[9];
uniform float u_blur_weights[5];
#else // !GAUSSIAN_BLUR
varying vec2 v_tex_coord;
#endif // !GAUSSIAN_BLUR

#ifdef YUV_INPUT
uniform sampler2D u_y_texture;
uniform sampler2D u_uv_texture;
uniform vec3 u_yuv_offset;
#elif defined(RGB_INPUT)
uniform sampler2D u_rgb_texture;
#endif // RGB_INPUT

#if defined(LINEAR_TILT_SHIFT) || defined(RADIAL_TILT_SHIFT)
uniform sampler2D u_tilt_shift_texture;
uniform vec2 u_tilt_shift_origin;
#ifdef LINEAR_TILT_SHIFT
uniform vec2 u_tilt_shift_normal;
#endif // LINEAR_TILT_SHIFT
uniform float u_tilt_shift_near;
uniform float u_tilt_shift_far;
uniform float u_tilt_shift_whiteness;
#endif // defined(LINEAR_TILT_SHIFT) || defined(RADIAL_TILT_SHIFT)

#ifdef COLOR_MATRIX
uniform mat3 u_color_matrix;
#endif // COLOR_MATRIX

#ifdef CURVES
uniform sampler2D u_curves_texture;
#endif // CURVES

#ifdef VIGNETTE
varying vec2 v_vignette_coord;
uniform float u_vignette_inner_distance;
uniform float u_vignette_outer_distance;
#endif // VIGNETTE

mediump vec3 sample(mediump vec2 tex_coord) {
#ifdef YUV_INPUT
  return vec3(texture2D(u_y_texture, tex_coord).r,
              texture2D(u_uv_texture, tex_coord).rg) - u_yuv_offset;
#elif defined(RGB_INPUT)
  return texture2D(u_rgb_texture, tex_coord).rgb;
#endif // RGB_INPUT
}

void main() {
#ifdef EDGE_DETECT
  vec3 samples[9];
  samples[0] = sample(v_edge_coord[0]);
  samples[1] = sample(v_edge_coord[1]);
  samples[2] = sample(v_edge_coord[2]);
  samples[3] = sample(v_edge_coord[3]);
  samples[5] = sample(v_edge_coord[5]);
  samples[6] = sample(v_edge_coord[6]);
  samples[7] = sample(v_edge_coord[7]);
  samples[8] = sample(v_edge_coord[8]);
  vec3 gx = samples[2] + samples[8] - (samples[0] + samples[6]) +
      2.0 * (samples[5] - samples[3]);
  vec3 gy = samples[6] + samples[8] - (samples[0] + samples[2]) +
      2.0 * (samples[7] - samples[1]);
  vec3 color = sqrt(gx * gx + gy * gy);
#elif defined(GAUSSIAN_BLUR)
  vec3 color =
      u_blur_weights[0] *  sample(v_blur_coord[0]) +
      u_blur_weights[1] * (sample(v_blur_coord[1]) + sample(v_blur_coord[2])) +
      u_blur_weights[2] * (sample(v_blur_coord[3]) + sample(v_blur_coord[4])) +
      u_blur_weights[3] * (sample(v_blur_coord[5]) + sample(v_blur_coord[6])) +
      u_blur_weights[4] * (sample(v_blur_coord[7]) + sample(v_blur_coord[8]));
#else  // !GAUSSIAN_BLUR
  vec3 color = sample(v_tex_coord);
#endif // !GAUSSIAN_BLUR

#if defined(LINEAR_TILT_SHIFT) || defined(RADIAL_TILT_SHIFT)
#ifdef LINEAR_TILT_SHIFT
  float dist = abs(dot(v_blur_coord[0] - u_tilt_shift_origin,
                       u_tilt_shift_normal));
#elif defined(RADIAL_TILT_SHIFT)
  float dist = distance(v_blur_coord[0], u_tilt_shift_origin);
#endif // RADIAL_TILT_SHIFT
  vec3 orig_color = texture2D(u_tilt_shift_texture, v_blur_coord[0]).rgb;
  color = mix(orig_color,
              mix(color, vec3(1.0), u_tilt_shift_whiteness),
              smoothstep(u_tilt_shift_near, u_tilt_shift_far, dist));
#endif // defined(LINEAR_TILT_SHIFT) || defined(RADIAL_TILT_SHIFT)

#ifdef COLOR_MATRIX
  color = u_color_matrix * color;
#endif // COLOR_MATRIX

#ifdef CURVES
  color = vec3(texture2D(u_curves_texture, vec2(color.r, 0.0)).r,
               texture2D(u_curves_texture, vec2(color.g, 0.0)).g,
               texture2D(u_curves_texture, vec2(color.b, 0.0)).b);
#endif // CURVES

#ifdef VIGNETTE
  color *= smoothstep(u_vignette_outer_distance,
                      u_vignette_inner_distance,
                      distance(v_vignette_coord, vec2(0.5, 0.5)));
#endif // VIGNETTE

  gl_FragColor = vec4(color, 1.0);
}

// local variables:
// mode: c++
// end:

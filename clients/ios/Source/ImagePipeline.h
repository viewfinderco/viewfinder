// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_IMAGE_PIPELINE_H
#define VIEWFINDER_IMAGE_PIPELINE_H

#include <unordered_map>
#include "GL.h"
#include "ScopedPtr.h"
#include "Utils.h"
#include "Vector.h"

class ImageFilter {
  enum {
    A_POSITION,
    A_TEX_COORD,
  };

 public:
  enum {
    YUV_INPUT = 1 << 0,
    RGB_INPUT = 1 << 1,
    COLOR_MATRIX = 1 << 2,
    EDGE_DETECT = 1 << 3,
    GAUSSIAN_BLUR = 1 << 4,
    LINEAR_TILT_SHIFT = 1 << 5,
    RADIAL_TILT_SHIFT = 1 << 6,
    CURVES = 1 << 7,
    VIGNETTE = 1 << 8,

    INPUT_MASK = YUV_INPUT | RGB_INPUT,
    TILT_SHIFT_MASK = LINEAR_TILT_SHIFT | RADIAL_TILT_SHIFT,
  };

  struct Vignette {
    Vignette()
        : inner_distance(0.3),
          outer_distance(0.7) {
    }
    float inner_distance;
    float outer_distance;
  };

  struct Args {
    Args(float width, float height)
        : output_width(width),
          output_height(height),
          y_texture(NULL),
          uv_texture(NULL),
          rgb_texture(NULL),
          blur_weights(NULL),
          blur_direction(1),
          tilt_shift_texture(NULL),
          tilt_shift_near(0),
          tilt_shift_far(0),
          tilt_shift_whiteness(0),
          curves_texture(NULL),
          vignette(NULL) {
    }
    float output_width;
    float output_height;
    Matrix4f mvp;
    const GLTexture2D* y_texture;
    const GLTexture2D* uv_texture;
    const GLTexture2D* rgb_texture;
    Vector3f yuv_offset;
    Matrix3f yuv_matrix;
    Matrix3f color_matrix;
    vector<float>* blur_weights;
    int blur_direction;
    const GLTexture2D* tilt_shift_texture;
    Vector2f tilt_shift_origin;
    Vector2f tilt_shift_normal;
    float tilt_shift_near;
    float tilt_shift_far;
    float tilt_shift_whiteness;
    const GLTexture2D* curves_texture;
    const Vignette* vignette;
  };

 public:
  ImageFilter(int flags);

  bool Init();
  void Run(const Args& args) const;

  const string& id() const { return program_.id(); }

 private:
  static string FlagsToId(int flags);

 private:
  const int flags_;
  GLProgram program_;
  GLint u_mvp_;
  GLint u_y_texture_;
  GLint u_uv_texture_;
  GLint u_yuv_offset_;
  GLint u_rgb_texture_;
  GLint u_color_matrix_;
  GLint u_edge_step_;
  GLint u_blur_step_;
  GLint u_blur_weights_;
  GLint u_tilt_shift_texture_;
  GLint u_tilt_shift_origin_;
  GLint u_tilt_shift_normal_;
  GLint u_tilt_shift_near_;
  GLint u_tilt_shift_far_;
  GLint u_tilt_shift_whiteness_;
  GLint u_curves_texture_;
  GLint u_vignette_inner_distance_;
  GLint u_vignette_outer_distance_;
};

class ImagePipeline {
  typedef std::unordered_map<int, ImageFilter*> FilterMap;

 public:
  ImagePipeline();
  ~ImagePipeline();

  void Run(GLFrameBuffer* frame_buffer,
           const GLTexture2D& y_texture,
           const GLTexture2D& uv_texture,
           bool video_range, float zoom);
  void Run(GLFrameBuffer* frame_buffer,
           const GLTexture2D& rgb_texture,
           float zoom);

  void SetFlags(int flags);
  Matrix4f InitMVP(const Matrix4f& model, int width, int height, float zoom) const;

  int flags() const { return flags_; }
  Matrix3f* color_matrix() { return &color_matrix_; }
  vector<float>* blur_weights() { return &blur_weights_; }
  Vector2f* tilt_shift_origin() { return &tilt_shift_origin_; }
  Vector2f* tilt_shift_normal() { return &tilt_shift_normal_; }
  float* tilt_shift_near() { return &tilt_shift_near_; }
  float* tilt_shift_far() { return &tilt_shift_far_; }
  float* tilt_shift_whiteness() { return &tilt_shift_whiteness_; }
  ImageFilter::Vignette* vignette() { return &vignette_; }
  GLTexture2D** curves() { return &curves_; }

 private:
  void RunWithInput(GLFrameBuffer* frame_buffer,
                    ImageFilter::Args* args, int input_flags, float zoom);
  void RunWithArgs(const ImageFilter::Args& args, int combined_flags);
  void InitRenderBuffer(int i, int width, int height);
  Vector3f InitYUVOffset(bool video_range) const;
  Matrix3f InitYUVMatrix(bool video_range) const;

 private:
  int flags_;
  FilterMap filters_;
  Matrix3f color_matrix_;
  vector<float> blur_weights_;
  Vector2f tilt_shift_origin_;
  Vector2f tilt_shift_normal_;
  float tilt_shift_near_;
  float tilt_shift_far_;
  float tilt_shift_whiteness_;
  GLTexture2D* curves_;
  ImageFilter::Vignette vignette_;
  vector<GLMutableTexture2D*> render_textures_;
  vector<GLTexture2DFrameBuffer*> render_buffers_;
};

class FilterManager {
  struct Filter {
    Filter(const string& n, int f)
        : name(n),
          flags(f) {
    }
    const string name;
    int flags;
    Matrix3f color_matrix;
    ScopedPtr<GLTexture2D> curves;
    ImageFilter::Vignette vignette;
  };

 public:
  FilterManager(ImagePipeline* image_pipeline);
  ~FilterManager();

  const string& NextFilter();
  const string& SetFilter(int i);

 private:
  static Filter* NewNormalFilter();
  static Filter* NewGaussianBlurFilter();
  static Filter* NewEdgeDetectFilter();
  static Filter* NewRadialTiltShiftFilter();
  static Filter* NewLinearTiltShiftFilter();
  static Filter* NewVignetteFilter();
  static Filter* NewLomoEarlGreyFilter();
  static Filter* NewSunMakerFilter();
  static Filter* NewVelviaRVP100IIFilter();
  static void LoadGradient(const string& filename,
                           ScopedPtr<GLTexture2D>* curves);

 private:
  vector<Filter*> filters_;
  int index_;
  ImagePipeline* const image_pipeline_;
};

#endif // VIEWFINDER_IMAGE_PIPELINE_H

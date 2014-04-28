// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#include "ImagePipeline.h"
#include "Logging.h"
#include "MathUtils.h"
#include "STLUtils.h"
#include "Timer.h"

namespace {

void GaussianBlurWeights(vector<float>* v, double stddev) {
  const float stddev_sqr = stddev * stddev;
  float sum = 0;
  for (int i = 0; i < v->size(); ++i) {
    (*v)[i] = (1.0 / (sqrt(2 * kPi) * stddev)) *
        exp((-i * i) / (2 * stddev_sqr));
    // The total sum of weights is 2 times the individual weights, but we only
    // count the first weight once.
    sum += (*v)[i] * (1 + (i > 0));
  }
  for (int i = 0; i < v->size(); ++i) {
    (*v)[i] /= sum;
  }
}

}  // namespace

ImageFilter::ImageFilter(int flags)
    : flags_(flags),
      program_(FlagsToId(flags)),
      u_mvp_(-1),
      u_y_texture_(-1),
      u_uv_texture_(-1),
      u_yuv_offset_(-1),
      u_rgb_texture_(-1),
      u_color_matrix_(-1),
      u_edge_step_(-1),
      u_blur_step_(-1),
      u_blur_weights_(-1),
      u_tilt_shift_texture_(-1),
      u_tilt_shift_origin_(-1),
      u_tilt_shift_normal_(-1),
      u_tilt_shift_near_(-1),
      u_tilt_shift_far_(-1),
      u_tilt_shift_whiteness_(-1),
      u_curves_texture_(-1),
      u_vignette_inner_distance_(-1),
      u_vignette_outer_distance_(-1) {
}

bool ImageFilter::Init() {
  string defines;
  if (flags_ & YUV_INPUT) {
    defines += "#define YUV_INPUT\n";
  } else if (flags_ & RGB_INPUT) {
    defines += "#define RGB_INPUT\n";
  }
  if (flags_ & (YUV_INPUT | COLOR_MATRIX)) {
    defines += "#define COLOR_MATRIX\n";
  }
  if (flags_ & EDGE_DETECT) {
    defines += "#define EDGE_DETECT\n";
  } else if (flags_ & (TILT_SHIFT_MASK | GAUSSIAN_BLUR)) {
    defines += "#define GAUSSIAN_BLUR\n";
  }
  if (flags_ & LINEAR_TILT_SHIFT) {
    defines += "#define LINEAR_TILT_SHIFT\n";
  } else if (flags_ & RADIAL_TILT_SHIFT) {
    defines += "#define RADIAL_TILT_SHIFT\n";
  }
  if (flags_ & CURVES) {
    defines += "#define CURVES\n";
  }
  if (flags_ & VIGNETTE) {
    defines += "#define VIGNETTE\n";
  }
  if (!program_.Compile("ImageFilter", defines)) {
    LOG("unable to compile: %s", program_.id());
    return false;
  }

  program_.BindAttribute("a_position", A_POSITION);
  program_.BindAttribute("a_tex_coord", A_TEX_COORD);

  if (!program_.Link()) {
    LOG("unable to link: %s", program_.id());
    return false;
  }

  u_mvp_ = program_.GetUniform("u_MVP");
  if (flags_ & YUV_INPUT) {
    u_y_texture_ = program_.GetUniform("u_y_texture");
    u_uv_texture_ = program_.GetUniform("u_uv_texture");
    u_yuv_offset_ = program_.GetUniform("u_yuv_offset");
  } else if (flags_ & RGB_INPUT) {
    u_rgb_texture_ = program_.GetUniform("u_rgb_texture");
  }
  if (flags_ & (YUV_INPUT | COLOR_MATRIX)) {
    u_color_matrix_ = program_.GetUniform("u_color_matrix");
  }
  if (flags_ & EDGE_DETECT) {
    u_edge_step_ = program_.GetUniform("u_edge_step");
  } else if (flags_ & (TILT_SHIFT_MASK | GAUSSIAN_BLUR)) {
    u_blur_step_ = program_.GetUniform("u_blur_step");
    u_blur_weights_ = program_.GetUniform("u_blur_weights");
  }
  if (flags_ & TILT_SHIFT_MASK) {
    u_tilt_shift_texture_ = program_.GetUniform("u_tilt_shift_texture");
    u_tilt_shift_origin_ = program_.GetUniform("u_tilt_shift_origin");
    u_tilt_shift_near_ = program_.GetUniform("u_tilt_shift_near");
    u_tilt_shift_far_ = program_.GetUniform("u_tilt_shift_far");
    u_tilt_shift_whiteness_ = program_.GetUniform("u_tilt_shift_whiteness");
    if (flags_ & LINEAR_TILT_SHIFT) {
      u_tilt_shift_normal_ = program_.GetUniform("u_tilt_shift_normal");
    }
  }
  if (flags_ & CURVES) {
    u_curves_texture_ = program_.GetUniform("u_curves_texture");
  }
  if (flags_ & VIGNETTE) {
    u_vignette_inner_distance_ =
        program_.GetUniform("u_vignette_inner_distance");
    u_vignette_outer_distance_ =
        program_.GetUniform("u_vignette_outer_distance");
  }
  return true;
}

void ImageFilter::Run(const Args& a) const {
  // Bind the texture units.
  if (u_y_texture_ != -1) {
    glActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, a.y_texture->name());
    GL_CHECK_ERRORS();
    glActiveTexture(GL_TEXTURE1);
    glBindTexture(GL_TEXTURE_2D, a.uv_texture->name());
    GL_CHECK_ERRORS();
  } else if (u_rgb_texture_ != -1) {
    glActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, a.rgb_texture->name());
    GL_CHECK_ERRORS();
  }
  if (u_tilt_shift_texture_ != -1) {
    glActiveTexture(GL_TEXTURE2);
    glBindTexture(GL_TEXTURE_2D, a.tilt_shift_texture->name());
    GL_CHECK_ERRORS();
  }
  if (u_curves_texture_ != -1) {
    glActiveTexture(GL_TEXTURE3);
    glBindTexture(GL_TEXTURE_2D, a.curves_texture->name());
    GL_CHECK_ERRORS();
  }

  // Set up the uniform variables for our shader program.
  glUseProgram(program_.name());
  GL_CHECK_ERRORS();
  glUniformMatrix4fv(u_mvp_, 1, false, a.mvp.data());
  if (u_yuv_offset_ != -1) {
    glUniform3fv(u_yuv_offset_, 1, a.yuv_offset.data());
  }
  if (u_color_matrix_ != -1) {
    const Matrix3f m = a.yuv_matrix * a.color_matrix;
    glUniformMatrix3fv(u_color_matrix_, 1, false, m.data());
  }
  if (u_edge_step_ != -1) {
    glUniform2f(u_edge_step_,
                1.0 / a.output_width,
                1.0 / a.output_height);
  }
  if (u_blur_step_ != -1) {
    glUniform2f(u_blur_step_,
                a.blur_direction / a.output_width,
                !a.blur_direction / a.output_height);
    glUniform1fv(u_blur_weights_, 5, a.blur_weights->data());
  }
  if (u_y_texture_ != -1) {
    glUniform1i(u_y_texture_, 0);
    glUniform1i(u_uv_texture_, 1);
  } else if (u_rgb_texture_ != -1) {
    glUniform1i(u_rgb_texture_, 0);
  }
  if (u_vignette_inner_distance_ != -1) {
    glUniform1f(u_vignette_inner_distance_, a.vignette->inner_distance);
    glUniform1f(u_vignette_outer_distance_, a.vignette->outer_distance);
  }
  if (u_tilt_shift_texture_ != -1) {
    glUniform1i(u_tilt_shift_texture_, 2);
    glUniform2fv(u_tilt_shift_origin_, 1, a.tilt_shift_origin.data());
    glUniform1f(u_tilt_shift_near_, a.tilt_shift_near);
    glUniform1f(u_tilt_shift_far_, a.tilt_shift_far);
    glUniform1f(u_tilt_shift_whiteness_, a.tilt_shift_whiteness);
    if (u_tilt_shift_normal_ != -1) {
      Vector2f v = a.tilt_shift_normal;
      v.normalize();
      glUniform2fv(u_tilt_shift_normal_, 1, v.data());
    }
  }
  if (u_curves_texture_ != -1) {
    glUniform1i(u_curves_texture_, 3);
  }
  GL_CHECK_ERRORS();

  // Draw our full screen rect.
  const struct {
    Vector4f position;
    Vector2f tex_coord;
  } kVertices[4] = {
    { Vector4f(-1, -1, 0, 1), Vector2f(0, 0) },
    { Vector4f( 1, -1, 0, 1), Vector2f(1, 0) },
    { Vector4f(-1,  1, 0, 1), Vector2f(0, 1) },
    { Vector4f( 1,  1, 0, 1), Vector2f(1, 1) },
  };

  // Set up the attributes for our shader program.
  glVertexAttribPointer(A_POSITION, 4, GL_FLOAT, GL_FALSE,
                        sizeof(kVertices[0]), &kVertices[0].position);
  glVertexAttribPointer(A_TEX_COORD, 2, GL_FLOAT, GL_FALSE,
                        sizeof(kVertices[0]), &kVertices[0].tex_coord);
  glEnableVertexAttribArray(A_POSITION);
  glEnableVertexAttribArray(A_TEX_COORD);
  GL_CHECK_ERRORS();

  // Validate the program and draw our triangles.
  CHECK(program_.Validate());
  glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);

  // Disable the attributes we set up.
  glDisableVertexAttribArray(A_POSITION);
  glDisableVertexAttribArray(A_TEX_COORD);
  GL_CHECK_ERRORS();
}

string ImageFilter::FlagsToId(int flags) {
  string id;
  if (flags & YUV_INPUT) {
    id += "yuv";
  } else if (flags & RGB_INPUT) {
    id += "rgb";
  }
  if (flags & COLOR_MATRIX) {
    id += "+color_matrix";
  }
  if (flags & EDGE_DETECT) {
    id += "+edge_detect";
  } else if (flags & GAUSSIAN_BLUR) {
    id += "+gaussian_blur";
  }
  if (flags & LINEAR_TILT_SHIFT) {
    id += "+linear_tilt_shift";
  } else if (flags & RADIAL_TILT_SHIFT) {
    id += "+radial_tilt_shift";
  }
  if (flags & CURVES) {
    id += "+curves";
  }
  if (flags & VIGNETTE) {
    id += "+vignette";
  }
  return id;
}

ImagePipeline::ImagePipeline()
    : flags_(0),
      blur_weights_(5, 0),
      tilt_shift_origin_(0.5, 0.5),
      tilt_shift_normal_(0, 1),
      tilt_shift_near_(0.1),
      tilt_shift_far_(0.2),
      tilt_shift_whiteness_(0.5),
      curves_(NULL) {
  GaussianBlurWeights(&blur_weights_, 3);
}

ImagePipeline::~ImagePipeline() {
  Clear(&filters_);
  Clear(&render_textures_);
  Clear(&render_buffers_);
}

void ImagePipeline::Run(
    GLFrameBuffer* frame_buffer,
    const GLTexture2D& y_texture,
    const GLTexture2D& uv_texture,
    bool video_range, float zoom) {
  ImageFilter::Args args(frame_buffer->width(), frame_buffer->height());
  args.y_texture = &y_texture;
  args.uv_texture = &uv_texture;
  args.mvp = InitMVP(
      y_texture.transform(), args.output_width, args.output_height, zoom);
  args.yuv_offset = InitYUVOffset(video_range);
  args.yuv_matrix = InitYUVMatrix(video_range);
  RunWithInput(frame_buffer, &args, ImageFilter::YUV_INPUT, zoom);
}

void ImagePipeline::Run(
    GLFrameBuffer* frame_buffer,
    const GLTexture2D& rgb_texture,
    float zoom) {
  ImageFilter::Args args(frame_buffer->width(), frame_buffer->height());
  args.rgb_texture = &rgb_texture;
  args.mvp = InitMVP(
      rgb_texture.transform(), args.output_width, args.output_height, zoom);
  RunWithInput(frame_buffer, &args, ImageFilter::RGB_INPUT, zoom);
}

void ImagePipeline::SetFlags(int flags) {
  CHECK_EQ(flags & ImageFilter::INPUT_MASK, 0);
  flags_ = flags;
}

void ImagePipeline::RunWithInput(
    GLFrameBuffer* frame_buffer,
    ImageFilter::Args* args, int input_flags, float zoom) {
  if (flags_ & ImageFilter::EDGE_DETECT) {
    // Pass 1: convert YUV to RGB data if necessary.
    if (1 || input_flags & ImageFilter::YUV_INPUT) {
      InitRenderBuffer(0, args->output_width, args->output_height);
      render_buffers_[0]->Activate();
      RunWithArgs(*args, input_flags);
      args->rgb_texture = render_textures_[0];
      Matrix4f m;
      m.scale(args->rgb_texture->width(), args->rgb_texture->height(), 1);
      args->mvp = InitMVP(m, args->output_width, args->output_height, zoom);
      args->yuv_matrix.identity();
      input_flags = ImageFilter::RGB_INPUT;
    }

    // Pass 2: edge detect.
  } else if (flags_ &
             (ImageFilter::TILT_SHIFT_MASK | ImageFilter::GAUSSIAN_BLUR)) {
    InitRenderBuffer(0, args->output_width, args->output_height);
    InitRenderBuffer(1, args->output_width, args->output_height);
    int i = 0;

    // Pass 1: convert YUV to RGB data if necessary.

    // TODO(pmattis): Handle the difference between the tilt_shift_texture
    // transform and the blur texture transform if the original input is
    // RGB. The "if (1 || ...)" is a hack!
    if (1 || input_flags & ImageFilter::YUV_INPUT) {
      render_buffers_[i]->Activate();
      RunWithArgs(*args, input_flags);
      args->rgb_texture = render_textures_[i];
      Matrix4f m;
      m.scale(args->rgb_texture->width(), args->rgb_texture->height(), 1);
      args->mvp = InitMVP(m, args->output_width, args->output_height, zoom);
      args->yuv_matrix.identity();
      input_flags = ImageFilter::RGB_INPUT;
      i = !i;
    }

    // Save away the original input texture (now definitely RGB) in case we're
    // performing a tilt-shift.
    args->tilt_shift_texture = args->rgb_texture;

    // Pass 2: horizontal gaussian blur.
    render_buffers_[i]->Activate();
    args->blur_weights = &blur_weights_;
    args->blur_direction = 0;
    RunWithArgs(*args, input_flags | ImageFilter::GAUSSIAN_BLUR);
    args->rgb_texture = render_textures_[i];
    Matrix4f m;
    m.scale(args->rgb_texture->width(), args->rgb_texture->height(), 1);
    args->mvp = InitMVP(m, args->output_width, args->output_height, zoom);

    // Pass 3: vertical gaussian blur.
    args->blur_direction = !args->blur_direction;
  }

  args->color_matrix = color_matrix_;
  args->tilt_shift_origin = tilt_shift_origin_;
  args->tilt_shift_normal = tilt_shift_normal_;
  args->tilt_shift_near = tilt_shift_near_;
  args->tilt_shift_far = tilt_shift_far_;
  args->tilt_shift_whiteness = tilt_shift_whiteness_;
  args->curves_texture = curves_;
  args->vignette = &vignette_;

  frame_buffer->Activate();
  RunWithArgs(*args, flags_ | input_flags);
}

void ImagePipeline::RunWithArgs(
    const ImageFilter::Args& args, int combined_flags) {
  ImageFilter*& f = filters_[combined_flags];
  if (!f) {
    f = new ImageFilter(combined_flags);
    if (!f->Init()) {
      DIE("unable to initialize image filter: %s", f->id());
    }
    LOG("initialized filter: %s", f->id());
  }
  f->Run(args);
}

void ImagePipeline::InitRenderBuffer(int i, int width, int height) {
  if (render_textures_.size() <= i) {
    render_textures_.resize(i + 1, NULL);
  }
  if (render_buffers_.size() <= i) {
    render_buffers_.resize(i + 1, NULL);
  }
  if (!render_textures_[i]) {
    render_textures_[i] = new GLMutableTexture2D;
    render_textures_[i]->SetFormat(GL_RGBA);
  }
  if (render_textures_[i]->width() != width ||
      render_textures_[i]->height() != height) {
    render_textures_[i]->SetPixels(width, height, NULL);
  }
  if (!render_buffers_[i]) {
    render_buffers_[i] = new GLTexture2DFrameBuffer(render_textures_[i]);
  }
}

Matrix4f ImagePipeline::InitMVP(
    const Matrix4f& model, int width, int height, float zoom) const {
  // Set up our model-view-projection matrix.
  Matrix4f mvp(model);
  mvp.scale(zoom, zoom, 1);
  mvp.ortho(-width, width, -height, height, -1, 1);
  return mvp;
}

Vector3f ImagePipeline::InitYUVOffset(bool video_range) const {
  Vector3f v(0, 0.5, 0.5);
  if (video_range) {
    // Video-range data has luma=[16,235] and chroma=[16,240]. Offset the data
    // to the full range.
    v.x() += 16 / 255.0;
  }
  return v;
}

Matrix3f ImagePipeline::InitYUVMatrix(bool video_range) const {
  // Full-range data color offset and matrix for yuv to rgb conversion.
  Matrix3f m(     1,        1,     1,
                  0, -0.34414, 1.772,
              1.402, -0.71414,     0);
  if (video_range) {
    // Video-range data has luma=[16,235] and chroma=[16,240]. Scale the data
    // to the full range.
    m.scale(255.0 / (235 - 16),
            255.0 / (240 - 16),
            255.0 / (240 - 16));
  }
  return m;
}

FilterManager::FilterManager(ImagePipeline* image_pipeline)
    : index_(0),
      image_pipeline_(image_pipeline) {
  filters_.push_back(NewNormalFilter());
  filters_.push_back(NewGaussianBlurFilter());
  filters_.push_back(NewEdgeDetectFilter());
  filters_.push_back(NewRadialTiltShiftFilter());
  filters_.push_back(NewLinearTiltShiftFilter());
  filters_.push_back(NewVignetteFilter());
  filters_.push_back(NewLomoEarlGreyFilter());
  filters_.push_back(NewSunMakerFilter());
  filters_.push_back(NewVelviaRVP100IIFilter());
  SetFilter(index_);
}

FilterManager::~FilterManager() {
  for (int i = 0; i < filters_.size(); ++i) {
    delete filters_[i];
  }
}

const string& FilterManager::NextFilter() {
  return SetFilter((index_ + 1) % filters_.size());
}

const string& FilterManager::SetFilter(int i) {
  Filter* f = filters_[i];
  index_ = i;
  image_pipeline_->SetFlags(f->flags);
  *image_pipeline_->color_matrix() = f->color_matrix;
  *image_pipeline_->curves() = f->curves.get();
  *image_pipeline_->vignette() = f->vignette;
  return f->name;
}

FilterManager::Filter* FilterManager::NewNormalFilter() {
  return new Filter("normal", 0);
}

FilterManager::Filter* FilterManager::NewGaussianBlurFilter() {
  return new Filter("gaussian blur", ImageFilter::GAUSSIAN_BLUR);
}

FilterManager::Filter* FilterManager::NewEdgeDetectFilter() {
  return new Filter("edge detect", ImageFilter::EDGE_DETECT);
}

FilterManager::Filter* FilterManager::NewRadialTiltShiftFilter() {
  return new Filter("radial tilt shift", ImageFilter::RADIAL_TILT_SHIFT);
}

FilterManager::Filter* FilterManager::NewLinearTiltShiftFilter() {
  return new Filter("linear tilt shift", ImageFilter::LINEAR_TILT_SHIFT);
}

FilterManager::Filter* FilterManager::NewVignetteFilter() {
  return new Filter("vignette", ImageFilter::VIGNETTE);
}

FilterManager::Filter* FilterManager::NewLomoEarlGreyFilter() {
  Filter* f = new Filter("lomo earl grey", ImageFilter::CURVES);
  LoadGradient("gradient-lomo-earl-grey.png", &f->curves);
  return f;
}

FilterManager::Filter* FilterManager::NewSunMakerFilter() {
  Filter* f = new Filter("sun maker", ImageFilter::CURVES);
  LoadGradient("gradient-sun-maker.png", &f->curves);
  return f;
}

FilterManager::Filter* FilterManager::NewVelviaRVP100IIFilter() {
  Filter* f = new Filter("velvia rvp 100 II", ImageFilter::CURVES);
  LoadGradient("gradient-velvia-rvp-100-II.png", &f->curves);
  return f;
}

void FilterManager::LoadGradient(
    const string& filename, ScopedPtr<GLTexture2D>* curves) {
  curves->reset(GLTextureLoader::LoadFromFile(filename));
  if (!curves->get()) {
    DIE("unable to load: %s", filename);
  }
  glBindTexture(GL_TEXTURE_2D, (*curves)->name());
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
}

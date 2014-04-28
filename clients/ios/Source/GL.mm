// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <CoreVideo/CVOpenGLESTexture.h>
#import <CoreVideo/CVOpenGLESTextureCache.h>
#import <GLKit/GLKit.h>
#import <ImageIO/CGImageSource.h>
#import "FileUtils.h"
#import "GL.h"
#import "Logging.h"
#import "PathUtils.h"
#import "ScopedRef.h"

void GLCheckErrors(const char *file, int line) {
  GLuint errnum;
  int num_errors = 0;
  while ((errnum = glGetError()) != GL_NO_ERROR) {
    const char *errstr = "unknown";
    switch (errnum) {
      case GL_INVALID_ENUM:
        errstr = "invalid enum";
        break;
      case GL_INVALID_VALUE:
        errstr = "invalid value";
        break;
      case GL_INVALID_OPERATION:
        errstr = "invalid operation";
        break;
      case GL_INVALID_FRAMEBUFFER_OPERATION:
        errstr = "invalid framebuffer operation";
        break;
      case GL_OUT_OF_MEMORY:
        errstr = "out of memory";
        break;
      default:
        errstr = "unknown";
        break;
    }
    LOG("%s:%d: error %d: %s", file, line, errnum, errstr);
    ++num_errors;
  }
  assert(num_errors == 0);
}


GLTexture2D::GLTexture2D(GLuint name, GLint width, GLint height)
    : name_(name),
      width_(width),
      height_(height) {
  glBindTexture(GL_TEXTURE_2D, name_);
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
  glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
  glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
  GL_CHECK_ERRORS();
}

GLTexture2D::~GLTexture2D() {
}


GLMutableTexture2D::GLMutableTexture2D()
    : GLTexture2D(GenTexture(), -1, -1),
      format_(GL_RGBA),
      type_(GL_UNSIGNED_BYTE) {
}

GLMutableTexture2D::~GLMutableTexture2D() {
  if (name() != 0) {
    GLuint tmp = name();
    glDeleteTextures(1, &tmp);
    GL_CHECK_ERRORS();
  }
}

void GLMutableTexture2D::SetPixels(int width, int height, const void* pixels) {
  glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
  glBindTexture(GL_TEXTURE_2D, name());
  GL_CHECK_ERRORS();

  if (width_ != width || height_ != height) {
    width_ = width;
    height_ = height;
    glTexImage2D(GL_TEXTURE_2D, 0, internal_format(),
                 width_, height_, 0, format_, type_, pixels);
    GL_CHECK_ERRORS();
  } else {
    glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0,
                    width_, height_, format_, type_, pixels);
    GL_CHECK_ERRORS();
  }
}

void GLMutableTexture2D::SetFormat(GLenum format) {
  format_ = format;
  width_ = -1;
  height_ = -1;
}

void GLMutableTexture2D::SetType(GLenum type) {
  type_ = type;
}

GLuint GLMutableTexture2D::GenTexture() {
  GLuint name;
  glGenTextures(1, &name);
  return name;
}

GLint GLMutableTexture2D::internal_format() const {
  switch (format_) {
    case GL_BGRA_EXT:
      return GL_RGBA;
  }
  return format_;
}


class GLTextureLoader::Texture2D : public GLTexture2D {
 public:
  Texture2D(GLKTextureInfo* info)
      : GLTexture2D([info name], [info width], [info height]) {
  }
};

GLTexture2D* GLTextureLoader::LoadFromFile(const string& filename) {
  const string path = MainBundlePath(filename);
  NSError* error = NULL;
  GLKTextureInfo* texture_info =
      [GLKTextureLoader textureWithContentsOfFile:
                   [NSString stringWithUTF8String:path.c_str()]
                                          options:NULL
                                            error:&error];
  if (!texture_info) {
    LOG("%s: unable to load texture: %@", path, error);
    return NULL;
  }
  return new Texture2D(texture_info);
}


class GLTextureCache::Impl {
  class VideoTexture2D : public GLTexture2D {
   public:
    VideoTexture2D(CVOpenGLESTextureRef texture_ref, int width, int height)
        : GLTexture2D(CVOpenGLESTextureGetName(texture_ref), width, height),
          texture_(texture_ref) {
    }
    ~VideoTexture2D() {
    }

   private:
    ScopedRef<CVOpenGLESTextureRef> texture_;
  };

 public:
  Impl() {
    CVOpenGLESTextureCacheRef texture_cache_ref;
    CVReturn err = CVOpenGLESTextureCacheCreate(
        kCFAllocatorDefault, NULL,
        [EAGLContext currentContext],
        NULL, &texture_cache_ref);
    if (err) {
      LOG("CVOpenGLESTextureCacheCreate() failed: %d", err);
      return;
    }
    texture_cache_.reset(texture_cache_ref);
  }
  ~Impl() {
  }

  void Flush() {
    CVOpenGLESTextureCacheFlush(texture_cache_, 0);
  }

  GLTexture2D* CreateTextureFromImage(
      CVImageBufferRef buffer, GLenum target,
      GLint internal_format, GLsizei width, GLsizei height,
      GLenum format, GLenum type, size_t plane) {
    CVOpenGLESTextureRef texture_ref;
    CVReturn err = CVOpenGLESTextureCacheCreateTextureFromImage(
        kCFAllocatorDefault, texture_cache_, buffer,
        NULL, target, internal_format, width, height,
        format, type, plane, &texture_ref);
    if (err) {
      LOG("CVOpenGLESTextureCacheCreateTextureFromImage() failed: %d", err);
      return NULL;
    }
    return new VideoTexture2D(texture_ref, width, height);
  }

 private:
  ScopedRef<CVOpenGLESTextureCacheRef> texture_cache_;
};

GLTextureCache::GLTextureCache()
    : impl_(new Impl){
}

GLTextureCache::~GLTextureCache() {
}

void GLTextureCache::Flush() {
  impl_->Flush();
}

GLTexture2D* GLTextureCache::CreateTextureFromImage(
    CVImageBufferRef buffer, GLenum target,
    GLint internal_format, GLsizei width, GLsizei height,
    GLenum format, GLenum type, size_t plane) {
  return impl_->CreateTextureFromImage(
      buffer, target, internal_format,
      width, height, format, type, plane);
}


GLTexture2DFrameBuffer::GLTexture2DFrameBuffer(GLTexture2D* texture)
    : name_(0),
      texture_(texture) {
  glGenFramebuffers(1, &name_);
  glBindFramebuffer(GL_FRAMEBUFFER, name_);
  GL_CHECK_ERRORS();
  glFramebufferTexture2D(
      GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, texture_->name(), 0);
  GL_CHECK_ERRORS();
  CheckStatus();
}

GLTexture2DFrameBuffer::~GLTexture2DFrameBuffer() {
  if (name_) {
    glDeleteFramebuffers(1, &name_);
    GL_CHECK_ERRORS();
    name_ = 0;
  }
}

void GLTexture2DFrameBuffer::CheckStatus() {
  if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
    DIE("Failed to make complete framebuffer object: %x",
        glCheckFramebufferStatus(GL_FRAMEBUFFER));
  }
}

void GLTexture2DFrameBuffer::Activate() {
  glBindFramebuffer(GL_FRAMEBUFFER, name_);
  GL_CHECK_ERRORS();
  glViewport(0, 0, width(), height());
  GL_CHECK_ERRORS();
}


GLProgram::GLProgram(const string& id)
    : id_(id),
      name_(glCreateProgram()) {
}

GLProgram::~GLProgram() {
  glDeleteProgram(name_);
}

bool GLProgram::Compile(const string& file, const string& defines) {
  struct {
    GLenum shader_type;
    string extension;
  } shaders[] = {
    { GL_VERTEX_SHADER, ".vsh" },
    { GL_FRAGMENT_SHADER, ".fsh" },
  };

  for (int i = 0; i < 2; i++) {
    const string path = MainBundlePath(file + shaders[i].extension);
    if (!FileExists(path)) {
      LOG("%s: unable to find: %s", id_, path);
      return false;
    }
    const string source = defines + ReadFileToString(path);

    // Create the shader objects.
    const GLuint shader = glCreateShader(shaders[i].shader_type);
    if (shader == 0) {
      LOG("%s: failed to create shader:\n%s", id_, path);
      return false;
    }
    GL_CHECK_ERRORS();

    // Load the shader source
    const char *shader_src = source.c_str();
    glShaderSource(shader, 1, &shader_src, NULL);
    GL_CHECK_ERRORS();

    // Compile the shader
    glCompileShader(shader);
    GL_CHECK_ERRORS();

    // Check the compile status
    GLint compiled;
    glGetShaderiv(shader, GL_COMPILE_STATUS, &compiled);
    if (!compiled) {
      GLint info_len = 0;
      glGetShaderiv(shader, GL_INFO_LOG_LENGTH, &info_len);

      if (info_len > 1) {
        char* info_log = (char*) malloc(sizeof(char) * info_len);
        glGetShaderInfoLog(shader, info_len, NULL, info_log);
        LOG("%s: error compiling shader:\n%s\n%s",
            id_, path, info_log);
        free(info_log);
      }

      glDeleteShader(shader);
      GL_CHECK_ERRORS();
      return false;
    }

    glAttachShader(name_, shader);
    GL_CHECK_ERRORS();
  }
  return true;
}

bool GLProgram::Link() {
  glLinkProgram(name_);
  GL_CHECK_ERRORS();

#if defined(DEBUG)
  GLint log_length;
  glGetProgramiv(name_, GL_INFO_LOG_LENGTH, &log_length);
  if (log_length > 0) {
    GLchar *log = (GLchar*) malloc(log_length);
    glGetProgramInfoLog(name_, log_length, &log_length, log);
    LOG("%s: program link log:\n%s", id_, log);
    free(log);
  }
#endif

  GLint status;
  glGetProgramiv(name_, GL_LINK_STATUS, &status);
  if (status == GL_FALSE) {
    LOG("%s: failed to link program: %d", id_, name_);
    return false;
  }

  return true;
}

bool GLProgram::Validate() const {
  glValidateProgram(name_);

  GLint log_length;
  glGetProgramiv(name_, GL_INFO_LOG_LENGTH, &log_length);
  if (log_length > 0) {
    GLchar *log = (GLchar*) malloc(log_length);
    glGetProgramInfoLog(name_, log_length, &log_length, log);
    LOG("%s: program validate log:\n%s", id_, log);
    free(log);
  }

  GLint status;
  glGetProgramiv(name_, GL_VALIDATE_STATUS, &status);
  if (status == GL_FALSE) {
    LOG("%s: failed to validate program: %d", id_, name_);
    return false;
  }

  GL_CHECK_ERRORS();
  return true;
}

void GLProgram::BindAttribute(const string& name, GLint location) {
  glBindAttribLocation(name_, location, name.c_str());
  GL_CHECK_ERRORS();
}

GLint GLProgram::GetUniform(const string& name) {
  return glGetUniformLocation(name_, name.c_str());
}

// local variables:
// mode: c++
// end:

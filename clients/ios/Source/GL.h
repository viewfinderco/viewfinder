// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_GL_H
#define VIEWFINDER_GL_H

#include <CoreVideo/CVImageBuffer.h>
#include <CoreVideo/CVOpenGLESTexture.h>
#include <OpenGLES/ES2/gl.h>
#include <OpenGLES/ES2/glext.h>
#include "Matrix.h"
#include "ScopedPtr.h"
#include "Utils.h"

void GLCheckErrors(const char *file, int line);
#define GL_CHECK_ERRORS()  GLCheckErrors(__FILE__, __LINE__)

class GLTexture2D {
 public:
  GLTexture2D(GLuint name, GLint width, GLint height);
  virtual ~GLTexture2D();

  GLuint name() const { return name_; }
  GLint width() const { return width_; }
  GLint height() const { return height_; }

  const Matrix4f& transform() const { return transform_; }
  Matrix4f* mutable_transform() { return &transform_; }

 protected:
  GLuint name_;
  GLint width_;
  GLint height_;
  Matrix4f transform_;
};

class GLMutableTexture2D : public GLTexture2D {
 public:
  GLMutableTexture2D();
  ~GLMutableTexture2D();

  void SetPixels(int width, int height, const void* pixels);
  void SetFormat(GLenum format);
  void SetType(GLenum type);

  GLenum format() const { return format_; }
  GLenum type() const { return type_; }

 private:
  static GLuint GenTexture();

  GLint internal_format() const;

 private:
  GLenum format_;
  GLenum type_;
};

class GLTextureLoader {
  class Texture2D;

 public:
  static GLTexture2D* LoadFromFile(const string& filename);
};

class GLTextureCache {
  class Impl;

 public:
  GLTextureCache();
  ~GLTextureCache();

  void Flush();

  GLTexture2D* CreateTextureFromImage(
      CVImageBufferRef buffer, GLenum target,
      GLint internal_format, GLsizei width, GLsizei height,
      GLenum format, GLenum type, size_t plane);

 private:
  ScopedPtr<Impl> impl_;
};

class GLFrameBuffer {
 public:
  virtual ~GLFrameBuffer() {
  }

  virtual void Activate() = 0;
  virtual GLint width() const = 0;
  virtual GLint height() const = 0;
};

class GLTexture2DFrameBuffer : public GLFrameBuffer{
 public:
  GLTexture2DFrameBuffer(GLTexture2D* texture);
  ~GLTexture2DFrameBuffer();

  void CheckStatus();
  void Activate();

  GLuint name() const { return name_; }
  GLint width() const { return texture_->width(); }
  GLint height() const { return texture_->height(); }

 private:
  GLuint name_;
  GLTexture2D *texture_;
};

class GLProgram {
 public:
  GLProgram(const string& id);
  ~GLProgram();

  bool Compile(const string& file, const string& defines);
  bool Link();
  bool Validate() const;
  void BindAttribute(const string& name, GLint location);
  GLint GetUniform(const string& name);

  const string& id() const { return id_; }
  GLint name() const { return name_; }

 private:
  const string id_;
  GLint name_;
};

#endif // VIEWFINDER_GL_H

// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.
// Author: Spencer Kimball.

#import <map>
#import <OpenGLES/EAGL.h>
#import <OpenGLES/EAGLDrawable.h>
#import <UIKit/UIKit.h>
#import "GL.h"
#import "ScopedPtr.h"

class GLMutableTexture2D;
class GLProgram;
class GLTexture2D;

// OpenGL shader attribute index values.
enum GLAttribute {
  A_POSITION,
  A_TEX_COORD,
  A_COLOR,
  A_ALPHA,
};

@interface GLLayer : CAEAGLLayer {
 @private
  EAGLContext* context_;
  GLuint framebuffer_;
  GLuint renderbuffer_;
  bool create_framebuffer_;
  void (^draw_)();
}

- (bool)setDraw:(void (^)())draw;

@end  // GLLayer


class GLState {
 public:
  GLState();
  ~GLState();

  bool Lock(void (^draw_callback)());
  void Release();

  GLLayer* layer() const { return layer_; }
  GLProgram* solid_shader() const { return solid_shader_.get(); }
  GLint u_solid_mvp() const { return u_solid_mvp_; }
  GLProgram* texture_shader() const { return texture_shader_.get(); }
  GLint u_texture_mvp() const { return u_texture_mvp_; }
  GLint u_texture_texture() const { return u_texture_texture_; }
  GLTexture2D* arc_texture() const { return  arc_texture_.get(); }

  void AccumulateGlyphs(Slice s, UIFont* font);
  void CommitGlyphTexture();

  struct GlyphInfo {
    NSString* str;
    CGSize size;
    CGSize scaled_size;
    float tx_start;
    float tx_end;
    float ty_start;
    float ty_end;
  };
  typedef std::pair<UIFont*, int> GlyphKey;
  const GlyphInfo* GetGlyphInfo(const GlyphKey& key) const;

 private:
  void Init();

 private:
  GLLayer* layer_;
  ScopedPtr<GLProgram> solid_shader_;
  GLint u_solid_mvp_;
  ScopedPtr<GLProgram> texture_shader_;
  GLint u_texture_mvp_;
  GLint u_texture_texture_;
  ScopedPtr<GLTexture2D> arc_texture_;
  bool rebuild_glyph_texture_;

  // A map from glyph (character) to glyph info (location in glyph texture).
  std::map<GlyphKey, GlyphInfo> glyphs_;
  ScopedPtr<GLMutableTexture2D> glyph_texture_;
};

GLState* LockGLState(void (^draw_callback)());
void ReleaseGLState();

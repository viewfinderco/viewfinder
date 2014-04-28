// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis, Spencer Kimball.

#import <QuartzCore/QuartzCore.h>
#import "GLState.h"
#import "Mutex.h"
#import "ScopedRef.h"
#import "STLUtils.h"
#import "Utils.h"
#import "ValueUtils.h"

namespace {

Mutex gl_mu;
GLState* gl_state = NULL;

}  // namespace


@implementation GLLayer

- (id)init {
  if (self = [super init]) {
    self.contentsScale = [UIScreen mainScreen].scale;
    self.rasterizationScale = [UIScreen mainScreen].scale;
    self.opaque = NO;
    self.drawableProperties =
        Dict(kEAGLDrawablePropertyRetainedBacking, NO,
             kEAGLDrawablePropertyColorFormat, kEAGLColorFormatRGBA8);

    context_ = [[EAGLContext alloc]
                     initWithAPI:kEAGLRenderingAPIOpenGLES2];
    [EAGLContext setCurrentContext:context_];
  }
  return self;
}

- (id)initWithLayer:(id)layer {
  DIE("unimplemented");
  return NULL;
}

- (bool)setDraw:(void (^)())draw {
  if (draw && draw_) {
    LOG("draw should be NULL before being set to another callback");
    return false;
  }
  draw_ = draw;
  return true;
}

- (void)setFrame:(CGRect)f {
  if (CGSizeEqualToSize(f.size, CGSizeZero)) {
    DCHECK(false);
    return;
  }

  if (!CGRectEqualToRect(self.frame, f)) {
    create_framebuffer_ = true;
  }
  [super setFrame:f];
}

- (void)display {
  if (CGSizeEqualToSize(self.bounds.size, CGSizeZero)) {
    DCHECK(false);
    return;
  }

  [EAGLContext setCurrentContext:context_];
  if (!framebuffer_ || create_framebuffer_) {
    [self framebufferCreate];
  }

  // Even though we're drawing over the entire viewport, clearing provides an
  // optimization path for the OpenGL driver.
  glClear(GL_COLOR_BUFFER_BIT);
  DCHECK(draw_);
  if (draw_) {
    draw_();
  }

  [context_ presentRenderbuffer:GL_RENDERBUFFER];
}

- (void)framebufferCreate {
  create_framebuffer_ = false;

  if (!framebuffer_) {
    glGenFramebuffers(1, &framebuffer_);
    CHECK_NE(0, framebuffer_);
  }
  glBindFramebuffer(GL_FRAMEBUFFER, framebuffer_);
  GL_CHECK_ERRORS();

  if (!renderbuffer_) {
    glGenRenderbuffers(1, &renderbuffer_);
    CHECK_NE(0, renderbuffer_);
  }
  glBindRenderbuffer(GL_RENDERBUFFER, renderbuffer_);
  GL_CHECK_ERRORS();

  CHECK([context_ renderbufferStorage:GL_RENDERBUFFER fromDrawable:self])
      << Format(": %.0f", self.bounds);
  glFramebufferRenderbuffer(
      GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, renderbuffer_);

  {
    GLint val;
    glGetFramebufferAttachmentParameteriv(
        GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
        GL_FRAMEBUFFER_ATTACHMENT_OBJECT_TYPE, &val);
    CHECK_EQ(val, GL_RENDERBUFFER);

    glGetFramebufferAttachmentParameteriv(
        GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
        GL_FRAMEBUFFER_ATTACHMENT_OBJECT_NAME, &val);
    CHECK_EQ(val, renderbuffer_);
  }

  if (glCheckFramebufferStatus(GL_FRAMEBUFFER) !=
      GL_FRAMEBUFFER_COMPLETE) {
    DIE("failed to make complete framebuffer object %x",
        glCheckFramebufferStatus(GL_FRAMEBUFFER));
  }

  GLint width;
  GLint height;
  glGetRenderbufferParameteriv(GL_RENDERBUFFER, GL_RENDERBUFFER_WIDTH, &width);
  glGetRenderbufferParameteriv(GL_RENDERBUFFER, GL_RENDERBUFFER_HEIGHT, &height);
  glViewport(0, 0, width, height);
  glClearColor(0, 0, 0, 0);
  glEnable(GL_BLEND);
  glBlendFunc(GL_SRC_ALPHA_SATURATE, GL_ONE);
  GL_CHECK_ERRORS();
}

- (void)framebufferDestroy {
  if (framebuffer_) {
    glDeleteFramebuffers(1, &framebuffer_);
    framebuffer_ = 0;
  }
  if (renderbuffer_) {
    glDeleteRenderbuffers(1, &renderbuffer_);
    renderbuffer_ = 0;
  }
}

- (void)dealloc {
  [self framebufferDestroy];
}

@end  // GLLayer


GLState::GLState() {
  Init();
}

GLState::~GLState() {
}

bool GLState::Lock(void (^draw_callback)()) {
  return [layer_ setDraw:draw_callback];
}

void GLState::Release() {
  [layer_ removeFromSuperlayer];
  [layer_ setDraw:NULL];
}

void GLState::AccumulateGlyphs(Slice s, UIFont* font) {
  while (!s.empty()) {
    const Slice last(s);
    const int r = utfnext(&s);
    if (r == -1) {
      break;
    }
    GlyphInfo& g = glyphs_[std::make_pair(font, r)];
    if (!g.str) {
      g.str = NewNSString(last.substr(0, last.size() - s.size()));
      rebuild_glyph_texture_ = true;
    }
  }
}

void GLState::CommitGlyphTexture() {
  if (rebuild_glyph_texture_) {
    rebuild_glyph_texture_ = false;

    typedef std::map<std::pair<UIFont*, int>, GlyphInfo> GlyphMap;

    const float scale = [UIScreen mainScreen].scale;
    int width = 0;
    int height = 0;

    for (GlyphMap::iterator iter(glyphs_.begin());
         iter != glyphs_.end();
         ++iter) {
      GlyphInfo& g = iter->second;
      UIFont* font = iter->first.first;
      g.size = [g.str sizeWithFont:font];
      if (scale != 1) {
        font = [font fontWithSize:font.pointSize * scale];
        g.scaled_size = [g.str sizeWithFont:font];
      } else {
        g.scaled_size = g.size;
      }
      width += 2 + ceil(g.scaled_size.width);
      height = std::max<int>(height, ceil(g.scaled_size.height));
    }

    // Round width to the next multiple of 32 to improve texture performance
    // (according to the Instruments OpenGL Analyzer).
    width += (32 - (width % 32));
    vector<char> data(4 * width * height, 0);
    ScopedRef<CGColorSpaceRef> colorspace(CGColorSpaceCreateDeviceRGB());
    ScopedRef<CGContextRef> context(
        CGBitmapContextCreate(&data[0], width, height, 8,
                              4 * width, colorspace,
                              kCGBitmapByteOrder32Little | kCGImageAlphaPremultipliedFirst));
    CHECK(context.get() != NULL);

    CGContextSetRGBFillColor(context, 1, 1, 1, 1);
    CGContextTranslateCTM(context, 0.0, height);
    CGContextScaleCTM(context, 1.0, -1.0);

    UIGraphicsPushContext(context);

    float x = 1;
    for (GlyphMap::iterator iter(glyphs_.begin());
         iter != glyphs_.end();
         ++iter) {
      GlyphInfo& g = iter->second;
      UIFont* font = iter->first.first;
      if (scale != 1) {
        font = [font fontWithSize:font.pointSize * scale];
      }
      [g.str drawAtPoint:CGPointMake(x, 0) withFont:font];
      g.tx_start = (x + g.scaled_size.width) / width;
      g.tx_end = x / width;
      g.ty_start = g.scaled_size.height / height;
      g.ty_end = 0;
      x += 2 + ceil(g.scaled_size.width);
    }

    UIGraphicsPopContext();

    if (!glyph_texture_.get()) {
      // TODO(pmattis): Figure out why GL_CHECK_ERRORS() inside the GLTexture2D
      // construtor is sometimes firing on the following line. Perhaps this
      // texture should be created in initGL.
      glyph_texture_.reset(new GLMutableTexture2D);
      glyph_texture_->SetFormat(GL_BGRA);
      glyph_texture_->SetType(GL_UNSIGNED_BYTE);
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);

      // Set up the uniform variables for our shader program.
      glUseProgram(texture_shader_->name());
      // Configure the texture for texture unit 0.
      glActiveTexture(GL_TEXTURE0);
      glBindTexture(GL_TEXTURE_2D, glyph_texture_->name());
    }
    glyph_texture_->SetPixels(width, height, &data[0]);
    GL_CHECK_ERRORS();
  }
}

const GLState::GlyphInfo* GLState::GetGlyphInfo(const GlyphKey& key) const {
  return FindPtrOrNull(glyphs_, key);
}

void GLState::Init() {
  layer_ = [GLLayer new];

  solid_shader_.reset(new GLProgram("solid"));
  if (!solid_shader_->Compile("Solid", "")) {
    DIE("unable to compile: %s", solid_shader_->id());
  }
  solid_shader_->BindAttribute("a_position", A_POSITION);
  solid_shader_->BindAttribute("a_color", A_COLOR);
  if (!solid_shader_->Link()) {
    DIE("unable to link: %s", solid_shader_->id());
  }
  u_solid_mvp_ = solid_shader_->GetUniform("u_MVP");

  texture_shader_.reset(new GLProgram("texture"));
  if (!texture_shader_->Compile("Texture", "")) {
    DIE("unable to compile: %s", texture_shader_->id());
  }
  texture_shader_->BindAttribute("a_position", A_POSITION);
  texture_shader_->BindAttribute("a_tex_coord", A_TEX_COORD);
  texture_shader_->BindAttribute("a_alpha", A_ALPHA);
  if (!texture_shader_->Link()) {
    DIE("unable to link: %s", texture_shader_->id());
  }
  u_texture_mvp_ = texture_shader_->GetUniform("u_MVP");
  u_texture_texture_ = texture_shader_->GetUniform("u_texture");

  const string filename = Format(
      "arc-background%s.png",
      ([UIScreen mainScreen].scale == 2) ? "@2x" : "");
  arc_texture_.reset(GLTextureLoader::LoadFromFile(filename));
  if (!arc_texture_.get()) {
    DIE("unable to load: %s", filename);
  }
  glBindTexture(GL_TEXTURE_2D, arc_texture_->name());
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST_MIPMAP_LINEAR);
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
  glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
  glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT);
  glGenerateMipmap(GL_TEXTURE_2D);
}


GLState* LockGLState(void (^draw_callback)()) {
  MutexLock l(&gl_mu);
  if (!gl_state) {
    gl_state = new GLState;
  }
  if (gl_state->Lock(draw_callback)) {
    return gl_state;
  }
  return NULL;
}

void ReleaseGLState() {
  MutexLock l(&gl_mu);
  CHECK(gl_state);
  gl_state->Release();
}

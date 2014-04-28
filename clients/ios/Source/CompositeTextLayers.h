// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import <UIKit/UIKit.h>
#import "DayTable.h"
#import "Diff.h"
#import "TextLayer.h"
#import "Utils.h"
#import "Vector.h"

@class ColoredTextLayer;
@class MaskedTextLayer;

// A CALayer subclass for transition text.
struct DiffLayer {
  DiffOp op;
  MaskedTextLayer* layer;

  DiffLayer()
      : layer(nil) {}
  DiffLayer(const DiffOp& o, MaskedTextLayer* l)
      : op(o), layer(l) {}
};

@interface TransitionTextLayer : CALayer {
 @private
  float transition_;
  float max_width_;
  float slide_left_;
  CALayer* slide_layer_;
  NSAttributedString* text_;
  NSAttributedString* to_text_;
  ColoredTextLayer* text_layer_;  // only text_ has been rendered; no diffs yet
  ColoredTextLayer* to_text_layer_;  // only to_text_ has been rendered; no diffs yet
  float max_ascent_;
  float max_descent_;
  float max_leading_;
  float max_height_;
  vector<DiffLayer> diffs_;
  float blend_ratio_;
}

@property (nonatomic, readonly) float ascent;
@property (nonatomic, readonly) float descent;
@property (nonatomic, readonly) float leading;
@property (nonatomic, readonly) float baseline;
@property (nonatomic, readonly) float lineHeight;
@property (nonatomic) float transition;
@property (nonatomic) float maxWidth;
@property (nonatomic) float slideLeft;

@end  // TransitionTextLayer


@interface CompositeTextLayer : CALayer {
 @protected
  vector<TransitionTextLayer*> layers_;
  float text_width_;
  float transition_;
  float max_width_;
  float slide_left_;
}

@property (nonatomic) float transition;
@property (nonatomic) float maxWidth;
@property (nonatomic) float slideLeft;
@property (nonatomic, readonly) float textWidth;

- (id)init;
- (void)clearShadow;
- (void)setShadowWithColor:(const Vector4f&)color;
- (void)blendForegroundColor:(const Vector4f&)color
                  blendRatio:(float)t;

@end  // CompositeTextLayer


@interface EpisodeTextLayer : CompositeTextLayer {
 @protected
  TransitionTextLayer* location_;
  TransitionTextLayer* full_info_;
  TransitionTextLayer* short_info_;
}

- (id)initWithEpisode:(const EpisodeHandle&)episode
     withContributors:(bool)with_contribs
       withPhotoCount:(int)photo_count
                atNow:(WallTime)now;

@end  // EpisodeTextLayer


@interface ActivityTextLayer : CompositeTextLayer {
 @protected
  TransitionTextLayer* info_;
  TransitionTextLayer* time_;
  TransitionTextLayer* short_info_;
}

- (id)initWithActivity:(const ActivityHandle&)activity
       withActivityRow:(const ViewpointSummaryMetadata::ActivityRow*)activity_row
        isContinuation:(bool)is_continuation;

@end  // ActivityTextLayer


@interface EventTextLayer : CompositeTextLayer {
 @protected
  TransitionTextLayer* location_;
  TransitionTextLayer* full_info_;
  TransitionTextLayer* short_info_;
  bool location_first_;
}

- (id)initWithEvent:(const Event&)event
         withWeight:(float)weight
      locationFirst:(bool)location_first;

@end  // EventTextLayer


@interface EventCardTextLayer : CompositeTextLayer {
 @protected
  TransitionTextLayer* title_;
  TransitionTextLayer* date_;
}

- (id)initWithEvent:(const Event&)event
         withWeight:(float)weight;

@end  // EventCardTextLayer


@interface FullEventCardTextLayer : CompositeTextLayer {
 @protected
  TransitionTextLayer* title_;
  TransitionTextLayer* date_;
}

- (id)initWithEvent:(const Event&)event
         withWeight:(float)weight;

@end  // FullEventCardTextLayer


@interface InboxCardTextLayer : CompositeTextLayer {
 @protected
  float top_margin_;
  TransitionTextLayer* title_;
  TransitionTextLayer* contrib_;
  TransitionTextLayer* short_title_;
  TransitionTextLayer* short_info_;
  TransitionTextLayer* time_;
}

- (id)initWithTrapdoor:(const Trapdoor&)trapdoor
         withViewpoint:(const ViewpointHandle&)vh
            withWeight:(float)weight;

@end  // InboxCardTextLayer


// local variables:
// mode: objc
// end:

// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import "CheckmarkBadge.h"
#import "ShareActivityRowView.h"
#import "UIStyle.h"
#import "UIView+geometry.h"

namespace {

const float kDuration = 0.3;
const float kConversationMargin = 8;
const float kTitleLeftMargin = 38;
const float kTitleTopMargin = 69;
const float kTitleBannerHeight = 36;

LazyStaticHexColor kTitleBannerColor = { "#7f7c7c" };

}  // namespace

@implementation ShareActivityRowView

+ (float)suggestedHeight:(NSAttributedString*)text
               textWidth:(float)text_width {
  return kTitleBannerHeight;
}

- (id)initWithActivity:(const ActivityHandle&)activity
       withActivityRow:(const ViewpointSummaryMetadata::ActivityRow*)activity_row
                  text:(NSAttributedString*)text
             textWidth:(float)text_width
             topMargin:(float)top_margin
          bottomMargin:(float)bottom_margin
            leftMargin:(float)left_margin
            threadType:(ActivityThreadType)thread_type
               comment:(const NSRange&)comment_range {
  if (self = [super initWithActivity:activity
                                text:text
                           textWidth:text_width
                           topMargin:top_margin
                        bottomMargin:bottom_margin
                          leftMargin:left_margin
                          threadType:thread_type
                             comment:comment_range]) {
    // We need the content_view so that we can properly recognize taps on the
    // share activity row.
    // TODO(spencer): this is inadequate. We want to provide links to
    //   all episodes, not just the first.
    const ShareEpisodes* episodes = activity_->GetShareEpisodes();
    if (episodes->size() > 0) {
      ContentView* content_view = [ContentView new];
      content_view.autoresizingMask =
          UIViewAutoresizingFlexibleWidth |
          UIViewAutoresizingFlexibleHeight;
      content_view.backgroundColor = [UIColor clearColor];
      content_view.viewpointId = activity_->viewpoint_id().local_id();
      content_view.episodeId = episodes->Get(0).episode_id().local_id();
      [self insertSubview:content_view atIndex:0];
    }

    // Move activity text down by top margin.
    activity_text_.frameLeft = kTitleLeftMargin;
    activity_text_.frameTop = kTitleTopMargin;

    UIView* title_banner = [UIView new];
    title_banner.autoresizingMask = UIViewAutoresizingFlexibleWidth;
    title_banner.backgroundColor = kTitleBannerColor;
    title_banner.frame = CGRectMake(kConversationMargin, top_margin + kConversationMargin,
                                    self.frameWidth, kTitleBannerHeight);
    [self insertSubview:title_banner belowSubview:activity_text_];
  }
  return self;
}

- (void)setEditing:(bool)value {
  [super setEditing:value];
}

- (CGSize)sizeThatFits:(CGSize)size {
  return CGSizeMake(
      self.frameWidth, top_margin_ + kConversationMargin + kTitleBannerHeight);
}

@end  // ShareActivityRowView

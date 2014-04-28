// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "AttrStringUtils.h"
#import "CompositeTextLayers.h"
#import "ConversationActivityRowView.h"
#import "LayoutUtils.h"
#import "UIStyle.h"
#import "UIView+geometry.h"

namespace {

const float kActivityThreadLeftMargin = 22;
const float kBadgeLeftMargin = -26;
const float kBadgeTopMargin = 0;
const float kTextEditModeOffset = 55 - 39;
const float kConversationSpacing = 8;
const float kDuration = 0.3;

LazyStaticImage kConvoThreadStart(
    @"convo-thread-start.png", UIEdgeInsetsMake(23, 0, 0, 0));
LazyStaticImage kConvoThreadEnd(
    @"convo-thread-end.png", UIEdgeInsetsMake(23, 0, 0, 0));
LazyStaticImage kConvoThreadPhotos(
    @"convo-thread-photoshare.png", UIEdgeInsetsMake(23, 0, 0, 0));
LazyStaticImage kConvoThreadPoint(
    @"convo-thread-point.png", UIEdgeInsetsMake(23, 0, 0, 0));
LazyStaticImage kConvoThreadStroke(@"convo-thread-stroke.png");

UIImage* ActivityThreadImage(ActivityThreadType thread_type) {
  switch (thread_type) {
    case THREAD_START:
      return kConvoThreadStart;
    case THREAD_PHOTOS:
      return kConvoThreadPhotos;
    case THREAD_END:
    case THREAD_COMBINE_END:
    case THREAD_COMBINE_END_WITH_TIME:
      return kConvoThreadEnd;
    case THREAD_POINT:
      return kConvoThreadPoint;
    case THREAD_COMBINE:
    case THREAD_COMBINE_NEW_USER:
    case THREAD_COMBINE_WITH_TIME:
    case THREAD_COMBINE_NEW_USER_WITH_TIME:
      return kConvoThreadStroke;
    case THREAD_NONE:
      return NULL;
    default:
      LOG("Unknown thread type");
      return NULL;
  }
}

UIView* NewActivityThread(ActivityThreadType thread_type) {
  UIImage* thread_image = ActivityThreadImage(thread_type);
  if (!thread_image) {
    return NULL;
  }
  UIView* thread = [[UIImageView alloc] initWithImage:thread_image];
  thread.frameLeft = kActivityThreadLeftMargin;
  thread.frameHeight = 0;
  thread.tag = kConversationThreadTag;
  switch (thread_type) {
    case THREAD_START:
    case THREAD_PHOTOS:
      thread.autoresizingMask = UIViewAutoresizingFlexibleHeight;
      break;
    case THREAD_END:
    case THREAD_COMBINE_END:
    case THREAD_COMBINE_END_WITH_TIME:
      thread.autoresizingMask = UIViewAutoresizingFlexibleHeight;
      break;
    case THREAD_POINT:
      thread.autoresizingMask = UIViewAutoresizingFlexibleHeight;
      break;
    case THREAD_COMBINE:
    case THREAD_COMBINE_NEW_USER:
    case THREAD_COMBINE_WITH_TIME:
    case THREAD_COMBINE_NEW_USER_WITH_TIME:
      thread.autoresizingMask = UIViewAutoresizingFlexibleHeight;
      break;
    case THREAD_NONE:
      return NULL;
    default:
      LOG("Unknown thread type");
      return NULL;
  }
  return thread;
}

}  // namespace

@implementation ConversationActivityRowView

+ (float)suggestedHeight:(NSAttributedString*)text
               textWidth:(float)text_width {
  return AttrStringSize(text, CGSizeMake(text_width, CGFLOAT_MAX)).height;
}

- (id)initWithActivity:(const ActivityHandle&)activity
                  text:(NSAttributedString*)text
             textWidth:(float)text_width
             topMargin:(float)top_margin
          bottomMargin:(float)bottom_margin
            leftMargin:(float)left_margin
            threadType:(ActivityThreadType)thread_type
               comment:(const NSRange&)comment_range {
  if (self = [super init]) {
    self.autoresizesSubviews = YES;
    activity_ = activity;
    top_margin_ = top_margin;
    bottom_margin_ = bottom_margin;

    thread_ = NewActivityThread(thread_type);
    if (thread_) {
      [self addSubview:thread_];
    }
    const CGRect text_frame = CGRectMake(
        left_margin, top_margin, text_width, 0);
    activity_text_ = [[TextView alloc] initWithFrame:text_frame];
    activity_text_.delegate = self;
    activity_text_.editable = NO;
    activity_text_.linkStyle = UIStyle::kLinkAttributes;
    activity_text_.keyboardAppearance = UIKeyboardAppearanceAlert;
    activity_text_.attrText = text;
    activity_text_.editableRange = comment_range;
    activity_text_.frameHeight = activity_text_.contentHeight;
    [self addSubview:activity_text_];
  }
  return self;
}

- (bool)editing {
  return activity_text_.editable || [super editing];
}

- (void)setEditing:(bool)value {
  if (activity_->has_post_comment()) {
    // TODO(peter): We currently don't allow editing of comments after they
    // have been created.
    // activity_text_.editable = value;

    if (value) {
      // We're entering edit mode, stash away the original text.
      if (activity_text_.editable && !orig_text_) {
        orig_text_ = activity_text_.editableText;
        orig_editable_range_ = activity_text_.editableRange;
      }
    } else {
      // We're exiting edit mode, revert the text.
      if (orig_text_) {
        if (activity_text_.editable) {
          activity_text_.editableText = orig_text_;
          activity_text_.editableRange = orig_editable_range_;
        }
        orig_text_ = NULL;
      }
    }
  } else if (activity_->has_share_new() ||
             activity_->has_share_existing()) {
    [super setEditing:value];
  }

  if (value) {
    if (thread_.alpha == 0 || ![UIView areAnimationsEnabled]) {
      thread_.alpha = 0;
      return;
    }

    [UIView animateWithDuration:kDuration
                     animations:^{
        thread_.alpha = 0;
      }];
  } else {
    if (thread_.alpha == 1 || ![UIView areAnimationsEnabled]) {
      return;
    }

    thread_.alpha = 0;
    [UIView animateWithDuration:kDuration
                     animations:^{
        thread_.alpha = 1;
      }];
  }
}

- (bool)modified {
  if (!orig_text_) {
    return false;
  }
  return ToSlice(activity_text_.editableText) != ToSlice(orig_text_);
}

- (void)commitEdits {
  // Calling resign first responder commits any autosuggestions.
  [activity_text_ resignFirstResponder];

  if (self.modified) {
    orig_text_ = activity_text_.editableText;
    [self.env rowViewCommitText:self text:activity_text_.editableText];
  }
}

- (CGSize)sizeThatFits:(CGSize)size {
  return CGSizeMake(
      self.frameWidth,
      activity_text_.contentHeight + activity_text_.frameTop + bottom_margin_);
}

- (void)layoutSubviews {
  [super layoutSubviews];
  activity_text_.frameHeight = activity_text_.contentHeight;
}

- (void)textViewDidChange:(TextView*)text_view {
  if (activity_text_.frameHeight != activity_text_.contentHeight) {
    [self.env rowViewDidChange:self];
  }
}

- (float)badgeLeftMargin {
  return kBadgeLeftMargin;
}

- (float)badgeTopMargin {
  return kBadgeTopMargin;
}

- (float)textEditModeOffset {
  return kTextEditModeOffset;
}

@end  // ConversationActivityRowView

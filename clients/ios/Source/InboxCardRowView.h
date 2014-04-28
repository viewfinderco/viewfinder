// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import <UIKit/UIKit.h>
#import <unordered_map>
#import "ContentView.h"
#import "DayTable.h"
#import "LayoutUtils.h"
#import "RowView.h"

struct LayoutRow;
@class CompositeTextLayer;
@class InboxCardRowView;

// Expanding/collapsing inbox card view which provides a seamless
// animation between sampled collection of photos within conversation
// to fully expanded collection of all photos in convo.
typedef std::unordered_map<PhotoView*, CGRect, HashObjC> ViewFrameMap;

@protocol InboxCardRowEnv
- (void)inboxCardAddPhotos:(InboxCardRowView*)row_view;
- (void)inboxCardMuteConvo:(InboxCardRowView*)row_view;
- (void)inboxCardRemoveConvo:(InboxCardRowView*)row_view;
- (void)inboxCardUnmuteConvo:(InboxCardRowView*)row_view;
- (void)toggleExpandRow:(InboxCardRowView*)row_view;

- (void)inboxCardDidScroll:(InboxCardRowView*)row_view
                scrollView:(UIScrollView*)scroll_view;
@end  // InboxCardRowEnv

@interface InboxCardRowView : RowView<UIScrollViewDelegate> {
 @private
  UIAppState* state_;
  __weak id<InboxCardRowEnv> inbox_card_row_env_;
  TrapdoorHandle trh_;
  float width_;
  float height_;
  float title_height_;
  float photo_height_;
  float footer_height_;
  float expanded_height_;
  float expanded_photo_height_;
  float expanded_photo_frame_height_;
  PhotoView* cover_photo_;
  UIScrollView* title_section_;
  UIScrollView* photo_section_;
  UIView* button_tray_;
  UIButton* expand_button_;
  UIButton* mute_button_;
  UIButton* remove_button_;
  UIButton* ridges_button_;
  UIImageView* gradient_;
  CALayer* mask_;
  bool expanded_;
  bool expanded_initialized_;
  // Vectors of photos for collapsed/expanded states.
  vector<PhotoView*> collapsed_photos_;
  vector<PhotoView*> expanded_photos_;
  // Maps from view to canonical frame.
  ViewFrameMap collapsed_frames_;
  ViewFrameMap expanded_frames_;
  UIImageView* muted_;
}

@property (nonatomic, readonly) TrapdoorHandle trapdoor;
@property (nonatomic, weak) id<InboxCardRowEnv> inboxCardRowEnv;
@property (nonatomic, readonly) UIScrollView* photoSection;

- (id)initWithState:(UIAppState*)state
       withTrapdoor:(const TrapdoorHandle&)trh
        interactive:(bool)interactive
          withWidth:(float)width;

- (float)animateToggleExpandPrepare:(float)max_height;
- (void)animateToggleExpandCommit;
- (void)animateToggleExpandFinalize;
- (float)toggleExpand:(float)max_height;

struct CardState {
  float photo_offset;
  float title_offset;
};
typedef std::unordered_map<int64_t, CardState> CardStateMap;
+ (CardStateMap*) cardStateMap;

+ (float)getInboxCardHeightWithState:(UIAppState*)state
                        withTrapdoor:(const Trapdoor&)trap
                           withWidth:(float)width;

+ (CompositeTextLayer*)newTextLayerWithTrapdoor:(const Trapdoor&)trap
                                  withViewpoint:(const ViewpointHandle&)vh
                                      withWidth:(float)width
                                     withWeight:(float)weight;

@end  // InboxCardRowView

// local variables:
// mode: objc
// end:

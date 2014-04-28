// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "Callback.h"
#import "FollowerFieldView.h"
#import "RowView.h"
#import "TextView.h"
#import "ViewpointTable.h"

enum HeaderEditMode {
  EDIT_HEADER_NONE = 0,
  EDIT_HEADER_TITLE,
  EDIT_HEADER_FOLLOWERS,
  EDIT_HEADER_PHOTOS,
};

@interface ConversationHeaderRowView : RowView<TextViewDelegate,
                                               FollowerFieldViewDelegate> {
 @private
  UIAppState* state_;
  bool provisional_;
  ViewpointHandle vh_;
  string default_title_;
  HeaderEditMode edit_mode_;
  float min_height_;
  float min_header_y_;
  float cover_photo_height_;
  UIView* header_;
  UIView* header_cap_;
  TextView* title_;
  UIView* title_container_;
  UIButton* title_edit_;
  UIButton* title_cta_;
  bool show_title_cta_;
  UIButton* edit_cover_photo_button_;
  UIButton* cover_photo_cta_;
  FollowerFieldView* followers_;
  UIView* title_separator_;
  UIView* followers_separator_;
  NSString* title_orig_text_;
  CallbackSet edit_cover_photo_callback_;
}

@property (nonatomic) bool editing;
@property (nonatomic) bool selected;
@property (nonatomic) bool showAllFollowers;
@property (nonatomic, readonly) bool editingTitle;
@property (nonatomic, readonly) bool editingFollowers;
@property (nonatomic, readonly) int numContacts;
@property (nonatomic, readonly) NSString* title;
@property (nonatomic, readonly) bool emptyTitle;
@property (nonatomic, readonly) UIView* header;
@property (nonatomic, readonly) float coverPhotoHeight;
@property (nonatomic, readonly) CallbackSet* editCoverPhotoCallback;
@property (nonatomic, readonly) UIButton* editCoverPhotoButton;
@property (nonatomic, readonly) UIButton* coverPhotoCTA;

- (id)initWithState:(UIAppState*)state
        viewpointId:(int64_t)viewpoint_id
      hasCoverPhoto:(bool)has_cover_photo
              width:(float)width;
- (void)setCoverPhoto:(PhotoView*)p;
- (void)startEditingTitle;
- (void)startEditingFollowers;
- (bool)canEndEditing;
// Possibly cancel the editing if the touch location is outside
// of the component currently being edited.
- (bool)maybeStopEditing:(CGPoint)p;

@end  // ConversationHeaderRowView

// local variables:
// mode: objc
// end:

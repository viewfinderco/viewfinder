// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <vector>
#import <UIKit/UIKit.h>
#import "ContactManager.h"
#import "ContentView.h"
#import "PhotoSelection.h"

@class CompositeTextLayer;
@class PhotoView;
@class RowView;

extern const float kExpandAnimationDuration;

@protocol RowViewEnv<NSObject>
- (void)rowViewDidChange:(RowView*)row;
@optional
// Called when row view wants parent to stop editing
- (void)rowViewStopEditing:(RowView*)row commit:(bool)commit;
- (void)rowViewCommitText:(RowView*)row
                     text:(NSString*)text;
- (void)rowViewCommitFollowers:(RowView*)row
                 addedContacts:(const ContactManager::ContactVec&)added_contacts
                    removedIds:(const vector<int64_t>&)removed_ids;
- (void)rowViewDidBeginEditing:(RowView*)row;
- (void)rowViewDidEndEditing:(RowView*)row;
@end  // RowViewEnv

@interface RowView : ContentView {
 @protected
  std::vector<PhotoView*> photos_;
  __weak id<RowViewEnv> env_;

 @private
  CompositeTextLayer* text_layer_;
  int index_;
}

@property (nonatomic, readonly) float desiredFrameHeight;
@property (nonatomic, readonly) bool hasFocus;
@property (nonatomic) bool editing;
@property (nonatomic, readonly) UIView* editingView;
@property (nonatomic, weak) id<RowViewEnv> env;
@property (nonatomic) int index;
@property (nonatomic, readonly) bool modified;
@property (nonatomic) bool selected;
@property (nonatomic) bool enabled;
@property (nonatomic, readonly) CompositeTextLayer* textLayer;
@property (nonatomic, readonly) std::vector<PhotoView*>* photos;

- (bool)hasPhoto:(int64_t)photo_id;
- (PhotoView*)findPhotoView:(int64_t)photo_id;
- (void)addTextLayer:(CompositeTextLayer*)layer;
- (void)commitEdits;

// Animating row expansion / collapse.

// Call prepare before expanding, outside of the animation block.
// Returns the new height after toggling the event view between
// collapsed and expanded (or vice versa).
- (float)animateToggleExpandPrepare:(float)max_height;
- (void)animateToggleExpandCommit;
- (void)animateToggleExpandFinalize;

// Non-animated expansion / collapse.
- (float)toggleExpand:(float)max_height;

@end  // RowView

// local variables:
// mode: objc
// end:

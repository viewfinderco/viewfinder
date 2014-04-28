// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import "Analytics.h"
#import "AssetsManager.h"
#import "AsyncState.h"
#import "AttrStringUtils.h"
#import "CALayer+geometry.h"
#import "Dashboard.h"
#import "DashboardCard.h"
#import "DashboardNotice.h"
#import "Defines.h"
#import "LayoutUtils.h"
#import "NetworkManager.h"
#import "RootViewController.h"
#import "STLUtils.h"
#import "SummaryLayoutController.h"
#import "UIAppState.h"
#import "UIStyle.h"
#import "UIView+geometry.h"

namespace {

const float kSpacing = 8;

const string kDashboardBackgroundPhotoIdKey =
    DBFormat::metadata_key("dashboard_background_photo_id");

LazyStaticImage kDashboardDefault(@"dashboard-default.jpg");
LazyStaticImage kTourBackground(@"tour-background-image.jpg");
LazyStaticImage kTourButton(
    @"tour-button-rounded.png", UIEdgeInsetsMake(0, 12, 0, 12));
LazyStaticImage kTourIconConvo(@"tour-icon-convo.png");
LazyStaticImage kTourIconFind(@"tour-icon-find.png");
LazyStaticImage kTourIconUnlock(@"tour-icon-unlock.png");
LazyStaticImage kTourLogo(@"tour-logo.png");

LazyStaticUIFont kTourButtonFont = { kProximaNovaBold, 12 };
LazyStaticUIFont kTourSkipButtonFont = { kProximaNovaRegular, 15 };
LazyStaticUIFont kTourSkipButtonBoldFont = { kProximaNovaBold, 15 };
LazyStaticCTFont kTourSubtitleFont = { kProximaNovaRegular, 17 };
LazyStaticCTFont kTourTitleFont = { kProximaNovaSemibold, 22 };

LazyStaticHexColor kTourTextColor = { "#ffffff" };

// Decodes URL escapes, such as %3b and "+".
string URLDecode(const Slice& str) {
  NSString* s = NewNSString(str);
  s = [s stringByReplacingOccurrencesOfString:@"+" withString:@" "];
  s = [s stringByReplacingPercentEscapesUsingEncoding:NSUTF8StringEncoding];
  return ToString(s);
}

UIButton* NewTourButton(const char* title, id target, SEL selector) {
  // Note: kCTForegroundColorAttributeName is ignored when displaying
  // an attributed string in a UIView. We need to use
  // NSForegroundColorAttributeName and UIFont / UIColor and the
  // UIKit-based kerning instead.
  NSMutableAttributedString* attr_title =
      NewAttrString(title, kTourButtonFont, kTourTextColor);
  attr_title = AttrUIKern(attr_title, 2);

  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.contentEdgeInsets = UIEdgeInsetsMake(10, 13, 10, 13);
  b.contentVerticalAlignment = UIControlContentVerticalAlignmentCenter;
  UIImage* bg = kTourButton;
  [b setAttributedTitle:attr_title
               forState:UIControlStateNormal];
  [b setBackgroundImage:bg
               forState:UIControlStateNormal];
  [b setBackgroundImage:bg
               forState:UIControlStateHighlighted];
  if (target) {
    [b addTarget:target
          action:selector
       forControlEvents:UIControlEventTouchUpInside];
  }
  [b sizeToFit];
  b.frameHeight = bg.size.height;
  return b;
}

UIButton* NewSkipTourButton(id target, SEL selector) {
  NSMutableAttributedString* str = NewAttrString(
      "Have an account? Skip to ", kTourSkipButtonFont, kTourTextColor);
  AppendAttrString(str, "Login", kTourSkipButtonBoldFont, kTourTextColor);

  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.contentEdgeInsets = UIEdgeInsetsMake(10, 13, 10, 13);
  b.contentVerticalAlignment = UIControlContentVerticalAlignmentCenter;
  [b setAttributedTitle:str
               forState:UIControlStateNormal];
  if (target) {
    [b addTarget:target
          action:selector
       forControlEvents:UIControlEventTouchUpInside];
  }
  [b sizeToFit];
  return b;
}

UIView* NewTourPage(
    int index, float width, float height,
    id target, SEL selector, SEL skipped_selector) {
  UIView* page = [[UIView alloc] initWithFrame:CGRectMake(0, 0, width, height)];
  UIImage* image;
  NSMutableAttributedString* str;
  const char* button_title = NULL;
  float icon_top = 88;

  switch (index) {
    case 0: {
      image = kTourLogo;
      icon_top = 168;
      str = NewAttrString("is the easy and fun way to\n"
                          "privately share photos",
                          kTourTitleFont, kTourTextColor);
      button_title = "TAP TO START";

      UIButton* skip_to_login = NewSkipTourButton(target, skipped_selector);
      skip_to_login.frameBottom = height - 5;
      skip_to_login.frameLeft = (width - skip_to_login.frameWidth) / 2;
      [page addSubview:skip_to_login];
      break;
    }
    case 1:
      image = kTourIconUnlock;
      str = NewAttrString("Unlock Your Photos\n\n", kTourTitleFont, kTourTextColor);
      AppendAttrString(str,
                       "You have photos your friends want.\n"
                       "They have photos you want.\n"
                       "Find them and share as many as\n"
                       "you want with anyone",
                       kTourSubtitleFont, kTourTextColor);
      button_title = "CONTINUE";
      break;
    case 2:
      image = kTourIconConvo;
      str = NewAttrString("Enjoy Your Photos\n\n", kTourTitleFont, kTourTextColor);
      AppendAttrString(str,
                       "Share, don't post. Every share\n"
                       "creates a private place where you\n"
                       "and your friends can add more\n"
                       "photos, messages and people.",
                       kTourSubtitleFont, kTourTextColor);
      button_title = "CONTINUE";
      break;
    case 3:
      image = kTourIconFind;
      str = NewAttrString("Find Your Photos\n\n", kTourTitleFont, kTourTextColor);
      AppendAttrString(str,
                       "Everything in your pocket.\n"
                       "Any photo you send or receive is\n"
                       "securely stored by Viewfinder\n"
                       "and searchable when you want it.",
                       kTourSubtitleFont, kTourTextColor);
      break;
  }

  UIImageView* icon = [[UIImageView alloc] initWithImage:image];
  // The "((height + 20) - 480) / 2" expression accounts for the differing
  // screen heights on 4" and 5" iphones.
  icon.frameTop = icon_top + ((height + 20) - 480) / 2;
  icon.frameLeft = (width - icon.frameWidth) / 2;
  [page addSubview:icon];

  TextLayer* text = [TextLayer new];
  text.attrStr = AttrCenterAlignment(str);
  text.frameOrigin = CGPointMake(
      (width - text.frameWidth) / 2, icon.frameBottom);
  [page.layer addSublayer:text];

  if (button_title) {
    UIButton* button = NewTourButton(button_title, target, selector);
    button.frameLeft = (width - button.frameWidth) / 2;
    button.frameBottom = height - 108;
    button.tag = index;
    [page addSubview:button];
  }

  return page;
}

}  // namespace

@implementation Dashboard

@synthesize maintenanceDone = maintenance_done_;

- (id)initWithState:(UIAppState*)state
                env:(id<DashboardEnv>)env {
  if (self = [super init]) {
    state_ = state;
    env_ = env;
    active_ = false;

    self.autoresizesSubviews = YES;
    self.autoresizingMask =
        UIViewAutoresizingFlexibleHeight |
        UIViewAutoresizingFlexibleWidth;
    self.backgroundColor = [UIColor blackColor];

    // AddRoundedCorners(self);

    background_ = [[PhotoView alloc] initWithState:state];
    background_.autoresizesSubviews = YES;
    background_.autoresizingMask =
        UIViewAutoresizingFlexibleWidth |
        UIViewAutoresizingFlexibleHeight;
    [self addSubview:background_];

    content_ = [UIScrollView new];
    content_.alwaysBounceVertical = YES;
    content_.autoresizesSubviews = YES;
    content_.autoresizingMask =
        UIViewAutoresizingFlexibleHeight |
        UIViewAutoresizingFlexibleWidth;
    content_.bounces = YES;
    content_.delegate = self;
    content_.scrollsToTop = NO;
    content_.showsVerticalScrollIndicator = NO;
    content_.showsHorizontalScrollIndicator = NO;
    [self addSubview:content_];

    bg_edit_ = UIStyle::NewEditButton(self, @selector(editBackgroundPhoto));
    bg_edit_.autoresizingMask =
        UIViewAutoresizingFlexibleLeftMargin | UIViewAutoresizingFlexibleBottomMargin;
    bg_edit_.frameRight = content_.frameWidth;
    bg_edit_.frameTop = 64;  // status-bar + toolbar
    [content_ addSubview:bg_edit_];

    photo_queue_.name = "dashboard";
    photo_queue_.block = [^(vector<PhotoView*>* q) {
        if (![background_ isAppropriatelyScaled]) {
          q->push_back(background_);
        }
      } copy];

    state_->open_url()->Add(^(NSURL* url) {
        if (ToSlice(url.host) != "verify_id") {
          return;
        }
        string identity;
        string access_token;
        const vector<string> params(Split(ToString(url.query), "&"));
        for (int i = 0; i < params.size(); ++i) {
          const vector<string> vals(Split(params[i], "="));
          if (vals.size() != 2) {
            continue;
          }
          if (vals[0] == "identity") {
            identity = URLDecode(vals[1]);
          } else if (vals[0] == "access_token") {
            access_token = URLDecode(vals[1]);
          }
        }

        LOG("link identity '%s' with access code: '%s'", identity, access_token);
        if (!identity.empty() && !access_token.empty()) {
          state_->net_manager()->VerifyViewfinder(
              identity, access_token, false,
              ^(int status, int error_id, const string& msg) {
                NSString* msg_str = NewNSString(msg);
                state_->async()->dispatch_main(^{
                    if (status != 200) {
                      [[[UIAlertView alloc]
                         initWithTitle:@"Hmmm…"
                               message:msg_str
                              delegate:NULL
                         cancelButtonTitle:@"OK"
                         otherButtonTitles:NULL] show];
                    } else {
                      [login_signup_card_ confirmedIdentity:msg_str];
                    }
                  });
              });
        }
      });

    [self startInit];
  }
  return self;
}

- (bool)active {
  return active_;
}

- (void)setActive:(bool)active {
  active_ = active;
  if (active_) {
    [default_card_ startAnimating];
  }
}

- (void)setHidden:(BOOL)hidden {
  [super setHidden:hidden];
  content_.scrollsToTop = !hidden;

  // Install the keyboard notification handlers if the dashboard is not hidden
  // or the login/signup card is present.
  if (hidden && !login_signup_card_) {
    keyboard_will_show_.Clear();
    keyboard_will_hide_.Clear();
    return;
  }
  if (!hidden) {
    // Refresh the notices within an animation block in order to disable other
    // UIView animations.
    const ScopedDisableCAActions disable_ca_actions;
    [self refreshNotices:false];
  }
  if (!keyboard_will_show_.get()) {
    keyboard_will_show_.Init(
        UIKeyboardWillShowNotification,
        ^(NSNotification* n) {
          if (login_signup_card_) {
            // Ensure the dashboard is showing if the login/signup card is
            // present.
            [state_->root_view_controller() showDashboard:ControllerTransition()];
          }

          // Disable the parent scroll views while the keyboard is visible.
          content_.scrollEnabled = NO;

          const Dict d(n.userInfo);
          CGRect f = d.find_value(UIKeyboardFrameEndUserInfoKey).rect_value();
          // Convert the keyboard frame (in window coordinates) to the
          // superview's coordinates. This is necessary if the superview is
          // rotated.
          f = [self.superview convertRect:f fromView:self.window];
          if (CGRectEqualToRect(f, keyboard_frame_)) {
            // On iOS 7, we can receive a keyboard will show notification when
            // the keyboard is already visible. Be conscious of this situation.
            return;
          }
          keyboard_frame_ = f;

          const double duration =
              d.find_value(UIKeyboardAnimationDurationUserInfoKey).double_value();
          const int curve =
              d.find_value(UIKeyboardAnimationCurveUserInfoKey).int_value();
          const int options =
              (curve << 16) | UIViewAnimationOptionBeginFromCurrentState;
          [UIView animateWithDuration:duration
                                delay:0
                              options:options
                           animations:^{
              content_.contentOffset = CGPointMake(0, content_.contentOffsetMaxY);
              [self setSubviewFrames:self.frame];
            }
                           completion:NULL];
        });
  }
  if (!keyboard_will_hide_.get()) {
    keyboard_will_hide_.Init(
        UIKeyboardWillHideNotification,
        ^(NSNotification* n) {
          // Re-enable the parent scroll views.
          content_.scrollEnabled = YES;

          keyboard_frame_ = CGRectZero;

          const Dict d(n.userInfo);
          const double duration =
              d.find_value(UIKeyboardAnimationDurationUserInfoKey).double_value();
          const int curve =
              d.find_value(UIKeyboardAnimationCurveUserInfoKey).int_value();
          const int options =
              (curve << 16) | UIViewAnimationOptionBeginFromCurrentState;
          [UIView animateWithDuration:duration
                                delay:0
                              options:options
                           animations:^{
              [self setSubviewFrames:self.frame];
            }
                           completion:^(BOOL finished) {
              [self refreshNotices:true];
            }];
        });
  }
}

- (void)setBackgroundImage {
  const int64_t photo_id = state_->db()->Get<int64_t>(kDashboardBackgroundPhotoIdKey, 0);
  if (state_->is_registered() && photo_id != 0 &&
      (!background_ || photo_id != background_.photoId)) {
    PhotoHandle ph = state_->photo_table()->LoadPhoto(photo_id, state_->db());
    if (ph.get()) {
      EpisodeHandle eh = state_->episode_table()->GetEpisodeForPhoto(ph, state_->db());
      if (eh.get()) {
        background_.photoId = ph->id().local_id();
        background_.episodeId = eh->id().local_id();
        background_.aspectRatio = ph->aspect_ratio();
        background_.position = CGPointMake(0.5, 0.5);
        background_.image = NULL;

        // TODO(peter): Make the usage of PhotoLoader simpler in this case. There
        // should be no need to create a PhotoQueue and make multiple calls to
        // PhotoLoader. Just one call with a PhotoView as an argument.

        {
          // Load thumbnail immediately.
          MutexLock l(state_->photo_loader()->mutex());
          state_->photo_loader()->LoadThumbnailLocked(background_);
          state_->photo_loader()->WaitThumbnailsLocked(L(background_), 0.1);
        }

        // Dispatch loading of high-resolution photo.
        state_->photo_loader()->LoadPhotos(&photo_queue_);
        return;
      }
    }
  }

  UIImage* bg_image = state_->is_registered() ? kDashboardDefault : kTourBackground;
  if (background_.image != bg_image) {
    background_.photoId = 0;
    background_.image = bg_image;
    // Need to set the aspectRatio correctly in order for the parallax
    // scrolling in the tour to work correctly.
    background_.aspectRatio = bg_image.size.width / bg_image.size.height;
  }

  if (state_->is_registered()) {
    // After registration, position the background at the bottom of the default
    // background image.
    background_.position = CGPointMake(0.5, 1);
  }
}

- (void)handleSingleTap:(UITapGestureRecognizer*)recognizer {
  if (recognizer.state != UIGestureRecognizerStateEnded ||
      IsIgnoringInteractionEvents() ||
      background_.photoId == 0) {
    return;
  }
  ControllerState new_controller_state =
      [state_->root_view_controller() photoLayoutController].controllerState;
  CurrentPhotos* cp = &new_controller_state.current_photos;
  cp->prev_callback = NULL;
  cp->next_callback = NULL;
  cp->refresh_callback = NULL;
  cp->photo_ids.clear();
  cp->photo_ids.push_back(std::make_pair(background_.photoId, background_.episodeId));
  new_controller_state.current_photo = background_;

  [state_->root_view_controller() showPhoto:ControllerTransition(new_controller_state)];
}

- (void)editBackgroundPhoto {
  photo_picker_ = [[PhotoPickerView alloc] initWithState:state_
                                    singlePhotoSelection:true];
  photo_picker_.env = self;
  photo_picker_.frame = CGRectMake(
      0, state_->status_bar_height(), self.boundsWidth,
      self.boundsHeight - state_->status_bar_height());
  [photo_picker_ show];
}

- (void)photoPickerAddPhotos:(PhotoSelectionVec)photo_ids {
  DCHECK_EQ(photo_ids.size(), 1);
  state_->db()->Put<int64_t>(kDashboardBackgroundPhotoIdKey, photo_ids[0].photo_id);
  [self setBackgroundImage];
  [self photoPickerExit];
}

- (void)photoPickerExit {
  [photo_picker_ hide:true];
  photo_picker_ = NULL;
}

- (void)maybeShowMaintenanceCard {
  if (maintenance_card_) {
    return;
  }

  maintenance_card_ = [[MaintenanceDashboardCard alloc] initWithState:state_];
  maintenance_card_.alpha = 0;
  [content_ addSubview:maintenance_card_];
  [env_ dashboardMaintenanceBegin];
  content_.bounces = NO;
  content_.pagingEnabled = NO;

  const float duration = (login_signup_card_ || default_card_) ? 0.3 : 0.0;
  [UIView animateWithDuration:duration
                   animations:^{
      maintenance_card_.alpha = 1;
      login_signup_card_.alpha = 0;
      tour_.alpha = 0;
      account_setup_card_.alpha = 0;
      default_card_.alpha = 0;
      [self setNoticeAlpha:0];
    }
                   completion:^(BOOL finished) {
      [self removeLoginSignupCard];
      [self removeAccountSetupCard];
      [self removeDefaultCard];
    }];
}

- (void)showAquariumCard {
  [self maybeShowMaintenanceCard];
  const string settings_detail = (kIOSVersion < "6.0") ?
      "Settings > Location Services > Viewfinder" :
      "Settings > Privacy > Photos > Viewfinder";
  const string body = "\nTo use the Viewfinder mobile app,\nyou must grant "
      "access to your photos.\nEnable access via:\n\n" +
      settings_detail;
  [maintenance_card_ setMessage:"Photo Access Required" body:body];
  maintenance_card_.showActivity = false;
  [self setSubviewFrames:self.frame];
}

- (void)removeMaintenanceCard {
  const bool maintenance_end = maintenance_card_ != NULL;
  [maintenance_card_ removeFromSuperview];
  maintenance_card_ = NULL;
  if (maintenance_end) {
    [env_ dashboardMaintenanceEnd];
  }
}

- (void)maybeShowAccountSetupCard {
  if (account_setup_card_) {
    return;
  }

  account_setup_card_ = [[AccountSetupDashboardCard alloc] initWithState:state_];
  account_setup_card_.alpha = 0;
  [content_ addSubview:account_setup_card_];
  content_.bounces = NO;
  content_.pagingEnabled = NO;

  state_->analytics()->OnboardingAccountSetupCard();
  [UIView animateWithDuration:0.3
                   animations:^{
      account_setup_card_.alpha = 1;
      maintenance_card_.alpha = 0;
      default_card_.alpha = 0;
      login_signup_card_.alpha = 0;
      tour_.alpha = 0;
      [self setNoticeAlpha:0];
    }
                   completion:^(BOOL finished) {
      [self removeDefaultCard];
      [self removeMaintenanceCard];
      [self removeLoginSignupCard];
      [state_->root_view_controller() showDashboard:ControllerTransition()];
    }];
}

- (void)showAccountSetupCard {
  [self maybeShowAccountSetupCard];
  [self setSubviewFrames:self.frame];
}

- (void)removeAccountSetupCard {
  [account_setup_card_ removeFromSuperview];
  account_setup_card_ = NULL;
}

- (void)showLoginSignupCard:(const string&)key {
  if (login_signup_card_) {
    [login_signup_card_ removeFromSuperview];
  }
  login_signup_card_ = [[LoginSignupDashboardCard alloc]
                         initWithState:state_
                            withParent:content_
                               withKey:key];
  login_signup_card_.alpha = 0;
  [content_ addSubview:login_signup_card_];
  [self setSubviewFrames:self.frame];

  content_.bounces = NO;
  content_.pagingEnabled = YES;

  const float duration = (default_card_ || maintenance_card_) ? 0.3 : 0.0;
  [UIView animateWithDuration:duration
                   animations:^{
      login_signup_card_.alpha = 1;
      tour_.alpha = 1;
      account_setup_card_.alpha = 0;
      maintenance_card_.alpha = 0;
      default_card_.alpha = 0;
      [self setNoticeAlpha:0];
    }
                   completion:^(BOOL finished) {
      [self removeAccountSetupCard];
      [self removeMaintenanceCard];
      [self removeDefaultCard];
      [self refreshNotices:false];
      [state_->root_view_controller() showDashboard:ControllerTransition()];
    }];
}

- (void)removeLoginSignupCard {
  [login_signup_card_ removeFromSuperview];
  login_signup_card_ = NULL;
  [tour_ removeFromSuperview];
  tour_ = NULL;
}

- (bool)maybeShowDefaultCard {
  switch (state_->view_state()) {
    case STATE_NOT_REGISTERED:
    case STATE_RESET_DEVICE_ID:
    case STATE_PHOTO_NOT_AUTHORIZED:
    case STATE_ACCOUNT_SETUP:
      return false;
    default:
      break;
  }
  if (default_card_) {
    return false;
  }

  default_card_ = [[DefaultDashboardCard alloc] initWithState:state_];
  default_card_.alpha = 0;
  [default_card_ rebuild];
  [content_ addSubview:default_card_];
  [self refreshNotices:false];
  [self setNoticeAlpha:0];
  content_.bounces = YES;
  content_.pagingEnabled = NO;

  single_tap_recognizer_ =
      [[UITapGestureRecognizer alloc]
          initWithTarget:self action:@selector(handleSingleTap:)];
  single_tap_recognizer_.cancelsTouchesInView = NO;
  single_tap_recognizer_.delegate = self;
  single_tap_recognizer_.numberOfTapsRequired = 1;
  [self addGestureRecognizer:single_tap_recognizer_];

  const float duration = (login_signup_card_ || maintenance_card_) ? 0.3 : 0.0;
  [UIView animateWithDuration:duration
                   animations:^{
      default_card_.alpha = 1;
      login_signup_card_.alpha = 0;
      tour_.alpha = 0;
      account_setup_card_.alpha = 0;
      maintenance_card_.alpha = 0;
      [self setNoticeAlpha:1];
    }
                   completion:^(BOOL finished) {
      [self removeLoginSignupCard];
      [self removeAccountSetupCard];
      [self removeMaintenanceCard];
      [state_->root_view_controller() showSummaryLayout:ControllerTransition()];
    }];

  return true;
}

- (void)removeDefaultCard {
  [default_card_ removeFromSuperview];
  default_card_ = NULL;
}

- (void)startInit {
  // The default card will only be present if the device is unlinked or "fake
  // logout" is performed.
  [self removeMaintenanceCard];
  [self removeLoginSignupCard];
  [self removeAccountSetupCard];
  [self removeDefaultCard];

  [self refreshNotices:false];
  [state_->root_view_controller() showSummaryLayout:ControllerTransition()];

  __block int progress_id =
      state_->maintenance_progress()->Add(^(const string msg) {
          dispatch_main(^{
              [self updateMaintenanceProgress:msg];
            });
        });
  __block int done_id =
      state_->maintenance_done()->Add(^(bool reset) {
          dispatch_main(^{
              if (!state_->assets_manager().initialScan) {
                // If this isn't the initial asset scan, resume event refreshes
                // immediately. Note that all refreshes are still blocked until
                // ResumeAllRefreshes() is called below. If this is the initial
                // asset scan, event refreshes will be resumed when the scan is
                // complete.
                state_->day_table()->ResumeEventRefreshes();
              }
              if (reset) {
                // The day table was reset. Resume day table refreshes but wait
                // for the first set of refreshes to complete before finishing
                // initialization.
                [self updateMaintenanceProgress:"Optimizing Data for Display"];
                state_->day_table()->ResumeAllRefreshes(^{
                    dispatch_after_main(0, ^{
                        [self maybeRegister];
                      });
                  });
              } else {
                state_->day_table()->ResumeAllRefreshes();
                // Signal the SummaryLayoutController to rebuild state in case
                // there were no day table refreshes to perform.
                state_->day_table()->update()->Run();
                [self maybeRegister];
              }

              state_->maintenance_done()->Remove(done_id);
              state_->maintenance_progress()->Remove(progress_id);
            });
        });
}

- (void)maybeRegister {
  // Watch for a transition in the registration status.
  __block int settings_changed_id =
      state_->settings_changed()->Add(^(bool downloaded) {
          LOG("settings changed");
          DCHECK(dispatch_is_main_thread());
          if (state_->is_registered()) {
            if (login_signup_card_ &&
                !login_signup_card_.changingPassword &&
                !default_card_) {
              [self finishInit];
              [state_->root_view_controller() showInbox:ControllerState()];
            } else if (default_card_) {
              [self refreshNotices:true];
            }
          } else if (!login_signup_card_ && !maintenance_card_) {
            // Only restart the init process if we're not currently showing the
            // login/signup card.
            registered_ = false;
            background_.image = NULL;
            [self setBackgroundImage];
            state_->settings_changed()->Remove(settings_changed_id);
            [self startInit];
          }
        });

  maintenance_done_ = true;
  if (state_->is_registered()) {
    [self finishInit];
    return;
  }

  const float tour_page_height = self.boundsHeight;

  tour_ = [UIView new];
  tour_.frame = self.bounds;
  tour_.frameHeight = ARRAYSIZE(tour_page_) * tour_page_height;
  [content_ addSubview:tour_];

  for (int i = 0; i < ARRAYSIZE(tour_page_); ++i) {
    tour_page_[i] = NewTourPage(
        i, self.boundsWidth, tour_page_height,
        self, @selector(tourButtonTapped:), @selector(tourSkipButtonTapped:));
    tour_page_[i].frameTop = i * tour_page_height;
    [tour_ addSubview:tour_page_[i]];
  }

  [self scrollViewDidScroll:content_];

  state_->analytics()->OnboardingStart();
  [LoginSignupDashboardCard
      prepareForLoginSignup:state_
                     forKey:kLoginEntryDetailsKey];
  [self showLoginSignupCard:kLoginEntryDetailsKey];
}

- (void)finishInit {
  DCHECK(state_->is_registered());

  content_.pagingEnabled = YES;
  [self setBackgroundImage];

  if (!registered_) {
    registered_ = true;

    // Only initiate the scan if we already have assets authorization.
    if (state_->assets_manager().authorized) {
      // No need to show the library pending screen if the user has already
      // authorized photo access.
      [state_->assets_manager() scan];
    }
  }

  if (state_->NeedDeviceIdReset()) {
    [LoginSignupDashboardCard
      prepareForResetDeviceId:state_
                       forKey:kLoginEntryDetailsKey];
    [self showLoginSignupCard:kLoginEntryDetailsKey];
  } else {
    [self maybeShowDefaultCard];
  }
}

- (void)updateMaintenanceProgress:(const string&)message {
  [self maybeShowMaintenanceCard];
  [maintenance_card_
    setMessage:message
          body:"This may take several minutes.\nPlease be patient."];
  maintenance_card_.showActivity = true;
  [self setSubviewFrames:self.frame];
}

- (void)tappedNotice:(DashboardNoticeType)type {
  state_->analytics()->DashboardNoticeClick(type);
  switch (type) {
    default:
      break;
  }
}

- (void)toggledNotice:(DashboardNoticeType)type {
  DashboardNotice* n = FindOrNull(notices_, type);
  if (!n.expanded) {
    state_->analytics()->DashboardNoticeExpand(type);
    // If the notice is being expanded, collapse any other expanded
    // notices.
    for (DashboardNoticeMap::iterator iter(notices_.begin());
         iter != notices_.end();
         ++iter) {
      iter->second.expanded = false;
    }
  }
  n.expanded = !n.expanded;
  [UIView animateWithDuration:0.3
                   animations:^{
      [self setSubviewFrames:self.frame];
    }];
}

- (void)setNoticeAlpha:(float)alpha {
  for (DashboardNoticeMap::iterator iter(notices_.begin());
         iter != notices_.end();
         ++iter) {
    iter->second.alpha = alpha;
  }
}

- (void)refreshNotices:(bool)animated {
  CHECK(dispatch_is_main_thread());
  if (!default_card_) {
    // Notices are only shown when the default dashboard card is present.
    for (DashboardNoticeMap::iterator iter(notices_.begin());
         iter != notices_.end();
         ++iter) {
      [iter->second removeFromSuperview];
    }
    notices_.clear();
    return;
  }
  for (int i = 0; i < DASHBOARD_NOTICE_COUNT; ++i) {
    const DashboardNoticeType type = static_cast<DashboardNoticeType>(i);
    DashboardNotice* n = FindOrNull(notices_, type);
    const string needed_identifier = DashboardNoticeNeededIdentifier(state_, type);
    if (!needed_identifier.empty()) {
      if (!n || n.identifier != needed_identifier) {
        if (n) {
          // We're replacing an existing notice. Make sure we remove it.
          [n removeFromSuperview];
        }
        n = NewDashboardNotice(state_, type, needed_identifier, self.boundsWidth);
        __weak Dashboard* weak_self = self;
        n.tapped = ^{
          [weak_self tappedNotice:type];
        };
        n.toggled = ^{
          [weak_self toggledNotice:type];
        };
        n.updated = ^{
          [weak_self refreshNotices:true];
        };
        notices_[n.type] = n;
      }
    } else if (n) {
      n.removed = true;
    }
  }
  // Initialize the positions of new notices.
  float pos = default_card_.presentationFrameTop;
  for (DashboardNoticeMap::iterator iter(notices_.begin());
       iter != notices_.end();
       ++iter) {
    DashboardNotice* notice = iter->second;
    if (!notice.superview) {
      notice.frameTop = pos;
      [content_ addSubview:notice];
    }
    pos = notice.presentationFrameTop;
  }

  [UIView animateWithDuration:animated ? 0.3 : 0.0
                   animations:^{
      [self setSubviewFrames:self.frame];
    }
                   completion:^(BOOL finished) {
      // Delete any removed notices.
      for (DashboardNoticeMap::iterator iter(notices_.begin());
           iter != notices_.end();) {
        DashboardNotice* notice = iter->second;
        DashboardNoticeMap::iterator cur(iter++);
        if (!notice.removed) {
          continue;
        }

        [notice removeFromSuperview];
        notices_.erase(cur);
      }
    }];
}

- (void)setSubviewFrames:(CGRect)f {
  content_.frameTop =
      self.keyboardVisible ? state_->status_bar_height() : 0;
  content_.frameHeight =
      (self.keyboardVisible ? keyboard_frame_.origin.y : f.size.height) -
      content_.frameTop;
  if (tour_) {
    content_.contentSize = tour_.bounds.size;
  } else {
    // TODO(peter): Set content height to max of bounds height and the height of
    // the content (card + notices).
    content_.contentSize = content_.bounds.size;
  }

  const float card_width = content_.boundsWidth - kSpacing * 2;
  DashboardCard* cards[] = { account_setup_card_, default_card_, login_signup_card_, maintenance_card_ };
  for (int i = 0; i < ARRAYSIZE(cards); ++i) {
    if (!cards[i]) {
      continue;
    }
    cards[i].keyboardVisible = self.keyboardVisible;
    cards[i].frameWidth = card_width;
  }

  if (tour_) {
    const bool hide_tour = state_->is_registered() || self.keyboardVisible;
    tour_.alpha = hide_tour ? 0 : 1;
  }

  {
    // Stack the notices.
    float pos = default_card_.frameTop;
    for (DashboardNoticeMap::iterator iter(notices_.begin());
         iter != notices_.end();
         ++iter) {
      DashboardNotice* notice = iter->second;
      const float height = notice.desiredHeight;
      CGRect f = notice.frame;
      f.origin.y = pos - height;
      f.size.height = height;
      notice.frame = f;
      pos = notice.frameTop;
      if (notice.removed) {
        notice.alpha = 0;
      }
    }
  }
}

- (void)setFrame:(CGRect)f {
  if (CGRectEqualToRect(self.frame, f)) {
    return;
  }
  [super setFrame:f];
  if (background_) {
    background_.frame = self.bounds;
    if (!background_.image) {
      [self setBackgroundImage];
    }
  }
  [self setSubviewFrames:f];
}

- (void)rebuild {
  switch (state_->view_state()) {
    case STATE_PHOTO_NOT_AUTHORIZED:
      [self showAquariumCard];
      break;
    case STATE_ACCOUNT_SETUP:
      if (maintenance_done_) {
        [self showAccountSetupCard];
      }
      break;
    case STATE_OK:
      if (maintenance_done_) {
        // Only show the default card if the login/signup card is not currently
        // present. The login signup card may still be present if the user
        // requested to reset their password.
        if (!login_signup_card_ && ![self maybeShowDefaultCard]) {
          [default_card_ rebuild];
        }
        [self refreshNotices:true];
      }
      break;
    default:
      break;
  }
  bg_edit_.hidden = (state_->view_state() == STATE_OK && maintenance_done_) ? NO : YES;
}

- (void)resetBackground {
  state_->db()->Delete(kDashboardBackgroundPhotoIdKey);
  background_.photoId = 0;
  background_.image = kTourBackground;
}

- (void)tourButtonTapped:(UIButton*)source {
  const float y = (source.tag + 1) * content_.boundsHeight;
  [content_ setContentOffset:CGPointMake(0, y)
                    animated:YES];
}

- (void)tourSkipButtonTapped:(UIButton*)source {
  [login_signup_card_ showLogin:source];
}

- (void)scrollViewDidScroll:(UIScrollView*)scroll_view {
  if (tour_) {
    // TODO(peter): Per Dan's suggestion, on 4" displays adjust the position so
    // that the first 44 pixels are offscreen when we're at scroll-offset-y==0.
    background_.position = CGPointMake(
        0.5, scroll_view.contentOffset.y /
        std::max<float>(1, scroll_view.contentOffsetMaxY));

    const float page = std::max<float>(
        0, std::min<float>(ARRAYSIZE(tour_page_) - 1,
                           scroll_view.contentOffset.y / scroll_view.boundsHeight));
    for (int i = 0; i < ARRAYSIZE(tour_page_); ++i) {
      const float dist = 2 * fabs(i - page);
      tour_page_[i].alpha = 1.0 - dist;
    }
  }
}

- (BOOL)gestureRecognizerShouldBegin:(UIGestureRecognizer*)recognizer {
  if (photo_picker_) {
    return NO;
  }
  return [self hitTest:[recognizer locationInView:self] withEvent:NULL] == content_;
}

- (BOOL)gestureRecognizer:(UIGestureRecognizer*)recognizer
       shouldReceiveTouch:(UITouch*)touch {
  return YES;
}

- (bool)keyboardVisible {
  return (keyboard_frame_.origin.y > 0);
}

- (int)noticeCount {
  // Only count non-removed notices.
  int count = 0;
  for (DashboardNoticeMap::iterator iter(notices_.begin());
       iter != notices_.end();
       ++iter) {
    if (!iter->second.removed &&
        iter->second.type == DASHBOARD_NOTICE_NEW_USERS) {
      ++count;
    }
  }
  return count;
}

@end  // Dashboard

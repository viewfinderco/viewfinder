// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import <UIKit/UIKit.h>
#import <unordered_set>
#import "Callback.h"
#import "CppDelegate.h"
#import "DBFormat.h"
#import "EpisodeTable.h"
#import "PhotoUtils.h"
#import "UIAppState.h"
#import "WallTime.h"

namespace {

const WallTime kClawbackGracePeriod = 7 * 24 * 60 * 60;  // 1 week

const string kStarTutorialShownKey = DBFormat::metadata_key("star_tutorial_shown");

}  // namespace

bool FilterUnshareSelection(
    UIAppState* state, PhotoSelectionSet* selection,
    FilterCallback filter_callback, DBHandle snapshot) {
  typedef std::unordered_set<int64_t> EpisodeIdSet;

  // Gather up a list of all the episodes being unshared from.
  EpisodeIdSet episode_ids;
  for (PhotoSelectionSet::iterator iter(selection->begin());
       iter != selection->end();
       ++iter) {
    episode_ids.insert(iter->episode_id);
  }

  // For each episode being unshared from, check to see if the user has
  // permission to perform the unshare.
  const WallTime now = WallTime_Now();
  EpisodeIdSet invalid_user_episode_ids;
  EpisodeIdSet too_old_episode_ids;

  for (EpisodeIdSet::iterator iter(episode_ids.begin());
       iter != episode_ids.end();
       ++iter) {
    const EpisodeHandle eh = state->episode_table()->LoadEpisode(*iter, snapshot);
    if (!eh.get()) {
      // Huh? This should be impossible.
      continue;
    }

    const WallTime publish_timestamp =
        eh->has_publish_timestamp() ? eh->publish_timestamp() : eh->timestamp();
    if (eh->user_id() != state->user_id()) {
      invalid_user_episode_ids.insert(*iter);
    } else if (now - publish_timestamp >= kClawbackGracePeriod) {
      too_old_episode_ids.insert(*iter);
    } else {
      // Episode is ok to unshare from.
      continue;
    }
  }

  if (invalid_user_episode_ids.empty() &&
      too_old_episode_ids.empty()) {
    return false;
  }

  struct {
    EpisodeIdSet* episode_ids;
    NSString* title;
    NSString* reason;
    NSString* cancel;
  } alerts[] = {
    { &invalid_user_episode_ids,
      @"Unshare Failed",
      @"About that…you can't unshare a photo you didn't share. Just not possible.",
      @"OK" },
    { &too_old_episode_ids,
      @"Unshare Failed",
      @"Photos can only be unshared within 7 days of sharing.",
      @"OK" },
  };

  // Deselect photos from episodes we don't own first, then deselect photos
  // from episodes which are too old.
  for (int i = 0; i < ARRAYSIZE(alerts); ++i) {
    if (alerts[i].episode_ids->empty()) {
      continue;
    }
    const EpisodeIdSet filtered_episode_ids(*alerts[i].episode_ids);

    CppDelegate* cpp_delegate = new CppDelegate;
    cpp_delegate->Add(
        @protocol(UIAlertViewDelegate), @selector(alertView:clickedButtonAtIndex:),
        ^(UIAlertView* alert, NSInteger index) {
          for (PhotoSelectionSet::iterator iter = selection->begin();
               iter != selection->end(); ) {
            const PhotoSelection key = *iter++;
            if (ContainsKey(filtered_episode_ids, key.episode_id)) {
              selection->erase(key);
            }
          }
          if (filter_callback) {
            filter_callback();
          }
          alert.delegate = NULL;
          delete cpp_delegate;
          // Recursively call this method to handle other filtering cases.
          FilterUnshareSelection(state, selection, filter_callback, snapshot);
        });
    [[[UIAlertView alloc] initWithTitle:alerts[i].title
                                message:alerts[i].reason
                               delegate:cpp_delegate->delegate()
                      cancelButtonTitle:alerts[i].cancel
                      otherButtonTitles:NULL] show];
    break;
  }

  return true;
}

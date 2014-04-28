// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import "AppState.h"
#import "DayTable.h"
#import "DBStats.h"
#import "ViewpointTable.h"

DBStats::DBStats(AppState* state)
    : state_(state) {
}

void DBStats::ComputeStats() {
  ComputeViewpointStats();
  ComputeEventStats();
}

void DBStats::ComputeViewpointStats() {
  int vp_count = 0;
  int unique_count = 0;
  std::unordered_set<string> unique_sets;
  std::map<int, int> histogram;

  for (DB::PrefixIterator iter(state_->db(), DBFormat::viewpoint_key());
       iter.Valid();
       iter.Next()) {
    const int64_t vp_id = state_->viewpoint_table()->DecodeContentKey(iter.key());
    ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(vp_id, state_->db());
    vector<int64_t> follower_ids;
    vh->ListFollowers(&follower_ids);
    std::sort(follower_ids.begin(), follower_ids.end());
    string vec_str = ToString(follower_ids);
    if (!follower_ids.empty() && !ContainsKey(unique_sets, vec_str)) {
      unique_sets.insert(vec_str);
      unique_count++;
      histogram[follower_ids.size()]++;
    }
    vp_count++;
  }

  LOG("%d unique sets of followers from %d viewpoints", unique_sets.size(), vp_count);
  LOG("VIEWPOINT UNIQUE USER COUNTS:");
  int cumulative_count = 0;
  for (std::map<int, int>::iterator iter = histogram.begin();
       iter != histogram.end();
       ++iter) {
    cumulative_count += iter->second;
    LOG("%d followers: %d\t%0.2f%%ile", iter->first, iter->second,
        float(cumulative_count * 100) / unique_count);
  }
}

void DBStats::ComputeEventStats() {
  int ev_count = 0;
  int ep_count = 0;
  int ph_count = 0;
  int tr_count = 0;
  std::map<int, int> event_photo_hist;
  std::map<int, int> event_episode_hist;
  std::map<int, int> event_trapdoor_hist;
  std::map<int, int> episode_photo_hist;

  for (DB::PrefixIterator iter(state_->db(), DBFormat::day_event_key(""));
       iter.Valid();
       iter.Next()) {
    const Slice value = iter.value();
    EventMetadata em;
    if (em.ParseFromArray(value.data(), value.size())) {
      if (em.episodes_size() > 0) {
        int ev_ph_count = 0;
        int ev_ep_count = 0;
        for (int i = 0; i < em.episodes_size(); ++i) {
          const FilteredEpisode& fe = em.episodes(i);
          // Lots of derivative episodes which are filtered out because
          // they're completely redundant.
          if (fe.photo_ids_size() == 0) {
            continue;
          }
          ph_count += fe.photo_ids_size();
          ev_ph_count += fe.photo_ids_size();
          ep_count++;
          ev_ep_count++;
          episode_photo_hist[fe.photo_ids_size()]++;
        }
        ev_count++;
        event_photo_hist[ev_ph_count]++;
        event_episode_hist[em.episodes_size()]++;

        // Trapdoors.
        event_trapdoor_hist[em.trapdoors_size()]++;
        tr_count += em.trapdoors_size();
      }
    }
  }

  LOG("%d events, %d episodes, %d photos, %d trapdoors",
      ev_count, ep_count, ph_count, tr_count);

  if (!episode_photo_hist.empty()) {
    LOG("EPISODE PHOTO COUNTS:");
    int cumulative_count = 0;
    for (std::map<int, int>::iterator iter = episode_photo_hist.begin();
         iter != episode_photo_hist.end();
         ++iter) {
      cumulative_count += iter->second;
      LOG("%d photos: %d\t%0.2f%%ile", iter->first, iter->second,
          float(cumulative_count * 100) / ep_count);
    }
  }

  if (!event_episode_hist.empty()) {
    LOG("EVENT EPISODE COUNTS:");
    int cumulative_count = 0;
    for (std::map<int, int>::iterator iter = event_episode_hist.begin();
         iter != event_episode_hist.end();
         ++iter) {
      cumulative_count += iter->second;
      LOG("%d episodes: %d\t%0.2f%%ile", iter->first, iter->second,
          float(cumulative_count * 100) / ev_count);
    }
  }

  if (!event_photo_hist.empty()) {
    LOG("EVENT PHOTO COUNTS:");
    int cumulative_count = 0;
    for (std::map<int, int>::iterator iter = event_photo_hist.begin();
         iter != event_photo_hist.end();
         ++iter) {
      cumulative_count += iter->second;
      LOG("%d photos: %d\t%0.2f%%ile", iter->first, iter->second,
          float(cumulative_count * 100) / ev_count);
    }
  }

  if (!event_trapdoor_hist.empty()) {
    LOG("EVENT TRAPDOOR COUNTS:");
    int cumulative_count = 0;
    for (std::map<int, int>::iterator iter = event_trapdoor_hist.begin();
         iter != event_trapdoor_hist.end();
         ++iter) {
      cumulative_count += iter->second;
      LOG("%d trapdoors: %d\t%0.2f%%ile", iter->first, iter->second,
          float(cumulative_count * 100) / ev_count);
    }
  }

  int cumulative_count = 0;
  float last = 0;
  for (int i = 0; i < 20; ++i) {
    if (ContainsKey(event_trapdoor_hist, i)) {
      cumulative_count += event_trapdoor_hist[i];
      LOG("%0.2f", float(cumulative_count * 100) / ev_count);
      last = float(cumulative_count * 100) / ev_count;
    } else {
      LOG("%0.2f", last);
    }
  }
}

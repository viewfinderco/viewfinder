// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell.

#import "AppState.h"
#import "CommentTable.h"
#import "ContactManager.h"
#import "DayMetadata.pb.h"
#import "EpisodeTable.h"
#import "FullTextIndex.h"
#import "SearchUtils.h"
#import "Timer.h"
#import "ViewpointTable.h"

template void PopulateEventSearchResults<>(AppState* state, const DayTable::EventSummaryHandle& events,
                                vector<SummaryRow>* results, const Slice& query, std::map<int, int>* row_map);
template void PopulateEventSearchResults<>(AppState* state, const DayTable::FullEventSummaryHandle& events,
                                           vector<SummaryRow>* results, const Slice& query, std::map<int, int>* row_map);

namespace {

template<typename SummaryType>
void AddEventRow(const SummaryType& events, int row_index,
                 vector<SummaryRow>* results, std::set<int>* row_indexes) {
  if (row_index < 0 || ContainsKey(*row_indexes, row_index)) {
    return;
  }
  row_indexes->insert(row_index);

  SummaryRow row;
  events->GetSummaryRow(row_index, &row);
  row.set_original_row_index(row_index);
  results->push_back(row);
}

template<typename SummaryType>
void AddEpisodeToResults(AppState* state, const SummaryType& events,
                           int64_t ep_id, vector<SummaryRow>* results, std::set<int>* row_indexes);

// For EventSummaryHandle and FullEventSummaryHandle
template<typename SummaryType>
void AddEpisodeToResults(AppState* state, const SummaryType& events,
                         int64_t ep_id, vector<SummaryRow>* results, std::set<int>* row_indexes) {
  EpisodeHandle eh(state->episode_table()->LoadEpisode(ep_id, state->db()));
  if (!eh.get()) {
    return;
  }
  if (eh->InLibrary()) {
    // If it's a library episode, add its event to the results.
    const int row_index = events->GetEpisodeRowIndex(ep_id);
    AddEventRow(events, row_index, results, row_indexes);
  } else {
    // If it's a conversation episode, see if it has any child episodes in the library (i.e. if it is starred).
    vector<int64_t> children;
    state->episode_table()->ListEpisodesByParentId(eh->id().local_id(), &children, state->db());
    for (int j = 0; j < children.size(); j++) {
      EpisodeHandle child(state->episode_table()->LoadEpisode(children[j], state->db()));
      if (!child.get() || !child->InLibrary() || child->CountPhotos() == 0) {
        // TODO(ben): if these checks fail, GetEpisodeRowIndex will fail (and log a warning).
        // Is it faster to do these checks or just fall through and let GetEpisodeRowIndex fail?
        continue;
      }
      const int row_index = events->GetEpisodeRowIndex(children[j]);
      AddEventRow(events, row_index, results, row_indexes);
    }
  }
}

void AddViewpointToResults(const DayTable::ConversationSummaryHandle& conversations, int64_t vp_id,
                           vector<SummaryRow>* results, std::set<int64_t>* viewpoint_ids) {
  if (ContainsKey(*viewpoint_ids, vp_id)) {
    return;
  }
  viewpoint_ids->insert(vp_id);

  const int row_index = conversations->GetViewpointRowIndex(vp_id);
  if (row_index < 0) {
    return;
  }

  SummaryRow row;
  conversations->GetSummaryRow(row_index, &row);
  row.set_original_row_index(row_index);
  results->push_back(row);
}

}  // namespace

void PopulateEventAutocomplete(AppState* state, SummaryAutocompleteResults* results, const Slice& query) {
  if (query.empty()) {
    return;
  }

  // First get the regular autocomplete results.
  FullTextIndex::SuggestionResults sugg_results;
  state->episode_table()->episode_index()->GetSuggestions(state->db(), query, &sugg_results);
  state->viewpoint_table()->viewpoint_index()->GetSuggestions(state->db(), query, &sugg_results);
  for (int i = 0; i < sugg_results.size(); i++) {
    results->Add(SummaryTokenInfo(
                     SummaryTokenInfo::TEXT,
                     sugg_results[i].second, sugg_results[i].second),
                 sugg_results[i].first);
  }

  sugg_results.clear();
  state->episode_table()->location_index()->GetSuggestions(state->db(), query, &sugg_results);
  for (int i = 0; i < sugg_results.size(); i++) {
    results->Add(SummaryTokenInfo(
                     SummaryTokenInfo::LOCATION,
                     sugg_results[i].second, sugg_results[i].second),
                 sugg_results[i].first);
  }

  vector<ContactManager::AutocompleteUserInfo> users;
  state->contact_manager()->GetAutocompleteUsers(query, state->episode_table()->episode_index(), &users);
  for (auto u : users) {
    results->Add(SummaryTokenInfo(SummaryTokenInfo::CONTACT,
                                  u.name,
                                  ContactManager::FormatUserToken(u.user_id)),
                 u.score);
    // TODO(ben): SEARCH: get raw terms
  }

  ScopedPtr<FullTextQuery> parsed_query(FullTextQuery::Parse(query, FullTextQuery::PREFIX_MATCH));
  StringSet all_terms;
  FullTextQueryTermExtractor extractor(&all_terms);
  extractor.VisitNode(*parsed_query);
  results->reset_filter_re(FullTextIndex::BuildFilterRE(all_terms));
}

void PopulateConversationAutocomplete(AppState* state, SummaryAutocompleteResults* results, const Slice& query) {
  if (query.empty()) {
    return;
  }
  StringSet all_terms;

  ScopedPtr<FullTextQuery> parsed_query(FullTextQuery::Parse(query, FullTextQuery::PREFIX_MATCH));
  ViewpointTable::ViewpointSearchResults viewpoint_results;
  StringSet seen_titles;
  for (ScopedPtr<FullTextResultIterator> iter(
           state->viewpoint_table()->viewpoint_index()->Search(state->db(), *parsed_query));
       iter->Valid();
       iter->Next()) {
    const int64_t vp_id = FastParseInt64(iter->doc_id());
    ViewpointHandle vh(state->viewpoint_table()->LoadViewpoint(vp_id, state->db()));

    if (!vh.get() || ContainsKey(seen_titles, vh->title())) {
      continue;
    }
    seen_titles.insert(vh->title());

    // Our standard autocomplete ranking is by number of matched viewpoints, which would put these
    // single-viewpoint rows at the bottom, so give them an artificial boost.
    const int score = 10;
    results->Add(SummaryTokenInfo(
                     SummaryTokenInfo::CONVERSATION,
                     vh->title(), vh->title()),

                 score);
    iter->GetRawTerms(&all_terms);
  }

  FullTextIndex::SuggestionResults sugg_results;
  state->comment_table()->comment_index()->GetSuggestions(state->db(), query, &sugg_results);
  state->viewpoint_table()->viewpoint_index()->GetSuggestions(state->db(), query, &sugg_results);
  state->episode_table()->episode_index()->GetSuggestions(state->db(), query, &sugg_results);
  for (int i = 0; i < sugg_results.size(); i++) {
    results->Add(SummaryTokenInfo(
                     SummaryTokenInfo::TEXT,
                     sugg_results[i].second, sugg_results[i].second),
                 sugg_results[i].first);
  }

  sugg_results.clear();
  state->episode_table()->location_index()->GetSuggestions(state->db(), query, &sugg_results);
  for (int i = 0; i < sugg_results.size(); i++) {
    results->Add(SummaryTokenInfo(
                     SummaryTokenInfo::LOCATION,
                     sugg_results[i].second, sugg_results[i].second),
                 sugg_results[i].first);
  }

  vector<ContactManager::AutocompleteUserInfo> users;
  state->contact_manager()->GetAutocompleteUsers(query, state->viewpoint_table()->viewpoint_index(), &users);
  for (auto u : users) {
    results->Add(SummaryTokenInfo(SummaryTokenInfo::CONTACT,
                                  u.name,
                                  ContactManager::FormatUserToken(u.user_id)),
                 u.score);
    // TODO(ben): SEARCH: get raw terms
  }

  FullTextQueryTermExtractor extractor(&all_terms);
  extractor.VisitNode(*parsed_query);
  results->reset_filter_re(FullTextIndex::BuildFilterRE(all_terms));
}

template<typename SummaryType>
void PopulateEventSearchResults(AppState* state, const SummaryType& events,
                                vector<SummaryRow>* results, const Slice& s, std::map<int, int>* row_map) {
  WallTimer timer;
  const string query = ToLowercase(s);

  std::set<int> row_indexes;
  EpisodeTable::EpisodeSearchResults episode_results;
  state->episode_table()->Search(query, &episode_results);
  for (int i = 0; i < episode_results.size(); i++) {
    AddEpisodeToResults(state, events, episode_results[i], results, &row_indexes);
  }
  LOG("event summary: searched episodes in %.0f ms", timer.Milliseconds());
  timer.Restart();

  ViewpointTable::ViewpointSearchResults viewpoint_results;
  state->viewpoint_table()->Search(query, &viewpoint_results);
  for (int i = 0; i < viewpoint_results.size(); i++) {
    const int64_t vp_id = viewpoint_results[i];
    vector<int> vp_rows;
    events->GetViewpointRowIndexes(vp_id, &vp_rows);
    for (int j = 0; j < vp_rows.size(); j++) {
      AddEventRow(events, vp_rows[j], results, &row_indexes);
    }
  }
  LOG("event summary: searched viewpoints in %.0f ms", timer.Milliseconds());

  std::sort(results->begin(), results->end(), SummaryRowLessThan());
  int position = 0;
  for (int i = 0; i < results->size(); i++) {
    (*results)[i].set_position(position);
    position += (*results)[i].height();
    if (row_map) {
      (*row_map)[(*results)[i].original_row_index()] = i;
    }
  }
}

void PopulateConversationSearchResults(AppState* state, const DayTable::ConversationSummaryHandle& conversations,
                                       vector<SummaryRow>* results, const Slice& s, RowIndexMap* row_map) {
  WallTimer timer;
  const string query = ToLowercase(s);
  std::set<int64_t> viewpoint_ids;

  ViewpointTable::ViewpointSearchResults viewpoint_results;
  state->viewpoint_table()->Search(query, &viewpoint_results);
  for (int i = 0; i < viewpoint_results.size(); i++) {
    AddViewpointToResults(conversations, viewpoint_results[i], results, &viewpoint_ids);
  }
  LOG("convo summary: searched viewpoints in %.0f ms", timer.Milliseconds());

  CommentTable::CommentSearchResults comment_results;
  state->comment_table()->Search(query, &comment_results);
  for (int i = 0; i < comment_results.size(); i++) {
    const int64_t vp_id = comment_results[i].first;
    AddViewpointToResults(conversations, vp_id, results, &viewpoint_ids);
  }
  LOG("convo summary: searched comments in %.0f ms", timer.Milliseconds());

  EpisodeTable::EpisodeSearchResults episode_results;
  state->episode_table()->Search(query, &episode_results);
  for (int64_t ep_id : episode_results) {
    EpisodeHandle eh = state->episode_table()->LoadEpisode(ep_id, state->db());
    if (eh.get()) {
      AddViewpointToResults(conversations, eh->viewpoint_id().local_id(), results, &viewpoint_ids);
    }
  }

  // Find viewpoints followed by users named in the query.
  // TODO(ben): Do this with query rewriting instead of a separate pass so we can combine
  // user and title terms in one query.  Probably needs OR support in the query processor,
  // and definitely needs user-to-viewpoint mapping in the full-text index instead of a custom index.
  vector<ContactMetadata> contact_results;
  state->contact_manager()->Search(query, &contact_results, NULL,
                                    ContactManager::SORT_BY_NAME | ContactManager::VIEWFINDER_USERS_ONLY);
  for (int i = 0; i < contact_results.size(); i++) {
    vector<int64_t> contact_viewpoints;
    state->viewpoint_table()->ListViewpointsForUserId(contact_results[i].user_id(), &contact_viewpoints,
                                                       state->db());
    for (int j = 0; j < contact_viewpoints.size(); j++) {
      AddViewpointToResults(conversations, contact_viewpoints[j], results, &viewpoint_ids);
    }
  }
  LOG("convo summary: searched viewpoints for %d contacts in %.0fms", contact_results.size(), timer.Milliseconds());
  timer.Restart();

  std::sort(results->begin(), results->end(), SummaryRowLessThan());
  int position = 0;
  for (int i = 0; i < results->size(); i++) {
    (*results)[i].set_position(position);
    position += (*results)[i].height();
    if (row_map) {
      (*row_map)[(*results)[i].original_row_index()] = i;
    }
  }
}

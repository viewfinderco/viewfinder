// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell.

#import <map>
#import <re2/re2.h>
#import "DayTable.h"
#import "ScopedPtr.h"
#import "Utils.h"

class AppState;
class SummaryRow;

// Maps from unfiltered row indexes to filtered indexes.
typedef std::map<int, int> RowIndexMap;

struct SummaryTokenInfo {
 public:
  enum Type {
    TEXT,
    CONTACT,
    CONVERSATION,
    LOCATION,
  };

  SummaryTokenInfo() {
  }

  SummaryTokenInfo(Type type, const Slice& display_term, const Slice& query_term)
      : type(type),
        display_term(display_term.as_string()),
        query_term(query_term.as_string()) {
  }

  bool operator<(const SummaryTokenInfo& other) const;

  Type type;
  string display_term;
  string query_term;
};


class SummaryAutocompleteResults {
 public:
  SummaryAutocompleteResults();
  ~SummaryAutocompleteResults();

  void Add(const SummaryTokenInfo& token, int score);

  void GetSortedResults(vector<pair<int, SummaryTokenInfo> >* tokens);

  void reset_filter_re(RE2* re) { filter_re_.reset(re); }
  RE2* release_filter_re() { return filter_re_.release(); }

 private:
  // This could be an unordered_map if we defined hash and equality functions.
  std::map<SummaryTokenInfo, int> tokens_;
  ScopedPtr<RE2> filter_re_;
};

struct SummaryRowLessThan {
  bool operator()(const SummaryRow& a, const SummaryRow& b) {
    return a.timestamp() > b.timestamp();
  }
};

void PopulateEventAutocomplete(AppState* state, SummaryAutocompleteResults* results, const Slice& query);
void PopulateConversationAutocomplete(AppState* state, SummaryAutocompleteResults* results, const Slice& query);

template<typename SummaryType>
void PopulateEventSearchResults(AppState* state, const SummaryType& events,
                                vector<SummaryRow>* results, const Slice& query, RowIndexMap* row_map);
extern template void PopulateEventSearchResults(AppState* state, const DayTable::EventSummaryHandle& events,
                                vector<SummaryRow>* results, const Slice& query, RowIndexMap* row_map);
extern template void PopulateEventSearchResults(AppState* state, const DayTable::FullEventSummaryHandle& events,
                                vector<SummaryRow>* results, const Slice& query, RowIndexMap* row_map);

void PopulateConversationSearchResults(AppState* state, const DayTable::ConversationSummaryHandle& conversations,
                                       vector<SummaryRow>*results, const Slice& query, RowIndexMap* row_map);

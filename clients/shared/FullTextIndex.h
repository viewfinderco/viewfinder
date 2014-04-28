// Copyright 2013 Viewfinder. All rights Reserved.
// Author: Ben Darnell

#ifndef VIEWFINDER_FULL_TEXT_INDEX_H
#define VIEWFINDER_FULL_TEXT_INDEX_H

#import <google/protobuf/repeated_field.h>
#import <re2/re2.h>
#import "DB.h"
#import "Mutex.h"
#import "STLUtils.h"
#import "Utils.h"

class AppState;
class FullTextIndex;

class FullTextQuery {
 public:
  virtual ~FullTextQuery();

  enum Type {
    TERM,
    AND,
    OR,
    PREFIX,
  };

  enum Options {
    PREFIX_MATCH = 1 << 0,
  };

  virtual Type type() const = 0;

  virtual bool empty() const = 0;

  virtual string ToString() const = 0;

  static FullTextQuery* Parse(const Slice& query, int options=0);
};


class FullTextQueryTermNode : public FullTextQuery {
 public:
  FullTextQueryTermNode(const Slice& term);
  ~FullTextQueryTermNode();

  Type type() const override { return TERM; }

  bool empty() const override { return false; }

  string ToString() const override { return term_; }

  const string& term() const { return term_; }

 private:
  string term_;
};

class FullTextQueryPrefixNode : public FullTextQuery {
 public:
  FullTextQueryPrefixNode(const Slice& prefix);
  ~FullTextQueryPrefixNode();

  Type type() const override { return PREFIX; }

  bool empty() const override { return false; }

  string ToString() const override { return prefix_ + "*"; }

  const string& prefix() const { return prefix_; }

 private:
  string prefix_;
};


class FullTextQueryParentNode : public FullTextQuery {
 public:
  FullTextQueryParentNode(const vector<FullTextQuery*>& children);
  ~FullTextQueryParentNode();

  bool empty() const override { return children_.size() == 0; }

  string ToString() const override;

  const vector<FullTextQuery*>& children() const { return children_; }

 private:
  vector<FullTextQuery*> children_;
};

class FullTextQueryAndNode : public FullTextQueryParentNode {
 public:
  FullTextQueryAndNode(const vector<FullTextQuery*>& children)
      : FullTextQueryParentNode(children) {
  }
  Type type() const override { return AND; }
};

class FullTextQueryOrNode : public FullTextQueryParentNode {
 public:
  FullTextQueryOrNode(const vector<FullTextQuery*>& children)
      : FullTextQueryParentNode(children) {
  }
  Type type() const override { return OR; }
};


class FullTextQueryVisitor {
 public:
  virtual ~FullTextQueryVisitor();

  void VisitNode(const FullTextQuery& node);
  void VisitChildren(const FullTextQueryParentNode& node);
  virtual void VisitTermNode(const FullTextQueryTermNode& node) { };
  virtual void VisitPrefixNode(const FullTextQueryPrefixNode& node) { };
  virtual void VisitParentNode(const FullTextQueryParentNode& node);
  virtual void VisitAndNode(const FullTextQueryAndNode& node);
  virtual void VisitOrNode(const FullTextQueryOrNode& node);
};


class FullTextQueryTermExtractor : public FullTextQueryVisitor {
 public:
  // Adds all terms in the query to the given set.
  explicit FullTextQueryTermExtractor(StringSet* terms)
      : terms_(terms) {
  }

  void VisitTermNode(const FullTextQueryTermNode& node) override {
    terms_->insert(node.term());
  }

  void VisitPrefixNode(const FullTextQueryPrefixNode& node) override {
    terms_->insert(node.prefix());
  }

 private:
  StringSet* terms_;
};


class FullTextResultIterator {
 public:
  virtual ~FullTextResultIterator();

  // Returns true if the iterator is positioned at a valid result.
  // Unless otherwise noted, other methods are undefined if Valid() returns false.
  virtual bool Valid() const = 0;

  // Advances the iterator to the next result, or sets Valid() to false if there are no more results.
  virtual void Next() = 0;

  // Advances to the first position >= other.  Only moves forward, never backward, so if the current
  // position is already >= other, nothing is changed.
  virtual void Seek(const FullTextResultIterator& other);

  // Return the doc id for the current result.
  virtual const Slice doc_id() const = 0;

  // Return the sort key for the current result.
  virtual const Slice sort_key() const = 0;

  // If this result is derived from a normalized token, add the original denormalized form(s) to *raw_terms.
  virtual void GetRawTerms(StringSet* raw_terms) const {
  }

 protected:
  FullTextResultIterator() {};

 private:
  // Disallow evil constructors.
  FullTextResultIterator(const FullTextResultIterator&);
  void operator=(const FullTextResultIterator&);
};


class FullTextQueryIteratorBuilder : FullTextQueryVisitor {
 public:
  FullTextQueryIteratorBuilder(std::initializer_list<const FullTextIndex*> indexes, const DBHandle& db);
  ~FullTextQueryIteratorBuilder();

  FullTextResultIterator* BuildIterator(const FullTextQuery& query);

  virtual void VisitTermNode(const FullTextQueryTermNode& node) override;
  virtual void VisitPrefixNode(const FullTextQueryPrefixNode& node) override;
  virtual void VisitParentNode(const FullTextQueryParentNode& node) override;

 private:
  std::initializer_list<const FullTextIndex*> indexes_;
  const DBHandle& db_;

  typedef vector<FullTextResultIterator*> Accumulator;
  vector<Accumulator> stack_;
};

struct FullTextIndexTerm {
  string index_term;
  string raw_term;
  int index;
  static const char* kNameKeyFormat;

  FullTextIndexTerm();
  FullTextIndexTerm(const string& it, const string& rt, int i);
  ~FullTextIndexTerm();
  string GetIndexTermKey(const Slice& prefix, const Slice& doc_id) const;
};

class FullTextIndex {
  friend class FullTextQueryIteratorBuilder;

 public:
  FullTextIndex(AppState* state, const Slice& name);
  ~FullTextIndex();

  // Returns a result iterator, which the caller is responsible for deleting.
  // Typical usage:
  //   for (ScopedPtr<FullTextResultIterator> iter(index->Search(db, query));
  //        iter->Valid();
  //        iter->Next()) {
  //     LoadDocument(iter->doc_id());
  //   }
  FullTextResultIterator* Search(const DBHandle& db, const FullTextQuery& query) const;

  // Retrieves a list of (frequency, string) pairs beginning with prefix.
  // The results are sorted by descending frequency.
  typedef vector<pair<int, string> > SuggestionResults;
  void GetSuggestions(const DBHandle& db, const Slice& prefix, SuggestionResults* results);

  // Tokenizes 'phrase' and appends the resulting tokens to 'terms'.
  // Multiple tokens may be generated for the same word based on
  // punctuation removal and ascii transliteration.
  int ParseIndexTerms(int index, const Slice& phrase,
                      vector<FullTextIndexTerm>* terms) const;

  // Adds 'token' to 'terms' without additional processing.
  int AddVerbatimToken(int index, const Slice& token,
                       vector<FullTextIndexTerm>* terms) const;

  // Writes the given 'terms' to the database.  'disk_terms' is updated to contain the terms
  // that were written, and should be persisted and passed back on future calls to UpdateIndex
  // for this entity.
  // 'sort_key' is used as a heuristic when there are too many results to retrieve;
  // records with the lowest sort_keys are returned first.  It may not contain spaces.
  // All terms indexed for a given doc_id must have the same sort_key.
  void UpdateIndex(const vector<FullTextIndexTerm>& terms,
                   const Slice& doc_id, const Slice& sort_key,
                   google::protobuf::RepeatedPtrField<string>* disk_terms,
                   const DBHandle& updates);

  // Removes the given previously-indexed terms from the index, to be used when deleting a document.
  void RemoveTerms(google::protobuf::RepeatedPtrField<string>* disk_terms,
                   const DBHandle& updates);

  // Returns a string that will order results by decreasing timestamp.
  static string TimestampSortKey(WallTime time);

  // Find and return a prefix of 'raw_term' corresponding to 'index_prefix'.  'index_prefix' is a prefix of
  // some transliteration of 'raw_term'.  For example, FindRawPrefix("vlad", "Владимир") returns
  // "Влад". FindRawPefix Returns an empty string if a corresponding prefix could not be computed.  Only public
  // for tests.
  static string FindRawPrefix(const Slice& index_prefix, const Slice& raw_term);

  // Remove all punctuation (actually all non-alphanumerics) from the given string.
  // Only public for tests.
  static string RemovePunctuation(const Slice& term);

  // Blocks until all pending background operations have completed.
  // Only public for tests.
  void DrainBackgroundOps();

  // Returns the database prefix for the given token.
  // For use in TokenResultIterator.
  string FormatIndexTermPrefix(int64_t token_id) const;

  // Builds a filter regex that matches portions of a string that contributed to a search query.
  // *all_terms must have been populated by calling GetRawTerms on a result iterator.
  // and FullTextQueryTermExtractor on a parsed query.
  // Caller takes ownership of the returned pointer.
  static RE2* BuildFilterRE(const StringSet& all_terms);

 private:
  // Generates additional index terms by lossily converting to 7-bit
  // ascii. Adds index term and any denormalized version(s) of it to
  // 'terms'.
  void DenormalizeIndexTerm(int index, const string& term,
                            vector<FullTextIndexTerm>* terms) const;


  string FormatLexiconKey(const Slice& term, const Slice& raw_term) const;
  int64_t AddToLexicon(const FullTextIndexTerm& term);
  void InvalidateLexiconStats(int64_t token_id, const DBHandle& updates);

  int64_t AllocateTokenIdLocked(const Slice& lex_key, const DBHandle& updates);

  void MaybeUpdateLexiconStats();
  // Returns true if any stats needed updating.
  bool UpdateLexiconStats();

  // Caller is responsible for deleting the iterator.
  FullTextResultIterator* CreateTokenIterator(const DBHandle& db, const Slice& token) const;
  FullTextResultIterator* CreateTokenPrefixIterator(const DBHandle& db, const Slice& token_prefix) const;

  AppState* state_;
  const string name_;
  const string index_prefix_;
  const string lexicon_prefix_;

  std::unordered_map<string, int64_t> lexicon_cache_;

  // Held during AddToLexicon.
  Mutex lexicon_mutex_;

  // Protects updating_lexicon_stats_.
  Mutex lexicon_stats_mutex_;
  bool updating_lexicon_stats_;
};

#endif  // VIEWFINDER_FULL_TEXT_INDEX_H

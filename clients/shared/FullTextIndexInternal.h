// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell
//
// This file contains implementation details of FullTextIndex which are only exposed for testing.

#import "FullTextIndex.h"

namespace full_text_index {

class NullResultIterator : public FullTextResultIterator {
 public:
  NullResultIterator();
  ~NullResultIterator();

  bool Valid() const override {
    return false;
  }

  void Next() override { };
  const Slice doc_id() const override {
    return "";
  }
  const Slice sort_key() const override {
    return "";
  }
};

// Iterates over the intersection of a list of child iterators.
class AndResultIterator : public FullTextResultIterator {
 public:
  // Takes ownership of child iterators.
  static FullTextResultIterator* Create(const vector<FullTextResultIterator*>& iterators);
  ~AndResultIterator();

  virtual bool Valid() const;
  virtual void Next();

  virtual const Slice doc_id() const;
  virtual const Slice sort_key() const;

  virtual void GetRawTerms(StringSet* raw_terms) const;

 private:
  explicit AndResultIterator(const vector<FullTextResultIterator*>& iterators);

  void SynchronizeIterators();

  bool valid_;
  vector<FullTextResultIterator*> iterators_;
};

// Iterates over the union of a list of child iterators.
class OrResultIterator : public FullTextResultIterator {
 public:
  // Takes ownership of child iterators.
  static FullTextResultIterator* Create(const vector<FullTextResultIterator*>& iterators);
  ~OrResultIterator();

  virtual bool Valid() const;
  virtual void Next();

  virtual const Slice doc_id() const;
  virtual const Slice sort_key() const;

  virtual void GetRawTerms(StringSet* raw_terms) const;

 private:
  explicit OrResultIterator(const vector<FullTextResultIterator*>& iterators);

  vector<FullTextResultIterator*> iterators_;
};

// Iterates over all occurrences of a token.
class TokenResultIterator : public FullTextResultIterator {
 public:
  TokenResultIterator(const FullTextIndex& index, const DBHandle& db, int64_t token_id, const Slice& raw_term);
  ~TokenResultIterator();

  virtual bool Valid() const;
  virtual void Next();

  virtual const Slice doc_id() const {
    return doc_id_;
  }
  virtual const Slice sort_key() const {
    return sort_key_;
  }

  virtual void GetRawTerms(StringSet* raw_terms) const;

 private:
  void ParseHit();

  const int64_t token_id_;
  const string raw_prefix_;
  DB::PrefixIterator db_iter_;
  bool error_;
  string doc_id_;
  string sort_key_;
};

}  // namespace full_text_index

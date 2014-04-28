// Copyright 2012 Viewfinder.  All rights reserved.
// Author: Ben Darnell

#ifdef TESTING

#import "FullTextIndex.h"
#import "FullTextIndexInternal.h"
#import "Testing.h"
#import "TestUtils.h"

namespace {

using namespace full_text_index;

class StringResultIterator : public FullTextResultIterator {
 public:
  explicit StringResultIterator(const string& str)
      : str_(str),
        pos_(0) {
  }

  virtual bool Valid() const {
    return pos_ < str_.size();
  }

  virtual void Next() {
    pos_++;
  }

  virtual const Slice doc_id() const {
    return Slice(&str_[pos_], 1);
  }

  virtual const Slice sort_key() const {
    return doc_id();
  }

 private:
  const string str_;
  int pos_;
};

class ResultIteratorTest : public Test {
 public:
  string TestAndResultIterator(const vector<string>& input_strs) {
    vector<FullTextResultIterator*> input_iters;
    for (int i = 0; i < input_strs.size(); i++) {
      input_iters.push_back(new StringResultIterator(input_strs[i]));
    }
    ScopedPtr<FullTextResultIterator> and_iter(AndResultIterator::Create(input_iters));
    return IterToString(and_iter.get());
  }

  string TestOrResultIterator(const vector<string>& input_strs) {
    vector<FullTextResultIterator*> input_iters;
    for (int i = 0; i < input_strs.size(); i++) {
      input_iters.push_back(new StringResultIterator(input_strs[i]));
    }
    ScopedPtr<FullTextResultIterator> or_iter(OrResultIterator::Create(input_iters));
    return IterToString(or_iter.get());
  }

  string IterToString(FullTextResultIterator* iter) {
    string result;
    for (; iter->Valid(); iter->Next()) {
      result += iter->doc_id().as_string();
    }
    return result;
  }
};

TEST(FullTextQueryTest, Parse) {
  struct {
    const string query;
    const string expected;
  } kTestData[] = {
    { "", "" },
    { "hello", "hello" },
    { "foo bar", "bar|foo" },
    { "Héllo  world", "héllo|world" },
    { "ΓΝῶΘΙ ΣΕΑΥΤΌΝ", "γνῶθι|σεαυτόν"},
    { "日本將派遣副首相麻生太郎於4月前往中國大陸訪問", "4|中國大陸|前往|副|太郎|將|於|日本|月|派遣|訪問|首相|麻生"},
  };
  for (int i = 0; i < ARRAYSIZE(kTestData); ++i) {
    ScopedPtr<FullTextQuery> query(FullTextQuery::Parse(kTestData[i].query));
    StringSet term_set;
    FullTextQueryTermExtractor extractor(&term_set);
    extractor.VisitNode(*query);
    // Re-order the terms for a deterministic test.
    vector<string> terms(term_set.begin(), term_set.end());
    std::sort(terms.begin(), terms.end());
    EXPECT_EQ(Join(terms, "|"), kTestData[i].expected);
  }
}

TEST(FullTextIndexTest, RemovePunctuation) {
  struct {
    const string str;
    const string expected;
  } kTestData[] = {
    { "", "" },
    { "hello", "hello" },
    { "hello, world", "helloworld" },
    { "O'Connor", "OConnor" },
    { "O’Connor", "OConnor" },  // curly apostrophe
    { "「japanese、punctuation」", "japanesepunctuation" },
  };

  for (int i = 0; i < ARRAYSIZE(kTestData); ++i) {
    EXPECT_EQ(FullTextIndex::RemovePunctuation(kTestData[i].str), kTestData[i].expected);
  }
}

TEST(FullTextIndexTest, FindRawPrefix) {
  struct {
    const string index_prefix;
    const string raw_term;
    const string expected;
  } kTestData[] = {
    { "", "hello", "" },
    { "h", "Hello", "H" },
    { "hel", "hello", "hel" },
    { "helloworld", "hello", "hello" },
    { "cant", "can't", "can't" },
    { "o'c", "O'Connor", "O'C" },
    { "oc", "O'Connor", "O'C" },
    { "andrea", "Andréa", "Andréa" },
    { "andréa", "Andréa", "Andréa" },
    { "Andréa", "Andréa", "Andréa" },
    { "vlad", "Владимир", "Влад" },
    { "习", "习", "习" },
    { "xi", "习", "习" },
    { "j", "近平", "近" },
    // This should really only match the first character, but we'd need to do be smarter about transliteration.
    { "ji", "近平", "近平" },
    { "jinp", "近平", "近平" },
  };
  for (int i = 0; i < ARRAYSIZE(kTestData); ++i) {
    EXPECT_EQ(FullTextIndex::FindRawPrefix(kTestData[i].index_prefix, kTestData[i].raw_term),
              kTestData[i].expected);
  }
}

TEST(FullTextIndexTest, GetSuggestions) {
  TestTmpDir dir;
  TestUIAppState state(dir.dir());;

  FullTextIndex index(&state, "test");
  vector<FullTextIndexTerm> terms;
  index.ParseIndexTerms(0, "who what where when why where where where", &terms);
  google::protobuf::RepeatedPtrField<string> disk_terms;
  {
    // We must update the index in a transaction so commit triggers will work.
    DBHandle updates = state.NewDBTransaction();
    index.UpdateIndex(terms, "doc1", "", &disk_terms, updates);
    updates->Commit();
    index.DrainBackgroundOps();
  }

  // Index two more (identical) documents to increase the word frequencies.
  // Multiple hits in the same document don't count.
  terms.clear();
  index.ParseIndexTerms(0, "how when", &terms);
  {
    google::protobuf::RepeatedPtrField<string> disk_terms2;
    DBHandle updates = state.NewDBTransaction();
    index.UpdateIndex(terms, "doc2", "", &disk_terms2, updates);
    disk_terms2.Clear();
    index.UpdateIndex(terms, "doc3", "", &disk_terms2, updates);
    updates->Commit();
    index.DrainBackgroundOps();
  }

  FullTextIndex::SuggestionResults results;
  index.GetSuggestions(state.db(), "whe", &results);
  ASSERT_EQ(results.size(), 2);
  EXPECT_EQ(results[0], std::make_pair(3, string("when")));
  EXPECT_EQ(results[1], std::make_pair(1, string("where")));

  results.clear();
  index.GetSuggestions(state.db(), "when", &results);
  ASSERT_EQ(results.size(), 1);
  EXPECT_EQ(results[0], std::make_pair(3, string("when")));

  results.clear();
  index.GetSuggestions(state.db(), "whence", &results);
  ASSERT_EQ(results.size(), 0);

  index.GetSuggestions(state.db(), "", &results);
  ASSERT_EQ(results.size(), 6);
  EXPECT_EQ(results[0], std::make_pair(3, string("when")));
  EXPECT_EQ(results[1], std::make_pair(2, string("how")));

  // Add a second document.
  terms.clear();
  index.ParseIndexTerms(0, "who whooo", &terms);
  {
    DBHandle updates = state.NewDBTransaction();
    google::protobuf::RepeatedPtrField<string> disk_terms2;
    index.UpdateIndex(terms, "doc4", "", &disk_terms2, updates);
    updates->Commit();
    index.DrainBackgroundOps();
  }

  results.clear();
  index.GetSuggestions(state.db(), "who", &results);
  ASSERT_EQ(results.size(), 2);
  EXPECT_EQ(results[0], std::make_pair(2, string("who")));
  EXPECT_EQ(results[1], std::make_pair(1, string("whooo")));

  // Update the first document and see that old terms are removed and
  // refcounts are updated accordingly.
  terms.clear();
  index.ParseIndexTerms(0, "when when who who", &terms);
  {
    DBHandle updates = state.NewDBTransaction();
    index.UpdateIndex(terms, "doc1", "", &disk_terms, updates);
    updates->Commit();
    index.DrainBackgroundOps();
  }

  results.clear();
  index.GetSuggestions(state.db(), "", &results);
  ASSERT_EQ(results.size(), 4);
  EXPECT_EQ(results[0], std::make_pair(3, string("when")));
  EXPECT_EQ(results[1], std::make_pair(2, string("who")));
  EXPECT_EQ(results[2], std::make_pair(2, string("how")));
  EXPECT_EQ(results[3], std::make_pair(1, string("whooo")));
}

TEST(FullTextIndexTest, TimestampSortKey) {
  EXPECT_EQ(FullTextIndex::TimestampSortKey(1), "1EzzzzzzwAqz");
  const WallTime base = 1375241745.018779;
  double offsets[] = { 0.01, 1, 1.5, 2, 100, 1000, 10000, 100000, 1000000 };
  for (int i = 0; i < ARRAYSIZE(offsets); i++) {
    const WallTime before = base - offsets[i];
    const WallTime after = base + offsets[i];
    EXPECT_GT(FullTextIndex::TimestampSortKey(before),
              FullTextIndex::TimestampSortKey(base));
    EXPECT_GT(FullTextIndex::TimestampSortKey(base),
              FullTextIndex::TimestampSortKey(after));
    EXPECT_GT(FullTextIndex::TimestampSortKey(before),
              FullTextIndex::TimestampSortKey(after));
  }
}

TEST_F(ResultIteratorTest, AndResultIterator) {
  // No child iterators.
  EXPECT_EQ(TestAndResultIterator(vector<string>()), "");
  // One empty child iterator.
  EXPECT_EQ(TestAndResultIterator(L("")), "");
  // Three empty child iterators.
  EXPECT_EQ(TestAndResultIterator(L("", "", "")), "");

  // One non-empty child iterator.
  EXPECT_EQ(TestAndResultIterator(L("abc")), "abc");
  // Two identical child iterators.
  EXPECT_EQ(TestAndResultIterator(L("abc", "abc")), "abc");
  // Two different child iterators.
  EXPECT_EQ(TestAndResultIterator(L("abcefg", "acdfg")), "acfg");
  // Empty results.
  EXPECT_EQ(TestAndResultIterator(L("ace", "bdf")), "");
  // Multi-way intersection.
  EXPECT_EQ(TestAndResultIterator(L("abcdefmno",
                                    "abcghimno",
                                    "abcjklmno")),
            "abcmno");
}

TEST_F(ResultIteratorTest, OrResultIterator) {
  // No child iterators.
  EXPECT_EQ(TestOrResultIterator(vector<string>()), "");
  // One empty child iterator.
  EXPECT_EQ(TestOrResultIterator(L("")), "");
  // Three empty child iterators.
  EXPECT_EQ(TestOrResultIterator(L("", "", "")), "");

  // One non-empty child iterator.
  EXPECT_EQ(TestOrResultIterator(L("abc")), "abc");
  // Two identical child iterators.
  EXPECT_EQ(TestOrResultIterator(L("abc", "abc")), "abc");
  // Two different child iterators.
  EXPECT_EQ(TestOrResultIterator(L("abcefg", "acdfg")), "abcdefg");
  // Empty results.
  EXPECT_EQ(TestOrResultIterator(L("ace", "bdf")), "abcdef");
  // Multi-way intersection.
  EXPECT_EQ(TestOrResultIterator(L("abcdefmno",
                                   "abcghimno",
                                   "abcjklmno")),
            "abcdefghijklmno");
}

}  // namespace

#endif  // TESTING

// local variables:
// mode: c++
// end:

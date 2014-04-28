// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#import <re2/re2.h>
#import <unicode/utext.h>
#import "AppState.h"
#import "AsyncState.h"
#import "DBFormat.h"
#import "FullTextIndex.h"
#import "FullTextIndexInternal.h"
#import "FullTextIndexMetadata.pb.h"
#import "LazyStaticPtr.h"
#import "Logging.h"
#import "StringUtils.h"

namespace {

// Parse everything between unicode separator characters. This
// will include all punctuation, both internal to the string and
// leading and trailing.
LazyStaticPtr<RE2, const char*> kWhitespaceUnicodeRE = { "([\\pZ]+)" };
LazyStaticPtr<RE2, const char*> kNonAlphaNumUnicodeRE = { "[^\\pL\\pN]+" };

// Indexed terms are stored with the following format:
//
// ft/<name>/i/<token-id> <sort-key> <doc_id>
//
// The database value is an empty string; all the information is contained in the key.
LazyStaticPtr<RE2, const char*> kIndexTermKeyRE = { "ft/[a-z]+/i/(\\d+)\t([^\t]*)\t(.*)" };

// Previous version of the index term RE used for backwards compatibility.
LazyStaticPtr<RE2, const char*> kIndexTermKeyREv1 = { "ft/[a-z]+/i/(\\d+)\t([^\t]*)\t\\d+\t(.*)" };

const char* kIndexTermKeyFormat = "%s%s\t%s\t%s";

// Lexicon terms are stored with the following format:
//
// ft/<name>/l/<index-term> (<raw-term>|'')
//
// The constituent pieces are tab-delimited because we want to allow
// arbitrary punctuation and symbols in names. Think hyphenation,
// apostrophes, periods (possibly slashes '/', which was the original
// delimiter).  Special tokens may also include spaces, although these
// tokens may not be queried in the usual manner.
//
// The database value is a FullTextLexiconMetadata protobuf.
LazyStaticPtr<RE2, const char*> kLexiconKeyRE = { "ft/[a-z]+/l/([^\t]+)\t([^\t]*)" };
const char* kLexiconKeyFormat = "%s%s\t%s";

// Reverse lexicon entries are stored with the following format:
//
// ft/<name>/r/<token-id>
//
// The value is the entire database key of the corresponding lexicon entry (ft/*/l/*).
const char* kReverseLexiconKeyFormat = "ft/%s/r/%s";

// Metadata entries are stored under ft/<name>/m/<key>.
const char* kMetadataKeyFormat = "ft/%s/m/%s";

// Lexicon invalidation keys are stored under ft/<name>/ti/<token-id>.
const char* kTokenInvalidationPrefixFormat = "ft/%s/ti/";
LazyStaticPtr<RE2, const char*> kTokenInvalidationKeyRE = { "ft/[a-z]+/ti/(\\d+)" };
const char* kTokenInvalidationKeyFormat = "ft/%s/ti/%s";

const int kLexiconCacheSize = 1000;

// Format used to build filter regexp (case-insensitve match) on the filter
// string or on the filter string alone or with a leading separator character.
const char* kFilterREFormat = "(?i)(?:^|[\\s]|[[:punct:]])(%s)";

const DBRegisterKeyIntrospect kFullTextIndexKeyIntrospect(
    DBFormat::full_text_index_key(), NULL, NULL);

bool operator<(const FullTextResultIterator& a, const FullTextResultIterator& b) {
  if (a.sort_key() != b.sort_key()) {
    return a.sort_key() < b.sort_key();
  }
  return a.doc_id() < b.doc_id();
}

// Compares two iterator *pointers*.  Useful when constructing a heap of iterators.
struct ResultIteratorGreaterThan {
  bool operator()(FullTextResultIterator* a, FullTextResultIterator* b) {
    return *b < *a;
  }
};

}  // namespace


FullTextQueryIteratorBuilder::FullTextQueryIteratorBuilder(
    std::initializer_list<const FullTextIndex*> indexes, const DBHandle& db)
  : indexes_(indexes),
    db_(db) {
}

FullTextQueryIteratorBuilder::~FullTextQueryIteratorBuilder() {
}

FullTextResultIterator* FullTextQueryIteratorBuilder::BuildIterator(const FullTextQuery& query) {
  stack_.push_back(Accumulator());
  VisitNode(query);
  CHECK_EQ(stack_.size(), 1);
  CHECK_EQ(stack_[0].size(), 1);
  return stack_[0][0];
}

void FullTextQueryIteratorBuilder::VisitTermNode(const FullTextQueryTermNode& node) {
  vector<FullTextResultIterator*> iterators;
  for (auto it : indexes_) {
    iterators.push_back(it->CreateTokenIterator(db_, node.term()));
  }
  stack_.back().push_back(full_text_index::OrResultIterator::Create(iterators));
}

void FullTextQueryIteratorBuilder::VisitPrefixNode(const FullTextQueryPrefixNode& node) {
  vector<FullTextResultIterator*> iterators;
  for (auto it : indexes_) {
    iterators.push_back(it->CreateTokenPrefixIterator(db_, node.prefix()));
  }
  stack_.back().push_back(full_text_index::OrResultIterator::Create(iterators));
}

void FullTextQueryIteratorBuilder::VisitParentNode(const FullTextQueryParentNode& node) {
  stack_.push_back(Accumulator());
  VisitChildren(node);
  FullTextResultIterator* new_iter;
  if (node.type() == FullTextQuery::AND) {
    new_iter = full_text_index::AndResultIterator::Create(stack_.back());
  } else {
    new_iter = full_text_index::OrResultIterator::Create(stack_.back());
  }
  stack_.pop_back();
  stack_.back().push_back(new_iter);
}


FullTextQuery::~FullTextQuery() {
}

FullTextQuery* FullTextQuery::Parse(const Slice& query, int options) {
  // Break the incoming query into terms at whitespace boundaries.
  const vector<string> words = SplitWords(query);
  vector<FullTextQuery*> nodes;
  for (int i = 0; i < words.size(); i++) {
    if (options & PREFIX_MATCH) {
      nodes.push_back(new FullTextQueryPrefixNode(ToLowercase(words[i])));
    } else {
      nodes.push_back(new FullTextQueryTermNode(ToLowercase(words[i])));
    }
  }
  return new FullTextQueryAndNode(nodes);
}


FullTextQueryTermNode::FullTextQueryTermNode(const Slice& term)
    : term_(term.as_string()) {
}

FullTextQueryTermNode::~FullTextQueryTermNode() {
}


FullTextQueryPrefixNode::FullTextQueryPrefixNode(const Slice& prefix)
    : prefix_(prefix.as_string()) {
}

FullTextQueryPrefixNode::~FullTextQueryPrefixNode() {
}


FullTextQueryParentNode::FullTextQueryParentNode(const vector<FullTextQuery*>& children)
    : children_(children) {
}

FullTextQueryParentNode::~FullTextQueryParentNode() {
}

string FullTextQueryParentNode::ToString() const {
  string s = "(";
  s.append(type() == AND ? "and" : "or");
  for (auto child : children()) {
    s.append(" ");
    s.append(child->ToString());
  }
  s.append(")");
  return s;
}

FullTextQueryVisitor::~FullTextQueryVisitor() {
}

void FullTextQueryVisitor::VisitNode(const FullTextQuery& node) {
  switch (node.type()) {
    case FullTextQuery::TERM:
      VisitTermNode(static_cast<const FullTextQueryTermNode&>(node));
      break;
    case FullTextQuery::AND:
      VisitAndNode(static_cast<const FullTextQueryAndNode&>(node));
      break;
    case FullTextQuery::OR:
      VisitOrNode(static_cast<const FullTextQueryOrNode&>(node));
      break;
    case FullTextQuery::PREFIX:
      VisitPrefixNode(static_cast<const FullTextQueryPrefixNode&>(node));
      break;
  }
}

void FullTextQueryVisitor::VisitChildren(const FullTextQueryParentNode& node) {
  for (FullTextQuery *const child : node.children()) {
    VisitNode(*child);
  }
}

void FullTextQueryVisitor::VisitParentNode(const FullTextQueryParentNode& node) {
  VisitChildren(node);
}

void FullTextQueryVisitor::VisitAndNode(const FullTextQueryAndNode& node) {
  VisitParentNode(node);
}

void FullTextQueryVisitor::VisitOrNode(const FullTextQueryOrNode& node) {
  VisitParentNode(node);
}


FullTextResultIterator::~FullTextResultIterator() {
}

void FullTextResultIterator::Seek(const FullTextResultIterator& other) {
  while (Valid() && *this < other) {
    Next();
  }
}

FullTextIndexTerm::FullTextIndexTerm()
    : index(0) {
}

FullTextIndexTerm::FullTextIndexTerm(const string& it, const string& rt, int i)
    : index_term(it),
      raw_term(it == rt ? "" : rt),
      index(i) {
}

FullTextIndexTerm::~FullTextIndexTerm() {
}

FullTextIndex::FullTextIndex(AppState* state, const Slice& name)
    : state_(state),
      name_(name.as_string()),
      index_prefix_(DBFormat::full_text_index_key(name_) + "i/"),
      lexicon_prefix_(DBFormat::full_text_index_key(name_) + "l/"),
      updating_lexicon_stats_(false) {
  MaybeUpdateLexiconStats();
}

FullTextIndex::~FullTextIndex() {
}

FullTextResultIterator* FullTextIndex::CreateTokenIterator(const DBHandle& db, const Slice& token) const {
  return CreateTokenPrefixIterator(db, token.as_string() + "\t");
}

FullTextResultIterator* FullTextIndex::CreateTokenPrefixIterator(const DBHandle& db, const Slice& token_prefix) const {
  vector<FullTextResultIterator*> token_iters;
  for (DB::PrefixIterator lex_iter(db, lexicon_prefix_ + token_prefix.as_string());
       lex_iter.Valid();
       lex_iter.Next()) {
    const Slice lex_key = lex_iter.key();

    Slice index_term;
    Slice raw_term;
    if (!RE2::FullMatch(lex_key, *kLexiconKeyRE, &index_term, &raw_term)) {
      LOG("index: unable to parse lexicon key: %s", lex_key);
      continue;
    }

    FullTextLexiconMetadata lex_data;
    if (!lex_data.ParseFromArray(lex_iter.value().data(), lex_iter.value().size())) {
      LOG("index: unable to parse lexicon value for %s", lex_key);
      continue;
    }

    // If the raw term differs from the filter term, save the matching prefix from the raw term.
    string raw_prefix;
    if (!raw_term.empty() && raw_term != index_term) {
      raw_prefix = FindRawPrefix(token_prefix, raw_term);
    }
    token_iters.push_back(new full_text_index::TokenResultIterator(*this, db, lex_data.token_id(), raw_prefix));
  }

  return full_text_index::OrResultIterator::Create(token_iters);
}

FullTextResultIterator* FullTextIndex::Search(const DBHandle& db, const FullTextQuery& query) const {
  FullTextQueryIteratorBuilder builder({this}, db);
  return builder.BuildIterator(query);
}

void FullTextIndex::GetSuggestions(const DBHandle& db, const Slice& prefix, SuggestionResults* results) {
  for (DB::PrefixIterator iter(db, lexicon_prefix_ + prefix.as_string());
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    Slice index_term;
    Slice raw_term;
    if (!RE2::FullMatch(key, *kLexiconKeyRE, &index_term, &raw_term)) {
      LOG("index: unable to parse lexicon key: %s", key);
      continue;
    }
    FullTextLexiconMetadata data;
    if (!data.ParseFromArray(iter.value().data(), iter.value().size())) {
      LOG("index: unable to parse lexicon data for: %s", key);
    }
    if (data.count() == 0) {
      continue;
    }
    results->push_back(std::make_pair(data.count(),
                                      (raw_term.empty() ? index_term : raw_term).as_string()));
  }
  std::sort(results->begin(), results->end());
  std::reverse(results->begin(), results->end());
}

string FullTextIndex::FindRawPrefix(const Slice& index_prefix, const Slice& raw_term) {
  // The matching prefix can be tricky. We walk the raw term until
  // we've assembled the same number of alphanumeric characters as
  // were contained in the filter term.
  int target_len = 0;
  for (UnicodeCharIterator it(index_prefix); !it.Done(); it.Advance()) {
    if (IsAlphaNumUnicode(it.Get())) {
      ++target_len;
    }
  }

  icu::UnicodeString out;
  for (UnicodeCharIterator it(raw_term); !it.Done() && target_len > 0; it.Advance()) {
    UChar32 c = it.Get();
    out.append(c);
    if (IsAlphaNumUnicode(c)) {
      --target_len;
    }
  }
  string out_utf8;
  out.toUTF8String(out_utf8);
  return out_utf8;
}


int FullTextIndex::ParseIndexTerms(int index, const Slice& phrase,
                                   vector<FullTextIndexTerm>* terms) const {
  const vector<string> words = SplitWords(phrase);
  for (int i = 0; i < words.size(); i++) {
    DenormalizeIndexTerm(index, ToLowercase(words[i]), terms);
    index++;
  }
  return index;
}

// Generates additional index terms by lossily converting to 7-bit
// ascii. Adds index term and any denormalized version(s) of it to
// 'terms'.
void FullTextIndex::DenormalizeIndexTerm(int index, const string& term,
                                         vector<FullTextIndexTerm>* terms) const {
  //LOG("pushing index term %s", term);
  terms->push_back(FullTextIndexTerm(term, term, index));

  const string unpunctuated = RemovePunctuation(term);
  if (!unpunctuated.empty() && unpunctuated != term) {
    terms->push_back(FullTextIndexTerm(unpunctuated, term, index));
  }

  // See if converting to ascii yields a different, but
  // non-empty result. If so, index that as well.
  string lossy(ToAsciiLossy(term));
  // The transliterator may have introduced spaces (especially for Chinese, where it adds a space
  // between syllables), but we don't allow spaces in tokens.
  RE2::GlobalReplace(&lossy, *kWhitespaceUnicodeRE, "");
  if (!lossy.empty() && term != lossy) {
    terms->push_back(FullTextIndexTerm(lossy, term, index));
    string np_lossy = ToAsciiLossy(unpunctuated);
    RE2::GlobalReplace(&np_lossy, *kWhitespaceUnicodeRE, "");
    if (!np_lossy.empty() && np_lossy != unpunctuated) {
      terms->push_back(FullTextIndexTerm(np_lossy, term, index));
    }
  }
}

int FullTextIndex::AddVerbatimToken(int index, const Slice& token,
                                    vector<FullTextIndexTerm>* terms) const {
  const string token_str(token.as_string());
  terms->push_back(FullTextIndexTerm(token_str, token_str, index));
  return index + 1;
}

void FullTextIndex::UpdateIndex(const vector<FullTextIndexTerm>& terms,
                                const Slice& doc_id, const Slice& sort_key,
                                google::protobuf::RepeatedPtrField<string>* disk_terms,
                                const DBHandle& updates) {
  // TODO(ben): don't remove and re-add terms that were present before and after.
  // It's inefficient and causes token ids to be wasted (a token loses its id when its refcount hits zero).

  // Remove any existing name indexes.
  RemoveTerms(disk_terms, updates);
  disk_terms->Clear();

  CHECK_EQ(sort_key.find('\t'), Slice::npos);

  // Add all the indexed terms.
  for (int i = 0; i < terms.size(); ++i) {
    const int64_t token_id = AddToLexicon(terms[i]);
    const string term_key = Format(kIndexTermKeyFormat, index_prefix_, token_id,
                                   sort_key, doc_id);
    *disk_terms->Add() = term_key;
    updates->Put(term_key, "");
    InvalidateLexiconStats(token_id, updates);
  }
}

void FullTextIndex::RemoveTerms(google::protobuf::RepeatedPtrField<string>* disk_terms,
                                const DBHandle& updates) {
  for (int i = 0; i < disk_terms->size(); ++i) {
    const string& key = disk_terms->Get(i);
    updates->Delete(key);

    int64_t token_id;
    Slice sort_key;
    Slice doc_id;
    // NOTE(ben): if this doesn't match, we're either migrating from a
    // pre-lexicon format or the format has changed.  In the later
    // case the lexicon counts may get out of sync, so we'll need to either
    // rebuild the lexicon from scratch or ensure we can continue to parse
    // the old keys here.
    if (RE2::FullMatch(key, *kIndexTermKeyRE, &token_id, &sort_key, &doc_id) ||
        RE2::FullMatch(key, *kIndexTermKeyREv1, &token_id, &sort_key, &doc_id)) {
      InvalidateLexiconStats(token_id, updates);
    }
  }
}

string FullTextIndex::TimestampSortKey(WallTime time) {
  int64_t usec = time * 1000000;
  string s;
  OrderedCodeEncodeVarint64Decreasing(&s, usec);
  // Sort keys cannot contain spaces, so base64hex-encode it.
  return Base64HexEncode(s, false);
}

string FullTextIndex::RemovePunctuation(const Slice& term) {
  string unpunctuated = term.as_string();
  RE2::GlobalReplace(&unpunctuated, *kNonAlphaNumUnicodeRE, "");
  return unpunctuated;
}

void FullTextIndex::DrainBackgroundOps() {
  MutexLock lock(&lexicon_stats_mutex_);
  lexicon_stats_mutex_.Wait([this]{
      return !updating_lexicon_stats_;
    });
}

string FullTextIndex::FormatIndexTermPrefix(int64_t token_id) const {
  // Append a tab because we don't want token ids that are prefixes of
  // each other, just records that have the token id as a prefix.
  return Format("%s%s\t", index_prefix_, token_id);
}

RE2* FullTextIndex::BuildFilterRE(const StringSet& all_terms) {
  string s;
  for (StringSet::const_iterator iter(all_terms.begin());
       iter != all_terms.end();
       ++iter) {
    if (!s.empty()) {
      s += "|";
    }
    const string& t = *iter;
    if (!t.empty()) {
      s += RE2::QuoteMeta(*iter);
    }
  }
  if (s.empty()) {
    return NULL;
  } else {
    // We want the regexp to return the longest match so that the regexp
    // "kat|k" will match "[kat]hryn" and not "[k]athryn".
    RE2::Options opts;
    opts.set_longest_match(true);
    return new RE2(string(Format(kFilterREFormat, s)), opts);
  }
}

string FullTextIndex::FormatLexiconKey(const Slice& term, const Slice& raw_term) const {
  return Format(kLexiconKeyFormat, lexicon_prefix_, term, raw_term);
}

int64_t FullTextIndex::AddToLexicon(const FullTextIndexTerm& term) {
  const string lex_key = FormatLexiconKey(term.index_term, term.raw_term);
  MutexLock lock(&lexicon_mutex_);

  const int64_t* cache_token_id = FindPtrOrNull(lexicon_cache_, lex_key);
  if (cache_token_id) {
    return *cache_token_id;
  }

  // The mapping of tokens to ids is append-only, so write it immediately in a separate transaction.
  DBHandle updates = state_->NewDBTransaction();
  FullTextLexiconMetadata data;
  const bool exists = updates->GetProto(lex_key, &data);
  if (!exists) {
    const string id_key = Format(kMetadataKeyFormat, name_, "next_id");
    int64_t id = updates->Get<int64_t>(id_key);
    updates->Put<int64_t>(id_key, id + 1);
    updates->Put(Format(kReverseLexiconKeyFormat, name_, id), lex_key);
    data.set_token_id(id);
    updates->PutProto(lex_key, data);
  }
  updates->Commit();

  if (lexicon_cache_.size() > kLexiconCacheSize) {
    // TODO(ben): Use LRU eviction instead of throwing the whole thing out.
    lexicon_cache_.clear();
  }
  lexicon_cache_[lex_key] = data.token_id();

  return data.token_id();
}

void FullTextIndex::InvalidateLexiconStats(int64_t token_id, const DBHandle& updates) {
  const string invalidation_key = Format(kTokenInvalidationKeyFormat, name_, token_id);
  updates->Put(invalidation_key, "");
  CHECK(updates->AddCommitTrigger(
            Format("InvalidateTokenStats:%s", name_),
            [this]{
              MaybeUpdateLexiconStats();
            }));
}

int64_t FullTextIndex::AllocateTokenIdLocked(const Slice& lex_key, const DBHandle& updates) {
  lexicon_mutex_.AssertHeld();
  const string key = Format(kMetadataKeyFormat, name_, "next_id");
  int64_t id = updates->Get<int64_t>(key);
  updates->Put<int64_t>(key, id + 1);
  updates->Put(Format(kReverseLexiconKeyFormat, name_, id), lex_key);
  FullTextLexiconMetadata data;
  data.set_token_id(id);
  updates->PutProto(lex_key, data);
  return id;
}

void FullTextIndex::MaybeUpdateLexiconStats() {
  MutexLock lock(&lexicon_stats_mutex_);
  if (updating_lexicon_stats_) {
    return;
  }
  updating_lexicon_stats_ = true;
  state_->async()->dispatch_background([this]{
      while (UpdateLexiconStats()) {
      }
      // There's a small race condition here if a transaction commits between the last UpdateLexiconStats
      // call and our setting updating_lexicon_stats, but it's OK if stats are a bit out of date.
      MutexLock lock(&lexicon_stats_mutex_);
      updating_lexicon_stats_ = false;
    });
}

bool FullTextIndex::UpdateLexiconStats() {
  DBHandle updates = state_->NewDBTransaction();
  for (DB::PrefixIterator inv_iter(updates, (string)Format(kTokenInvalidationPrefixFormat, name_));
       inv_iter.Valid();
       inv_iter.Next()) {
    int64_t token_id;
    if (!RE2::FullMatch(inv_iter.key(), *kTokenInvalidationKeyRE, &token_id)) {
      LOG("index: could not parse token invalidation key %s", inv_iter.key());
      DCHECK(false);
      continue;
    }

    const string rev_lex_key = Format(kReverseLexiconKeyFormat, name_, token_id);
    const string lex_key = updates->Get<string>(rev_lex_key);
    if (lex_key.empty()) {
      LOG("index: could not find lexicon key for token %s", rev_lex_key);
      continue;
    }

    int hit_count = 0;
    for (DB::PrefixIterator hit_iter(updates, FormatIndexTermPrefix(token_id));
         hit_iter.Valid();
         hit_iter.Next()) {
      hit_count++;
    }

    FullTextLexiconMetadata lex_data;
    if (!updates->GetProto(lex_key, &lex_data)) {
      LOG("index: could not load lexicon stats for %s", lex_key);
      continue;
    }
    lex_data.set_count(hit_count);
    updates->PutProto(lex_key, lex_data);

    updates->Delete(inv_iter.key());
  }
  const bool changed = updates->tx_count();
  updates->Commit();
  return changed;
}

namespace full_text_index {

NullResultIterator::NullResultIterator() {
}

NullResultIterator::~NullResultIterator() {
}

FullTextResultIterator* AndResultIterator::Create(const vector<FullTextResultIterator*>& iterators) {
  if (iterators.size() == 0) {
    return new NullResultIterator();
  } else if (iterators.size() == 1) {
    return iterators[0];
  } else {
    return new AndResultIterator(iterators);
  }
}

AndResultIterator::AndResultIterator(const vector<FullTextResultIterator*>& iterators)
    : valid_(iterators.size() > 0),
      iterators_(iterators) {
  SynchronizeIterators();
}

AndResultIterator::~AndResultIterator() {
  Clear(&iterators_);
}

bool AndResultIterator::Valid() const {
  return valid_;
}

void AndResultIterator::Next() {
  DCHECK(valid_);
  // Precondition: all iterators are pointing to the same document.
  // Increment one then advance until they align again.
  iterators_[0]->Next();
  SynchronizeIterators();
}

const Slice AndResultIterator::doc_id() const {
  DCHECK(valid_);
  return iterators_[0]->doc_id();
}

const Slice AndResultIterator::sort_key() const {
  DCHECK(valid_);
  return iterators_[0]->sort_key();
}

void AndResultIterator::GetRawTerms(StringSet* raw_terms) const {
  for (int i = 0; i < iterators_.size(); i++) {
    iterators_[0]->GetRawTerms(raw_terms);
  }
}

void AndResultIterator::SynchronizeIterators() {
  if (iterators_.size() == 0 ||
      !iterators_[0]->Valid()) {
    valid_ = false;
    return;
  }
  // Try to bring the rest of the iterators to match the first one.
  for (int i = 1; i < iterators_.size(); i++) {
    iterators_[i]->Seek(*iterators_[0]);
    if (!iterators_[i]->Valid()) {
      valid_ = false;
      return;
    }
    // The iterator we just advanced overshot the first iterator.
    // Bring the first one up to match and start over.
    if (*iterators_[0] < *iterators_[i]) {
      iterators_[0]->Seek(*iterators_[i]);
      if (!iterators_[0]->Valid()) {
        valid_ = false;
        return;
      }
      i = 0;
    }
  }
}

FullTextResultIterator* OrResultIterator::Create(const vector<FullTextResultIterator*>& iterators) {
  if (iterators.size() == 0) {
    return new NullResultIterator();
  } else if (iterators.size() == 1) {
    return iterators[0];
  } else {
    return new OrResultIterator(iterators);
  }
}

OrResultIterator::OrResultIterator(const vector<FullTextResultIterator*>& iterators) {
  for (int i = 0; i < iterators.size(); i++) {
    if (iterators[i]->Valid()) {
      iterators_.push_back(iterators[i]);
    } else {
      delete iterators[i];
    }
  }
  std::make_heap(iterators_.begin(), iterators_.end(), ResultIteratorGreaterThan());
}

OrResultIterator::~OrResultIterator() {
  Clear(&iterators_);
}

bool OrResultIterator::Valid() const {
  return !iterators_.empty();
}

void OrResultIterator::Next() {
  if (iterators_.size() == 0) {
    return;
  }
  const string current_doc_id = iterators_[0]->doc_id().as_string();
  while (iterators_.size() > 0 &&
         iterators_[0]->doc_id() == current_doc_id) {
    FullTextResultIterator* iter = iterators_[0];
    std::pop_heap(iterators_.begin(), iterators_.end(), ResultIteratorGreaterThan());
    iter->Next();
    if (iter->Valid()) {
      std::push_heap(iterators_.begin(), iterators_.end(), ResultIteratorGreaterThan());
    } else {
      delete iter;
      iterators_.resize(iterators_.size() - 1);
    }
  }
}

const Slice OrResultIterator::doc_id() const {
  return iterators_[0]->doc_id();
}

const Slice OrResultIterator::sort_key() const {
  return iterators_[0]->sort_key();
}

void OrResultIterator::GetRawTerms(StringSet* raw_terms) const {
  for (int i = 0; i < iterators_.size(); i++) {
    // Get the raw terms from all iterators that match the current position.
    if (*iterators_[0] < *iterators_[i]) {
      continue;
    }
    iterators_[0]->GetRawTerms(raw_terms);
  }
}

TokenResultIterator::TokenResultIterator(const FullTextIndex& index, const DBHandle& db,
                                         int64_t token_id, const Slice& raw_prefix)
    : token_id_(token_id),
      raw_prefix_(raw_prefix.as_string()),
      db_iter_(db, index.FormatIndexTermPrefix(token_id_)),
      error_(false) {
  ParseHit();
}

TokenResultIterator::~TokenResultIterator() {
}

bool TokenResultIterator::Valid() const {
  return !error_ && db_iter_.Valid();
}

void TokenResultIterator::Next() {
  db_iter_.Next();
  ParseHit();
}

void TokenResultIterator::ParseHit() {
  if (!db_iter_.Valid()) {
    return;
  }
  const Slice key = db_iter_.key();
  int64_t token_id;
  if (!RE2::FullMatch(key, *kIndexTermKeyRE, &token_id, &sort_key_, &doc_id_)) {
    LOG("index: unable to parse token key: %s", key);
    error_ = true;
    return;
  }
  DCHECK_EQ(token_id, token_id_);
}

void TokenResultIterator::GetRawTerms(StringSet* raw_terms) const {
  if (!raw_prefix_.empty()) {
    raw_terms->insert(raw_prefix_);
  }
}

}  // namespace full_text_index

// local variables:
// mode: c++
// end:

// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.
//
// The idea behind the perceptual fingerprint is based on the papers "Fast
// Multiresolution Image Querying" - Jacobs, et al and "Image Similarity Search
// with Compact Data Structures" - Lv, et al. The high-level: downsize the
// image to 32x32 grayscale (i.e. only consider luminance). The downsizing
// removes noise and some minor compression artifacts. Apply a 5x5 box blur to
// remove more noise/compression artifacts. Normalize the image
// orientation. Apply the discrete Haar wavelet transform which computes
// horizontal and vertical image gradients at various scales. Create a
// fingerprint using the resulting gradients by setting a bit in the
// fingerprint if the corresponding gradient has a non-negative value. The
// resulting fingerprint can be compared with another fingerprint using a
// simple hamming distance calculation. Similar fingerprints will correspond to
// similar images. Why does this work? The fingerprint captures image gradients
// at multiple scale levels and similar images will have similar gradient
// profiles.
//
// Note that we can't use an exact match on the fingerprint for
// searching. Minor compression artifacts will still cause a few bits in the
// fingerprint to change. When searching for a matching fingerprint, brute
// force would be possible. The hamming distance calculation is extremely fast
// (xor + number-of-bits-set). But we can do a bit better since we're only
// searching for near-duplicate images with a small number of differences from
// a target fingerprint.
//
// The perceptual hash contains 160 bits. When performing a search, we want to
// find the other fingerprints which have a small hamming distance from our
// search fingerprint. For our fingerprint, a hamming distance <= 5% of the
// fingerprint length usually gives solid confirmation of near-duplicate
// images. 160 bits * 5% == 8 bits.
//
// When adding a fingerprint to the index, we index 12-bit N-grams (tags) for
// each 160-bit fingerprint. There are 13 non-overlapping 12-bit N-grams in
// each fingerprint and, by the pigeon-hole principle, we are guaranteed that 2
// fingerprints with a hamming distance <= 12 will contain at least 1 N-gram in
// common.
//
// A 12-bit tag size provides 4096 buckets. With 100,000 unique images indexed,
// we would expect ~25 fingerprints per bucket. A search needs to examine all
// 13 buckets for a fingerprint giving an expected 325 fingerprints comparisons
// per search.
//
// TODO(peter): Can/should we incorporate chrominance into the fingerprint?

#import "DBFormat.h"
#import "ImageFingerprintPrivate.h"
#import "ImageIndex.h"
#import "Logging.h"
#import "Timer.h"

namespace {

// The tag lengths are expressed in hexadecimal characters (i.e. 4 bits) and
// must sum to 40 characters.
const int kTagLengths[13] = {
  3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4,
};
const int kMatchThreshold = 12;

const string kImageIndexKeyPrefix = DBFormat::image_index_key("");

const DBRegisterKeyIntrospect kImageIndexKeyIntrospect(
    kImageIndexKeyPrefix, NULL, [](Slice value) {
      return DBIntrospect::FormatProto<ImageFingerprint>(value);
    });

// #define SQUARE_ZIG_ZAG
#ifdef SQUARE_ZIG_ZAG

// Generate a vector of offsets for the zig-zag traversal of the upper-left
// NxN square region of an MxM matrix.
vector<int> MakeSquareZigZagOffsets(int n, int m) {
  assert(m >= n);
  vector<int> offsets(n * n);
  int i = 0, j = 0;
  int d = -1;
  int start = 0;
  int end = n * n - 1;
  do {
    offsets[start++] = i * m + j;
    offsets[end--] = (n - i - 1) * m + n - j - 1;
    i += d;
    j -= d;
    if (i < 0) {
      ++i;
      d = -d;
    } else if (j < 0) {
      ++j;
      d = -d;
    }
  } while (start < end);
  if (start == end) {
    offsets[start] = i * m + j;
  }
  return offsets;
}

#else  // !SQUARE_ZIG_ZAG

// Generate a vector of offsets for the zig-zag traversal of the first K cells of an NxN matrix.
vector<int> MakeTriangularZigZagOffsets(int k, int n) {
  assert(k < (n * n));
  vector<int> offsets(k);
  int i = 0, j = 0;
  int d = -1;
  int start = 0;
  int end = n * n - 1;
  do {
    offsets[start++] = i * n + j;
    if (end < k) {
      offsets[end] = (n - i) * n - j - 1;
    }
    end--;
    i += d;
    j -= d;
    if (i < 0) {
      ++i;
      d = -d;
    } else if (j < 0) {
      ++j;
      d = -d;
    }
  } while (start < k && start < end);
  if (start == end && start < k) {
    offsets[start] = i * n + j;
  }
  return offsets;
}

#endif  // !SQUARE_ZIG_ZAG

string EncodeKey(const Slice& hex_term, int i, int n, const string& id) {
  return Format("%s%02d:%s#%s", kImageIndexKeyPrefix,
                i, hex_term.substr(i, n), id);
}

bool DecodeKey(Slice key, Slice* tag, Slice* id) {
  if (!key.starts_with(kImageIndexKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kImageIndexKeyPrefix.size());
  const int pos = key.find('#');
  if (pos == key.npos) {
    return false;
  }
  if (tag) {
    *tag = key.substr(0, pos);
  }
  if (id) {
    *id = key.substr(pos + 1);
  }
  return true;
}

StringSet GenerateKeys(const ImageFingerprint& f, const string& id) {
  StringSet keys;
  for (int i = 0; i < f.terms_size(); ++i) {
    const string hex_term = BinaryToHex(f.terms(i));
    const int n = hex_term.size();
    for (int j = 0, k = 0, len; j < n; j += len, ++k) {
      len = kTagLengths[k];
      keys.insert(EncodeKey(hex_term, j, len, id));
    }
  }
  return keys;
}

string Intersect(const Slice& a, const Slice& b) {
  DCHECK_EQ(a.size(), b.size());
  string r(a.ToString());
  for (int i = 0; i < r.size(); ++i) {
    r[i] ^= b[i];
  }
  return r;
}

int HammingDistance(const Slice& a, const Slice& b) {
  DCHECK_EQ(a.size(), b.size());
  DCHECK_EQ(0, a.size() % 4);
  int count = 0;
  const uint32_t* a_ptr = (const uint32_t*)a.data();
  const uint32_t* b_ptr = (const uint32_t*)b.data();
  for (int i = 0, n = a.size() / 4; i < n; ++i) {
    count += __builtin_popcount(a_ptr[i] ^ b_ptr[i]);
  }
  return count;
}

}  // namespace

#ifdef SQUARE_ZIG_ZAG
const vector<int> kZigZagOffsets = MakeSquareZigZagOffsets(
    kHaarHashN, kHaarSmallN);
#else  // !SQUARE_ZIG_ZAG
const vector<int> kZigZagOffsets = MakeTriangularZigZagOffsets(
    kHaarHashBits + kHaarHashSkip, kHaarSmallN);
#endif  // !SQUARE_ZIG_ZAG

ostream& operator<<(ostream& os, const ImageFingerprint& f) {
  for (int i = 0; i < f.terms_size(); ++i) {
    if (i > 0) {
      os << ":";
    }
    os << BinaryToHex(f.terms(i));
  }
  return os;
}

ImageIndex::ImageIndex(bool histogram)
    : histogram_(histogram ? new vector<int>(kHaarHashBits) : NULL),
      histogram_count_(0) {
}

ImageIndex::~ImageIndex() {
}

void ImageIndex::Add(const ImageFingerprint& fingerprint,
                     const string& id, const DBHandle& updates) {
  const StringSet keys = GenerateKeys(fingerprint, id);
  for (StringSet::const_iterator iter(keys.begin());
       iter != keys.end();
       ++iter) {
    updates->PutProto(*iter, fingerprint);
  }

  if (histogram_.get()) {
    // Keep a histogram of the bits set in the fingerprints so that we can
    // verify in tests that every bit is being used.
    for (int i = 0; i < fingerprint.terms_size(); ++i) {
      const string& s = fingerprint.terms(i);
      ++histogram_count_;
      const uint8_t* p = (const uint8_t*)s.data();
      for (int j = 0; j < s.size() * 8; ++j) {
        if (p[j / 8] & (1 << (j % 8))) {
          (*histogram_)[j] += 1;
        }
      }
    }
  }
}

void ImageIndex::Remove(const ImageFingerprint& fingerprint,
                        const string& id, const DBHandle& updates) {
  const StringSet keys = GenerateKeys(fingerprint, id);
  for (StringSet::const_iterator iter(keys.begin());
       iter != keys.end();
       ++iter) {
    updates->Delete(*iter);
  }
}

int ImageIndex::Search(const DBHandle& db, const ImageFingerprint& fingerprint,
                       StringSet* matched_ids) const {
  const StringSet keys = GenerateKeys(fingerprint, "");
  std::unordered_set<string> checked_ids;
  int candidates = 0;
  for (StringSet::const_iterator key_iter(keys.begin());
       key_iter != keys.end();
       ++key_iter) {
    for (DB::PrefixIterator iter(db, *key_iter);
         iter.Valid();
         iter.Next()) {
      Slice id;
      if (!DecodeKey(iter.key(), NULL, &id)) {
        DCHECK(false);
        continue;
      }
      const string id_str = id.ToString();
      if (ContainsKey(checked_ids, id_str)) {
        continue;
      }
      ++candidates;
      ImageFingerprint candidate_fingerprint;
      if (!candidate_fingerprint.ParseFromArray(
              iter.value().data(), iter.value().size())) {
        DCHECK(false);
        continue;
      }
      checked_ids.insert(id_str);
      const int n = HammingDistance(fingerprint, candidate_fingerprint);
      if (n > kMatchThreshold) {
        continue;
      }
      matched_ids->insert(id_str);
    }
  }
  return candidates;
}

string ImageIndex::PrettyHistogram() const {
  if (!histogram_.get()) {
    return "";
  }
  vector<string> v(kHaarSmallN * kHaarSmallN);
  if (histogram_count_ > 0) {
    for (int i = 0; i < kHaarHashSkip; ++i) {
      v[kZigZagOffsets[i]] = "   ";
    }
    for (int i = 0; i < histogram_->size(); ++i) {
      const int val = (100 * (*histogram_)[i]) / histogram_count_;
      v[kZigZagOffsets[i + kHaarHashSkip]] = Format("%3d", val);
    }
  }
  string s;
  for (int i = 0; i < kHaarSmallN; ++i) {
    if (v[i + kHaarSmallN].empty()) {
      break;
    }
    for (int j = 0; j < kHaarSmallN; ++j) {
      const string& t = v[i * kHaarSmallN + j];
      if (t.empty()) {
        break;
      }
      s += " " + t;
    }
    s += "\n";
  }
  return s;
}

int ImageIndex::TotalTags(const DBHandle& db) const {
  int count = 0;
  for (DB::PrefixIterator iter(db, kImageIndexKeyPrefix);
       iter.Valid();
       iter.Next()) {
    ++count;
  }
  return count;
}

int ImageIndex::UniqueTags(const DBHandle& db) const {
  string last_tag;
  int count = 0;
  for (DB::PrefixIterator iter(db, kImageIndexKeyPrefix);
       iter.Valid();
       iter.Next()) {
    Slice tag;
    if (!DecodeKey(iter.key(), &tag, NULL)) {
      DCHECK(false);
      continue;
    }
    if (last_tag != tag) {
      ++count;
      last_tag = tag.ToString();
    }
  }
  return count;
}

ImageFingerprint ImageIndex::Intersect(
    const ImageFingerprint& a, const ImageFingerprint& b) {
  ImageFingerprint f;
  int best_dist = std::numeric_limits<int>::max();
  int best_index_a = -1;
  int best_index_b = -1;
  for (int i = 0; i < a.terms_size(); ++i) {
    for (int j = 0; j < b.terms_size(); ++j) {
      const int dist = ::HammingDistance(a.terms(i), b.terms(j));
      if (best_dist > dist) {
        best_dist = dist;
        best_index_a = i;
        best_index_b = j;
      }
    }
  }
  f.add_terms(::Intersect(a.terms(best_index_a), b.terms(best_index_b)));
  return f;
}

int ImageIndex::HammingDistance(
    const ImageFingerprint& a, const ImageFingerprint& b) {
  int best = std::numeric_limits<int>::max();
  for (int i = 0; i < a.terms_size(); ++i) {
    for (int j = 0; j < b.terms_size(); ++j) {
      best = std::min(best, ::HammingDistance(a.terms(i), b.terms(j)));
    }
  }
  return best;
}

// local variables:
// mode: c++
// end:

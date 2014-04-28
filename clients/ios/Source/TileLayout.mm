// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "LazyStaticPtr.h"
#import "Logging.h"
#import "Random.h"
#import "TileLayout.h"

namespace {

struct SummaryTileLayouts4x3 : public std::vector<std::vector<TileLayout> > {
  SummaryTileLayouts4x3()
      : std::vector<std::vector<TileLayout> >(7, std::vector<TileLayout>()) {
    // 1 photo layouts.
    layouts(1)->push_back(TileLayout("0000",
                                     "0000",
                                     "0000"));

    // 2 photo layouts. Note that the layout of 2 horizontal photos looks poor
    // and is intentionally not included below.
    AddLayouts(2, 1);
    layouts(2)->push_back(TileLayout("0011",
                                     "0011",
                                     "0011"));
    layouts(2)->push_back(TileLayout("0001",
                                     "0001",
                                     "0001"));
    layouts(2)->push_back(TileLayout("0111",
                                     "0111",
                                     "0111"));

    // 3 photo layouts.
    layouts(3)->push_back(TileLayout("0012",
                                     "0012",
                                     "0012"));
    layouts(3)->push_back(TileLayout("0112",
                                     "0112",
                                     "0112"));
    layouts(3)->push_back(TileLayout("0122",
                                     "0122",
                                     "0122"));
    layouts(3)->push_back(TileLayout("0022",
                                     "0022",
                                     "1122"));
    layouts(3)->push_back(TileLayout("0011",
                                     "0011",
                                     "0022"));
    layouts(3)->push_back(TileLayout("0011",
                                     "0011",
                                     "2222"));
    layouts(3)->push_back(TileLayout("0111",
                                     "0111",
                                     "0222"));
    layouts(3)->push_back(TileLayout("0001",
                                     "0001",
                                     "2221"));

    // 4 photo layouts.
    AddLayouts(4, 3);
    layouts(4)->push_back(TileLayout("0012",
                                     "0012",
                                     "0013"));
    layouts(4)->push_back(TileLayout("0112",
                                     "0112",
                                     "0113"));
    layouts(4)->push_back(TileLayout("0133",
                                     "0133",
                                     "0233"));
    layouts(4)->push_back(TileLayout("0011",
                                     "0011",
                                     "0023"));
    layouts(4)->push_back(TileLayout("0012",
                                     "0012",
                                     "0033"));
    layouts(4)->push_back(TileLayout("0011",
                                     "0022",
                                     "0033"));
    layouts(4)->push_back(TileLayout("0001",
                                     "0002",
                                     "0003"));
    layouts(4)->push_back(TileLayout("0133",
                                     "0133",
                                     "2233"));
    layouts(4)->push_back(TileLayout("0033",
                                     "0033",
                                     "1233"));
    layouts(4)->push_back(TileLayout("0033",
                                     "1133",
                                     "2233"));
    layouts(4)->push_back(TileLayout("0333",
                                     "1333",
                                     "2333"));

    // 5 photo layouts.
    AddLayouts(5, 4);
    layouts(5)->push_back(TileLayout("0012",
                                     "0012",
                                     "0034"));
    layouts(5)->push_back(TileLayout("0013",
                                     "0023",
                                     "0024"));
    layouts(5)->push_back(TileLayout("0013",
                                     "0014",
                                     "0024"));
    layouts(5)->push_back(TileLayout("0144",
                                     "0144",
                                     "2344"));
    layouts(5)->push_back(TileLayout("0244",
                                     "1244",
                                     "1344"));
    layouts(5)->push_back(TileLayout("0244",
                                     "0344",
                                     "1344"));
    layouts(6)->push_back(TileLayout("0011",
                                     "0011",
                                     "2234"));
    layouts(6)->push_back(TileLayout("0011",
                                     "0011",
                                     "2344"));

    // 6 photo layouts.
    AddLayouts(6, 5);
    layouts(6)->push_back(TileLayout("0023",
                                     "0023",
                                     "1145"));
    layouts(6)->push_back(TileLayout("0122",
                                     "0122",
                                     "3345"));
    layouts(6)->push_back(TileLayout("0022",
                                     "0033",
                                     "1145"));
    layouts(6)->push_back(TileLayout("0022",
                                     "1122",
                                     "3345"));
    layouts(6)->push_back(TileLayout("0011",
                                     "0011",
                                     "2345"));
    layouts(6)->push_back(TileLayout("0012",
                                     "0055",
                                     "3455"));
    layouts(6)->push_back(TileLayout("0133",
                                     "2233",
                                     "2245"));
    layouts(6)->push_back(TileLayout("0001",
                                     "0001",
                                     "2345"));
    layouts(6)->push_back(TileLayout("0111",
                                     "0111",
                                     "2345"));

    // 7 photo layouts
    AddLayouts(7, 6);
    layouts(7)->push_back(TileLayout("0112",
                                     "0112",
                                     "3456"));
    layouts(7)->push_back(TileLayout("0001",
                                     "0002",
                                     "3456"));
    layouts(7)->push_back(TileLayout("0111",
                                     "2111",
                                     "3456"));
  }

 private:
  vector<TileLayout>* layouts(int i) {
    return &(*this)[i - 1];
  }

  void AddLayouts(int dest, int src) {
    vector<TileLayout>* dest_vec = layouts(dest);
    vector<TileLayout>* src_vec = layouts(src);
    dest_vec->insert(dest_vec->end(), src_vec->begin(), src_vec->end());
  }
};

struct SummaryTileLayouts4x2 : public std::vector<std::vector<TileLayout> > {
  SummaryTileLayouts4x2()
      : std::vector<std::vector<TileLayout> >(5, std::vector<TileLayout>()) {
    std::vector<std::vector<TileLayout> >& v = *this;

    // 1 photo layouts.
    v[0].push_back(TileLayout("0000",
                              "0000"));

    // 2 photo layouts.
    v[1].push_back(TileLayout("0011",
                              "0011"));
    v[1].push_back(TileLayout("0001",
                              "0001"));
    v[1].push_back(TileLayout("0111",
                              "0111"));

    // 3 photo layouts.
    v[2].push_back(TileLayout("0012",
                              "0012"));
    v[2].push_back(TileLayout("0112",
                              "0112"));
    v[2].push_back(TileLayout("0122",
                              "0122"));
    v[2].push_back(TileLayout("0011",
                              "0022"));
    v[2].push_back(TileLayout("0022",
                              "1122"));

    // 4 photo layouts.
    v[3].push_back(TileLayout("0012",
                              "0013"));
    v[3].push_back(TileLayout("0112",
                              "0113"));
    v[3].push_back(TileLayout("0133",
                              "0233"));
    v[3].push_back(TileLayout("0011",
                              "0023"));
    v[3].push_back(TileLayout("0012",
                              "0033"));
    v[3].push_back(TileLayout("0033",
                              "1233"));
    v[3].push_back(TileLayout("0133",
                              "2233"));

    // 5 photo layouts.
    v[4].push_back(TileLayout("0013",
                              "0024"));
    v[4].push_back(TileLayout("0144",
                              "2344"));
    v[4].push_back(TileLayout("0012",
                              "0012"));
    v[4].push_back(TileLayout("0122",
                              "0122"));
    v[4].push_back(TileLayout("0011",
                              "0022"));
    v[4].push_back(TileLayout("0022",
                              "1122"));
  }
};

struct SummaryTileLayouts4x1 : public std::vector<std::vector<TileLayout> > {
  SummaryTileLayouts4x1()
      : std::vector<std::vector<TileLayout> >(4, std::vector<TileLayout>()) {
    std::vector<std::vector<TileLayout> >& v = *this;

    // 1 photo layouts.
    v[0].push_back(TileLayout("0000"));

    // 2 photo layouts.
    v[1].push_back(TileLayout("0011"));

    // 3 photo layouts.
    v[2].push_back(TileLayout("0012"));
    v[2].push_back(TileLayout("0112"));
    v[2].push_back(TileLayout("0122"));

    // 4 photo layouts.
    v[3].push_back(TileLayout("0123"));
  }
};

struct SummaryTileLayouts3x1 : public std::vector<std::vector<TileLayout> > {
  SummaryTileLayouts3x1()
      : std::vector<std::vector<TileLayout> >(3, std::vector<TileLayout>()) {
    std::vector<std::vector<TileLayout> >& v = *this;

    // 1 photo layouts.
    v[0].push_back(TileLayout("000"));

    // 2 photo layouts.
    v[1].push_back(TileLayout("001"));
    v[1].push_back(TileLayout("011"));

    // 3 photo layouts.
    v[2].push_back(TileLayout("012"));
  }
};

LazyStaticPtr<SummaryTileLayouts4x3> kSummaryTileLayouts4x3;
LazyStaticPtr<SummaryTileLayouts4x2> kSummaryTileLayouts4x2;
LazyStaticPtr<SummaryTileLayouts4x1> kSummaryTileLayouts4x1;
LazyStaticPtr<SummaryTileLayouts3x1> kSummaryTileLayouts3x1;

////
// From backend/resources/static/js/views.js

const int kMaxRowsPerCombo = 3;
const int kMaxRowCombos = 30;
const float kMinPhotoRowAspectSmall = 9.0 / 2.5;
const float kMaxPhotoRowAspectSmall = 9.0 / 1.25;
const float kMinPhotoRowAspectLarge = 9.0 / 5.0;
const float kMaxPhotoRowAspectLarge = 9.0 / 2.5;

// Rows used for layout are vectors of floating point aspect ratios.
struct PhotoRow {
  vector<float> photos;
  float total_aspect_ratio;
  float score;

  PhotoRow()
      : total_aspect_ratio(0),
        score(0) {
  }

  void AddPhoto(float aspect_ratio, float min_aspect, float max_aspect) {
    photos.push_back(aspect_ratio);
    total_aspect_ratio += aspect_ratio;
    if (total_aspect_ratio > max_aspect) {
      score = pow(10, (total_aspect_ratio / max_aspect)) - 10;
    } else if (total_aspect_ratio < min_aspect) {
      score = pow(10, (min_aspect / total_aspect_ratio)) - 10;
    } else {
      score = 0;
    }
  }
};

// A combination of up to three photo rows.
struct RowCombo {
  PhotoRow rows[kMaxRowsPerCombo];
  int count;
  float score;

  RowCombo()
      : count(0),
        score(0) {
  }

  void AddRow(const PhotoRow& row) {
    DCHECK_LT(count, kMaxRowsPerCombo);
    rows[count++] = row;
    score += row.score;
  }

  bool operator<(const RowCombo& other) const {
    return score < other.score;
  }
};

// Structure to store over-height rows.
struct OverheightRow {
  PhotoRow row;     // list of photo aspect ratios in overheight row.
  int start_index;  // starting index into the master list of photo aspect ratios.

  OverheightRow()
      : start_index(-1) {
  }
};

// Recursively consider possible combinations of photo layouts.
void RecurseRowCombos(
    const vector<float>& aspect_ratios, const RowCombo& partial,
    int index, vector<RowCombo>* combos, float min_aspect, float max_aspect) {
  // Consider a maximum number of combinations for any iteration of this.
  if (combos->size() >= kMaxRowCombos) {
    return;
  }

  // If the partial combo contains three rows OR we're out of photos,
  // this combination is complete.
  if (partial.count == kMaxRowsPerCombo || index == aspect_ratios.size()) {
    combos->push_back(partial);
    return;
  }

  // For the current partial combination, compute possibilities for
  // the next row. We will consider each row of ideal height, plus up
  // to one overheight and one underheight row.
  PhotoRow row;
  float aspect = 0.0;
  OverheightRow overheight;

  for (int i = index; i < aspect_ratios.size(); ++i) {
    row.AddPhoto(aspect_ratios[i], min_aspect, max_aspect);

    // Calculate ideal height of this row, preserving aspect.
    aspect += aspect_ratios[i];

    if (aspect < min_aspect) {
      overheight.row = row;
      overheight.start_index = i;
    } else {
      // Add this row to the current partial combination and calculate
      // the next set of possible rows.
      RowCombo recurse_combo = partial;
      recurse_combo.AddRow(row);
      RecurseRowCombos(aspect_ratios, recurse_combo, i + 1,
                       combos, min_aspect, max_aspect);
      if (aspect < max_aspect) {
        break;
      }
    }
  }

  if (overheight.start_index != -1) {
    RowCombo recurse_combo = partial;
    recurse_combo.AddRow(overheight.row);
    RecurseRowCombos(aspect_ratios, recurse_combo, overheight.start_index + 1,
                     combos, min_aspect, max_aspect);
  }
}

float PreserveAspectRatioTileLayout(
    const vector<float>& aspect_ratios, vector<CGRect>* frames, int* num_rows,
    float group_width, float spacing,
    float minimum_aspect_ratio, float min_aspect, float max_aspect) {
  if (num_rows) {
    *num_rows = 0;
  }
  int index = 0;
  float y = 0;

  while (index < aspect_ratios.size()) {
    // To determine the next row, lay out the next three rows in ideal
    // fashion and take the first row.  This is accomplished by
    // calculating a number of possible combinations for the next
    // three rows and scoring each combination.  The first row of the
    // highest scoring combination will be accepted.

    // Completed candidate combinations. A combination is an array of
    // rows. Each row is an array of photos.
    RowCombo partial;
    vector<RowCombo> combos;

    // Starting with an empty row combination, recursively find a list
    // of good candidates.
    RecurseRowCombos(aspect_ratios, partial, index, &combos, min_aspect, max_aspect);

    // Sort row combinations by total score.
    std::sort(combos.begin(), combos.end());

    // Take the best combo's first row of photos as next row.
    const PhotoRow& row = combos[0].rows[0];

    // Truncate the height to an integral value to ensure that photo frames are
    // placed on integer boundaries. This avoids discrepancies between the
    // photo position and labels placed on top of the photos by the
    // ViewfinderTool.
    const int n = row.photos.size();
    const float total_width = group_width - spacing * (n - 1);
    const float ideal_h = ceil(total_width / row.total_aspect_ratio);
    const float actual_h = ceil(total_width / std::max<float>(minimum_aspect_ratio, row.total_aspect_ratio));
    float x = 0;

    for (int j = 0; j < n; ++j) {
      CGRect* f = &(*frames)[index + j];
      float w = (j == n - 1) ? group_width - x : ideal_h * row.photos[j];
      *f = CGRectMake(x, y, w, actual_h);
      x = CGRectGetMaxX(*f) + spacing;
    }

    index += n;
    y += actual_h + (index == aspect_ratios.size() ? 0 : spacing);
    if (num_rows) {
      *num_rows += 1;
    }
  }

  return y;
}

}  // namespace

TileLayout::TileLayout(const char* row1, const char* row2, const char* row3)
    : nrows_(1 + (row2 != NULL) + (row3 != NULL)),
      ncols_(strlen(row1)) {
  const char* g[] = { row1, row2, row3 };
  if (row2) {
    CHECK_EQ(ncols_, strlen(row2));
  }
  if (row3) {
    CHECK_EQ(ncols_, strlen(row3));
  }

  int ntiles = 0;
  for (int r = 0; r < nrows_; ++r) {
    for (int c = 0; c < ncols_; ++c) {
      ntiles = std::max<int>(ntiles, 1 + (g[r][c] - '0'));
    }
  }
  CHECK_GE(ntiles, 0);
  tiles_.resize(ntiles, Tile());

  for (int r = 0; r < nrows_; ++r) {
    for (int c = 0; c < ncols_; ++c) {
      Tile* t = &tiles_[g[r][c] - '0'];
      t->min_col = std::min(t->min_col, c);
      t->max_col = std::max(t->max_col, c);
      t->min_row = std::min(t->min_row, r);
      t->max_row = std::max(t->max_row, r);
    }
  }

  for (int i = 0; i < tiles_.size(); ++i) {
    const Tile& t = tiles_[i];
    CHECK_LT(t.min_col, ncols_);
    CHECK_GE(t.max_col, 0);
    CHECK_LT(t.min_row, nrows_);
    CHECK_GE(t.max_row, 0);
  }
}

void TileLayout::Apply(vector<CGRect>* frames, float tile_width,
                       float tile_height, float tile_spacing) const {
  for (int i = 0; i < frames->size(); ++i) {
    Tile t;
    if (i < tiles_.size()) {
      t = tiles_[i];
    } else {
      const int j = i - tiles_.size();
      t.min_col = t.max_col = 4 + (j / 2);
      t.min_row = t.max_row = j % 2;
    }

    // Adjust the width and height if this tile does not cover the last
    // col/row.
    const float width_adjust = tile_spacing * (1 + t.max_col < ncols_);
    const float height_adjust = tile_spacing * (1 + t.max_row < nrows_);
    (*frames)[i] = CGRectMake(
        t.min_col * tile_width,
        t.min_row * tile_height,
        (1 + t.max_col - t.min_col) * tile_width - width_adjust,
        (1 + t.max_row - t.min_row) * tile_height - height_adjust);
  }
}

const TileLayout* TileLayout::Select(
    const std::vector<TileLayout>& layouts,
    const vector<float>& aspect_ratios, int seed) {
  // Gather the best layouts.
  std::vector<const TileLayout*> best_layouts;
  float best_score = -1;

  for (int i = 0; i < layouts.size(); ++i) {
    const float score = layouts[i].Score(aspect_ratios);
    if (best_score < score) {
      best_score = score;
      best_layouts.clear();
      best_layouts.push_back(&layouts[i]);
    } else if (best_score == score) {
      best_layouts.push_back(&layouts[i]);
    }
  }

  if (best_layouts.size() > 1) {
    // Shuffle the best layouts.

    // TODO(pmattis): Instead of using random shuffle, provide a weight for
    // each layout and randomly pick based on the weight.
    Random r(seed);
    std::random_shuffle(best_layouts.begin(), best_layouts.end(), r);
  }

  return best_layouts[0];
}

const TileLayout* TileLayout::Select4x3(
    const vector<float>& aspect_ratios, int seed) {
  const int n = std::min<int>(
      kSummaryTileLayouts4x3->size(), aspect_ratios.size());
  return Select((*kSummaryTileLayouts4x3)[n - 1], aspect_ratios, seed);
}

const TileLayout* TileLayout::Select4x2(
    const vector<float>& aspect_ratios, int seed) {
  const int n = std::min<int>(
      kSummaryTileLayouts4x2->size(), aspect_ratios.size());
  return Select((*kSummaryTileLayouts4x2)[n - 1], aspect_ratios, seed);
}

const TileLayout* TileLayout::Select4x1(
    const vector<float>& aspect_ratios, int seed) {
  const int n = std::min<int>(
      kSummaryTileLayouts4x1->size(), aspect_ratios.size());
  return Select((*kSummaryTileLayouts4x1)[n - 1], aspect_ratios, seed);
}

const TileLayout* TileLayout::Select3x1(
    const vector<float>& aspect_ratios, int seed) {
  const int n = std::min<int>(
      kSummaryTileLayouts3x1->size(), aspect_ratios.size());
  return Select((*kSummaryTileLayouts3x1)[n - 1], aspect_ratios, seed);
}

float TileLayout::Score(const vector<float>& aspect_ratios) const {
  float score = 0;
  for (int i = 0; i < tiles_.size(); ++i) {
    const float photo_aspect_ratio = aspect_ratios[i];
    const float tile_aspect_ratio =
        (1.0 + tiles_[i].max_col - tiles_[i].min_col) /
        (1.0 + tiles_[i].max_row - tiles_[i].min_row);
    // We calculate the visible fraction of the photo given its aspect ratio
    // and the proposed tile aspect ratio. The photo is a rectangle that is
    // photo_aspect_ratio x 1. The tile is a rectangle that is
    // tile_aspect_ratio x 1.
    if (photo_aspect_ratio <= tile_aspect_ratio) {
      // If photo_aspect_ratio is <= tile_aspect_ratio we have to scale the
      // photo up to fill in the tile rectangle. The scale factor is:
      //   tile_aspect_ratio / photo_aspect_ratio.
      //
      // The area the photo now covers is its new width (photo_aspect_ratio *
      // s) times its new height (1 * s). This reduces down to:
      //   tile_aspect_ratio * tile_aspect_ratio / photo_aspect_ratio;
      //
      // Divide the area of the tile rectangle (tile_aspect_ratio * 1) by the
      // area of the photo rectangle produces:
      score += photo_aspect_ratio / tile_aspect_ratio;
    } else {
      // The photo_aspect_ratio is > tile_aspect_ratio. The photo already fills
      // the tile rectangle in both width and height. Just need to divide the
      // area of the tile rectangle (tile_aspect_ratio * 1) by the area of the
      // photo rectangle (photo_aspect_ratio * 1).
      score += tile_aspect_ratio / photo_aspect_ratio;
    }
  }
  return score;
}

float ShareLayout::Apply(
    const vector<float>& aspect_ratios, vector<CGRect>* frames, int* num_rows,
    float group_width, float spacing, float minimum_aspect_ratio) {
  return PreserveAspectRatioTileLayout(
      aspect_ratios, frames, num_rows, group_width, spacing, minimum_aspect_ratio,
      kMinPhotoRowAspectLarge, kMaxPhotoRowAspectLarge);
}

float EventLayout::Apply(
    const vector<float>& aspect_ratios, vector<CGRect>* frames, int* num_rows,
    float group_width, float spacing, float minimum_aspect_ratio) {
  return PreserveAspectRatioTileLayout(
      aspect_ratios, frames, num_rows, group_width, spacing, minimum_aspect_ratio,
      kMinPhotoRowAspectLarge, kMaxPhotoRowAspectLarge);
}

float InboxCardLayout::Apply(
    const vector<float>& aspect_ratios, vector<CGRect>* frames, int* num_rows,
    float group_width, float spacing, float minimum_aspect_ratio) {
  return PreserveAspectRatioTileLayout(
      aspect_ratios, frames, num_rows, group_width, spacing, minimum_aspect_ratio,
      kMinPhotoRowAspectSmall, kMaxPhotoRowAspectSmall);
}

float InboxCardLayout::ApplyExpanded(
    const vector<float>& aspect_ratios, vector<CGRect>* frames, int* num_rows,
    float group_width, float spacing, float minimum_aspect_ratio) {
  return PreserveAspectRatioTileLayout(
      aspect_ratios, frames, num_rows, group_width, spacing, minimum_aspect_ratio,
      kMinPhotoRowAspectLarge, kMaxPhotoRowAspectLarge);
}

// local variables:
// mode: c++
// end:

// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_TILE_LAYOUT_H
#define VIEWFINDER_TILE_LAYOUT_H

#import <limits>
#import <vector>
#import <CoreGraphics/CGGeometry.h>

class TileLayout {
  struct Tile {
    Tile()
        : min_col(std::numeric_limits<int>::max()),
          max_col(std::numeric_limits<int>::min()),
          min_row(std::numeric_limits<int>::max()),
          max_row(std::numeric_limits<int>::min()) {
    }
    int min_col;
    int max_col;
    int min_row;
    int max_row;
  };

 public:
  TileLayout(const char* row1, const char* row2 = NULL,
             const char* row3 = NULL);

  void Apply(vector<CGRect>* frames, float tile_width,
             float tile_height, float tile_spacing) const;

  static const TileLayout* Select(
      const std::vector<TileLayout>& layouts,
      const vector<float>& aspect_ratios, int seed);
  static const TileLayout* Select4x3(
      const vector<float>& aspect_ratios, int seed);
  static const TileLayout* Select4x2(
      const vector<float>& aspect_ratios, int seed);
  static const TileLayout* Select4x1(
      const vector<float>& aspect_ratios, int seed);
  static const TileLayout* Select3x1(
      const vector<float>& aspect_ratios, int seed);

  int size() const { return tiles_.size(); }

 private:
  float Score(const vector<float>& aspect_ratios) const;

 private:
  std::vector<Tile> tiles_;
  int nrows_;
  int ncols_;
};

// Maximally preserve aspect ratios.
class ShareLayout {
 public:
  // Returns the total height of the layout.
  static float Apply(const vector<float>& aspect_ratios, vector<CGRect>* frames, int* num_rows,
                     float group_width, float spacing, float minimum_aspect_ratio);
};

class EventLayout {
 public:
  // Returns the total height of the layout.
  static float Apply(const vector<float>& aspect_ratios, vector<CGRect>* frames, int* num_rows,
                     float group_width, float spacing, float minimum_aspect_ratio);
};

class InboxCardLayout {
 public:
  // Returns the total height of the layout.
  static float Apply(const vector<float>& aspect_ratios, vector<CGRect>* frames, int* num_rows,
                     float group_width, float spacing, float minimum_aspect_ratio);
  static float ApplyExpanded(const vector<float>& aspect_ratios, vector<CGRect>* frames, int* num_rows,
                             float group_width, float spacing, float minimum_aspect_ratio);
};

#endif // VIEWFINDER_TILE_LAYOUT_H

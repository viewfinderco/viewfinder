// Copyright 2013 Viewfinder. All rights reserved.
// Author: Andy Kimball
package co.viewfinder.widgets;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Rect;
import android.util.AttributeSet;
import android.util.Log;
import android.view.View;
import junit.framework.Assert;

import java.util.ArrayList;
import java.util.Random;

/**
 * This widget lays out a set of images using an algorithm that attempts to minimize cropping
 * by preserving aspect ratios of the images. It does this by generating a number of different
 * possible row combinations, scoring each combination, and picking the combination with the
 * best score. The best score is the score that results in the least cropping. All photos in
 * a particular row are scaled to fit a single height; heights of rows may vary according to
 * the width of the screen and the min and max row aspect ratios.
 *
 * The adapter allows the layout to ask for bitmaps "just-in-time" when they become visible on
 * the screen. Since no bitmaps are cached by this class, its direct memory usage is minimal.
 */
public class ImageAspectLayout extends View {
  private static final int MAX_COMBOS = 20;
  private static final int MAX_ROWS_PER_COMBO = 3;
  private static final float DEFAULT_MIN_ROW_ASPECT = 9f / 5f;
  private static final float DEFAULT_MAX_ROW_ASPECT = 9f / 2.5f;
  private static final int DEFAULT_BORDER_SIZE = 1;
  private static final boolean DEBUG_COMBOS = false;

  private Adapter mAdapter;
  private int mImageCount;
  private float mMinRowAspect;
  private float mMaxRowAspect;
  private int mBorderSize;
  private ArrayList<Row> mLayoutRows;
  private int mMeasuredWidth;
  private int mMeasuredHeight;
  private Random mRandom;

  private Combo mBestCombo;
  private int mCombosGenerated;
  private Combo mPartialCombo;
  private int mSameScoreCount;

  public interface Adapter {
    public int count();

    public float getAspect(int index);

    public Bitmap getImage(int index, int minSuggestedHeight);
  }

  public ImageAspectLayout(Context context) {
    super(context);
    init();
  }

  public ImageAspectLayout(Context context, AttributeSet attrs) {
    super(context, attrs);
    init();
  }

  private void init() {
    mPartialCombo = new Combo();
    mLayoutRows = new ArrayList<Row>();
    mMinRowAspect = DEFAULT_MIN_ROW_ASPECT;
    mMaxRowAspect = DEFAULT_MAX_ROW_ASPECT;
    mMeasuredWidth = -1;
    mBorderSize = DEFAULT_BORDER_SIZE;
  }

  public void setAdapter(Adapter adapter) {
    Assert.assertNull("Adapter can be set only once.", mAdapter);
    mAdapter = adapter;
    mImageCount = adapter.count();
    mRandom = new Random(mImageCount);
  }

  public float getMinRowAspect() {
    return mMinRowAspect;
  }

  /**
   * Sets the minimum aspect ratio of an entire row of images.
   */
  public void setMinRowAspect(float aspectRatio) {
    mMinRowAspect = aspectRatio;
  }

  public float getMaxRowAspect() {
    return mMaxRowAspect;
  }

  /**
   * Sets the maximum aspect ratio of an entire row of images.
   */
  public void setMaxRowAspect(float aspectRatio) {
    mMaxRowAspect = aspectRatio;
  }

  public int getBorderSize() {
    return mBorderSize;
  }

  /**
   * Sets the size of the border, in pixels.
   */
  public void setBorderSize(int borderSize) {
    mBorderSize = borderSize;
  }

  @Override
  protected void onMeasure(int widthMeasureSpec, int heightMeasureSpec) {
    // Fill any available width.
    int measuredWidth = MeasureSpec.getSize(widthMeasureSpec);

    // Don't re-measure everything unless width changes.
    if (mMeasuredWidth != measuredWidth) {
      mMeasuredWidth = measuredWidth;

      // From the full list of images, repeatedly carve off individual rows. Rows will be
      // selected to ensure a minimal amount of cropping while maintaining the aspect ratio of
      // each individual bitmap.
      int imageIndex = 0;
      while (imageIndex < mImageCount) {
        // To determine the next row, lay out the next three rows in ideal fashion and take the first row.
        // This is accomplished by calculating a number of possible combinations for the next three rows
        // and scoring each combination.  The first row of the highest scoring combination will be accepted.
        Assert.assertTrue(mPartialCombo.size() == 0);
        mBestCombo = null;
        mCombosGenerated = 0;
        mSameScoreCount = 0;

        if (DEBUG_COMBOS) {
          Log.d("DebugCombos", "ROW #" + (mLayoutRows.size() + 1));
        }

        generateCombos(imageIndex);

        // Add first row from highest scoring combo to the list of rows for layout.
        Row row = mBestCombo.getRow(0);
        mLayoutRows.add(row);

        // Skip past images that are already laid out.
        imageIndex += row.size();
      }

      // Calculate total height by adding together height of all rows.
      mMeasuredHeight = 0;

      for (int i = 0; i < mLayoutRows.size(); i++) {
        Row row = mLayoutRows.get(i);
        row.measure(mMeasuredWidth);
        mMeasuredHeight += row.getMeasuredHeight();
        mMeasuredHeight += mBorderSize;
      }
    }

    // Height may be constrained by container.
    int measuredHeight = mMeasuredHeight;
    switch (MeasureSpec.getMode(heightMeasureSpec)) {
      case MeasureSpec.AT_MOST:
        measuredHeight = Math.min(mMeasuredHeight, MeasureSpec.getSize(heightMeasureSpec));
        break;

      case MeasureSpec.EXACTLY:
        measuredHeight = MeasureSpec.getSize(heightMeasureSpec);
        break;
    }

    setMeasuredDimension(measuredWidth, measuredHeight);
  }

  @Override
  protected void onLayout(boolean changed, int left, int top, int right, int bottom) {
    super.onLayout(changed, left, top, right, bottom);

    if (changed) {
      // Layout each row.
      for (int i = 0; i < mLayoutRows.size(); i++) {
        Row row = mLayoutRows.get(i);
        row.layout(left, top);
        top += row.getMeasuredHeight() + mBorderSize;
      }
    }
  }

  @Override
  protected void onDraw(Canvas canvas) {
    super.onDraw(canvas);

    // Skip rows that are not in the canvas clipping bounds.
    Rect bounds = canvas.getClipBounds();
    for (int i = 0; i < mLayoutRows.size(); i++) {
      Row row = mLayoutRows.get(i);

      if (row.getLayoutTop() + row.getMeasuredHeight() <= bounds.top) {
        // Before the canvas bounds, so skip to next row.
        continue;
      }

      if (row.getLayoutTop() >= bounds.bottom) {
        // After the canvas bounds, so no more to do.
        break;
      }

      row.draw(canvas);
    }
  }

  /**
   * Recursive function to find all viable candidate combinations for laying out the next
   * three rows.
   */
  private void generateCombos(int imageIndex) {
    if (mCombosGenerated >= MAX_COMBOS) {
      // Consider a maximum of 30 combinations for any iteration of this.
      return;
    }

    if (mPartialCombo.size() == MAX_ROWS_PER_COMBO || imageIndex == mImageCount) {
      // If the partial combo contains max rows OR we are out of images, this combination
      // is complete.
      StringBuilder builder = null;
      if (DEBUG_COMBOS) {
        builder = new StringBuilder();
        builder.append('[');
        builder.append(mPartialCombo.computeScore());
        builder.append("] ");

        for (int i = 0; i < mPartialCombo.size(); i++) {
          if (i != 0) {
            builder.append(", ");
          }

          Row row = mPartialCombo.getRow(i);
          builder.append(row.startIndex());
          builder.append(" - ");
          builder.append(row.startIndex() + row.size() - 1);
        }
      }

      // Increment number of combos that have been generated.
      mCombosGenerated++;

      float scoreDiff = mBestCombo == null ? -1f : mPartialCombo.computeScore() - mBestCombo.computeScore();

      // Pseudo-randomly decide whether to select between combos of equal score.
      if (scoreDiff == 0f) {
        mSameScoreCount++;
        int randomInt = mRandom.nextInt(mSameScoreCount);
        scoreDiff = (randomInt == 0) ? -1 : 1;
      } else if (scoreDiff < 0f) {
        mSameScoreCount = 1;
      }

      if (scoreDiff < 0f) {
        // Found new best combo, so save it (as a clone, since the partial combo wil continue
        // to be modified during combo generation.
        mBestCombo = mPartialCombo.clone();
      }

      if (DEBUG_COMBOS) {
        if (scoreDiff < 0f) {
          // Indicate in the log that the combo was selected as current best.
          builder.append(" ***");
        }

        Log.d("DebugCombos", builder.toString());
      }

      return;
    }

    // For the current partial combination, compute possibilities for the next row.  We will
    // consider each row of ideal height, plus up to one overheight and one underheight row.
    Row row = new Row(imageIndex);
    int overHeightSize = 0;

    for (int i = imageIndex; i < mImageCount; i++) {
      // Add photo to next row under consideration.
      row.addImage();

      if (row.getAspect() < mMinRowAspect) {
        overHeightSize++;
      } else {
        // Add this row to the current partial combination and calculate the next set of
        // possible rows.
        mPartialCombo.addRow(row.clone());
        generateCombos(i + 1);
        mPartialCombo.removeRow();

        if (row.getAspect() > mMaxRowAspect) {
          break;
        }
      }
    }

    if (overHeightSize > 0) {
      mPartialCombo.addRow(new Row(imageIndex, overHeightSize));
      generateCombos(imageIndex + overHeightSize);
      mPartialCombo.removeRow();
    }
  }

  /**
   * A combination holds onto several rows that are scored as a unit in terms of how much
   * cropping is necessary to keep the aspect ratios of the rows within limited bounds.
   */
  private class Combo {
    private static final int MAX_SIZE = 3;

    private Row[] mRows;
    private int mSize;
    private float mScore;

    public Combo() {
      mRows = new Row[MAX_SIZE];
      mScore = -1f;
    }

    /**
     * Copy constructor.
     */
    private Combo(Combo combo) {
      mRows = combo.mRows.clone();
      mSize = combo.mSize;
      mScore = combo.mScore;
    }

    public int size() {
      return mSize;
    }

    public void addRow(Row row) {
      mRows[mSize++] = row;
      mScore = -1f;
    }

    public void removeRow() {
      mSize--;
      mScore = -1f;
    }

    public Row getRow(int index) {
      return mRows[index];
    }

    /**
     * Function to determine the total score of a possible row combination. For now, it is
     * just the sum of the individual row scores.
     */
    public float computeScore() {
      if (mScore == -1f) {
        mScore = 0f;
        for (int i = 0; i < mSize; i++) {
          mScore += mRows[i].computeScore();
        }
      }

      return mScore;
    }

    /**
     * Returns clone of this combo. Rows are assumed to be idempotent at this point, so
     * only the list of rows is cloned.
     */
    public Combo clone() {
      return new Combo(this);
    }
  }

  /**
   * A row encapsulates a slice of images in the layout. The aspect ratio of the row is equal
   * to the sum of the aspect ratios of its images. The row is able to measure, layout, and
   * draw its images.
   */
  private class Row implements Cloneable {
    private int mStartIndex;
    private int mSize;
    private float mAspect;
    private int mMeasuredWidth;
    private int mMeasuredHeight;
    private int mLayoutTop;
    private int[] mLayoutLeftOffsets;
    private Rect mSourceRect;
    private Rect mDestRect;

    public Row(int startIndex) {
      this(startIndex, 0);
    }

    public Row(int startIndex, int size) {
      Assert.assertTrue(size >= 0);

      mStartIndex = startIndex;

      // If size > 0, add additional images.
      for (int i = size; i > 0; i--) {
        addImage();
      }
    }

    public int size() {
      return mSize;
    }

    public int startIndex() {
      return mStartIndex;
    }

    public float getAspect() {
      return mAspect;
    }

    /**
     * Width of the entire rows, in pixels. This is only valid after a call to "measure".
     */
    public int getMeasuredWidth() {
      return mMeasuredWidth;
    }

    /**
     * Height of the entire rows, in pixels. This is only valid after a call to "measure".
     */
    public int getMeasuredHeight() {
      return mMeasuredHeight;
    }

    public int getLayoutTop() {
      return mLayoutTop;
    }

    public void addImage() {
      Assert.assertTrue("No more images to add.", mStartIndex + mSize < mImageCount);
      Assert.assertNotNull("Adapter must be set.", mAdapter);

      // Incrementally calculate ideal height of this row, preserving aspect.
      mAspect += mAdapter.getAspect(mStartIndex + mSize);

      mSize++;
    }

    public void measure(int pixelWidth) {
      mMeasuredWidth = pixelWidth;

      // Get bounded aspect ratio and use that to compute the height in pixels.
      float aspect = Math.min(Math.max(mAspect, mMinRowAspect), mMaxRowAspect);
      mMeasuredHeight = (int)Math.ceil((double)getNoBorderWidth() / (double)aspect);
    }

    public void layout(int left, int top) {
      float widthError = 0f;
      float exactImageHeight = (float)getNoBorderWidth() / mAspect;
      int endIndex = mStartIndex + mSize;

      if (mLayoutLeftOffsets == null || mLayoutLeftOffsets.length != mSize) {
        mLayoutLeftOffsets = new int[mSize];
      }

      for (int i = mStartIndex; i < endIndex; i++) {
        // Compute width of image -- its width is proportional to the ratio of its aspect
        // and the aspect of the row.
        float exactImageWidth = exactImageHeight * mAdapter.getAspect(i);

        // Accumulate width error and make adjustments as it exceeds a pixel.
        int imageWidth = (int)exactImageWidth;
        widthError += exactImageWidth - imageWidth;
        if (widthError >= 1.0f) {
          widthError--;
          imageWidth++;
        }

        // Make sure to use the very last pixel if there is rounding error.
        if (i == endIndex - 1) {
          imageWidth = mMeasuredWidth - left;
        }

        // Save left offsets of each image to be used in "draw".
        mLayoutLeftOffsets[i - mStartIndex] = left;

        // Draw next item after border allowance.
        left += imageWidth + mBorderSize;
      }

      mLayoutTop = top;
    }

    public void draw(Canvas canvas) {
      // Lazily create the rects.
      if (mSourceRect == null) mSourceRect = new Rect();
      if (mDestRect == null) mDestRect = new Rect();

      int endIndex = mStartIndex + mSize;
      for (int i = mStartIndex; i < endIndex; i++) {
        Bitmap image = mAdapter.getImage(i, mMeasuredHeight);

        // Set source bounds using center cropping.
        if (mAspect > mMaxRowAspect) {
          // Compute percentage of image width that needs to be cropped.
          float cropPercentage = mMaxRowAspect / mAspect;

          float width = (float)image.getWidth() * cropPercentage;
          float offset = ((float)image.getWidth() - width) / 2f;
          mSourceRect.set((int)offset, 0, (int)(offset + width), image.getHeight());
        } else if (mAspect < mMinRowAspect) {
          // Compute percentage of image height that needs to be cropped.
          float cropPercentage = mAspect / mMinRowAspect;

          float height = (float)image.getHeight() * cropPercentage;
          float offset = ((float)image.getHeight() - height) / 2f;
          mSourceRect.set(0, (int)offset, image.getWidth(), (int)(offset + height));
        } else {
          mSourceRect.set(0, 0, image.getWidth(), image.getHeight());
        }

        // Set destination bounds.
        int left = mLayoutLeftOffsets[i - mStartIndex];
        int right = (i == endIndex - 1) ? mMeasuredWidth : mLayoutLeftOffsets[i - mStartIndex + 1] - mBorderSize;
        mDestRect.set(left, mLayoutTop, right, mLayoutTop + mMeasuredHeight);

        canvas.drawBitmap(image, mSourceRect, mDestRect, null);
      }
    }

    /**
     * Function to determine the 'score' of a single potential row.  0 is a perfect score,
     * higher is worse.
     */
    public float computeScore() {
      if (mAspect > mMaxRowAspect) {
        return (float)Math.pow(10, mAspect / mMaxRowAspect) - 10f;
      }

      if (mAspect < mMinRowAspect) {
        return (float)Math.pow(10, (mMinRowAspect / mAspect)) - 10f;
      }

      return 0f;
    }

    public Row clone() {
      try {
        return (Row)super.clone();
      }
      catch (CloneNotSupportedException ex) {
        Assert.fail("Should never get here.");
        return null;
      }
    }

    private int getNoBorderWidth() {
      return mMeasuredWidth - (mSize - 1) * mBorderSize;
    }
  }
}

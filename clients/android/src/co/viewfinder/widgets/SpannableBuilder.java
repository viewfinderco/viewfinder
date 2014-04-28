// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder.widgets;

import android.content.Context;
import android.graphics.Typeface;
import android.text.Spannable;
import android.text.SpannableStringBuilder;
import android.text.style.ForegroundColorSpan;
import android.text.style.StyleSpan;

/**
 * Help with construction of Spannables.
 * This class uses a 'fluent interface' design.  Most of the public methods return 'this'.
 */
public class SpannableBuilder {
  private final static String TAG = "Viewfinder.SpannableBuilder";

  private Context mContext;
  private SpannableStringBuilder mSsb = new SpannableStringBuilder();
  private int mBoldOnPosition = -1;
  private int mItalicOnPosition = -1;
  private int mColorOnPosition = -1;
  private int mTextColorResource;

  public SpannableBuilder(Context context) {
    mContext = context;
  }

  public SpannableBuilder append(String s) {
    mSsb.append(s);
    return this;
  }

  public SpannableBuilder turnBoldOn() {
    if (mBoldOnPosition < 0) {
      mBoldOnPosition = mSsb.length();
    }
    return this;
  }

  public Spannable getSpannable() {
    closeOpenSpans();
    return mSsb;
  }

  public SpannableBuilder turnBoldOff() {
    if (mBoldOnPosition >= 0) {
      mSsb.setSpan(getBoldStyleSpan(),
                   mBoldOnPosition,
                   mSsb.length(),
                   SpannableStringBuilder.SPAN_EXCLUSIVE_EXCLUSIVE);
      mBoldOnPosition = -1;
    }
    return this;
  }

  public SpannableBuilder turnItalicOn() {
    if (mItalicOnPosition < 0) {
      mItalicOnPosition = mSsb.length();
    }
    return this;
  }

  public SpannableBuilder turnItalicOff() {
    if (mItalicOnPosition >= 0) {
      mSsb.setSpan(getItalicStyleSpan(),
                   mItalicOnPosition,
                   mSsb.length(),
                   SpannableStringBuilder.SPAN_EXCLUSIVE_EXCLUSIVE);
      mItalicOnPosition = -1;
    }
    return this;
  }

  public SpannableBuilder setTextColor(int colorResource) {
    if (colorResource < 0) {
      setDefaultTextColor();
    } else if (mColorOnPosition < 0 || mTextColorResource != colorResource) {
      setDefaultTextColor();
      mTextColorResource = colorResource;
      mColorOnPosition = mSsb.length();
    }
    return this;
  }

  public SpannableBuilder setDefaultTextColor() {
    if (mColorOnPosition >= 0) {
      mSsb.setSpan(getColorSpan(mTextColorResource),
                   mColorOnPosition,
                   mSsb.length(),
                   SpannableStringBuilder.SPAN_EXCLUSIVE_EXCLUSIVE);
      mColorOnPosition = -1;
    }
    return this;
  }

  public SpannableBuilder appendListWithAnd(String[] strings, int andTextColorResource) {
    if (strings.length == 1) {
      append(strings[0]);
    } else if (strings.length > 1) {
      for (int i = 0; i < strings.length - 1; i++) {
        if (i != 0) {
          append(", ");
        }
        append(strings[i]);
      }

      // Pop off current bold/italic/color state, emit 'and' and restore bold/italic/color state.
      boolean wasBoldOn = isBoldOn();
      boolean wasItalicOn = isItalicOn();
      int prevTextColor = getCurrentTextColorResource();
      turnBoldOff();
      turnItalicOff();
      setTextColor(andTextColorResource);
      append(" and ");
      if (wasBoldOn) turnBoldOn();
      if (wasItalicOn) turnItalicOn();
      setTextColor(prevTextColor);

      append(strings[strings.length - 1]);
    }
    return this;
  }

  public SpannableBuilder appendList(String[] strings) {
    for (int i = 0; i < strings.length; i++) {
      if (i != 0) {
        append(", ");
      }
      append(strings[i]);
    }
    return this;
  }

  private void closeOpenSpans() {
    turnBoldOff();
    turnItalicOff();
    setDefaultTextColor();
  }

  private boolean isBoldOn() {
    return mBoldOnPosition >= 0;
  }

  private boolean isItalicOn() {
    return mItalicOnPosition >= 0;
  }

  private int getCurrentTextColorResource() {
    int textColorResource = -1;
    if (mColorOnPosition >= 0) {
      textColorResource = mTextColorResource;
    }
    return textColorResource;
  }

  private ForegroundColorSpan getColorSpan(int colorResource) {
    return new ForegroundColorSpan(mContext.getResources().getColor(colorResource));
  }

  private StyleSpan getBoldStyleSpan() {
    return new StyleSpan(Typeface.BOLD);
  }

  private StyleSpan getItalicStyleSpan() {
    return new StyleSpan(Typeface.ITALIC);
  }
}

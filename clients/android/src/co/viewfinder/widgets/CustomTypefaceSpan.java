// Copyright 2013 Viewfinder. All rights reserved.
// Author: Andy Kimball
package co.viewfinder.widgets;

import android.graphics.Paint;
import android.graphics.Typeface;
import android.text.TextPaint;
import android.text.style.MetricAffectingSpan;

/**
 * Sets a custom typeface to use for a certain span of text. The built-in Android TypefaceSpan
 * supports only a limited set of system typefaces.
 *
 * From: http://stackoverflow.com/questions/4819049/how-can-i-use-typefacespan-or-stylespan-with-custom-typeface
 */
public class CustomTypefaceSpan extends MetricAffectingSpan
{
  private Typeface mTypeface;

  public CustomTypefaceSpan(Typeface typeface)
  {
    mTypeface = typeface;
  }

  @Override
  public void updateDrawState(TextPaint drawState)
  {
    apply(drawState);
  }

  @Override
  public void updateMeasureState(TextPaint paint)
  {
    apply(paint);
  }

  private void apply(Paint paint)
  {
    Typeface oldTypeface = paint.getTypeface();
    int oldStyle = oldTypeface != null ? oldTypeface.getStyle() : 0;
    int fakeStyle = oldStyle & mTypeface.getStyle();

    if ((fakeStyle & Typeface.BOLD) != 0)
    {
      paint.setFakeBoldText(true);
    }

    if ((fakeStyle & Typeface.ITALIC) != 0)
    {
      paint.setTextSkewX(-0.25f);
    }

    paint.setTypeface(mTypeface);
  }
}

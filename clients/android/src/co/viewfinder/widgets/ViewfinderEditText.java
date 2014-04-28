// Copyright 2013 Viewfinder. All rights reserved.
// Author: Andy Kimball
package co.viewfinder.widgets;

import android.content.Context;
import android.content.res.TypedArray;
import android.graphics.Typeface;
import android.util.AttributeSet;
import android.widget.EditText;
import co.viewfinder.R;
import junit.framework.Assert;

/**
 * Overrides EditText in order to allow setting of a custom font. If the custom font is not
 * specified in the layout XML, defaults to ProximaNova.
 */
public class ViewfinderEditText extends EditText {
  private CustomTypefaceStylist mTypefaceStylist;
  private int mDefaultStyle;

  public ViewfinderEditText(Context context, AttributeSet attrs, int defStyle) {
    super(context, attrs, defStyle);
    init(attrs);
  }

  public ViewfinderEditText(Context context, AttributeSet attrs) {
    super(context, attrs);
    init(attrs);
  }

  public ViewfinderEditText(Context context) {
    super(context);
    init(null);
  }

  public void init(AttributeSet attrs) {
    mTypefaceStylist = new CustomTypefaceStylist(this, attrs, mDefaultStyle);
  }

  public void setTypeface(Typeface tf, int style) {
    if (mTypefaceStylist == null) {
      // setTypeface is called during construction to set the default style.
      mDefaultStyle = style;
    } else if (tf == null) {
      // When typeface is not specified, choose one of the fonts based on style.
      mTypefaceStylist.setTypeface(this, style);
    } else {
      // Else just use default behavior.
      super.setTypeface(tf, style);
    }
  }
}
// Copyright 2013 Viewfinder. All rights reserved.
// Author: Andy Kimball
package co.viewfinder.widgets;

import android.content.Context;
import android.content.res.TypedArray;
import android.graphics.Typeface;
import android.text.Editable;
import android.text.Spannable;
import android.text.Spanned;
import android.text.TextWatcher;
import android.text.style.StyleSpan;
import android.util.AttributeSet;
import android.widget.TextView;
import co.viewfinder.R;
import junit.framework.Assert;

/**
 *
 */
public class CustomTypefaceStylist {
  private Typeface mNormalTypeface;
  private Typeface mBoldTypeface;
  private Typeface mItalicTypeface;

  public CustomTypefaceStylist(TextView textView, AttributeSet attrs, int defStyle) {
    Context context = textView.getContext();
    TypedArray a = context.obtainStyledAttributes(attrs, R.styleable.ViewfinderTextView);
    for (int i = 0; i < a.getIndexCount(); i++) {
      int attr = a.getIndex(i);

      switch (attr) {
        case R.styleable.ViewfinderTextView_normalTypeface:
          mNormalTypeface = Typefaces.get(context, a.getString(attr));
          break;

        case R.styleable.ViewfinderTextView_boldTypeface:
          mBoldTypeface = Typefaces.get(context, a.getString(attr));
          break;

        case R.styleable.ViewfinderTextView_italicTypeface:
          mItalicTypeface = Typefaces.get(context, a.getString(attr));
          break;
      }
    }

    // Set default typeface values if they were not set in the layout xml.
    if (mNormalTypeface == null) {
      mNormalTypeface = Typefaces.get(context, "ProximaNova-Reg-VF.ttf");
    }

    if (mBoldTypeface == null) {
      mBoldTypeface = Typefaces.get(context, "ProximaNova-Bold-VF.ttf");
    }

    if (mItalicTypeface == null) {
      mItalicTypeface = Typefaces.get(context, "ProximaNova-RegIt-VF.ttf");
    }

    textView.addTextChangedListener(new TextWatcher() {
      /**
       * Called when the text changes. Replaces bold & italic style spans with spans that set
       * a bold or italic typeface.
       */
      @Override
      public void afterTextChanged(Editable editable) {
        for (StyleSpan span : editable.getSpans(0, editable.length(), StyleSpan.class)) {
          if (span.getStyle() == Typeface.BOLD) {
            editable.setSpan(
                new CustomTypefaceSpan(mBoldTypeface),
                editable.getSpanStart(span),
                editable.getSpanEnd(span),
                Spannable.SPAN_EXCLUSIVE_EXCLUSIVE);
            editable.removeSpan(span);
          }
          else if (span.getStyle() == Typeface.ITALIC) {
            editable.setSpan(
                new CustomTypefaceSpan(mItalicTypeface),
                editable.getSpanStart(span),
                editable.getSpanEnd(span),
                Spannable.SPAN_EXCLUSIVE_EXCLUSIVE);
            editable.removeSpan(span);
          }
        }
      }

      @Override
      public void beforeTextChanged(CharSequence s, int start, int count, int after) { }

      @Override
      public void onTextChanged(CharSequence s, int start, int before, int count) { }
    });

    // If text in TextView is styled, then force scan in order to update fonts.
    CharSequence text = textView.getText();
    if (text instanceof Spanned) {
      StyleSpan spans[] = ((Spanned)text).getSpans(0, text.length(), StyleSpan.class);
      if (spans.length > 0) {
        textView.setText(text);
      }
    }

    // Set typeface for the default style.
    setTypeface(textView, defStyle);

    a.recycle();
  }

  public void setTypeface(TextView textView, int style) {
    switch (style) {
      case Typeface.NORMAL:
        textView.setTypeface(mNormalTypeface);
        break;

      case Typeface.BOLD:
        textView.setTypeface(mBoldTypeface);
        break;

      case Typeface.ITALIC:
        textView.setTypeface(mItalicTypeface);
        break;
    }
  }
}

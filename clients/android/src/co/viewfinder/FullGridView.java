// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.content.Context;
import android.util.AttributeSet;
import android.widget.GridView;

/**
 * Modify GridView's behavior to always show all rows, not just a windowed view of the rows.
 */
public class FullGridView extends GridView {
  public FullGridView(Context context) {
    super(context);
  }

  public FullGridView(Context context, AttributeSet attrs) {
    super(context, attrs);
  }

  public FullGridView(Context context, AttributeSet attrs, int defStyle) {
    super(context, attrs, defStyle);
  }

  @Override
  protected void onMeasure(int widthMeasureSpec, int heightMeasureSpec) {
    // Ensure that the view has enough height to show all grid elements.

    // MEASURED_SIZE_MASK was introduced in API LEVEL 11 SDK for Honeycomb,
    //   but it should be OK to use it when running on older versions of Android.
    //   Final implementation of this may not even use it.
    int expandSpec = MeasureSpec.makeMeasureSpec(MEASURED_SIZE_MASK,
                                                 MeasureSpec.AT_MOST);
    super.onMeasure(widthMeasureSpec, expandSpec);
  }
}

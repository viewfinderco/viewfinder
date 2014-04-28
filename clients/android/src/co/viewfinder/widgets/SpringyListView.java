// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder.widgets;

import android.content.Context;
import android.util.AttributeSet;
import android.view.ViewTreeObserver;
import android.widget.ListView;

/**
 * Allow for ListView pull down/up in a springy fashion.
 * Spring back is relatively quick, but controlled by AbsListView implementation.
 * Note: In the future we may want to apply some animation to more finely control this effect.
 * Note: Overscroll functionality requires API level 9 (Android 2.3.x) or above.
 */
public class SpringyListView extends ListView {
  private static final String TAG = "Viewfinder.SpringyListView";
  private int mHeight = 0;

  public SpringyListView(Context context)
  {
    super(context);
    initialize();
  }

  public SpringyListView(Context context, AttributeSet attrs)
  {
    super(context, attrs);
    initialize();
  }

  public SpringyListView(Context context, AttributeSet attrs, int defStyle)
  {
    super(context, attrs, defStyle);
    initialize();
  }

  private void initialize()
  {
    getViewTreeObserver().addOnGlobalLayoutListener(new ViewTreeObserver.OnGlobalLayoutListener() {
      public void onGlobalLayout() {
        mHeight = getHeight();
      }
    });
  }

  @Override
  protected boolean overScrollBy(int deltaX,
                                 int deltaY,
                                 int scrollX,
                                 int scrollY,
                                 int scrollRangeX,
                                 int scrollRangeY,
                                 int maxOverScrollX,
                                 int maxOverScrollY,
                                 boolean isTouchEvent)
  {
    int newDeltaY = deltaY;
    int maxYOverscrollDistance = maxOverScrollY;

    if (isTouchEvent) {
      maxYOverscrollDistance = mHeight;
      // Decrease pull leverage as the amount of overscroll increases.
      float pullCoefficient = (1f - Math.abs(scrollY) / (float)mHeight) / 2f;
      newDeltaY = Math.round(deltaY * pullCoefficient);
    }

    return super.overScrollBy(deltaX,
                              newDeltaY,
                              scrollX,
                              scrollY,
                              scrollRangeX,
                              scrollRangeY,
                              maxOverScrollX,
                              maxYOverscrollDistance,
                              isTouchEvent);
  }
}

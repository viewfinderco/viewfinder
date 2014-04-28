// Copyright 2013 Viewfinder. All rights reserved.
// Author: Andy Kimball
package co.viewfinder.widgets;

import android.app.Activity;
import android.content.Context;
import android.support.v4.view.PagerAdapter;
import android.support.v4.view.ViewPager;
import android.util.AttributeSet;
import android.view.*;
import android.view.animation.AlphaAnimation;
import android.widget.*;
import co.viewfinder.R;
import co.viewfinder.Utils;
import junit.framework.Assert;

/**
 * Pages the welcome and tour pages. This is non-trivial, because:
 *   1. The welcome page is a different size than the tour pages.
 *   2. The next and previous tour pages needs to be visible to either side of the currently
 *      selected page.
 *
 * In order to solve these problems, an outer ViewPager contains the welcome page as well as
 * an inner ViewPager. The inner ViewPager contains the tour pages.
 */
public class TourPager extends ViewPager {
  private static final int STATE_USE_NO_PAGER = 0;
  private static final int STATE_USE_OUTER_PAGER = 1;
  private static final int STATE_USE_INNER_PAGER = 2;
  private static final float PAGE_MIN_ALPHA = 0.60f;

  private Activity mActivity;
  private ViewPager mInnerPager;
  private InnerAdapter mInnerAdapter;
  private int mStartX;
  private int mPagerState;

  public TourPager(Context context, AttributeSet attrs) {
    super(context, attrs);
    mActivity = (Activity)context;

    // Disable clipping of children so non-selected pages are visible
    setClipChildren(false);

    // Child clipping doesn't work with hardware acceleration in Android 3.x/4.x
    // You need to set this value here if using hardware acceleration in an
    // application targeted at these releases.
    if (Utils.isHoneycombCapableDevice()) {
      setLayerType(View.LAYER_TYPE_SOFTWARE, null);
    }

    setAdapter(new OuterAdapter());
  }

  @Override
  public boolean onInterceptTouchEvent(MotionEvent ev) {
    // Do not intercept as long as still on the welcome page.
    return getCurrentItem() != 0;
  }

  @Override
  public boolean onTouchEvent(MotionEvent ev) {
    // Do nothing special as long as still on the welcome page.
    if (getCurrentItem() == 0) {
      return super.onTouchEvent(ev);
    }

    switch (ev.getAction() & MotionEvent.ACTION_MASK) {
      case MotionEvent.ACTION_DOWN:
        // Remember the location of the DOWN action.
        mStartX = (int)ev.getX();
        mPagerState = STATE_USE_NO_PAGER;
        return true;

      case MotionEvent.ACTION_MOVE:
        if (mPagerState == STATE_USE_NO_PAGER) {
          // If not on the first tour page, or if swiping to the left, then delegate the swipe
          // action to the inner pager; otherwise, let the outer pager handle it.
          if (mInnerPager.getCurrentItem() != 0 || (int)ev.getX() < mStartX) {
            mPagerState = STATE_USE_INNER_PAGER;
          } else {
            mPagerState = STATE_USE_OUTER_PAGER;
          }

          // Synthesize a DOWN action, since the original action was suppressed.
          MotionEvent downEvent = MotionEvent.obtain(
              ev.getDownTime(),
              ev.getDownTime(),
              MotionEvent.ACTION_DOWN,
              mStartX,
              (int)ev.getY(),
              0);

          doDispatchTouchEvent(downEvent, 0);
        }

        break;
    }

    return doDispatchTouchEvent(ev, (int) ev.getX() - mStartX);
  }

  /**
   * Delegates to the onTouchEvent of either the inner or outer pager. When delegating to the
   * inner pager, makes sure that the swipe always starts at the center point of that pager,
   * even if the user really started outside its bounds.
   */
  private boolean doDispatchTouchEvent(MotionEvent ev, int innerXOffset) {
    if (mPagerState == STATE_USE_INNER_PAGER) {
      int centerX = (mInnerPager.getRight() - mInnerPager.getLeft()) / 2;
      int centerY = (mInnerPager.getBottom() - mInnerPager.getTop()) / 2;
      ev.setLocation(centerX + innerXOffset, centerY);

      return mInnerPager.onTouchEvent(ev);
    } else if (mPagerState == STATE_USE_OUTER_PAGER) {
      return super.onTouchEvent(ev);
    }

    return true;
  }

  /**
   * Sets the alpha for a tour page, as they need to get slightly dimmer when they are not
   * currently selected.
   */
  private void setPageAlpha(View pageView, float alphaPercent) {
    AlphaAnimation animation = new AlphaAnimation(1.0f, PAGE_MIN_ALPHA + alphaPercent * (1.0f - PAGE_MIN_ALPHA));
    animation.setFillAfter(true);
    pageView.startAnimation(animation);
  }

  /**
   * Adapter for the outer ViewPager, which instantiates views for the welcome page and for
   * the inner ViewPager.
   */
  private class OuterAdapter extends PagerAdapter implements
      ViewTreeObserver.OnGlobalLayoutListener,
      ViewPager.OnPageChangeListener {
    private TextView mTutorialText;
    private int mLastTextPos;

    @Override
    public Object instantiateItem(ViewGroup container, int position) {
      View view;

      switch (position) {
        case 0:
          // Instantiate the welcome page view.
          view = mActivity.getLayoutInflater().inflate(R.layout.auth_welcome, container, false);

          ImageButton takeTourButton = (ImageButton)view.findViewById(R.id.welcome_takeTour);
          takeTourButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
              TourPager.this.setCurrentItem(1, true /* smoothScroll */);
            }
          });
          break;

        case 1:
          // Instantiate the inner ViewPager.
          view = mActivity.getLayoutInflater().inflate(R.layout.tutorial, container, false);
          mTutorialText = (TextView)view.findViewById(R.id.tutorial_text);

          mInnerPager = (ViewPager)view.findViewById(R.id.tutorial_pager);
          mInnerAdapter = new InnerAdapter();
          mInnerPager.setAdapter(mInnerAdapter);
          mInnerPager.setOffscreenPageLimit(mInnerAdapter.getCount());
          mInnerPager.setPageMargin(12);

          mInnerPager.getViewTreeObserver().addOnGlobalLayoutListener(this);
          mInnerPager.setOnPageChangeListener(this);
          break;

        default:
          Assert.fail("Unexpected position.");
          return null;
      }

      container.addView(view);
      return view;
    }

    @Override
    public void destroyItem(ViewGroup container, int position, Object object) {
      container.removeView((View)object);
    }

    @Override
    public int getCount() {
      return 2;
    }

    @Override
    public boolean isViewFromObject(View view, Object object) {
      return view == object;
    }

    @Override
    public void onGlobalLayout() {
      Utils.removeOnGlobalLayoutListener(mInnerPager, this);

      // Make inner pager 60% of screen width.
      ViewGroup.LayoutParams layoutParams = mInnerPager.getLayoutParams();
      layoutParams.width = (int)(((RelativeLayout)mInnerPager.getParent()).getWidth() * 0.60f);
      mInnerPager.setLayoutParams(layoutParams);
    }

    /**
     * Called when the inner ViewPager is scrolled.
     */
    @Override
    public void onPageScrolled(int position, float positionOffset, int positionOffsetPixels) {
      // Set alpha on left and right pages, based on % that each is visible.
      View leftView = mInnerPager.getChildAt(position);
      setPageAlpha(leftView, 1.0f - positionOffset);

      if (position + 1 < mInnerPager.getAdapter().getCount()) {
        View rightView = mInnerPager.getChildAt(position + 1);
        setPageAlpha(rightView, positionOffset);
      }

      // Change tutorial text if necessary.
      int textPosition = (int)(position + positionOffset + 0.5);
      if (textPosition != mLastTextPos) {
        mTutorialText.setText(mInnerAdapter.getTextId(textPosition));
        mLastTextPos = textPosition;
      }

      // Set tutorial text alpha.
      float distance = Math.min(Math.abs(textPosition - (position + positionOffset)), 0.5f);
      AlphaAnimation animation = new AlphaAnimation(1.0f, 1.0f - distance / 0.5f);
      animation.setFillAfter(true);
      mTutorialText.startAnimation(animation);

      // Force the container to redraw on scrolling.
      // Without this the outer pages render initially and then stay static.
      invalidate();
    }

    @Override
    public void onPageSelected(int position) {
    }

    @Override
    public void onPageScrollStateChanged(int state) {
    }
  }

  /**
   * Adapter for the inner ViewPager, which instantiates views for the tour pages.
   */
  private class InnerAdapter extends PagerAdapter {
    @Override
    public Object instantiateItem(ViewGroup container, int position) {
      ImageView imageView;

      switch (position) {
        case 0:
          imageView = new ImageView(mActivity);
          imageView.setImageResource(R.drawable.walkthrough_dashboard_384x576);
          break;

        case 1:
          imageView = new ImageView(mActivity);
          imageView.setImageResource(R.drawable.walkthrough_feed_384x576);
          break;

        case 2:
          imageView = new ImageView(mActivity);
          imageView.setImageResource(R.drawable.walkthrough_library_384x576);
          break;

        default:
          Assert.fail("Unexpected position.");
          return null;
      }

      imageView.setScaleType(ImageView.ScaleType.FIT_START);
      setPageAlpha(imageView, 0.0f);
      container.addView(imageView);

      return imageView;
    }

    /**
     * Returns text that corresponds to each of the tour pages returned by instantiateItem.
     */
    public int getTextId(int position) {
      switch (position) {
        case 0:
          return R.string.tutorial_dash;

        case 1:
          return R.string.tutorial_inbox;

        case 2:
          return R.string.tutorial_library;

        default:
          Assert.fail("unexpected position.");
          return 0;
      }
    }

    @Override
    public void destroyItem(ViewGroup container, int position, Object object) {
      container.removeView((View)object);
    }

    @Override
    public int getCount() {
      return 3;
    }

    @Override
    public boolean isViewFromObject(View view, Object object) {
      return view == object;
    }
  }
}

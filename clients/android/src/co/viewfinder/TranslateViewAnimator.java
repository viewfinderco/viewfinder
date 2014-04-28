// Copyright 2013 Viewfinder. All rights reserved.
// Author: Andy Kimball
package co.viewfinder;

import android.os.Handler;
import android.view.View;
import android.view.animation.Animation;
import android.view.animation.TranslateAnimation;

/**
 * This class moves a view from one location to another using a TranslateAnimation. Once
 * the animation is complete, the view's top and left padding values are updated so that
 * it really exists at the new location. This is necessary because the TranslateAnimation
 * only moves a bitmap of the view to the new location, not the view itself.
 *
 * To use this class, pass the starting and ending padding values (or -1 to use current
 * value). Then set the duration, and then call the start() method.
 */
public class TranslateViewAnimator {
  private View mView;
  private int mStartLeft;
  private int mEndLeft;
  private int mStartTop;
  private int mEndTop;
  private long mDuration;
  private Animation.AnimationListener mListener;

  public TranslateViewAnimator(View view, int startLeft, int endLeft, int startTop, int endTop) {
    mView = view;
    mStartLeft = startLeft;
    mEndLeft = endLeft;
    mStartTop = startTop;
    mEndTop = endTop;
  }

  public void setDuration(long durationMillis) {
    mDuration = durationMillis;
  }

  public void setAnimationListener(Animation.AnimationListener listener) {
    mListener = listener;
  }

  public void start() {
    TranslateAnimation animation = new TranslateAnimation(
        mStartLeft != -1 ? mStartLeft : mView.getPaddingLeft(),
        mEndLeft != -1 ? mEndLeft : mView.getPaddingLeft(),
        mStartTop != -1 ? mStartTop : mView.getPaddingTop(),
        mEndTop != -1 ? mEndTop : mView.getPaddingTop());

    // Set the duration.
    animation.setDuration(mDuration);

    // Set fill after to true, since this improves the quality of the animation.
    animation.setFillAfter(true);

    // Remove left and top padding before translating it in order to minimize strange effects
    // that occur if the view is currently partly off the screen.
    mView.setPadding(0, 0, mView.getPaddingRight(), mView.getPaddingBottom());

    animation.setAnimationListener(new Animation.AnimationListener() {
      @Override
      public void onAnimationStart(Animation animation) {
        if (mListener != null) mListener.onAnimationStart(animation);
      }

      @Override
      public void onAnimationRepeat(Animation animation) {
        if (mListener != null) mListener.onAnimationRepeat(animation);
      }

      @Override
      public void onAnimationEnd(final Animation animation) {
        // Add a slight delay before clearing the animation. Doing this reduces jerkiness
        // that sometimes occurs at the end of the animation.
        new Handler().postDelayed(new Runnable() {
          @Override
          public void run() {
            // Animation is complete, so set the final padding values.
            mView.setPadding(mEndLeft, mEndTop, mView.getPaddingRight(), mView.getPaddingBottom());

            // Clear the animation so that the the transformation matrix associated with the
            // view is cleared (the setPadding call should compensate).
            mView.clearAnimation();

            if (mListener != null) mListener.onAnimationEnd(animation);
          }
        }, 10);
      }
    });

    // Start the animation.
    mView.startAnimation(animation);
  }
}

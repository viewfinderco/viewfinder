// Copyright 2013 Viewfinder. All rights reserved.
// Author: Andy Kimball
package co.viewfinder;

import android.app.Activity;
import android.view.View;
import android.view.animation.AlphaAnimation;
import android.view.animation.Animation;
import android.view.animation.TranslateAnimation;

/**
 * This is a custom activity transition which fades in the titlebar of the child activity
 * while sliding up the content of the child activity. The parent activity is visible
 * underneath during this process.
 *
 * The child activity is expected to have view with the following ids:
 *   - R.id.titlebar: View containing the titlebar which will fade in/out.
 *   - R.id.titlebar_content: View containing the content which will slide up/down.
 */
public class TitleBarActivityTransition extends CustomActivityTransition {
  private static final int DURATION = 400;

  public TitleBarActivityTransition(Activity parentActivity) {
    super(parentActivity);
    setDuration(DURATION);
  }

  @Override
  public void transition(final Activity childActivity, final boolean isForward, final CompletionListener listener) {
    setBackgroundToParent(childActivity);

    // Fade-in or fade-out the titlebar.
    AlphaAnimation alphaAnimation = isForward ? new AlphaAnimation(0f, 1.0f) : new AlphaAnimation(1.0f, 0f);
    alphaAnimation.setFillAfter(true);
    alphaAnimation.setDuration(getDuration());

    View alphaView = childActivity.findViewById(R.id.titlebar);
    alphaView.startAnimation(alphaAnimation);

    // Slide-up or slide-down the content.
    View translateView = childActivity.findViewById(R.id.titlebar_content);
    TranslateAnimation translateAnimation = new TranslateAnimation(
        TranslateAnimation.RELATIVE_TO_PARENT, 0.0f,
        TranslateAnimation.RELATIVE_TO_PARENT, 0.0f,
        TranslateAnimation.RELATIVE_TO_PARENT, isForward ? 1.0f : 0f,
        TranslateAnimation.RELATIVE_TO_PARENT, isForward ? 0.0f : 1.0f);
    translateAnimation.setFillAfter(true);
    translateAnimation.setDuration(getDuration());

    // Clear background bitmap when animation is complete (to save memory).
    translateAnimation.setAnimationListener(new Animation.AnimationListener() {
      @Override
      public void onAnimationStart(Animation animation) {}

      @Override
      public void onAnimationEnd(Animation animation) {
        if (isForward) {
          clearBackground(childActivity);
        }

        notifyCompletion(listener);
      }

      @Override
      public void onAnimationRepeat(Animation animation) {}
    });

    translateView.startAnimation(translateAnimation);
  }
}

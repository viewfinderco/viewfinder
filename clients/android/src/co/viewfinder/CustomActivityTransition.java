// Copyright 2013 Viewfinder. All rights reserved.
// Author: Andy Kimball
package co.viewfinder;

import android.app.Activity;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.drawable.BitmapDrawable;
import android.graphics.drawable.Drawable;
import android.view.View;

/**
 * The CustomActivityTransition can be used with BaseActivity in order to better control
 * animated transitions between activities.
 *
 * Android supports a restricted set of activity transitions. Certain things, such as animating
 * different parts of the activity in different ways, are not supported. For example, a caller
 * may want to fade in a titlebar, while at the same time sliding in the content.
 *
 * To use a CustomActivityTransition, override the transitionForward and transitionBackward
 * methods. In the parent activity, create an instance of the transition and pass it to
 * overridePendingTransition. Once the child activity is created, BaseActivity will invoke
 * transitionForward so that it can perform custom entrance animation. As the child activity is
 * destroyed, BaseActivity will invoke transitionBackward so that it can performe custom
 * exit animation.
 */
public abstract class CustomActivityTransition {
  public interface CompletionListener {
    void onCompletion();
  }

  private Activity mParentActivity;
  private int mDurationMillis;

  public CustomActivityTransition(Activity parentActivity) {
    mParentActivity = parentActivity;
    mDurationMillis = parentActivity.getResources().getInteger(R.integer.defaultAnimTime);
  }

  public Activity getParentActivity() {
    return mParentActivity;
  }

  /**
   * Set duration of the transition, in milliseconds.
   */
  public void setDuration(int durationMillis) {
    mDurationMillis = durationMillis;
  }

  /**
   * Get duration of the transition, in milliseconds.
   */
  public int getDuration() {
    return mDurationMillis;
  }

  /**
   * This method will be called during BaseActivity.onAttachedToWindow (isForward = true),
   * or BaseActivity.onBackPressed (isForward = false). The derived method should perform
   * the entrance or exit transition between the parent and child activity.
   *
   * @param childActivity: Activity which was invoked by the parent activity.
   * @param listener: If non-null, the listener is invoked upon completion of the transition.
   */
  public abstract void transition(Activity childActivity, boolean isForward, CompletionListener listener);

  /**
   * The derived class should call this once the transition is complete in order to notify
   * any listener.
   */
  protected void notifyCompletion(CompletionListener listener) {
    if (listener != null) {
      listener.onCompletion();
    }
  }

  /**
   * Helper method to set the child activity's background to a snapshot of the parent's view.
   * This is useful when a transparent child activity is not possible, since it presents the
   * illusion of transparency.
   */
  protected void setBackgroundToParent(Activity childActivity) {
    // First take a snapshot of the previous activity's base view.
    View prevView = getParentActivity().findViewById(android.R.id.content);
    Bitmap bitmap = getBitmapFromView(prevView);
    BitmapDrawable drawable = new BitmapDrawable(childActivity.getResources(), bitmap);

    // Now set the background of the child activity to that bitmap.
    setBackground(childActivity.findViewById(android.R.id.content), drawable);
  }

  /**
   * Helper method to clear the background previously set by a call to setBackgroundToParent.
   * This is recommended at the end of the transition in order to save memory.
   */
  protected void clearBackground(Activity childActivity) {
    setBackground(childActivity.findViewById(android.R.id.content), null);
  }

  /**
   * Helper method which sets a view's background.
   */
  @SuppressWarnings("deprecation")
  protected static void setBackground(View view, Drawable drawable) {
    // Android renamed setBackgroundDrawable.
    if (Utils.isJellyBeanCapableDevice()) {
      view.setBackground(drawable);
    } else {
      view.setBackgroundDrawable(drawable);
    }
  }

  /**
   * Helper method which draws a view into a bitmap and returns the bitmap.
   */
  protected static Bitmap getBitmapFromView(View view) {
    Bitmap bitmap = Bitmap.createBitmap(view.getWidth(), view.getHeight(), Bitmap.Config.ARGB_8888);
    Canvas c = new Canvas(bitmap);
    view.layout(view.getLeft(), view.getTop(), view.getRight(), view.getBottom());
    view.draw(c);
    return bitmap;
  }
}

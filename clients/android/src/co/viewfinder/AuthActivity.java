// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.view.View;
import android.view.ViewGroup;
import android.view.ViewTreeObserver;
import android.view.animation.AlphaAnimation;
import android.view.animation.Animation;
import android.widget.LinearLayout;

import android.content.Intent;
import android.os.Bundle;
import android.support.v4.app.Fragment;
import android.support.v4.app.FragmentManager;
import android.support.v4.app.FragmentTransaction;
import android.util.Log;
import junit.framework.Assert;

/**
 * AuthActivity is kicked off during app startup.  If the client is not already signed in,
 * this activity will handle various login/signup work flows.
 * Once login is complete, control will switch to ViewfinderActivity.
 */
public class AuthActivity extends BaseActivity implements
    AuthLoginFragment.OnLoginListener,
    AuthSignupFragment.OnSignupListener,
    AuthVerifyFragment.OnVerifyListener,
    AuthResetFragment.OnResetListener,
    AuthResetChangeFragment.OnResetChangeListener {
  private static final String TAG = "Viewfinder.AuthActivity";
  private static final String TAG_AUTH = "co.viewfinder.AuthFragment";
  private static final String TAG_SIGNUP = "co.viewfinder.AuthSignupFragment";
  private static final String TAG_LOGIN = "co.viewfinder.AuthLoginFragment";
  private static final String TAG_VERIFY = "co.viewfinder.AuthVerifyFragment";
  private static final String TAG_RESET = "co.viewfinder.AuthResetFragment";
  private static final String TAG_RESET_CHANGE = "co.viewfinder.AuthResetChangeFragment";

  private static final int TAB_TOP_OFFSET = 16;

  private boolean mAreTabsOpen;
  private AuthFragment mAuthFragment = null;
  private AuthSignupFragment mAuthSignupFragment = null;
  private AuthLoginFragment mAuthLoginFragment = null;

  @Override
  public void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    setContentView(R.layout.statusbar_activity);

    // Add initial fragments to the activity.
    FragmentManager fm = getSupportFragmentManager();
    FragmentTransaction ft = fm.beginTransaction();

    mAuthFragment = new AuthFragment();
    ft.add(R.id.statusbar_content, mAuthFragment, TAG_AUTH);

    mAuthSignupFragment = new AuthSignupFragment();
    ft.add(R.id.statusbar_content, mAuthSignupFragment, TAG_SIGNUP);

    mAuthLoginFragment = new AuthLoginFragment();
    ft.add(R.id.statusbar_content, mAuthLoginFragment, TAG_LOGIN);

    // Hide the login fragment until the login tab is clicked by user.
    ft.hide(mAuthLoginFragment);

    ft.commit();

    // Set initial state of tabs once layout information is available.
    final View activityView = findViewById(R.id.statusbar_content);
    ViewTreeObserver observer = activityView.getViewTreeObserver();
    observer.addOnGlobalLayoutListener(new ViewTreeObserver.OnGlobalLayoutListener() {
      public void onGlobalLayout() {
        Utils.removeOnGlobalLayoutListener(activityView, this);

        // Set initial state of tabs.
        transitionTabs(false /* openTabs */, true /* showSignupTab */);
      }
    });
  }

  /**
   *
   * ---------- OnSignupListener callbacks ----------
   *
   */

  /**
   * Called when the user clicks the signup tab. Open the signup tab if it is not yet open.
   */
  @Override
  public void onSelectSignup() {
    if (!mAreTabsOpen) {
      transitionTabs(true /* openTabs */, true /* showSignupTab */);
    }
  }


  /**
   * Called when the user clicks the login tab. Open the login tab if it is not yet open,
   * or switch to it if it is.
   */
  @Override
  public void onSwitchToLogin() {
    transitionTabs(true /* openTabs */, false /* showSignupTab */);
  }

  /**
   * Called once the user clicks the "Create Account" button in order to trigger registration
   * of a new user account.
   */
  @Override
  public void onCreateAccount(String first, String last, final String emailOrMobile, String password) {
    Log.d(TAG, "[onCreateAccount] email: " + emailOrMobile + ", first: " + first + ", last: " + last);

    getAppState().networkManager().sendAuthRegister(
        emailOrMobile,
        first,
        last,
        password,
        new NetworkManager.AuthResponseCallback() {
          @Override
          public void run() {
            if (onCompletedAuth(mStatusCode, mErrorId, mErrorMsg)) {
              // The number of token digits is the error id. bleh.
              // Push the fragment onto the backstack so that the back button will exit verification.
              Fragment verifyFragment = new AuthVerifyFragment(emailOrMobile, mErrorId);
              pushFragment(mAuthSignupFragment, verifyFragment, TAG_VERIFY);
            }
          }
        });
  }

  /**
   * Called when the user clicks the cancel button on the signup tab. Close the tab.
   */
  @Override
  public void onCancelSignup() {
    transitionTabs(false /* openTabs */, true /* showSignupTab */);
  }

  /**
   *
   * ---------- OnLoginListener callbacks ----------
   *
   */

  /**
   * Called when the user clicks the signup tab. Open the signup tab if it is not yet open,
   * or switch to it if it is.
   */
  @Override
  public void onSwitchToSignup() {
    transitionTabs(true /* openTabs */, true /* showSignupTab */);
  }

  /**
   * Called when the user clicks the "Log In" button in order to trigger login to an existing
   * user account.
   */
  @Override
  public void onLoginAccount(String emailOrMobile, String password) {
    Log.d(TAG, "[onLoginAccount] email: " + emailOrMobile);
    getAppState().networkManager().sendAuthLogin(
        emailOrMobile,
        password,
        new NetworkManager.AuthResponseCallback() {
          @Override
          public void run() {
            if (onCompletedAuth(mStatusCode, mErrorId, mErrorMsg)) {
              // Switch to inbox.
              startActivity(new Intent(AuthActivity.this, ViewfinderActivity.class));
            }
          }
        });
  }

  /**
   * Called when the user clicks the cancel button on the login tab. Closes the tab.
   */
  @Override
  public void onCancelLogin() {
    transitionTabs(false /* openTabs */, false /* showSignupTab */);
  }

  /**
   * Called when the user clicks the "Forgot Password?" button on the login tab. Shows the
   * reset password fragment.
   */
  @Override
  public void onForgotPassword() {
    // Push the reset fragment onto the backstack so that the back button will exit.
    pushFragment(mAuthLoginFragment, new AuthResetFragment(mAuthLoginFragment.getEmailOrMobile()), TAG_RESET);
  }

  /**
   *
   * ---------- OnVerifyListener callbacks ----------
   *
   */

  /**
   * Called when the user clicks the continue button. Completes the registration, login, or
   * reset process.
   */
  @Override
  public void onContinueVerify(String emailOrMobile, String verifyCode) {
    Log.d(TAG, "[onVerifyDone] code: " + verifyCode);
    getAppState().networkManager().sendAuthVerify(
        emailOrMobile,
        verifyCode,
        new NetworkManager.AuthResponseCallback() {
          @Override
          public void run() {
            if (onCompletedAuth(mStatusCode, mErrorId, mErrorMsg)) {
              // If password reset is in progress, then next allow the user to change their
              // password, else switch to the inbox (since register/login is complete).
              Fragment authResetFragment = getSupportFragmentManager().findFragmentByTag(TAG_RESET);
              if (authResetFragment != null) {
                // Dump the backstack, since user should not be able to back up any longer.
                FragmentManager fm = getSupportFragmentManager();
                fm.popBackStack(null, FragmentManager.POP_BACK_STACK_INCLUSIVE);

                FragmentTransaction ft = fm.beginTransaction();
                ft.hide(mAuthLoginFragment);
                ft.hide(mAuthSignupFragment);
                ft.add(R.id.statusbar_content, new AuthResetChangeFragment(), TAG_RESET_CHANGE);
                ft.commit();
              } else {
                startActivity(new Intent(AuthActivity.this, ViewfinderActivity.class));
              }
            }
          }
        });
  }

  /**
   * Called when the user clicks the exit button. Returns to the previous page.
   */
  @Override
  public void onExitVerify() {
    getSupportFragmentManager().popBackStack();
  }

  /**
   * Called when the user clicks the "send code again" button. Triggers re-send of the verify
   * code.
   */
  @Override
  public void onSendCodeAgain() {
    Log.d(TAG, "[onSendCodeAgain]");

    // Re-send either the reset or the register request.
    AuthResetFragment authResetFragment = (AuthResetFragment)getSupportFragmentManager().findFragmentByTag(TAG_RESET);
    if (authResetFragment != null) {
      getAppState().networkManager().sendAuthReset(
          authResetFragment.getEmailOrMobile(),
          new NetworkManager.AuthResponseCallback() {
            @Override
            public void run() {
              onCompletedAuth(mStatusCode, mErrorId, mErrorMsg);
            }
          });
    } else {
      getAppState().networkManager().sendAuthRegister(
          mAuthSignupFragment.getEmailOrMobile(),
          mAuthSignupFragment.getFirst(),
          mAuthSignupFragment.getLast(),
          mAuthSignupFragment.getPassword(),
          new NetworkManager.AuthResponseCallback() {
            @Override
            public void run() {
              onCompletedAuth(mStatusCode, mErrorId, mErrorMsg);
            }
          });
    }
  }

  /**
   *
   * ---------- OnResetListener callbacks ----------
   *
   */

  /**
   * Called when the user clicks the submit button. Shows the verify fragment.
   */
  @Override
  public void onSubmitReset(final String emailOrMobile) {
    Log.d(TAG, "[onSubmitReset] email: " + emailOrMobile);

    getAppState().networkManager().sendAuthReset(
        emailOrMobile,
        new NetworkManager.AuthResponseCallback() {
          @Override
          public void run() {
            if (onCompletedAuth(mStatusCode, mErrorId, mErrorMsg)) {
              // Push the reset fragment onto the backstack so that the back button will exit verification.
              Fragment authResetFragment = getSupportFragmentManager().findFragmentByTag(TAG_RESET);
              Fragment verifyFragment = new AuthVerifyFragment(emailOrMobile, mErrorId);
              pushFragment(authResetFragment, verifyFragment, TAG_VERIFY);
            }
          }
        });
  }

  /**
   * Called when the user clicks the back button. Returns to the previous page.
   */
  @Override
  public void onCancelReset() {
    getSupportFragmentManager().popBackStack();
  }

  /**
   *
   * ---------- OnResetChangeListener callbacks ----------
   *
   */

  /**
   * Called when the user clicks the submit button. Sends the password change request to the
   * server.
   */
  @Override
  public void onSubmitResetChange(String password) {
    Log.d(TAG, "[onSubmitResetChange]");

    // Provide empty oldPassword since we're doing a reset.
    getAppState().networkManager().sendChangePassword(
        "",
        password,
        new NetworkManager.AuthResponseCallback() {
          @Override
          public void run() {
            if (onCompletedAuth(mStatusCode, mErrorId, mErrorMsg)) {
              // Switch to inbox.
              startActivity(new Intent(AuthActivity.this, ViewfinderActivity.class));
            }
          }
        });
  }

  /**
   * Called when the user clicks the cancel button. Goes to the inbox.
   */
  @Override
  public void onCancelResetChange() {
    startActivity(new Intent(AuthActivity.this, ViewfinderActivity.class));
  }

  /**
   * Hides the previous fragment and adds a new fragment to the fragment manager. Adds the
   * fragment transaction to the backstack.
   */
  private void pushFragment(Fragment prevFragment, Fragment nextFragment, String tag) {
    FragmentTransaction ft = getSupportFragmentManager().beginTransaction();
    ft.hide(prevFragment);
    ft.add(R.id.statusbar_content, nextFragment, tag);
    ft.addToBackStack(null);
    ft.commit();
  }

  /**
   * Called when registration verification is complete, reset verification is complete, or
   * login is complete. Saves the user and device ids and returns true if successful, or
   * false if not.
   */
  private boolean onCompletedAuth(int statusCode, int errorId, String errorMsg) {
    if (statusCode == 200) {
      return true;
    }

    Log.d(TAG, "[onCompletedAuth] code: " + statusCode + ", errorId: " + errorId + ", error" + errorMsg);
    getErrorDialogManager().show(R.string.error_server, errorMsg);
    return false;
  }

  /**
   * Opens or closes the auth tabs, and shows either the signup or login tab on top.
   */
  private void transitionTabs(boolean openTabs, boolean showSignupTab) {
    boolean doAnimate = openTabs != mAreTabsOpen;
    mAreTabsOpen = openTabs;

    // Transfer email/mobile and password from one tab to the other if switching between tabs.
    if (showSignupTab == mAuthSignupFragment.isHidden()) {
      if (showSignupTab) {
        mAuthSignupFragment.setEmailOrMobile(mAuthLoginFragment.getEmailOrMobile());
        mAuthSignupFragment.setPassword(mAuthLoginFragment.getPassword());
      } else {
        mAuthLoginFragment.setEmailOrMobile(mAuthSignupFragment.getEmailOrMobile());
        mAuthLoginFragment.setPassword(mAuthSignupFragment.getPassword());
      }
    }

    // Show the signup fragment and hide the login fragment, or vice versa.
    FragmentManager fm = getSupportFragmentManager();
    FragmentTransaction ft = fm.beginTransaction();

    ft.show(showSignupTab ? mAuthSignupFragment : mAuthLoginFragment);
    ft.hide(showSignupTab ? mAuthLoginFragment : mAuthSignupFragment);

    ft.commit();

    // Notify the fragments that the auth tabs have been opened or closed.
    mAuthSignupFragment.onTabsOpenOrClose(mAreTabsOpen);
    mAuthLoginFragment.onTabsOpenOrClose(mAreTabsOpen);

    // Move fragments into proper position; animate a fragment only if it's going to be visible
    // and if it's not already in position.
    translateTabs(mAuthSignupFragment, openTabs, doAnimate && showSignupTab);
    translateTabs(mAuthLoginFragment, openTabs, doAnimate && !showSignupTab);
  }

  /**
   * Moves a tab fragment to top or bottom of the screen, animating it if requested.
   */
  private void translateTabs(Fragment tabFragment, final boolean openTabs, boolean doAnimate) {
    ViewGroup container = (ViewGroup)tabFragment.getView().getParent();
    int containerHeight = container.getHeight();
    Assert.assertTrue("Fragment layout should have occurred already.", containerHeight > 0);

    // Top of auth tabs should be just below the status bar.
    int top = TAB_TOP_OFFSET;

    // Calculate the height of the auth tabs so that right amount is showing at bottom of screen.
    LinearLayout tabTextLayout = (LinearLayout)tabFragment.getView().findViewById(R.id.auth_tabText);
    int bottom = containerHeight - (tabTextLayout.getBottom() + 14);

    // Animate the fragment if requested, else just set its final position.
    if (doAnimate) {
      TranslateViewAnimator animator;
      if (openTabs) {
        animator = new TranslateViewAnimator(tabFragment.getView(), 0, 0, bottom, top);
      } else {
        animator = new TranslateViewAnimator(tabFragment.getView(), 0, 0, top, bottom);
      }

      animator.setDuration(getResources().getInteger(R.integer.defaultAnimTime));

      // Open or close soft input at the same time that animation starts.
      animator.setAnimationListener(new Animation.AnimationListener() {
        @Override
        public void onAnimationStart(Animation animation) {
          if (openTabs) {
            showSoftInput();
          } else {
            hideSoftInput();
          }
        }

        @Override
        public void onAnimationEnd(Animation animation) {
          // If closing the login tab, then switch back to the signup tab now that the closing
          // animation is complete.
          if (!openTabs && mAuthLoginFragment.isVisible()) {
            transitionTabs(false /* openTabs */, true /* showSignupTab */);
          }
        }

        @Override
        public void onAnimationRepeat(Animation animation) {}
      });

      // Clear focus in order to make blue input pointer disappear more quickly.
      getCurrentFocus().clearFocus();

      // Run the translate animation.
      animator.start();

      // Fade the welcome background in or out.
      AlphaAnimation animation;
      if (openTabs) {
        animation = new AlphaAnimation(1.0f, 0.35f);
      } else {
        animation = new AlphaAnimation(0.35f, 1.0f);
      }

      animation.setFillAfter(true);
      animation.setDuration(getResources().getInteger(R.integer.defaultAnimTime));

      // Run the alpha animation.
      mAuthFragment.getView().startAnimation(animation);
    }
    else {
      tabFragment.getView().setPadding(0, openTabs ? top : bottom, 0, 0);
    }
  }
}

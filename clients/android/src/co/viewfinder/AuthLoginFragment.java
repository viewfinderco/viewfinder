// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.app.Activity;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.EditText;
import co.viewfinder.widgets.EmailOrMobileEdit;

/**
 * UI used to capture login information from the user.
 */
public class AuthLoginFragment extends BaseFragment {
  private OnLoginListener mCallback;

  private EmailOrMobileEdit mEmailOrMobile;
  private EditText mPasswordField;

  public interface OnLoginListener {
    public void onSwitchToSignup();
    public void onLoginAccount(String emailOrMobile, String password);
    public void onCancelLogin();
    public void onForgotPassword();
  }

  @Override
  public void onAttach(Activity activity) {
    super.onAttach(activity);
    mCallback = (OnLoginListener) activity;
  }

  @Override
  public View onCreateView(LayoutInflater inflater, final ViewGroup container, Bundle savedInstanceState) {
    View view = inflater.inflate(R.layout.auth_login_fragment, container, false);

    mEmailOrMobile = new EmailOrMobileEdit(view.findViewById(R.id.auth_loginEmailOrMobile));
    mPasswordField = (EditText)view.findViewById(R.id.auth_loginPassword);

    view.findViewById(R.id.auth_signupTabButton).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onSwitchToSignup();
      }
    });

    view.findViewById(R.id.auth_loginCancel).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onCancelLogin();
      }
    });

    view.findViewById(R.id.auth_loginAccount).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        // Validate input fields.
        boolean succeeded = InputValidation.setHintIfEmpty(mPasswordField, R.string.auth_passwordRequired);

        if (mEmailOrMobile.getText().length() == 0) {
          mEmailOrMobile.setHint(true);
          succeeded = false;
        }

        if (succeeded) {
          mCallback.onLoginAccount(
              mEmailOrMobile.getText().toString(),
              mPasswordField.getText().toString());
        }
      }
    });

    view.findViewById(R.id.auth_forgotPassword).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onForgotPassword();
      }
    });

    return view;
  }

  public String getEmailOrMobile() {
    return mEmailOrMobile.getText().toString();
  }

  public void setEmailOrMobile(CharSequence emailOrMobile) {
    mEmailOrMobile.setText(emailOrMobile);
  }

  public String getPassword() {
    return mPasswordField.getText().toString();
  }

  public void setPassword(CharSequence password) {
    mPasswordField.setText(password);
  }

  /**
   * Called by the activity when the auth tabs open or close.
   */
  public void onTabsOpenOrClose(boolean tabsOpen) {
    // If tabs are open, show the selected login tabs image. If tabs are closed, show the default
    // tabs image that is clipped so that it won't be mis-drawn when it's partially off-screen.
    View tabsView = getView().findViewById(R.id.auth_loginTabs);
    View cardView = getView().findViewById(R.id.auth_loginCard);

    if (tabsOpen) {
      cardView.setPadding(0, 0, 0, getResources().getDimensionPixelSize(R.dimen.auth_openTabPadding));
      tabsView.setBackgroundResource(R.drawable.tabs_modal_login_selected_android);
    } else {
      cardView.setPadding(0, 0, 0, getResources().getDimensionPixelSize(R.dimen.auth_closedTabPadding));
      tabsView.setBackgroundResource(R.drawable.tabs_modal_login_default_android);
    }

    // Clear any validation error text.
    mPasswordField.setHint(R.string.auth_password);
    mEmailOrMobile.setHint(false /* useErrorHint */);
  }
}

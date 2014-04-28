// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.app.Activity;
import android.os.Bundle;
import android.view.*;
import android.widget.*;
import co.viewfinder.widgets.EmailOrMobileEdit;

/**
 * UI to support collecting signup information from the user.
 */
public class AuthSignupFragment extends BaseFragment {
  private OnSignupListener mCallback;

  private EditText mFirstField;
  private EditText mLastField;
  private EmailOrMobileEdit mEmailOrMobile;
  private EditText mPasswordField;

  public interface OnSignupListener {
    public void onSelectSignup();
    public void onSwitchToLogin();
    public void onCreateAccount(String emailOrMobile, String password, String first, String last);
    public void onCancelSignup();
  }

  @Override
  public void onAttach(Activity activity) {
    super.onAttach(activity);
    mCallback = (OnSignupListener) activity;
  }

  @Override
  public View onCreateView(LayoutInflater inflater, final ViewGroup container, Bundle savedInstanceState) {
    View view = inflater.inflate(R.layout.auth_signup_fragment, container, false);

    mFirstField = (EditText)view.findViewById(R.id.auth_signupFirst);
    mLastField = (EditText)view.findViewById(R.id.auth_signupLast) ;
    mEmailOrMobile = new EmailOrMobileEdit(view.findViewById(R.id.auth_signupEmailOrMobile));
    mPasswordField = (EditText)view.findViewById(R.id.auth_signupPassword);

    Button cancelButton = (Button)view.findViewById(R.id.auth_signupCancel);
    Button createAccountButton = (Button)view.findViewById(R.id.auth_signupCreateAccount);
    Button signupTabButton = (Button)view.findViewById(R.id.auth_signupTabButton);
    Button loginTabButton = (Button)view.findViewById(R.id.auth_loginTabButton);

    signupTabButton.setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onSelectSignup();
      }
    });

    loginTabButton.setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onSwitchToLogin();
      }
    });

    createAccountButton.setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        // Validate input fields.
        boolean succeeded = InputValidation.setHintIfEmpty(mFirstField, R.string.auth_required);
        succeeded &= InputValidation.setHintIfEmpty(mLastField, R.string.auth_required);
        succeeded &= InputValidation.setHintIfEmpty(mPasswordField, R.string.auth_passwordRequired);

        if (mEmailOrMobile.getText().length() == 0) {
          mEmailOrMobile.setHint(true);
          succeeded = false;
        }

        if (succeeded) {
          mCallback.onCreateAccount(getFirst(), getLast(), getEmailOrMobile(), getPassword());
        }
      }
    });

    cancelButton.setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onCancelSignup();
      }
    });

    return view;
  }

  public String getFirst() {
    return mFirstField.getText().toString();
  }

  public String getLast() {
    return mLastField.getText().toString();
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
    View tabsView = getView().findViewById(R.id.auth_signupTabs);
    View cardView = getView().findViewById(R.id.auth_signupCard);

    if (tabsOpen) {
      cardView.setPadding(0, 0, 0, getResources().getDimensionPixelSize(R.dimen.auth_openTabPadding));
      tabsView.setBackgroundResource(R.drawable.tabs_modal_signup_selected_android);
    } else {
      cardView.setPadding(0, 0, 0, getResources().getDimensionPixelSize(R.dimen.auth_closedTabPadding));
      tabsView.setBackgroundResource(R.drawable.tabs_modal_signup_default_android);
    }

    // Reset the hint text for all fields in case input validation errors had changed them.
    mFirstField.setHint(R.string.auth_first);
    mLastField.setHint(R.string.auth_last);
    mPasswordField.setHint(R.string.auth_password);
    mEmailOrMobile.setHint(false /* useErrorHint */);
  }
}

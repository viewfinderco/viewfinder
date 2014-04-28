// Copyright 2013 Viewfinder. All rights reserved.
// Author: Andy Kimball
package co.viewfinder;

import android.app.Activity;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import co.viewfinder.widgets.EmailOrMobileEdit;

/**
 * UI to support collecting information for reset of user password.
 */
public class AuthResetFragment extends BaseFragment {
  private OnResetListener mCallback;

  private String mInitialEmailOrMobile;
  private EmailOrMobileEdit mEmailOrMobile;

  public interface OnResetListener {
    public void onSubmitReset(String emailOrMobile);
    public void onCancelReset();
  }

  public AuthResetFragment(String emailOrMobile) {
    mInitialEmailOrMobile = emailOrMobile;
  }

  @Override
  public void onAttach(Activity activity) {
    super.onAttach(activity);
    mCallback = (OnResetListener) activity;
  }

  @Override
  public View onCreateView(LayoutInflater inflater, final ViewGroup container, Bundle savedInstanceState) {
    View view = inflater.inflate(R.layout.auth_reset_fragment, container, false);

    mEmailOrMobile = new EmailOrMobileEdit(view.findViewById(R.id.auth_resetEmailOrMobile));
    mEmailOrMobile.setText(mInitialEmailOrMobile);

    ((Button)view.findViewById(R.id.auth_submit)).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        // Validate input field.
        if (mEmailOrMobile.getText().length() == 0) {
          mEmailOrMobile.setHint(true);
        } else {
          mCallback.onSubmitReset(mEmailOrMobile.getText().toString());
        }
      }
    });

    ((Button)view.findViewById(R.id.auth_back)).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onCancelReset();
      }
    });

    return view;
  }

  @Override
  public void onResume() {
    super.onResume();
    mEmailOrMobile.requestFocus();
    showSoftInput();
  }

  public String getEmailOrMobile() {
    return mEmailOrMobile.getText().toString();
  }
}

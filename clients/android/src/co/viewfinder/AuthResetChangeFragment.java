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

/**
 * UI to support collecting information for changing password after reset.
 */
public class AuthResetChangeFragment extends BaseFragment {
  private OnResetChangeListener mCallback;

  private EditText mNewPasswordField;
  private EditText mReEnterPasswordField;

  public interface OnResetChangeListener {
    public void onSubmitResetChange(String password);
    public void onCancelResetChange();
  }

  @Override
  public void onAttach(Activity activity) {
    super.onAttach(activity);
    mCallback = (OnResetChangeListener) activity;
  }

  @Override
  public View onCreateView(LayoutInflater inflater, final ViewGroup container, Bundle savedInstanceState) {
    View view = inflater.inflate(R.layout.auth_reset_change_fragment, container, false);

    mNewPasswordField = (EditText)view.findViewById(R.id.auth_newPassword);
    mReEnterPasswordField = (EditText)view.findViewById(R.id.auth_reEnterPassword);

    ((Button)view.findViewById(R.id.auth_submit)).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        // Validate input fields.
        boolean succeeded = InputValidation.setHintIfEmpty(mNewPasswordField, R.string.auth_newPasswordRequired);
        succeeded &= InputValidation.setHintIfEmpty(mReEnterPasswordField, R.string.auth_reEnterPasswordRequired);

        String newPassword = mNewPasswordField.getText().toString();
        String reEnterPassword = mReEnterPasswordField.getText().toString();
        if (!newPassword.equals(reEnterPassword)) {
          getErrorDialogManager().show(R.string.error_mismatchedPasswords);
          succeeded = false;
        }

        if (succeeded) {
          mCallback.onSubmitResetChange(newPassword);
        }
      }
    });

    ((Button)view.findViewById(R.id.auth_cancel)).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onCancelResetChange();
      }
    });

    return view;
  }

  @Override
  public void onResume() {
    super.onResume();
    mNewPasswordField.requestFocus();
    showSoftInput();
  }
}

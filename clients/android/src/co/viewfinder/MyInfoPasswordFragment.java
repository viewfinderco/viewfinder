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
 * UI to support collecting information for changing password.
 */
public class MyInfoPasswordFragment extends BaseFragment {
  private OnMyInfoPasswordListener mCallback;

  private EditText mOldPasswordField;
  private EditText mNewPasswordField;

  public interface OnMyInfoPasswordListener {
    public void onSubmitPasswordChange(String oldPassword, String newPassword);
    public void onCancelPasswordChange();
  }

  @Override
  public void onAttach(Activity activity) {
    super.onAttach(activity);
    mCallback = (OnMyInfoPasswordListener) activity;
  }

  @Override
  public View onCreateView(LayoutInflater inflater, final ViewGroup container, Bundle savedInstanceState) {
    View view = inflater.inflate(R.layout.myinfo_password_fragment, container, false);

    mOldPasswordField = (EditText)view.findViewById(R.id.myinfo_oldPassword);
    mNewPasswordField = (EditText)view.findViewById(R.id.myinfo_newPassword);

    ((Button)view.findViewById(R.id.myinfo_submit)).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        // Validate input fields.
        boolean succeeded = InputValidation.setHintIfEmpty(mOldPasswordField, R.string.myinfo_oldPasswordRequired);
        succeeded &= InputValidation.setHintIfEmpty(mNewPasswordField, R.string.auth_newPasswordRequired);

        if (succeeded) {
          mCallback.onSubmitPasswordChange(
              mOldPasswordField.getText().toString(),
              mNewPasswordField.getText().toString());
        }
      }
    });

    ((Button)view.findViewById(R.id.myinfo_cancel)).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onCancelPasswordChange();
      }
    });

    return view;
  }

  @Override
  public void onResume() {
    super.onResume();
    mOldPasswordField.requestFocus();
    showSoftInput();
  }
}

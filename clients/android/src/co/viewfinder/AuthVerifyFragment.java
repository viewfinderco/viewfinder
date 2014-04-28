// Copyright 2013 Viewfinder. All rights reserved.
// Author: Marc Berhault
package co.viewfinder;

import android.app.Activity;
import android.os.Bundle;
import android.text.InputFilter;
import android.util.Log;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.view.animation.Animation;
import android.view.animation.AnimationUtils;
import android.widget.EditText;
import android.widget.TextView;

/**
 * UI used to capture verify information from the user.
 */
public class AuthVerifyFragment extends BaseFragment {
  private static final String TAG = "viewfinder.AuthVerifyFragment";
  private static final int SEND_CODE_INTERVAL = 10;

  private OnVerifyListener mCallback = null;

  private String mEmailOrMobile;
  private EditText mVerifyCodeField;
  private int mNumTokenDigits;
  private long mSendCodeTime;

  public interface OnVerifyListener {
    void onContinueVerify(String emailOrMobile, String verifyCode);
    void onExitVerify();
    void onSendCodeAgain();
  }

  public AuthVerifyFragment(String emailOrMobile, int numTokenDigits) {
    mEmailOrMobile = emailOrMobile;
    mNumTokenDigits = numTokenDigits;
  }

  @Override
  public void onAttach(Activity activity) {
    super.onAttach(activity);
    mCallback = (OnVerifyListener) activity;
    mSendCodeTime = Time.currentTime();
  }

  @Override
  public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
    final View view = inflater.inflate(R.layout.auth_verify_fragment, container, false);

    mVerifyCodeField = (EditText)view.findViewById(R.id.auth_verifyCode);
    mVerifyCodeField.setHint(getString(R.string.auth_verifyCode, mNumTokenDigits));
    mVerifyCodeField.setFilters(new InputFilter[] { new InputFilter.LengthFilter(mNumTokenDigits) });

    // Set the email address or mobile number to which the code was sent.
    ((TextView)view.findViewById(R.id.auth_verifyEmailOrMobile)).setText(mEmailOrMobile);

    view.findViewById(R.id.auth_exit).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onExitVerify();
      }
    });

    view.findViewById(R.id.auth_sendAgain).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        long now = Time.currentTime();
        if (now < mSendCodeTime + SEND_CODE_INTERVAL) {
          getErrorDialogManager().show(R.string.error_sentCode, now - mSendCodeTime);
          return;
        }

        mSendCodeTime = now;
        mCallback.onSendCodeAgain();

        Animation shake = AnimationUtils.loadAnimation(getActivity(), R.anim.shake);
        view.findViewById(R.id.auth_sentCode).startAnimation(shake);
      }
    });

    view.findViewById(R.id.auth_continue).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        String result = mVerifyCodeField.getText().toString();
        if (result.length() != mNumTokenDigits) {
          getErrorDialogManager().show(R.string.error_notValidCode, mNumTokenDigits, result.length());
        } else {
          mCallback.onContinueVerify(mEmailOrMobile, result);
        }
      }
    });

    return view;
  }

  @Override
  public void onResume() {
    super.onResume();
    mVerifyCodeField.requestFocus();
    showSoftInput();
  }
}

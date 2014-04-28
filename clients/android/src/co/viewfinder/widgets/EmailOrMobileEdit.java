// Copyright 2013 Viewfinder. All rights reserved.
// Author: Andy Kimball
package co.viewfinder.widgets;

import android.content.Context;
import android.graphics.Typeface;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.View;
import android.widget.ImageButton;
import co.viewfinder.R;

/**
 * This class contains the glue code for a custom edit text control that allows input of either
 * an email address or a mobile phone number. The edit text box is paired with a keyboard toggle
 * button control. When pressed, the button toggles between the email keyboard and the numeric
 * keyboard.
 *
 * This class encapsulates code used with the email_or_text_edit.xml. Import that layout into
 * a container layout, and then pass that container to the class constructor so that the edit
 * text box and button can be wired up.
 */
public class EmailOrMobileEdit {
  private View mContainerView;
  private ViewfinderEditText mEditText;
  private ImageButton mKeyboardToggle;
  private boolean mUseEmailKeyboard;
  private boolean mUseErrorHint;

  public EmailOrMobileEdit(View containerView) {
    mContainerView = containerView;
    mEditText = (ViewfinderEditText)containerView.findViewById(R.id.emailOrText_text);
    mKeyboardToggle = (ImageButton)containerView.findViewById(R.id.emailOrText_keyboardToggle);
    mUseEmailKeyboard = true;

    mKeyboardToggle.setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        // Toggle the keypad in use (alphabetic or numeric).
        mUseEmailKeyboard = !mUseEmailKeyboard;
        setState();
      }
    });

    mEditText.setOnFocusChangeListener(new View.OnFocusChangeListener() {
      @Override
      public void onFocusChange(View v, boolean hasFocus) {
        // Need to show or hide the keypad toggle button.
        setState();
      }
    });

    mEditText.addTextChangedListener(new TextWatcher() {
      @Override
      public void afterTextChanged(Editable s) {
      }

      @Override
      public void beforeTextChanged(CharSequence s, int start, int count, int after) {
      }

      @Override
      public void onTextChanged(CharSequence s, int start, int before, int count) {
        // Need to show or hide the keypad toggle button if transitioned to/from no text.
        int after = s.length();
        if ((after == 0 && before != 0) || (after != 0 && after == count)) {
          setState();
        }
      }
    });

    // Set initial state.
    setState();
  }

  public Editable getText() {
    return mEditText.getText();
  }

  public void setText(CharSequence text) {
    mEditText.setText(text);
  }

  public void requestFocus() {
    mEditText.requestFocus();
  }

  public void setHint(boolean useErrorHint) {
    mUseErrorHint = useErrorHint;
    if (mUseEmailKeyboard) {
      mEditText.setHint(useErrorHint ? R.string.auth_emailOrMobileRequired : R.string.auth_emailOrMobile);
    } else {
      mEditText.setHint(useErrorHint ? R.string.auth_mobileRequired : R.string.auth_mobile);
    }
  }

  private void setState() {
    // Do not show the keypad toggle if there's text in the email/mobile field, or if the
    // field does not have the focus.
    if (mEditText.getText().length() != 0 || !mEditText.isFocused()) {
      mKeyboardToggle.setVisibility(View.GONE);
    }
    else {
      // Show either the alphabetic or numeric keyboard toggle.
      if (mUseEmailKeyboard) {
        mKeyboardToggle.setImageResource(R.drawable.keypad_toggle_123);
      } else {
        mKeyboardToggle.setImageResource(R.drawable.keypad_toggle_abc);
      }

      setHint(mUseErrorHint);
      mKeyboardToggle.setVisibility(View.VISIBLE);
    }

    // Make sure that the input type is set to email or number.
    if (mUseEmailKeyboard) {
      mEditText.setInputType(InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS);
    } else {
      mEditText.setInputType(InputType.TYPE_CLASS_NUMBER);
    }
  }
}

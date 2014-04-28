package co.viewfinder;

import android.app.Activity;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.view.animation.AlphaAnimation;
import android.view.animation.Animation;
import android.view.animation.AnimationUtils;
import android.widget.EditText;
import android.widget.ListView;
import android.widget.TextView;
import co.viewfinder.proto.ContactMetadataPB;
import co.viewfinder.widgets.ContactCardLayout;
import co.viewfinder.widgets.ViewfinderEditText;
import co.viewfinder.widgets.ViewfinderButton;

public class ContactInfoFragment extends BaseFragment {
  private static final String TAG = "Viewfinder.ContactInfoFragment";
  private static final String ARG_CONTACT_ID = "co.viewfinder.contact_id";

  private ViewfinderEditText mNicknameField;
  private ViewfinderButton mDoneButton;
  private View mEditingMask;
  private ContactCardLayout mContactCardLayout;
  private ContactMetadataPB.ContactMetadata mContact;

  public static ContactInfoFragment newInstance(long contactId) {
    ContactInfoFragment contactInfoFragment = new ContactInfoFragment();
    Bundle args = new Bundle();
    args.putLong(ARG_CONTACT_ID, contactId);
    contactInfoFragment.setArguments(args);
    return contactInfoFragment;
  }

  /**
   * Tells the fragment to blur focus on any control currently being edited.
   *
   * @return true if a field was being edited, false otherwise.
   */
  public boolean stopEditing() {
    if (mNicknameField.hasFocus()) {
      mNicknameField.clearFocus();
      hideSoftInput();
      return true;
    }

    return false;
  }

  @Override
  public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
    View view = inflater.inflate(R.layout.fragment_contact_info, container, false);
    mContactCardLayout = (ContactCardLayout) view.findViewById(R.id.contact_card);
    mNicknameField = (ViewfinderEditText) view.findViewById(R.id.contact_info_nick_field);
    mEditingMask = view.findViewById(R.id.editing_mask);
    mDoneButton = (ViewfinderButton) view.findViewById(R.id.button_done);
    View nicknameCard = view.findViewById(R.id.nickname_card);

    // Set default visibility on edit-mode elements.
    mEditingMask.setVisibility(View.INVISIBLE);
    mDoneButton.setVisibility(View.INVISIBLE);

    nicknameCard.setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mNicknameField.requestFocus();
        showSoftInput();
      }
    });

    mNicknameField.setOnFocusChangeListener(new View.OnFocusChangeListener() {
      @Override
      public void onFocusChange(View v, boolean hasFocus) {
        if (hasFocus) {
          startEditNickname();
        } else {
          finishEditNickname();
        }
      }
    });

    mDoneButton.setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        String editedName = mNicknameField.getText().toString();
        if ((mContact.getNickname() != editedName)) {
          getViewData().getContactViewData().setNickname(mContact.getUserId(), editedName);
        }

        stopEditing();
      }
    });

    onUpdateSelf();

    return view;
  }

  private void onUpdateSelf() {
    long contactId = getArguments().getLong(ARG_CONTACT_ID);
    mContact = getViewData().getContactViewData().getItem(contactId);

    // Bind contact card to current contact.
    mContactCardLayout.setContact(mContact, false);
    mNicknameField.setText(mContact.getNickname());
  }

  private void fadeViewVisibility(final View view, final int targetVisibility) {
    final int currentVisibility = view.getVisibility();
    if (currentVisibility == targetVisibility) return;

    final int animationResource = (targetVisibility == View.VISIBLE) ? R.anim.fade_in : R.anim.fade_out;
    Animation fade = AnimationUtils.loadAnimation(view.getContext(), animationResource);
    fade.setAnimationListener(new Animation.AnimationListener() {
      @Override
      public void onAnimationStart(Animation animation) {
        view.setVisibility(View.VISIBLE);
      }

      @Override
      public void onAnimationEnd(Animation animation) {
        view.setVisibility(targetVisibility);
      }

      @Override
      public void onAnimationRepeat(Animation animation) {}
    });

    view.startAnimation(fade);
  }

  private void startEditNickname() {
    fadeViewVisibility(mEditingMask, View.VISIBLE);
    fadeViewVisibility(mDoneButton, View.VISIBLE);
  }

  private void finishEditNickname() {
    fadeViewVisibility(mEditingMask, View.INVISIBLE);
    fadeViewVisibility(mDoneButton, View.INVISIBLE);
    onUpdateSelf();
  }
}

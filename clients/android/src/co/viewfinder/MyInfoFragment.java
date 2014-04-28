// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.app.Activity;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import co.viewfinder.proto.ContactMetadataPB;
import co.viewfinder.widgets.ContactCardLayout;
import junit.framework.Assert;

/**
 * UI for 'My Info'.
 */
public class MyInfoFragment extends BaseFragment {
  private OnMyInfoListener mCallback = null;

  private ContactCardLayout mContactCard;

  public interface OnMyInfoListener {
    public void onEditName();
    public void onChangePassword();
  }

  @Override
  public void onAttach(Activity activity) {
    super.onAttach(activity);
    mCallback = (OnMyInfoListener) activity;
  }

  @Override
  public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
    View view = inflater.inflate(R.layout.myinfo_fragment, container, false);

    // Save contact info layout.
    mContactCard = (ContactCardLayout)view.findViewById(R.id.myinfo_contact);

    // Populate initial contact card.
    onUpdateSelf();

    view.findViewById(R.id.myinfo_changePassword).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onChangePassword();
      }
    });

    return view;
  }

  /**
   * Called when the self contact has been updated and view needs to be re-generated.
   */
  public void onUpdateSelf() {
    // Get info about self.
    ContactMetadataPB.ContactMetadata myself = getAppState().getSelfContact();
    Assert.assertNotNull("Should never get here if self metadata is not available", myself);

    // Set contact into card layout.
    mContactCard.setContact(myself, true /* allowEdit */);

    // Capture clicks on the first item in the contact card, which is the user's name.
    mContactCard.getChildAt(0).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onEditName();
      }
    });
  }
}

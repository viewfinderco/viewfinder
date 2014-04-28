// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.app.Activity;
import android.os.Bundle;
import android.util.Log;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;
import co.viewfinder.proto.ContactMetadataPB;
import co.viewfinder.proto.ContactMetadataPB.ContactMetadata;

/**
 * Handle Profile view.
 */
public class ProfileFragment extends BaseFragment {
  private static final String TAG = "viewfinder.ProfileFragment";
  private OnProfileListener mCallback = null;

  public interface OnProfileListener {
    public void onMyInfo();
    public void onContacts();
    public void onSettings();
    public void onMyPhotos();
    public void onInbox();
  }

  @Override
  public void onAttach(Activity activity) {
    super.onAttach(activity);
    mCallback = (OnProfileListener) activity;
  }

  @Override
  public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
    View view = inflater.inflate(R.layout.profile_fragment, container, false);

    // TODO(marc): we should have a callback here so we can be notified of QueryUsersResponse.
    // Only show name if contact info for self is available.
    ContactMetadataPB.ContactMetadata myself = getAppState().getSelfContact();
    view.findViewById(R.id.profile_userName).setVisibility(myself != null ? View.VISIBLE : View.GONE);
    if (myself != null) {
      TextView name = (TextView)view.findViewById(R.id.profile_userNameText);
      name.setText(myself.getName());
    }

    TextView textViewContactCount = (TextView)view.findViewById(R.id.profile_contactCount);
    textViewContactCount.setText(Integer.toString(getAppState().contactManager().viewfinderCount()));

    TextView textViewConvCount = (TextView)view.findViewById(R.id.profile_convoCount);
    // TODO(mike): register for data change notification on this so that the view gets updated
    //    when the count changes.
    textViewConvCount.setText(Integer.toString(getViewData().getInboxViewData().getCount()));

    view.findViewById(R.id.profile_settings).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onSettings();
      }
    });

    view.findViewById(R.id.profile_photos).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onMyPhotos();
      }
    });

    view.findViewById(R.id.profile_contacts).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onContacts();
      }
    });

    view.findViewById(R.id.profile_convos).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onInbox();
      }
    });

    view.findViewById(R.id.profile_userName).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onMyInfo();
      }
    });

    return view;
  }
}

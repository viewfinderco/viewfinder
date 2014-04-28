// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.app.Activity;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.*;
import co.viewfinder.widgets.SpringyListView;

/**
 * Handle inbox view.
 */
public class InboxFragment extends BaseFragment {
  private static final String TAG = "Viewfinder.InboxFragment";

  private OnInboxListener mCallback = null;

  public interface OnInboxListener {
    public void onCamera();
    public void onCompose();
    public void onContacts();
    public void onEditInbox();
    public void onInboxItem(int position);
    public void onMyPhotos();
    public void onProfile();
  }

  @Override
  public void onAttach(Activity activity) {
    super.onAttach(activity);
    mCallback = (OnInboxListener) activity;
  }

  @Override
  public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {

    View view = inflater.inflate(R.layout.fragment_inbox, container, false);

    ConvSummaryAdapter convSummaryAdapter = new ConvSummaryAdapter(this);
    convSummaryAdapter.setInboxItems(getViewData().getInboxViewData());
    SpringyListView listView = (SpringyListView)view.findViewById(R.id.listView_inbox);
    listView.setAdapter(convSummaryAdapter);
    convSummaryAdapter.setListView(listView);

    listView.setOnItemClickListener(new AdapterView.OnItemClickListener() {
      @Override
      public void onItemClick(AdapterView<?> parent, View view, int position, long id) {
        mCallback.onInboxItem(position);
      }
    });

    view.findViewById(R.id.imageButton_titleBarLeft).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onProfile();
      }
    });

    view.findViewById(R.id.imageButton_navbarLeft).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onContacts();
      }
    });

    view.findViewById(R.id.imageButton_navbarRight).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onMyPhotos();
      }
    });

    view.findViewById(R.id.imageButton_navbarMiddleLeft).setOnClickListener(new View.OnClickListener() {
      @Override
        public void onClick(View v) {
          mCallback.onCamera();
        }
    });

    view.findViewById(R.id.button_titleBarRight).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onEditInbox();
      }
    });

    view.findViewById(R.id.imageButton_navbarMiddleRight).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onCompose();
      }
    });

    return view;
  }
}

// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.app.Activity;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.AdapterView;
import android.widget.ListView;

/**
 *  UI for contacts.
 */
public class ContactsFragment extends BaseFragment {
  private static final String TAG = "Viewfinder.ContactsFragment";
  private OnContactsListener mCallback = null;

  public interface OnContactsListener {
    public void onContactSelected(long contactId);
  }

  @Override
  public void onAttach(Activity activity) {
    super.onAttach(activity);
    mCallback = (OnContactsListener) activity;
  }

  @Override
  public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
    View view = inflater.inflate(R.layout.fragment_contacts, container, false);

    ContactsListAdapter adapter = new ContactsListAdapter(inflater, getViewData().getContactViewData());
    ListView listView = (ListView)view.findViewById(R.id.contacts_list);
    listView.setAdapter(adapter);

    listView.setOnItemClickListener(new AdapterView.OnItemClickListener() {
      @Override
      public void onItemClick(AdapterView<?> parent, View view, int position, long id) {
        mCallback.onContactSelected(id);
      }
    });

    return view;

  }



}

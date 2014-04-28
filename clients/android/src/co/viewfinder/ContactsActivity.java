// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.content.Intent;
import android.util.Log;
import android.os.Bundle;
import android.support.v4.app.Fragment;
import android.support.v4.app.FragmentManager;


/**
 * Activity to manage contacts.
 */
public class ContactsActivity extends BaseActivity implements ContactsFragment.OnContactsListener {
  private final static String TAG = "Viewfinder.ContactsActivity";
  private final static String TAG_CONTACTS_FRAGMENT = "co.viewfinder.contacts_fragment";

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    setContentView(R.layout.statusbar_activity);

    FragmentManager fm = getSupportFragmentManager();
    Fragment fragment = fm.findFragmentByTag(TAG_CONTACTS_FRAGMENT);
    if (fragment == null) {
      fragment = new ContactsFragment();
      fm.beginTransaction()
          .add(R.id.statusbar_content, fragment, TAG_CONTACTS_FRAGMENT)
          .commit();
    }
  }

  @Override
  public void onContactSelected(long contactId) {
    Log.d(TAG, "onContactSelected");
    Intent i = new Intent(ContactsActivity.this, ContactInfoActivity.class);
    i.putExtra(ContactInfoActivity.EXTRA_CONTACT_ID, contactId);
    startActivity(i);
    overridePendingTransition(R.anim.slide_in_right, R.anim.hold);
  }
}

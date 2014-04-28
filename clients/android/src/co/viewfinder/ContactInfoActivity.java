package co.viewfinder;

import android.os.Bundle;
import android.support.v4.app.Fragment;
import android.support.v4.app.FragmentManager;

public class ContactInfoActivity extends BaseActivity {
  private final static String TAG = "Viewfinder.ContactInfoActivity";
  private final static String TAG_CONTACTS_FRAGMENT = "co.viewfinder.contact_info_fragment";

  public static final String EXTRA_CONTACT_ID = "co.viewfinder.contact_id";

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    setContentView(R.layout.statusbar_activity);

    FragmentManager fm = getSupportFragmentManager();
    Fragment fragment = fm.findFragmentByTag(TAG_CONTACTS_FRAGMENT);
    if (fragment == null) {
      fragment = ContactInfoFragment.newInstance(getIntent().getLongExtra(EXTRA_CONTACT_ID, -1));
      fm.beginTransaction()
              .add(R.id.statusbar_content, fragment, TAG_CONTACTS_FRAGMENT)
              .commit();
    }
  }

  @Override
  public void onBackPressed() {
    FragmentManager fm = getSupportFragmentManager();
    ContactInfoFragment cif = (ContactInfoFragment) fm.findFragmentByTag(TAG_CONTACTS_FRAGMENT);

    if (!cif.stopEditing()) {
      super.onBackPressed();
      overridePendingTransition(R.anim.hold, R.anim.slide_out_right);
    }
  }
}

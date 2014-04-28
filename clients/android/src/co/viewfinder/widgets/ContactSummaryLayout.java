// Copyright 2013 Viewfinder. All rights reserved.
// Author: Andy Kimball
package co.viewfinder.widgets;

import android.content.Context;
import android.graphics.Typeface;
import android.util.AttributeSet;
import android.view.LayoutInflater;
import android.view.View;
import android.widget.ImageView;
import android.widget.FrameLayout;
import android.widget.RelativeLayout;
import android.widget.TextView;
import co.viewfinder.IdentityUtils;
import co.viewfinder.R;
import co.viewfinder.proto.ContactMetadataPB;

/**
 * Layout that displays a short summary of a contact.
 *   1. Contact name (or nickname if available).
 *   2. The contact's primary identity (email, phone, etc).
 *   3. A description of the phone
 */
public class ContactSummaryLayout extends FrameLayout {
  private RelativeLayout mLayout;
  private ImageView mContactIcon;
  private TextView mDisplayName;
  private TextView mRealName;
  private TextView mIdentityString;

  public ContactSummaryLayout(Context context) {
    this(context, null);
  }

  public ContactSummaryLayout(Context context, AttributeSet attrs) {
    super(context, attrs);
  }

  public void setContact(ContactMetadataPB.ContactMetadata contact) {
    if (null == mLayout) {
      // Inflate a contact card item.
      LayoutInflater inflater = LayoutInflater.from(getContext());
      mLayout = (RelativeLayout) inflater.inflate(R.layout.contacts_item, this, false);
      mContactIcon = (ImageView) mLayout.findViewById(R.id.profile_image);
      mDisplayName = (TextView) mLayout.findViewById(R.id.contact_display_name);
      mRealName = (TextView) mLayout.findViewById(R.id.contact_real_name);
      mIdentityString = (TextView) mLayout.findViewById(R.id.contact_email);

      addView(mLayout);
    }


    // TODO: Implement using ContactManager methods.
    boolean isViewfinderUser = contact.hasUserId();

    if (isViewfinderUser) {
      mDisplayName.setTypeface(null, Typeface.BOLD);
    }

    // Set up display names.
    if (contact.hasNickname() && contact.getNickname().length() > 0) {
      mDisplayName.setText(contact.getNickname());
      mRealName.setText(contact.getName());
      mRealName.setVisibility(View.VISIBLE);
    } else {
      mDisplayName.setText(contact.getName());
      mRealName.setVisibility(View.GONE);
    }

    // Determine Identity summary string
    String identityString = IdentityUtils.getFormattedValue(contact.getPrimaryIdentity());
    if (contact.getIdentitiesCount() > 1) {
      identityString = identityString.concat(" (and " + (contact.getIdentitiesCount() - 1) + " more)");
    }

    mIdentityString.setText(identityString);

    // Icon image
    mContactIcon.setImageResource(isViewfinderUser ? R.drawable.contact_user_viewfinder : R.drawable.contact_nonuser);

    // Set background
    mLayout.setBackgroundResource(isViewfinderUser ? R.drawable.contact_summary_selector : R.drawable.contact_summary_nonuser_selector);
  }
}

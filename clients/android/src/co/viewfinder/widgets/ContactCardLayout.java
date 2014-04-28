// Copyright 2013 Viewfinder. All rights reserved.
// Author: Andy Kimball
package co.viewfinder.widgets;

import android.content.Context;
import android.graphics.Typeface;
import android.util.AttributeSet;
import android.view.LayoutInflater;
import android.view.View;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import co.viewfinder.IdentityUtils;
import co.viewfinder.R;
import co.viewfinder.proto.ContactMetadataPB;

/**
 * Layout that displays a card that contains information about a contact:
 *   1. Contact name (may be editable if the contact is the user himself).
 *   2. Contact identities (email, phone, etc).
 */
public class ContactCardLayout extends LinearLayout {
  public ContactCardLayout(Context context) {
    this(context, null);
  }

  public ContactCardLayout(Context context, AttributeSet attrs) {
    super(context, attrs);
  }

  public void setContact(ContactMetadataPB.ContactMetadata contact, boolean allowEdit) {
    // Remove any card items added before.
    removeAllViews();

    // Inflate a contact card item.
    LayoutInflater inflater = LayoutInflater.from(getContext());
    View contactCardView = inflater.inflate(R.layout.contact_card_item, this, false);

    // Set the contact name and make it bold.
    TextView nameView = (TextView)contactCardView.findViewById(R.id.contact_id);
    nameView.setText(contact.getName());
    nameView.setTypeface(null, Typeface.BOLD);

    // If editing of the name is not allowed, then remove edit icon.
    if (!allowEdit) {
      contactCardView.findViewById(R.id.contact_edit).setVisibility(View.GONE);
    }

    addView(contactCardView);

    // Inflate an item for each contact identity.
    for (int i = 0; i < contact.getIdentitiesCount(); i++) {
      String identity_key = contact.getIdentities(i).getIdentity();
      IdentityUtils.IdType idType = IdentityUtils.getType(identity_key);

      // Skip any identity types besides email and phone.
      if (idType == IdentityUtils.IdType.EMAIL || idType == IdentityUtils.IdType.PHONE) {
        contactCardView = inflater.inflate(R.layout.contact_card_item, this, false);
        contactCardView.findViewById(R.id.contact_edit).setVisibility(View.GONE);

        // Set the email or phone icon.
        ImageView iconView = (ImageView)contactCardView.findViewById(R.id.contact_icon);
        if (idType == IdentityUtils.IdType.EMAIL) {
          iconView.setImageResource(R.drawable.contact_info_email);
        } else {
          iconView.setImageResource(R.drawable.contact_info_mobile);
        }

        // Set the formatted email address or phone number.
        nameView = (TextView)contactCardView.findViewById(R.id.contact_id);
        nameView.setText(IdentityUtils.getFormattedValue(identity_key));

        addView(contactCardView);
      }
    }

    // Set card backgrounds for each row.
    int childCount = getChildCount();
    if (childCount > 1) {
      getChildAt(0).setBackgroundResource(R.drawable.table_cell_background_top);

      for (int i = 1; i < childCount - 1; i++) {
        getChildAt(i).setBackgroundResource(R.drawable.table_cell_background_middle);
      }

      getChildAt(childCount - 1).setBackgroundResource(R.drawable.table_cell_background_bottom);
    }
  }
}

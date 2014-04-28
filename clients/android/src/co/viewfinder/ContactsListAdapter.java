package co.viewfinder;

import android.database.DataSetObserver;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.BaseAdapter;
import android.content.Context;
import android.widget.ImageView;
import android.widget.TextView;
import co.viewfinder.proto.ContactMetadataPB;
import co.viewfinder.widgets.ContactSummaryLayout;

/**
 * Created with IntelliJ IDEA.
 * User: matttracy
 * Date: 10/1/13
 * Time: 3:53 PM
 * To change this template use File | Settings | File Templates.
 */
public class ContactsListAdapter extends BaseAdapter {
  private ViewData.ContactViewData mContacts;

  private LayoutInflater mInflater;

  public ContactsListAdapter(LayoutInflater inflater, ViewData.ContactViewData contacts)  {
    mInflater = inflater;
    mContacts = contacts;
  }

  @Override
  public int getCount() {
    return mContacts.getCount();
  }

  @Override
  public void registerDataSetObserver(DataSetObserver observer) {
    // Pass to contacts manager.
    mContacts.registerDataSetObserver(observer);
  }

  @Override
  public void unregisterDataSetObserver(DataSetObserver observer) {
    // Pass to contacts manager.
    mContacts.unregisterDataSetObserver(observer);
  }

  @Override
  public Object getItem(int position) {
    return mContacts.getItem(position);
  }

  @Override
  public long getItemId(int position) {
    return mContacts.getItem(position).getUserId();
  }

  @Override
  public View getView(int position, View convertView, ViewGroup parent) {
    ContactSummaryLayout row = (ContactSummaryLayout) convertView;
    if (null == convertView) {
      row = (ContactSummaryLayout) mInflater.inflate(R.layout.contact_summary_item, parent, false);
    }

    row.setContact((ContactMetadataPB.ContactMetadata) getItem(position));
    return row;
  }
}

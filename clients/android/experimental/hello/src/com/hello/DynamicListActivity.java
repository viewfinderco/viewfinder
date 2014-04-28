package com.hello;

import android.app.Activity;
import android.app.ListActivity;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Matrix;
import android.media.ExifInterface;
import android.os.Bundle;
import android.util.Log;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.AbsListView;
import android.widget.AbsListView.OnScrollListener;
import android.widget.BaseAdapter;
import android.widget.ImageView;
import android.widget.ListView;
import android.widget.TextView;
import java.util.HashMap;

public class DynamicListActivity extends ListActivity implements OnScrollListener {

  DynamicAdapter adapter = null;
  private PhotoTable photoTable = null;

  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    ListView listView = getListView();
    adapter = new DynamicAdapter(this, listView);
    setListAdapter(adapter);
    // Handle scroll events. Needed to tell the adapter the number of visible rows has changed.
    listView.setOnScrollListener(this);
    // Remove the 1 pixel line between items.
    listView.setDividerHeight(0);
    photoTable = ((App)getApplicationContext()).getPhotoTable();
    Log.i(HelloActivity.TAG, "Num photos in table: " + photoTable.numPhotos());
  }

  public void onScroll(AbsListView view, int firstVisible, int visibleCount, int totalCount) {
    ListView listView = getListView();
    Log.i(HelloActivity.TAG, "Range: [" + firstVisible + " - " + (firstVisible + visibleCount - 1) + "]");

    boolean loadMore = firstVisible + visibleCount >= totalCount;

    if (loadMore) {
      adapter.count += visibleCount; // or any other amount
      adapter.notifyDataSetChanged();
    }
  }

  public void onScrollStateChanged(AbsListView v, int s) { }

  class DynamicAdapter extends BaseAdapter {
    public DynamicAdapter(Activity activity, ListView listView) {
      super();
      this.activity = activity;
      this.listView = listView;
      this.app = (App)getApplicationContext();
      this.photoTable = app.getPhotoTable();
      this.savedViews = new HashMap<Integer, View>();
    }

    int count = 40; /* starting amount */
    private Activity activity;
    private ListView listView;
    private App app;
    private PhotoTable photoTable;
    private HashMap<Integer, View> savedViews;

    public int getCount() { return count; }
    public Object getItem(int pos) { return pos; }
    public long getItemId(int pos) { return pos; }

    public View getView(int pos, View convertView, ViewGroup p) {
      // We could reuse convertView (a previously-built view that is now invisible), but
      // we cache them, so let's not.
      // View newView = convertView;
      View newView = savedViews.get(Integer.valueOf(pos));
      if (newView != null) {
        return newView;
      }
      if (newView == null) {
        LayoutInflater inflater = this.activity.getLayoutInflater();
        // The parent view needs to be passed to apply the xml layout params.
        newView = inflater.inflate(R.layout.row_layout, this.listView, false);
        Log.i(HelloActivity.TAG, "New view pos: " + pos);

        // Save views as tags. This is faster than findViewById.
        newView.setTag(R.id.row_icon_view, newView.findViewById(R.id.row_icon));
        newView.setTag(R.id.row_date_view, newView.findViewById(R.id.row_date));
        newView.setTag(R.id.row_label_view, newView.findViewById(R.id.row_label));
      } else {
        Log.i(HelloActivity.TAG, "Reuse view: " + newView.getTag(R.id.row_entry_value) + " -> " + pos);
      }
      newView.setTag(R.id.row_entry_value, pos);

      ImageView image = (ImageView) newView.getTag(R.id.row_icon_view);

      PhotoTable.PhotoInfo info = photoTable.getPhoto(pos, true);
      ExifInterface exif = photoTable.getExif(info);
      String date = (exif == null) ? "N/A" : exif.getAttribute(ExifInterface.TAG_DATETIME);

      TextView date_text = (TextView) newView.getTag(R.id.row_date_view);
      date_text.setTypeface(app.getProximaNovaRegularTypeface());
      // Displays the "photo" icon.
      date_text.setText(date + " \u2632 1");

      TextView text = (TextView) newView.getTag(R.id.row_label_view);
      text.setTypeface(app.getProximaNovaBoldTypeface());
      String label_str = exif.getAttribute(ExifInterface.TAG_MAKE) + " " +
                         exif.getAttribute(ExifInterface.TAG_MODEL);
      text.setText(label_str);

      Bitmap exif_thumbnail = photoTable.getExifThumbnail(info);
      if (exif_thumbnail != null) {
        Log.i(HelloActivity.TAG, "Using EXIF thumbnail");
        image.setImageBitmap(exif_thumbnail);
      } else {
        String thumb_data = photoTable.getThumbnail(info);
        if (thumb_data != null) {
          Log.i(HelloActivity.TAG, "Using thumbnail");
          image.setImageBitmap(BitmapFactory.decodeFile(thumb_data));
        }
      }
      Log.i(HelloActivity.TAG, "Loading image in background");
      photoTable.setPhotoOnView(info, image);

      savedViews.put(Integer.valueOf(pos), newView);
      return newView;
    }
  }
}

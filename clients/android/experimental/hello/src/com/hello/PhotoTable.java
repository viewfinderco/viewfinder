package com.hello;

import android.app.LoaderManager;
import android.content.Context;
import android.content.CursorLoader;
import android.content.Loader;
import android.database.Cursor;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.media.ExifInterface;
import android.net.Uri;
import android.os.AsyncTask;
import android.os.Bundle;
import android.provider.MediaStore;
import android.provider.MediaStore.Images.Thumbnails;
import android.util.Log;
import android.widget.ImageView;
import java.io.IOException;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.ArrayList;

public class PhotoTable extends AsyncTask<Void, Void, ArrayList<PhotoTable.PhotoInfo>> {
  private ArrayList<PhotoInfo> photos = null;
  private boolean loaderStarted = false;
  private static final int LOADER_ID = 1;
  private Context context;

  public class PhotoInfo {
    public long image_id;
    public String uri;
    public String name;
    public PhotoInfo(long image_id, String uri, String name) {
      this.image_id = image_id;
      this.uri = uri;
      this.name = name;
    }
  }

  public PhotoTable(Context context) {
    this.context = context;
  }

  public int numPhotos() {
    Utils.assertIsUIThread();
    if (photos == null) {
      return 0;
    } else {
      return photos.size();
    }
  }

  public PhotoInfo getPhoto(int pos, boolean modulo) {
    Utils.assertIsUIThread();
    if (photos == null || photos.size() == 0) {
      return null;
    }
    int index = pos;
    if (modulo) {
      index = pos % photos.size();
    }
    if (index >= photos.size()) {
      return null;
    }
    return photos.get(index);
  }

  public String getThumbnail(PhotoInfo info) {
    // Get thumbnails.
    Uri uri = MediaStore.Images.Thumbnails.EXTERNAL_CONTENT_URI;
    String[] projection = new String[] {
      MediaStore.Images.Thumbnails._ID,
      MediaStore.Images.Thumbnails.KIND,
      MediaStore.Images.Thumbnails.IMAGE_ID,
      MediaStore.Images.Thumbnails.DATA,
    };
    String selection = MediaStore.Images.Thumbnails.IMAGE_ID + "= ?";
    String[] args = new String[]{String.valueOf(info.image_id)};

    Cursor cursor = this.context.getContentResolver().query(uri, null, selection, args, null);
    if (cursor == null) {
      Log.i(HelloActivity.TAG, "cursor is null");
      return null;
    }

    Log.i(HelloActivity.TAG, "num rows: " + cursor.getCount());
    // Cursor index starts at -1. let's not ask why.
    String data = null;
    if (cursor.moveToFirst()) {
      String id = cursor.getString(cursor.getColumnIndex(Thumbnails._ID));
      String kind = cursor.getString(cursor.getColumnIndex(Thumbnails.KIND));
      String image_id = cursor.getString(cursor.getColumnIndex(Thumbnails.IMAGE_ID));
      data = cursor.getString(cursor.getColumnIndex(Thumbnails.DATA));
      Log.i(HelloActivity.TAG, "ID: " + id + " kind: " + kind +
                               " image_id: " + image_id + " data: " + data);
    }
    cursor.close();
    return data;
  }

  public ExifInterface getExif(PhotoInfo info) {
    ExifInterface ret = null;
    try {
      ret = new ExifInterface(info.uri);
    } catch (IOException e) {

      e.printStackTrace();
    }
    return ret;
  }

  public Bitmap getExifThumbnail(PhotoInfo info) {
    Bitmap ret = null;
    try {
      ExifInterface exifInterface = new ExifInterface(info.uri);
      Log.i(HelloActivity.TAG, "Photo: " + info.uri +
                               " make: " + exifInterface.getAttribute(ExifInterface.TAG_MAKE) +
                               " model: " + exifInterface.getAttribute(ExifInterface.TAG_MODEL) +
                               " has_thumbnail: " + exifInterface.hasThumbnail());
      if (exifInterface.hasThumbnail()) {
        byte[] thumbnail =  exifInterface.getThumbnail();
        ret = BitmapFactory.decodeByteArray(thumbnail, 0, thumbnail.length);
      }
    } catch (IOException e) {
      e.printStackTrace();
    }
    return ret;
  }

  public void setPhotoOnView(PhotoInfo info, ImageView view) {
    // In UI thread: slow
    //view.setImageBitmap(BitmapFactory.decodeFile(info.uri));
    // In background: better
    (new PhotoLoader(info, view)).execute();
  }

  @Override
  protected void onPreExecute() {
    // On UI thread.
  }

  @Override
  protected ArrayList<PhotoInfo> doInBackground(Void... params) {
    // Get could fetch all thumbnails and populate the PhotoInfo objects that have them.
    //getAllThumbnails();
    return getAllImages();
  }

  @Override
  protected void onPostExecute(ArrayList<PhotoInfo> op_result) {
    // On UI thread.
    photos = op_result;
  }

  private ArrayList<PhotoInfo> getAllImages() {
    // Get images.
    Uri uri = MediaStore.Images.Media.EXTERNAL_CONTENT_URI;
    String[] projection = new String[] {
      MediaStore.Images.Media.BUCKET_DISPLAY_NAME,
      MediaStore.Images.Media.DATE_TAKEN,
      MediaStore.Images.Media.DISPLAY_NAME,
      MediaStore.Images.Media.LATITUDE,
      MediaStore.Images.Media.LONGITUDE,
      // Thumbnail ID.
      MediaStore.Images.ImageColumns.MINI_THUMB_MAGIC,
      MediaStore.Images.ImageColumns._ID,
      MediaStore.Images.ImageColumns.DATA,
    };
    String selection = null;

    Cursor cursor = this.context.getContentResolver().query(uri, projection, selection, null, null);
    if (cursor == null) {
      return null;
    }

    ArrayList<PhotoInfo> newList = new ArrayList<PhotoInfo>();

    Log.i(HelloActivity.TAG, "num rows: " + cursor.getCount());
    // Cursor index starts at -1. let's not ask why.
    cursor.moveToFirst();
    while (!cursor.isAfterLast()) {
      Log.i(HelloActivity.TAG, "pos: " + cursor.getPosition() + " columns: " + cursor.getColumnCount());
      String bucket_name = cursor.getString(0);
      String date_taken = cursor.getString(1);
      Date date = new Date(Long.parseLong(date_taken));
      String timestamp = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(date);
      String display_name = cursor.getString(2);
      String latitude = cursor.getString(3);
      String longitude = cursor.getString(4);
      long thumb_magic = cursor.getLong(5);
      long id = cursor.getLong(6);
      String data = cursor.getString(7);
      Log.i(HelloActivity.TAG, "ID: " + id + " data: " + data + " bucket: " + bucket_name + " name: " + display_name +
                               " timestamp: " + timestamp +
                               " Lat/Lon: " + latitude + "/" + longitude +
                               " thumb_magic: " + thumb_magic);
      newList.add(new PhotoInfo(id, data, display_name));
      cursor.moveToNext();
    }
    cursor.close();

    return newList;
  }

  private ArrayList<PhotoInfo> getAllThumbnails() {
    // Get images.
    Uri uri = MediaStore.Images.Thumbnails.EXTERNAL_CONTENT_URI;
    String[] projection = new String[] {
      MediaStore.Images.Thumbnails._ID,
      MediaStore.Images.Thumbnails.KIND,
      MediaStore.Images.Thumbnails.IMAGE_ID,
      MediaStore.Images.Thumbnails.DATA,
    };
    String selection = null;

    Cursor cursor = this.context.getContentResolver().query(uri, projection, selection, null, null);
    if (cursor == null) {
      return null;
    }

    Log.i(HelloActivity.TAG, "num rows: " + cursor.getCount());
    // Cursor index starts at -1. let's not ask why.
    cursor.moveToFirst();
    while (!cursor.isAfterLast()) {
      Log.i(HelloActivity.TAG, "pos: " + cursor.getPosition() + " columns: " + cursor.getColumnCount());
      String id = cursor.getString(0);
      String kind = cursor.getString(1);
      String image_id = cursor.getString(2);
      String data = cursor.getString(3);
      Log.i(HelloActivity.TAG, " Thumbnail ID: " + id + " data: " + data + " kind: " + kind +
                               " image_id: " + image_id);
      cursor.moveToNext();
    }
    cursor.close();

    return null;
  }

  public class PhotoLoader extends AsyncTask<Void, Void, Bitmap> {
    private PhotoInfo info;
    private ImageView view;

    public PhotoLoader(PhotoInfo info, ImageView view) {
      this.info = info;
      this.view = view;
    }

    @Override
    protected void onPreExecute() {
      // On UI thread.
    }

    @Override
    protected Bitmap doInBackground(Void... params) {
      BitmapFactory.Options resample = new BitmapFactory.Options();
      resample.inSampleSize = 8;
      return BitmapFactory.decodeFile(this.info.uri, resample);
    }

    @Override
    protected void onPostExecute(Bitmap op_result) {
      // On UI thread.
      this.view.setImageBitmap(op_result);
      // Tell the view that something had changed. This is only needed if we've previously set the thumbnail.
      this.view.invalidate();
    }
  }
}

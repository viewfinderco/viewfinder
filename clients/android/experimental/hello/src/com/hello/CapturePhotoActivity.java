package com.hello;

import java.io.File;
import java.io.IOException;
import java.lang.Long;
import java.text.SimpleDateFormat;
import java.util.Date;

import android.app.Activity;
import android.app.LoaderManager;
import android.content.Context;
import android.content.CursorLoader;
import android.content.Intent;
import android.content.Loader;
import android.database.Cursor;
import android.os.Environment;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.drawable.BitmapDrawable;
import android.graphics.drawable.LayerDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.provider.MediaStore;
import android.util.Log;
import android.view.View;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.Toast;
import android.widget.TextView;


public class CapturePhotoActivity extends Activity implements LoaderManager.LoaderCallbacks<Cursor> {
//  private ImageView imageView;
  private TextView textView;
  private String pending_photo;
  private boolean loaderStarted = false;
  private static final int CAPTURE_THUMBNAIL = 1;
  private static final int CAPTURE_FULL = 2;
  private static final int LOADER_ID = 4;

  public void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    setContentView(R.layout.capture_photo);
//    imageView = (ImageView) findViewById(R.id.imageView);
    textView = (TextView) findViewById(R.id.image_info);
  }

  public void clickButtonThumbnail(View view) {
    Log.i(HelloActivity.TAG, "clickButtonThumbnail");
    Intent takePictureIntent = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
    startActivityForResult(takePictureIntent, CAPTURE_THUMBNAIL);
  }

  public void clickButtonFull(View view) throws IOException {
    Log.i(HelloActivity.TAG, "clickButtonFull");

    File storage_dir = new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES), 
                                "viewfinder");
    Log.i(HelloActivity.TAG, "Storage dir: " + storage_dir.getAbsolutePath());
    storage_dir.mkdirs();
    String timestamp = new SimpleDateFormat("yyyyMMdd_HHmmss").format(new Date());
    String filename = timestamp + "_";
    File image = File.createTempFile(filename, ".jpg", storage_dir);
    pending_photo = image.getAbsolutePath();
    Log.i(HelloActivity.TAG, "Photo path: " + pending_photo);

    Intent takePictureIntent = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
    takePictureIntent.putExtra(MediaStore.EXTRA_OUTPUT, Uri.fromFile(image));
    startActivityForResult(takePictureIntent, CAPTURE_FULL);
  }

  public void clickButtonList(View view) {
    // Init loader, or restart it.
    if (loaderStarted) {
      getLoaderManager().restartLoader(LOADER_ID, null, this);
    } else {
      getLoaderManager().initLoader(LOADER_ID, null, this);
      loaderStarted = true;
    }
  }

  public Loader<Cursor> onCreateLoader(int id, Bundle bundle) {
    if (id != LOADER_ID) {
      return null;
    }

    Uri images_uri = MediaStore.Images.Media.EXTERNAL_CONTENT_URI;
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

    return new CursorLoader(
        this,            // Parent activity context
        images_uri,      // Table to query
        projection,      // Projection to return
        null,            // No selection clause
        null,            // No selection arguments
        null);           // Default sort order
  }

  public void onLoadFinished(Loader<Cursor> loader, Cursor cursor) {
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
      String id = cursor.getString(6);
      String data = cursor.getString(7);
      Log.i(HelloActivity.TAG, "ID: " + id + " data: " + data + " bucket: " + bucket_name + " name: " + display_name +
                               " timestamp: " + timestamp +
                               " Lat/Lon: " + latitude + "/" + longitude);
      cursor.moveToNext();
    }
    cursor.close();
  }

  public void onLoaderReset(Loader<Cursor> loader) {
  }

  protected void onActivityResult(int requestCode, int resultCode, Intent intent) {
    Log.i(HelloActivity.TAG, "Result: " + resultCode + " request: " + requestCode);
    if (resultCode == Activity.RESULT_OK) {
      if (requestCode == CAPTURE_THUMBNAIL) {
        Bundle extras = intent.getExtras();
        Bitmap bitmap = (Bitmap) extras.get("data");
        Log.i(HelloActivity.TAG, "Width: " + bitmap.getWidth() + " Height: " + bitmap.getHeight());
        textView.setText("Width: " + bitmap.getWidth() + " Height: " + bitmap.getHeight());
        //imageView.setImageBitmap(bitmap);
      } else if (requestCode == CAPTURE_FULL) {
        Bitmap bitmap = BitmapFactory.decodeFile(pending_photo);
        Log.i(HelloActivity.TAG, "Width: " + bitmap.getWidth() + " Height: " + bitmap.getHeight());
        textView.setText("Width: " + bitmap.getWidth() + " Height: " + bitmap.getHeight());
        Toast.makeText(getApplicationContext(), "File: " + pending_photo, Toast.LENGTH_SHORT).show();
        LayerDrawable ld = (LayerDrawable) getResources().getDrawable(R.drawable.event_layer);
        boolean testfactor = ld.setDrawableByLayerId(R.id.imageView, new BitmapDrawable(bitmap));
//        imageView.setImageBitmap(bitmap);
        ImageView layoutlist1 = (ImageView)findViewById(R.id.imageDisplay);
        layoutlist1.setImageDrawable(ld);
      }
    }
  }
}

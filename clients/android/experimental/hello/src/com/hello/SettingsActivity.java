package com.hello;

import com.hello.proto.Hello;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.util.Log;
import android.view.View;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.TextView;


public class SettingsActivity extends Activity {
  public static final String PREFS_NAME = "VFPreferences";

  // Called when the activity is first created.
  public void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    setContentView(R.layout.settings);
    Log.i(HelloActivity.TAG, "onCreate");
  }

  protected void savePreferences() {
    SharedPreferences settings = getSharedPreferences(PREFS_NAME, 0);
    SharedPreferences.Editor editor = settings.edit();

    Hello.Settings.Builder settings_builder = Hello.Settings.newBuilder();

    EditText editText = (EditText) findViewById(R.id.settings_box_a);
    settings_builder.setSettingString(editText.getText().toString());
    CheckBox checkBox = (CheckBox) findViewById(R.id.settings_checkbox_b);
    settings_builder.setSettingCheckbox(checkBox.isChecked());
    TextView uuidTextView = (TextView) findViewById(R.id.uuid_box);

    Hello.Settings settings_proto = settings_builder.build();

    editor.putString("setting-A", settings_proto.getSettingString());
    editor.putBoolean("setting-B", settings_proto.getSettingCheckbox());
    Log.i(HelloActivity.TAG, "Saving settings: " + settings_proto.toString());

    editor.commit();
  }

  protected void loadPreferences() {
    SharedPreferences settings = getSharedPreferences(PREFS_NAME, 0);

    String setting_a = settings.getString("setting-A", null);
    if (setting_a != null) {
      EditText editText = (EditText) findViewById(R.id.settings_box_a);
      editText.setText(setting_a);
    }

    boolean setting_b = settings.getBoolean("setting-B", false);
    CheckBox checkBox = (CheckBox) findViewById(R.id.settings_checkbox_b);
    checkBox.setChecked(setting_b);

    App myApp = (App)getApplicationContext();
    String device_uuid = myApp.getDeviceUUID();
    TextView uuidTextView = (TextView) findViewById(R.id.uuid_box);
    uuidTextView.setText(device_uuid);
  }

  public void onCheckboxClicked(View view) {
    // We don't do anything here, just show that we can know when this happens.
    boolean checked = ((CheckBox) view).isChecked();
    Log.i(HelloActivity.TAG, "Checkbox: " + checked);
  }

  @Override
  protected void onResume() {
    super.onResume();
    // Reload preferences as soon as we page into "settings".
    Log.i(HelloActivity.TAG, "onResume");
    loadPreferences();
  }

  @Override
  protected void onPause() {
    super.onPause();
    // Save preferences as soon as we leave "settings". This would not be a great idea since someone just
    // switching to another app would cause a save. We may need an actual button.
    Log.i(HelloActivity.TAG, "onPause");
    savePreferences();
  }
}

// Copyright 2013 Viewfinder. All rights reserved.
// Author: Mike Purtell
package co.viewfinder;

import android.app.Activity;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.CompoundButton;
import android.widget.TextView;
import android.widget.ToggleButton;
import org.jraf.android.backport.switchwidget.Switch;

/**
 *  UI for application settings.
 */
public class SettingsFragment extends BaseFragment {
  private OnSettingsListener mCallback = null;

  public interface OnSettingsListener {
    void onFAQ();
    void onSendFeedback();
    void onDebugLogs(boolean doDebugLogging);
    void onUnlinkDevice();
    void onTermsOfService();
    void onPrivacyPolicy();
    void onCrash();
  }

  @Override
  public void onAttach(Activity activity) {
    super.onAttach(activity);
    mCallback = (OnSettingsListener) activity;
  }

  @Override
  public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
    View view = inflater.inflate(R.layout.settings_fragment, container, false);

    view.findViewById(R.id.settings_faq).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onFAQ();
      }
    });

    view.findViewById(R.id.settings_feedback).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onSendFeedback();
      }
    });

    view.findViewById(R.id.settings_terms).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onTermsOfService();
      }
    });

    view.findViewById(R.id.settings_privacy).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        mCallback.onPrivacyPolicy();
      }
    });

    Switch debugLogsSwitch = (Switch)view.findViewById(R.id.settings_debugLogs);
    debugLogsSwitch.setOnCheckedChangeListener(new CompoundButton.OnCheckedChangeListener() {
      @Override
      public void onCheckedChanged(CompoundButton buttonView, boolean isChecked) {
        mCallback.onDebugLogs(isChecked);
      }
    });

    ((TextView)view.findViewById(R.id.settings_version))
        .setText(getString(R.string.settings_version, getAppState().appVersion()));

    if (getAppState().isDevBuild()) {
      view.findViewById(R.id.settings_unlinkPhone).setOnClickListener(new View.OnClickListener() {
        @Override
        public void onClick(View v) {
          mCallback.onUnlinkDevice();
        }
      });

      view.findViewById(R.id.settings_testStatusBar).setOnClickListener(new View.OnClickListener() {
        @Override
        public void onClick(View v) {
          ((ViewDataSim) getAppState().getViewData()).simulateStatusChanges();
        }
      });

      view.findViewById(R.id.settings_crash).setOnClickListener(new View.OnClickListener() {
        @Override
        public void onClick(View v) {
          mCallback.onCrash();
        }
      });
    } else {
      // Hide the buttons that are only available in dev build.
      view.findViewById(R.id.settings_devBuild).setVisibility(View.GONE);
    }

    return view;
  }
}

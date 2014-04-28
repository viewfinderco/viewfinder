package co.viewfinder;

import android.app.Activity;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.EditText;
import co.viewfinder.proto.ContactMetadataPB;

/**
 * UI for editing name in MyInfo page.
 */
public class MyInfoEditFragment extends BaseFragment {
  private OnMyInfoEditListener mCallback = null;

  private EditText mFirstField;
  private EditText mLastField;

  public interface OnMyInfoEditListener {
    public void onEditDone(String firstName, String lastName);
  }

  @Override
  public void onAttach(Activity activity) {
    super.onAttach(activity);
    mCallback = (OnMyInfoEditListener) activity;
  }

  @Override
  public View onCreateView(LayoutInflater inflater, ViewGroup container, Bundle savedInstanceState) {
    View view = inflater.inflate(R.layout.myinfo_edit_fragment, container, false);

    mFirstField = (EditText)view.findViewById(R.id.myinfo_first);
    mLastField = (EditText)view.findViewById(R.id.myinfo_last);

    // Set initial values from contact.
    ContactMetadataPB.ContactMetadata myself = getAppState().getSelfContact();
    mFirstField.setText(myself.getFirstName());
    mLastField.setText(myself.getLastName());

    view.findViewById(R.id.myinfo_done).setOnClickListener(new View.OnClickListener() {
      @Override
      public void onClick(View v) {
        boolean succeeded = InputValidation.setHintIfEmpty(mFirstField, R.string.myinfo_required);
        succeeded &= InputValidation.setHintIfEmpty(mLastField, R.string.myinfo_required);

        if (succeeded) {
          mCallback.onEditDone(getFirst(), getLast());
        }
      }
    });

    return view;
  }

  @Override
  public void onResume() {
    super.onResume();
    mFirstField.requestFocus();
    showSoftInput();
  }

  public String getFirst() {
    return mFirstField.getText().toString();
  }

  public String getLast() {
    return mLastField.getText().toString();
  }
}

  void EmailPhoto(int64_t photo_id);

void AppState::EmailPhoto(int64_t photo_id) {
  const PhotoHandle p = photo_table_->LoadPhoto(photo_id, db());
  if (!p.get()) {
    return;
  }

  MFMailComposeViewController* c = [MFMailComposeViewController new];
  [c setMessageBody:Format("%s", *p) isHTML:NO];
  [c setSubject:Format("user_id=%d photo_id=%d", user_id_, photo_id)];
  [c setToRecipients:Array(@"peter@emailscrubbed.com")];

  const vector<string> filenames = photo_storage_->ListAll(photo_id);
  for (int i = 0; i < filenames.size(); ++i) {
    NSData* data = ReadFileToData(JoinPath(photo_dir(), filenames[i]));
    [c addAttachmentData:data mimeType:@"image/jpeg" fileName:NewNSString(filenames[i])];
  }

  CppDelegate* cpp_delegate = new CppDelegate;
  cpp_delegate->Add(
      @protocol(MFMailComposeViewControllerDelegate),
      @selector(mailComposeController:didFinishWithResult:error:),
      ^(MFMailComposeViewController* controller, MFMailComposeResult result, NSError* error) {
        controller.delegate = NULL;
        delete cpp_delegate;
        [root_view_controller() dismissModalViewControllerAnimated:YES];
      });
  c.mailComposeDelegate = cpp_delegate->delegate();

  [root_view_controller() presentModalViewController:c animated:YES];
}

  // List all of the images associatd with the photo.
  vector<string> ListAll(int64_t photo_id);

vector<string> PhotoStorage::ListAll(int64_t photo_id) {
  const string max_key =
      DBFormat::photo_path_key(PhotoFilename(photo_id, kOriginalSize));
  vector<string> filenames;
  for (DB::PrefixIterator iter(state_->db(), DBFormat::photo_path_key(Format("%d-", photo_id)));
       iter.Valid();
       iter.Next()) {
    Slice key = iter.key();
    filenames.push_back(key.substr(kPhotoPathKeyPrefix.size()).ToString());
    if (key >= max_key) {
      break;
    }
  }
  return filenames;
}

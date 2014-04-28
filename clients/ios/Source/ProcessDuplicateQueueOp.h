// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_PROCESS_DUPLICATE_QUEUE_OP_H
#define VIEWFINDER_PROCESS_DUPLICATE_QUEUE_OP_H

#import "Image.h"
#import "PhotoTable.h"
#import "Timer.h"

class UIAppState;

class ProcessDuplicateQueueOp {
  typedef void (^CompletionBlock)();

 public:
  static void New(UIAppState* state, int64_t local_id, CompletionBlock completion);

 private:
  ProcessDuplicateQueueOp(UIAppState* state, int64_t photo_id, CompletionBlock completion);
  ~ProcessDuplicateQueueOp();

  void Run();

  void ProcessNextCandidate();
  void LoadPotentialDuplicateThumbnail(int64_t candidate_id);
  void LoadPotentialDuplicateFull(int64_t candidate_id, float thumbnail_c);
  void LoadCandidateImages(int64_t candidate_id);
  void LoadCandidateThumbnail(int64_t candidate_id);
  void LoadCandidateFull(int64_t candidate_id, float thumbnail_c);
  void Quarantine(const string& reason);
  void Finish(int64_t original_id, const string& reason);

 private:
  const WallTimer timer_;
  UIAppState* const state_;
  const int64_t photo_id_;
  CompletionBlock completion_;
  Image photo_thumbnail_;
  Image photo_full_;
  string photo_orig_md5_;
  float aspect_ratio_;
  vector<int> candidates_;
  int candidate_index_;
};

#endif  // VIEWFINDER_PROCESS_DUPLICATE_QUEUE_OP_H

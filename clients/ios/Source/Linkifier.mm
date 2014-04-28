// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.
//
// TODO(peter): Ben says: NSDataDetector will surely differ from the detection
// code we will use on web and android for some edge cases.  Do we want to use
// our own implementation for consistency? (such as
// https://github.com/facebook/tornado/blob/master/tornado/escape.py#L222)"

#import "LazyStaticPtr.h"
#import "Linkifier.h"
#import "Logging.h"

namespace {

const int kDetectionTypes = NSTextCheckingTypeLink;

class LinkDetector {
 public:
  LinkDetector()
      : data_detector_(NULL) {
    NSError* error;
    data_detector_ = [NSDataDetector
                       dataDetectorWithTypes:kDetectionTypes
                                       error:&error];
    if (error) {
      LOG("unable to create data detector: %s", error);
      data_detector_ = NULL;
    }
  }

  NSArray* Detect(NSString* str, const NSRange& range) {
    return [data_detector_ matchesInString:str
                                   options:0
                                     range:range];
  }

 private:
  NSDataDetector* data_detector_;
};

LazyStaticPtr<LinkDetector> detector;

}  // namespace

NSArray* FindLinks(NSString* str, const NSRange& range) {
  return detector->Detect(str, range);
}

void ApplyLinkAttributes(NSMutableAttributedString* attr_str,
                         NSArray* matches, const Dict& attributes) {
  for (NSTextCheckingResult* result in matches) {
    [attr_str addAttributes:attributes range:result.range];
  }
}

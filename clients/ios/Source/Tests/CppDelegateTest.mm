// Copyright 2012 Viewfinder. All rights reserved.
// Author: Ben Darnell

#ifdef TESTING

#import <Foundation/NSXMLParser.h>
#import <UIKit/UIActionSheet.h>
#import <UIKit/UITextField.h>
#import "CppDelegate.h"
#import "Testing.h"

namespace {

// Test CppDelegate using NSXMLParser because it has a protocol with multiple
// methods and doesn't depend on network access.
TEST(CppDelegateTest, TestXMLParsing) {
  std::string str = "<foo><bar>hello</bar></foo>";
  NSXMLParser* parser = [[NSXMLParser alloc] initWithData:[NSData dataWithBytes:str.data() length:str.size()]];

  __block std::vector<std::string> elements;
  __block std::string chardata;

  CppDelegate cpp_delegate;
  cpp_delegate.Add(@protocol(NSXMLParserDelegate), @selector(parser:didStartElement:namespaceURI:qualifiedName:attributes:),
                   ^(NSXMLParser* parser, NSString* element, NSString* namespace_uri,
                     NSString* qualname, NSDictionary* attributes) {
        elements.push_back([element UTF8String]);
      });
  cpp_delegate.Add(@protocol(NSXMLParserDelegate), @selector(parser:foundCharacters:),
      ^(NSXMLParser* parser, NSString* data) {
        chardata.append([data UTF8String]);
      });
  parser.delegate = cpp_delegate.delegate();
  [parser parse];

  EXPECT_EQ(chardata, "hello");
  ASSERT_EQ(2, elements.size());
  EXPECT_EQ(elements[0], "foo");
  EXPECT_EQ(elements[1], "bar");
}

// UIActionSheetDelegate has integer parameters
TEST(CppDelegateTest, Primitives) {
  __block NSInteger index = 0;
  CppDelegate cpp_delegate;
  cpp_delegate.Add(@protocol(UIActionSheetDelegate), @selector(actionSheet:clickedButtonAtIndex:),
                   ^(UIActionSheet* sheet, NSInteger i) {
                     index = i;
                   });
  [cpp_delegate.delegate() actionSheet:nil clickedButtonAtIndex:3];
  EXPECT_EQ(index, 3);
}

// UITextFieldDelegate has methods with non-void returns
TEST(CppDelegateTest, ReturnValue) {
  //__block int count = 0;
  CppDelegate cpp_delegate;
  cpp_delegate.Add(@protocol(UITextFieldDelegate), @selector(textFieldShouldReturn:),
                   ^(UITextField* text_field) {
                     return YES;
                   });
  BOOL result = [cpp_delegate.delegate() textFieldShouldReturn:nil];
  EXPECT_EQ(result, YES);
}

}  // unnamed namespace

#endif  // TESTING

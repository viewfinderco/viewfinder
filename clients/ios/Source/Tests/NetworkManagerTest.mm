// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifdef TESTING

#import <re2/re2.h>
#import "ContactManager.h"
#import "FileUtils.h"
#import "NetworkManager.h"
#import "NotificationManager.h"
#import "PathUtils.h"
#import "Server.pb.h"
#import "StringUtils.h"
#import "SubscriptionManagerIOS.h"
#import "TestAssets.h"
#import "Testing.h"
#import "TestUtils.h"

namespace {

string GetHostHeader(const mg_request_info* info) {
  for (int i = 0; i < info->num_headers; ++i) {
    if (ToLowercase(info->http_headers[i].name) == "host") {
      return info->http_headers[i].value;
    }
  }
  return "";
}

class NetworkManagerTest : public Test {
 protected:
  NetworkManagerTest()
      : query_notifications_(false) {
    // Setup handlers for all the stuff that NetworkManager tries to do on its
    // own.  Sub-tests should add additional handlers for the functionality
    // they are testing.

    // Authentication support is just stubs, but we need non-error endpoints for
    // both facebook and google.  NetworkManager will use either /register or
    // /login depending on whether ADHOC or APPSTORE is defined.
    const string kAuthURIs[] = {
      "/register/facebook",
      "/login/facebook",
      "/register/google",
      "/login/google",
    };
    for (int i = 0; i < ARRAYSIZE(kAuthURIs); i++) {
      http_server_.SetHandler(
          kAuthURIs[i],
          ^(mg_connection *conn, const mg_request_info *info) {
            SendResponse(conn, Format("{\"op_id\" : 1}"));
          });
    }
    http_server_.SetHandler(
      "/service/query_notifications",
      ^(mg_connection *conn, const mg_request_info *info){
        query_notifications_ = true;
        SendResponse(conn, GetQueryNotificationsResponse());
      });
    http_server_.SetHandler(
      "/service/new_client_log_url",
      ^(mg_connection *conn, const mg_request_info *info){
        SendResponse(conn, Format("{\"client_log_put_url\": \"http://localhost:%d/put_log\"}", http_server_.port()));
      });
    http_server_.SetHandler(
      "/put_log",
      ^(mg_connection *conn, const mg_request_info *info){
        SendResponse(conn, Format(""));
      });
    http_server_.SetHandler(
      "/ping",
      ^(mg_connection *conn, const mg_request_info *info){
        SendResponse(conn, Format(""));
      });

    // Don't create the UIAppState until the server is ready.  A ping will happen shortly after the
    // state is created, and the server must be configured for it.
    state_.reset(new TestUIAppState(dir(), "localhost", http_server_.port()));;
    state_->assets_scan_end()->Run(NULL);
  }

 protected:
  // Sends the specified body as an HTTP/1.1 response to the client. Always includes
  // a "user" and "_xsrf" cookie.
  void SendResponse(mg_connection* conn, const string& body) {
    string response = Format("HTTP/1.1 200\n"
                             "Content-Length: %d\n"
                             "Set-Cookie: user=USERCOOKIEDATA\n"
                             "Set-Cookie: _xsrf=XSRFCOOKIEDATA\n\n"
                             "%s\n", body.size(), body);
    mg_printf(conn, response.c_str());
  }

  void SendRedirect(mg_connection* conn, const string& url, const string& extra_headers) {
    string response = Format("HTTP/1.1 301\n"
                             "Location: %s\n%s\n",
                             url, extra_headers);
    mg_printf(conn, response.c_str());
  }

  virtual string GetQueryNotificationsResponse() {
    return "{}";
  }

 protected:
  HttpServer http_server_;
  ScopedPtr<TestUIAppState> state_;
  bool query_notifications_;
};

class InvalidateUserTest : public NetworkManagerTest {
 protected:
  virtual string GetQueryNotificationsResponse() {
    return "{\"notifications\": [{\"invalidate\": {\"users\": [3]}}]}";
  }
};

TEST_F(InvalidateUserTest, InvalidateUser) {
  Barrier* barrier = new Barrier(1);

  state_->contact_manager()->contact_changed()->Add(^{
      ContactMetadata m;
      if (state_->contact_manager()->LookupUser(3, &m)) {
        barrier->Signal();
      }
    });

  // query_contacts and query_followed need to return non-errors to
  // allow things to proceed to query_users.
  // (I'm not sure why query_followed is an issue, since MaybeQueryFollowed
  // is before MaybeQueryUsers in NetworkManager)
  http_server_.SetHandler(
      "/service/query_contacts",
      ^(mg_connection* conn, const mg_request_info* info) {
        SendResponse(conn, "{}");
      });
  http_server_.SetHandler(
      "/service/query_followed",
      ^(mg_connection* conn, const mg_request_info* info) {
        SendResponse(conn, "{}");
      });

  http_server_.SetHandler(
      "/service/query_users",
      ^(mg_connection* conn, const mg_request_info* info) {
        const JsonValue d(ParseJSON(HttpServer::DecompressedBody(conn, info)));
        ASSERT(!d.empty());
        const JsonRef user_ids = d["user_ids"];
        ASSERT(!user_ids.empty());
        ASSERT_EQ(user_ids.size(), 1);
        ASSERT_EQ(user_ids[0].int64_value(), 3);
        LOG("got query for invalidated user");
        SendResponse(conn, "{\"users\": [{\"user_id\": 3}]}");
      });

  barrier->Wait();
  delete barrier;
}

class RecordSubscriptionTest : public NetworkManagerTest {
 protected:
  RecordSubscriptionTest() {
    http_server_.SetHandler(
        "/service/record_subscription",
        ^(mg_connection* conn, const mg_request_info* info) {
          RE2 match_re("\"receipt_data\" \\: \"([^\"]+)\"");
          const string decompressed_post = HttpServer::DecompressedBody(conn, info);
          string receipt_data;
          ASSERT(RE2::PartialMatch(decompressed_post, match_re, &receipt_data));
          ASSERT_EQ(kReceiptData, Base64Decode(receipt_data));
          SendResponse(conn,
                       "{\n"
                       "  \"subscription\": {\n"
                       "    \"transaction_id\": \"itunes:1234\",\n"
                       "    \"product_type\": \"vf_sub1\"\n"
                       "  }\n"
                       "}");
        });
  }

  static const string kReceiptData;
};

const string RecordSubscriptionTest::kReceiptData("asdf");

TEST_F(RecordSubscriptionTest, QueueReceipt) {
  Barrier* barrier = new Barrier(1);

  dispatch_main(^{
      state_->subscription_manager_ios()->QueueReceipt(
          [NSData dataWithBytes:kReceiptData.data() length:kReceiptData.size()], ^{
            barrier->Signal();
          });
    });

  barrier->Wait();
  delete barrier;

  // The subscription details were returned by the server and written to the database.
  ServerSubscriptionMetadata sub;
  ASSERT(state_->db()->GetProto(DBFormat::server_subscription_key("itunes:1234"), &sub));
  EXPECT_EQ(sub.product_type(), "vf_sub1");
}

TEST_F(RecordSubscriptionTest, RequeueAtStartup) {
  // Simulate a failure on a previous run by inserting a transaction directly into the database.
  const string kTransactionKey = DBFormat::local_subscription_key("txn1");
  LocalSubscriptionMetadata m;
  m.set_receipt(kReceiptData);
  ASSERT(state_->db()->PutProto(kTransactionKey, m));

  // HACK: re-initialize the existing subscription manager
  Barrier* barrier = new Barrier(1);

  state_->subscription_manager_ios()->changed()->AddSingleShot(^{
      barrier->Signal();
    });
  // This will re-read the database, see that our transaction was not recorded,
  // and re-enqueue it.
  state_->subscription_manager_ios()->InitFromDB();

  barrier->Wait();
  delete barrier;

  // Make sure the subscription was marked as recorded
  m.Clear();
  ASSERT(state_->db()->GetProto(kTransactionKey, &m));
  EXPECT_EQ(m.receipt(), kReceiptData);
  EXPECT(m.recorded());
}

TEST_F(NetworkManagerTest, ResolveContact) {
  Barrier* barrier = new Barrier(1);

  state_->network_ready()->AddSingleShot(^(int) {
      barrier->Signal();
    });

  barrier->Wait();
  delete barrier;

  barrier = new Barrier(3);

  http_server_.SetHandler(
      "/service/resolve_contacts",
      ^(mg_connection* conn, const mg_request_info* info) {
        const JsonValue d(ParseJSON(HttpServer::DecompressedBody(conn, info)));
        const string ident = d["identities"][0].string_value();
        if (ident == "Email:user1@emailscrubbed.com") {
          SendResponse(
              conn, JsonDict("contacts",
                             JsonArray({ JsonDict({
                                     { "identity", ident },
                                     { "user_id", 1 }
                                   })})).Format());
        } else if (ident == "Email:give_me_an_error@emailscrubbed.com") {
          SendResponse(conn, "{}");
        } else {
          SendResponse(
              conn, JsonDict("contacts", JsonArray({ JsonDict("identity", ident) })).Format());
        }
      });

  __block std::map<string, ContactMetadata*> resolved_identities;
  state_->contact_manager()->contact_resolved()->Add(^(const string &identity, const ContactMetadata* metadata) {
      if (metadata) {
        resolved_identities[identity] = new ContactMetadata(*metadata);
      } else {
        resolved_identities[identity] = NULL;
      }
      barrier->Signal();
    });

  state_->net_manager()->ResolveContact("Email:user1@emailscrubbed.com");
  state_->net_manager()->ResolveContact("Email:nobody@emailscrubbed.com");
  state_->net_manager()->ResolveContact("Email:give_me_an_error@emailscrubbed.com");

  barrier->Wait();
  delete barrier;

  ContactMetadata* m = resolved_identities["Email:user1@emailscrubbed.com"];
  ASSERT(m);
  EXPECT_EQ(m->primary_identity(), "Email:user1@emailscrubbed.com");
  EXPECT_EQ(m->user_id(), 1);

  m = resolved_identities["Email:nobody@emailscrubbed.com"];
  ASSERT(m);
  EXPECT_EQ(m->primary_identity(), "Email:nobody@emailscrubbed.com");
  EXPECT(!m->has_user_id());

  // The identities that failed to resolve still generated callbacks, but with NULL metadata.
  ASSERT(ContainsKey(resolved_identities, "Email:give_me_an_error@emailscrubbed.com"));
  EXPECT(!resolved_identities["Email:give_me_an_error@emailscrubbed.com"]);

  Clear(&resolved_identities);
}

TEST_F(NetworkManagerTest, StagingRedirectTest) {
  // This test verifies that redirects to the staging server are handled and persisted appropriately.
  // Since we don't have multiple domains to work with we use localhost for "production" and
  // 127.0.0.1 for "staging".
  Barrier* barrier = new Barrier(1);

  __block int localhost_count = 0;
  __block int ip_count = 0;
  __block int upload_contacts_count = 0;

  http_server_.SetHandler(
      "/service/update_device",
      ^(mg_connection* conn, const mg_request_info* info) {
        const string decompressed_post = HttpServer::DecompressedBody(conn, info);
        // The push_token is sent in the body whether it's the original request or post-redirect.
        EXPECT(RE2::PartialMatch(decompressed_post, "push_token"));

        const string host = GetHostHeader(info);
        int port = 0;
        if (RE2::FullMatch(host, "localhost:([0-9]+)", &port)) {
          // Original request to localhost: redirect to 127.0.0.1
          localhost_count++;
          string location = Format("http://127.0.0.1:%d%s", port, info->uri);
          SendRedirect(conn, location, "X-VF-Staging-Redirect: 127.0.0.1\n");
        } else if (RE2::FullMatch(host, "127.0.0.1:[0-9]+")) {
          // After the redirect
          ip_count++;
          SendResponse(conn, "{\"op_id\": 1}");
        }
      });

  // The redirect is persisted and will be used on the next request as well.
  http_server_.SetHandler(
      "/service/upload_contacts",
      ^(mg_connection* conn, const mg_request_info* info) {
        const string host = GetHostHeader(info);
        EXPECT(RE2::FullMatch(host, "127.0.0.1:[0-9]+"));
        upload_contacts_count++;
        SendResponse(conn, "{\"contact_ids\": [\"abcd\"]}");
        barrier->Signal();
      });


  dispatch_main(^{
      // Trigger two network operations (which must be dispatched by the same queue to ensure
      // they are processed sequentially).
      state_->net_manager()->SetPushNotificationDeviceToken("test-token1");
      ContactMetadata cm;
      cm.add_identities()->set_identity("Email:foobar@example.com");
      cm.set_contact_source(ContactManager::kContactSourceManual);
      DBHandle updates = state_->NewDBTransaction();
      state_->contact_manager()->SaveContact(cm, true, WallTime_Now(), updates);
      updates->Commit();
    });

  barrier->Wait();
  delete barrier;

  EXPECT_EQ(localhost_count, 1);
  EXPECT_EQ(ip_count, 1);
  EXPECT_EQ(upload_contacts_count, 1);
}

TEST_F(NetworkManagerTest, UpdateDevice) {
  // Set device token and verify the server receives an update_device request.
  const string device_token("test-token");
  Barrier* barrier = new Barrier(1);

  http_server_.SetHandler(
      "/service/update_device",
      ^(mg_connection *conn, const mg_request_info *info){
        const string decompressed_post = HttpServer::DecompressedBody(conn, info);
        RE2 match_re("\"push_token\" \\: \"apns-dev:([^\"]+)\"");
        string push_token;
        ASSERT(RE2::PartialMatch(decompressed_post, match_re, &push_token));
        ASSERT_EQ(Base64Decode(push_token), device_token);
        SendResponse(conn, Format("{\"op_id\" : 1}"));
        barrier->Signal();
      });

  dispatch_main(^{
      state_->apn_device_token()->Run(NewNSData(device_token));
    });

  barrier->Wait();
  delete barrier;
}

TEST_F(NetworkManagerTest, UploadContacts) {
  // Use two different barriers for clarity, so if it fails in such a way that one hangs indefinitely
  // we can tell which it is.
  Barrier* network_barrier = new Barrier(1);
  Barrier* contact_barrier = new Barrier(1);

  // query_contacts and query_followed need to return non-errors to
  // allow things to proceed to upload_contacts.
  http_server_.SetHandler(
      "/service/query_contacts",
      ^(mg_connection* conn, const mg_request_info* info) {
        SendResponse(conn, "{}");
      });
  http_server_.SetHandler(
      "/service/query_followed",
      ^(mg_connection* conn, const mg_request_info* info) {
        SendResponse(conn, "{}");
      });

  __block string post_data;
  http_server_.SetHandler(
      "/service/upload_contacts",
      ^(mg_connection* conn, const mg_request_info* info) {
        post_data.assign(HttpServer::DecompressedBody(conn, info));
        SendResponse(conn,
                     "{\n"
                     "  \"contact_ids\" : [\n"
                     "    \"ip:1234\"\n"
                     "  ]\n"
                     "}");
        network_barrier->Signal();
      });

  // This callback is the last part of the test:  After the uploaded contacts have been committed,
  // the contact is updated with the new server-supplied id.
  int contact_changed_id = state_->contact_manager()->contact_changed()->Add(^{
      vector<ContactMetadata> results;
      state_->contact_manager()->Search("ben", &results, NULL);
      if (results.size() == 0) {
        return;
      }
      CHECK_EQ(results.size(), 1);
      if (results[0].has_server_contact_id()) {
        CHECK_EQ(results[0].server_contact_id(), "ip:1234");
        contact_barrier->Signal();
      }
    });

  dispatch_background(^{
      vector<ContactMetadata> contacts(1);
      contacts[0].set_contact_source(ContactManager::kContactSourceIOSAddressBook);
      contacts[0].set_name("Ben Darnell");
      contacts[0].set_primary_identity("Email:ben@emailscrubbed.com");
      contacts[0].add_identities()->set_identity("Email:ben@emailscrubbed.com");

      DBHandle updates = state_->NewDBTransaction();
      state_->contact_manager()->ProcessAddressBookImport(contacts, updates, ^{});
      updates->Commit();
      });

  network_barrier->Wait();
  delete network_barrier;

  const JsonValue request(ParseJSON(post_data));
  const JsonRef contacts = request["contacts"];
  ASSERT_EQ(contacts.size(), 1);
  const JsonRef contact = contacts[0];
  EXPECT_EQ(contact["name"].string_value(), "Ben Darnell");
  EXPECT_EQ(contact["contact_source"].string_value(), ContactManager::kContactSourceIOSAddressBook);
  const JsonRef identities = contact["identities"];
  ASSERT_EQ(identities.size(), 1);
  const JsonRef identity = identities[0];
  EXPECT_EQ(identity["identity"].string_value(), "Email:ben@emailscrubbed.com");

  contact_barrier->Wait();
  delete contact_barrier;
  state_->contact_manager()->contact_changed()->Remove(contact_changed_id);
}

TEST_F(NetworkManagerTest, RemoveContacts) {
  Barrier* barrier = new Barrier(1);

  // query_contacts and query_followed need to return non-errors to
  // allow things to proceed to remove_contacts.
  http_server_.SetHandler(
      "/service/query_contacts",
      ^(mg_connection* conn, const mg_request_info* info) {
        SendResponse(conn, "{}");
      });
  http_server_.SetHandler(
      "/service/query_followed",
      ^(mg_connection* conn, const mg_request_info* info) {
        SendResponse(conn, "{}");
      });

  __block string post_data;
  http_server_.SetHandler(
      "/service/remove_contacts",
      ^(mg_connection* conn, const mg_request_info* info) {
        post_data.assign(HttpServer::DecompressedBody(conn, info));
        SendResponse(conn, "{}");
        barrier->Signal();
      });

  dispatch_background(^{
      // Create a contact (with a server contact id, although that id
      // would normally be added via a different path) and remove it.
      vector<ContactMetadata> contacts(1);
      contacts[0].set_server_contact_id("12345");
      contacts[0].set_contact_source(ContactManager::kContactSourceIOSAddressBook);
      contacts[0].set_name("Ben Darnell");
      contacts[0].set_primary_identity("Email:ben@emailscrubbed.com");
      contacts[0].add_identities()->set_identity("Email:ben@emailscrubbed.com");

      DBHandle updates = state_->NewDBTransaction();
      state_->contact_manager()->ProcessAddressBookImport(contacts, updates, ^{});
      contacts.clear();
      state_->contact_manager()->ProcessAddressBookImport(contacts, updates, ^{});
      updates->Commit();
    });

  barrier->Wait();

  const JsonValue request(ParseJSON(post_data));
  const JsonRef contacts = request["contacts"];
  ASSERT_EQ(contacts.size(), 1);
  EXPECT_EQ(contacts[0].string_value(), "12345");
}

}  // namespace

#endif  // TESTING

// local variables:
// mode: c++
// end:

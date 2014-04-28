// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifdef TESTING

#import "AppState.h"
#import "ServerUtils.h"
#import "Testing.h"

namespace {

TEST(ServerUtilsTest, FormatJSON) {
  EXPECT_EQ("{\n"
            "   \"bar\" : 4.2,\n"
            "   \"foo\" : 1,\n"
            "   \"hello\" : \"world\"\n"
            "}\n",
            JsonDict({
                { "bar", 4.2 },
                { "foo", 1 },
                { "hello", "world" },
              }).FormatStyled());
  EXPECT_EQ("{\n"
            "   \"foo\" : [ 1, 2, 3, \"bar\" ]\n"
            "}\n",
            JsonDict({
                { "foo", { 1, 2, 3, "bar" } },
              }).FormatStyled());
}

TEST(ServerUtilsTest, IsS3RequestTimeout) {
  EXPECT(IsS3RequestTimeout(
             400, "<?xml version=\"1.0\" encoding=\"UTF-8\"?><Error><Code>RequestTimeout</Code><Message>Your socket connection to the server was not read from or written to within the timeout period. Idle connections will be closed.</Message><RequestId>C65F1272B86CDFA7</RequestId><HostId>VuNXwnE0z7U4K1EQk3BDA8GbSd6EeQnabgSWOxntyTbh6qgaOXIZQHtGfQgfMD00</HostId></Error>"));
  EXPECT(IsS3RequestTimeout(400, "<Code>RequestTimeout</Code>"));
  EXPECT(!IsS3RequestTimeout(399, "<Code>RequestTimeout</Code>"));
  EXPECT(!IsS3RequestTimeout(400, "RequestTimeout"));
}

TEST(ServerUtilsTest, ParseAuthResponse) {
  const string kAuthResponse1 =
      "{\n"
      "  \"user_id\" : 1,\n"
      "  \"device_id\" : 2,\n"
      "  \"token_digits\": 4,\n"
      "  \"cookie\" : \"boozle\"\n"
      "}\n";
  AuthResponse r;
  EXPECT(ParseAuthResponse(&r, kAuthResponse1));
  EXPECT_EQ(1, r.user_id());
  EXPECT_EQ(2, r.device_id());
  EXPECT_EQ(4, r.token_digits());
  EXPECT_EQ("boozle", r.cookie());
  EXPECT(!r.headers().has_op_id());

  r.Clear();
  const string kAuthResponse2 =
      "{\n"
      "  \"headers\" : {\n"
      "    \"op_id\" : \"foozle\"\n"
      "  },\n"
      "  \"user_id\" : 3,\n"
      "  \"device_id\" : 4\n"
      "}\n";
  EXPECT(ParseAuthResponse(&r, kAuthResponse2));
  EXPECT_EQ(3, r.user_id());
  EXPECT_EQ(4, r.device_id());
  EXPECT(!r.has_token_digits());
  EXPECT(!r.has_cookie());
  EXPECT_EQ("foozle", r.headers().op_id());
}

TEST(ServerUtilsTest, ParseErrorResponse) {
  const string kErrorResponse =
      "{\n"
      "  \"error\" : {\n"
      "    \"method\" : \"register\",\n"
      "    \"message\" : \"could not register\"\n"
      "  }\n"
      "}\n";
  ErrorResponse r;
  EXPECT(ParseErrorResponse(&r, kErrorResponse));
  EXPECT(r.has_error());
  EXPECT_EQ("register", r.error().method());
  EXPECT_EQ("could not register", r.error().text());
}

TEST(ServerUtilsTest, ParseUploadContactsResponse) {
  const string kUploadContactsResponse =
      "{\n"
      "  \"contact_ids\" : [\n"
      "    \"ip:asdf\",\n"
      "    \"ip:qwer\"\n"
      "  ],\n"
      "  \"op_id\" : 2\n"
      "}";
  UploadContactsResponse r;
  ASSERT(ParseUploadContactsResponse(&r, kUploadContactsResponse));
  ASSERT_EQ(2, r.contact_ids_size());
  EXPECT_EQ("ip:asdf", r.contact_ids(0));
  EXPECT_EQ("ip:qwer", r.contact_ids(1));
}

TEST(ServerUtilsTest, ParseUploadEpisodeResponse) {
  const string kUploadEpisodeResponse =
      "{\n"
      "  \"photos\" : [\n"
      "    {\n"
      "      \"full_put_url\" : \"a\",\n"
      "      \"med_put_url\" : \"b\",\n"
      "      \"photo_id\" : \"pgDoGmF62-F\",\n"
      "      \"orig_put_url\" : \"c\",\n"
      "      \"tn_put_url\" : \"d\"\n"
      "    },\n"
      "    {\n"
      "      \"full_put_url\" : \"e\",\n"
      "      \"med_put_url\" : \"f\",\n"
      "      \"photo_id\" : \"pgDoGnV61-F\",\n"
      "      \"orig_put_url\" : \"g\",\n"
      "      \"tn_put_url\" : \"h\"\n"
      "    }\n"
      "  ],\n"
      "  \"op_id\" : 2\n"
      "}\n";
  UploadEpisodeResponse r;
  EXPECT(ParseUploadEpisodeResponse(&r, kUploadEpisodeResponse));
  EXPECT_EQ(2, r.photos_size());
  EXPECT_EQ("pgDoGmF62-F", r.photos(0).metadata().id().server_id());
  EXPECT_EQ("a", r.photos(0).full_put_url());
  EXPECT_EQ("b", r.photos(0).med_put_url());
  EXPECT_EQ("c", r.photos(0).orig_put_url());
  EXPECT_EQ("d", r.photos(0).tn_put_url());
  EXPECT_EQ("pgDoGnV61-F", r.photos(1).metadata().id().server_id());
  EXPECT_EQ("e", r.photos(1).full_put_url());
  EXPECT_EQ("f", r.photos(1).med_put_url());
  EXPECT_EQ("g", r.photos(1).orig_put_url());
  EXPECT_EQ("h", r.photos(1).tn_put_url());
}

TEST(ServerUtilsTest, ParseQueryContactsResponse) {
  const string kQueryContactsResponse =
      "{\n"
      "  \"last_key\" : \"ItevV5lAFacebookGraph:1389817135\",\n"
      "  \"headers\" : {\n"
      "    \"version\" : 7\n"
      "  },\n"
      "  \"contacts\" : [\n"
      "    {\n"
      "      \"contact_source\" : \"fb\",\n"
      "      \"contact_id\" : \"ngurfdsiagndsa\",\n"
      "      \"identities\": [\n"
      "        {\n"
      "          \"identity\" : \"FacebookGraph:620482443\"\n"
      "        },\n"
      "        {\n"
      "          \"identity\" : \"Email:spencer.kimball@emailscrubbed.com\",\n"
      "          \"description\": \"home\"\n"
      "        },\n"
      "        {\n"
      "          \"identity\" : \"Email:spencer@emailscrubbed.com\",\n"
      "          \"description\": \"work\"\n"
      "        }\n"
      "      ],\n"
      "      \"name\" : \"Spencer Kimball\",\n"
      "      \"given_name\" : \"Sp3nc3r\",\n"
      "      \"family_name\" : \"K1mball\",\n"
      "      \"rank\" : 6\n"
      "    },\n"
      "    {\n"
      "      \"contact_source\" : \"fb\",\n"
      "      \"contact_id\" : \"htunedsinagsdut\",\n"
      "      \"identities\" : [\n"
      "        {\n"
      "          \"identity\" : \"FacebookGraph:1316024\",\n"
      "          \"user_id\" : 3\n"
      "        }\n"
      "      ],\n"
      "      \"name\" : \"James Brian McGinnis\"\n"
      "    },\n"
      "    {\n"
      "      \"contact_source\" : \"em\",\n"
      "      \"contact_id\": \"ngufdsiantged\",\n"
      "      \"identities\" : [\n"
      "        {\n"
      "          \"identity\" : \"Email:jb@emailscrubbed.com\",\n"
      "          \"user_id\" : 10\n"
      "        }\n"
      "      ],\n"
      "      \"name\" : \"J. B. McGinnis\"\n"
      "    },\n"
      "    {\n"
      "      \"contact_source\" : \"ip\",\n"
      "      \"contact_id\" : \"ip:abcdefgh\",\n"
      "      \"labels\" : [\n"
      "        \"removed\"\n"
      "      ]\n"
      "    }\n"
      "  ]\n"
      "}\n";
  QueryContactsResponse r;
  ContactSelection cs;
  cs.set_start_key("");
  ASSERT(ParseQueryContactsResponse(&r, &cs, 0, kQueryContactsResponse));
  EXPECT_EQ("ItevV5lAFacebookGraph:1389817135", r.last_key());
  EXPECT_EQ(r.last_key(), cs.start_key());
  EXPECT_EQ(7, r.headers().version());
  ASSERT_EQ(4, r.contacts_size());
  const ContactMetadata* c = &r.contacts(0);
  EXPECT_EQ("ngurfdsiagndsa", c->server_contact_id());
  EXPECT(!c->has_contact_id());
  EXPECT_EQ("FacebookGraph:620482443", c->primary_identity());
  ASSERT_EQ(3, c->identities_size());
  EXPECT_EQ("FacebookGraph:620482443", c->identities(0).identity());
  EXPECT(!c->identities(0).has_description());
  EXPECT(!c->identities(0).has_user_id());
  EXPECT_EQ("Email:spencer.kimball@emailscrubbed.com", c->identities(1).identity());
  EXPECT_EQ("home", c->identities(1).description());
  EXPECT_EQ("Email:spencer@emailscrubbed.com", c->identities(2).identity());
  EXPECT_EQ("work", c->identities(2).description());
  EXPECT_EQ("Spencer Kimball", c->name());
  EXPECT_EQ("Sp3nc3r", c->first_name());
  EXPECT_EQ("K1mball", c->last_name());
  EXPECT(!c->has_user_id());
  EXPECT(c->has_rank());
  EXPECT_EQ(6, c->rank());
  EXPECT(!c->has_user_id());
  c = &r.contacts(1);
  EXPECT_EQ("FacebookGraph:1316024", c->primary_identity());
  ASSERT_EQ(1, c->identities_size());
  EXPECT_EQ("FacebookGraph:1316024", c->identities(0).identity());
  EXPECT(!c->identities(0).has_description());
  EXPECT_EQ(3, c->identities(0).user_id());
  EXPECT_EQ("James Brian McGinnis", c->name());
  EXPECT(!c->has_user_id());
  EXPECT(!c->has_rank());
  EXPECT_EQ(0, c->rank());
  c = &r.contacts(2);
  EXPECT_EQ("Email:jb@emailscrubbed.com", c->primary_identity());
  ASSERT_EQ(1, c->identities_size());
  EXPECT_EQ("Email:jb@emailscrubbed.com", c->identities(0).identity());
  EXPECT(!c->identities(0).has_description());
  EXPECT_EQ(10, c->identities(0).user_id());
  EXPECT_EQ("J. B. McGinnis", c->name());
  c = &r.contacts(3);
  EXPECT_EQ("ip:abcdefgh", c->server_contact_id());
  EXPECT(c->label_contact_removed());
}

TEST(ServerUtilsTest, ParseQueryEpisodesResponse) {
  const string kQueryEpisodesResponse =
      "{\n"
      "  \"episodes\" : [\n"
      "    {\n"
      "      \"episode_id\" : \"efxERxF1U4F\",\n"
      "      \"photos\" : [\n"
      "        {\n"
      "          \"episode_id\" : \"efxERxMU6-V\",\n"
      "          \"user_id\" : 15,\n"
      "          \"photo_id\" : \"pfxERorUm5k\",\n"
      "          \"tn_size\" : 1,\n"
      "          \"med_size\" : 2,\n"
      "          \"full_md5\" : \"a\",\n"
      "          \"orig_md5\" : \"b\",\n"
      "          \"client_data\" : {\n"
      "          },\n"
      "          \"labels\" : [\n"
      "            \"removed\",\n"
      "            \"unshared\"\n"
      "          ]\n"
      "        },\n"
      "        {\n"
      "          \"episode_id\" : \"efxERxMU6-V\",\n"
      "          \"user_id\" : 15,\n"
      "          \"photo_id\" : \"pfxERqbUn5k\",\n"
      "          \"tn_md5\" : \"c\",\n"
      "          \"med_md5\" : \"d\",\n"
      "          \"tn_size\" : 1,\n"
      "          \"med_size\" : 2,\n"
      "          \"orig_size\" : 4,\n"
      "          \"labels\" : [\n"
      "            \"removed\",\n"
      "            \"error\",\n"
      "            \"unknown\"\n"
      "          ]\n"
      "        }\n"
      "      ],\n"
      "      \"last_key\" : \"pfxERqbUn5k\"\n"
      "    },\n"
      "    {\n"
      "      \"episode_id\" : \"eg2HFbk234k\",\n"
      "      \"photos\" : [\n"
      "        {\n"
      "          \"episode_id\" : \"eg2HFbmHZ-k\",\n"
      "          \"user_id\" : 16,\n"
      "          \"photo_id\" : \"pg2HFbmI24F\",\n"
      "          \"labels\" : [\n"
      "            \"hidden\"\n"
      "          ]\n"
      "        }\n"
      "      ],\n"
      "      \"last_key\" : \"pg2HFbmI24F\"\n"
      "    }\n"
      "  ],\n"
      "  \"headers\" : {\n"
      "    \"version\" : 3,\n"
      "    \"min_required_version\" : 0\n"
      "  }\n"
      "}\n";
  QueryEpisodesResponse r;
  ASSERT(ParseQueryEpisodesResponse(
             &r, NULL, 0, kQueryEpisodesResponse));
  ASSERT(r.has_headers());
  ASSERT_EQ(3, r.headers().version());
  ASSERT_EQ(0, r.headers().min_required_version());
  ASSERT_EQ(2, r.episodes_size());
  ASSERT_EQ("efxERxF1U4F", r.episodes(0).metadata().id().server_id());
  ASSERT_EQ("pfxERqbUn5k", r.episodes(0).last_key());
  ASSERT_EQ(2, r.episodes(0).photos_size());
  ASSERT_EQ("pfxERorUm5k", r.episodes(0).photos(0).metadata().id().server_id());
  ASSERT_EQ("efxERxMU6-V", r.episodes(0).photos(0).metadata().episode_id().server_id());
  ASSERT_EQ(15, r.episodes(0).photos(0).metadata().user_id());
  ASSERT_EQ(false, r.episodes(0).photos(0).metadata().images().tn().has_md5());
  ASSERT_EQ(1, r.episodes(0).photos(0).metadata().images().tn().size());
  ASSERT_EQ(false, r.episodes(0).photos(0).metadata().images().med().has_md5());
  ASSERT_EQ(2, r.episodes(0).photos(0).metadata().images().med().size());
  ASSERT_EQ("a", r.episodes(0).photos(0).metadata().images().full().md5());
  ASSERT_EQ(false, r.episodes(0).photos(0).metadata().images().full().has_size());
  ASSERT_EQ("b", r.episodes(0).photos(0).metadata().images().orig().md5());
  ASSERT_EQ(false, r.episodes(0).photos(0).metadata().images().orig().has_size());
  ASSERT_EQ(true, r.episodes(0).photos(0).metadata().label_removed());
  ASSERT_EQ(true, r.episodes(0).photos(0).metadata().label_unshared());
  ASSERT_EQ(false, r.episodes(0).photos(0).metadata().label_error());
  ASSERT_EQ("pfxERqbUn5k", r.episodes(0).photos(1).metadata().id().server_id());
  ASSERT_EQ("efxERxMU6-V", r.episodes(0).photos(1).metadata().episode_id().server_id());
  ASSERT_EQ(15, r.episodes(0).photos(1).metadata().user_id());
  ASSERT_EQ("c", r.episodes(0).photos(1).metadata().images().tn().md5());
  ASSERT_EQ(1, r.episodes(0).photos(1).metadata().images().tn().size());
  ASSERT_EQ("d", r.episodes(0).photos(1).metadata().images().med().md5());
  // size attributes take precedence over client_data fields.
  ASSERT_EQ(2, r.episodes(0).photos(1).metadata().images().med().size());
  ASSERT_EQ(false, r.episodes(0).photos(1).metadata().images().full().has_md5());
  ASSERT_EQ(false, r.episodes(0).photos(1).metadata().images().full().has_size());
  ASSERT_EQ(false, r.episodes(0).photos(1).metadata().images().orig().has_md5());
  ASSERT_EQ(4, r.episodes(0).photos(1).metadata().images().orig().size());
  ASSERT_EQ(true, r.episodes(0).photos(1).metadata().label_removed());
  ASSERT_EQ(false, r.episodes(0).photos(1).metadata().label_unshared());
  ASSERT_EQ(true, r.episodes(0).photos(1).metadata().label_error());
  ASSERT_EQ("pg2HFbmI24F", r.episodes(1).photos(0).metadata().id().server_id());
  ASSERT_EQ("eg2HFbmHZ-k", r.episodes(1).photos(0).metadata().episode_id().server_id());
  ASSERT_EQ(16, r.episodes(1).photos(0).metadata().user_id());
  ASSERT_EQ(false, r.episodes(1).photos(0).metadata().label_removed());
  ASSERT_EQ(false, r.episodes(1).photos(0).metadata().label_error());
  ASSERT_EQ(false, r.episodes(1).photos(0).metadata().has_images());
  ASSERT_EQ(true, r.episodes(1).photos(0).metadata().label_hidden());
}

TEST(ServerUtilsTest, ParseQueryFollowedResponse) {
  const string kQueryFollowedResponse1 =
      "{\n"
      "  \"last_key\" : \"0\"\n"
      "}\n";
  QueryFollowedResponse r;
  EXPECT(ParseQueryFollowedResponse(&r, kQueryFollowedResponse1));
  EXPECT_EQ("0", r.last_key());

  const string kQueryFollowedResponse2 =
      "{\n"
      "  \"last_key\" : \"v-V-\",\n"
      "  \"headers\" : {\n"
      "    \"version\" : 3\n"
      "  },\n"
      "  \"viewpoints\" : [\n"
      "    {\n"
      "      \"type\" : \"event\",\n"
      "      \"viewpoint_id\" : \"v-7-v\",\n"
      "      \"user_id\" : 2,\n"
      "      \"update_seq\" : 1,\n"
      "      \"viewed_seq\" : 0,\n"
      "      \"labels\" : [\n"
      "        \"admin\",\n"
      "        \"contribute\",\n"
      "        \"autosave\"\n"
      "      ]\n"
      "    },\n"
      "    {\n"
      "      \"type\" : \"event\",\n"
      "      \"viewpoint_id\" : \"v-77M\",\n"
      "      \"user_id\" : 3,\n"
      "      \"update_seq\" : 2,\n"
      "      \"sharing_user_id\" : 4,\n"
      "      \"viewed_seq\" : 0,\n"
      "      \"labels\" : [\n"
      "        \"contribute\"\n"
      "      ]\n"
      "    },\n"
      "    {\n"
      "      \"type\" : \"default\",\n"
      "      \"viewpoint_id\" : \"v-V-\",\n"
      "      \"user_id\" : 5,\n"
      "      \"update_seq\" : 5,\n"
      "      \"title\" : \"hello\",\n"
      "      \"description\" : \"world\",\n"
      "      \"name\" : \"bar\",\n"
      "      \"viewed_seq\" : 4,\n"
      "      \"labels\" : [\n"
      "        \"admin\",\n"
      "        \"contribute\",\n"
      "        \"unknown\"\n"
      "      ]\n"
      "    }\n"
      "  ]\n"
      "}\n";
  ASSERT(ParseQueryFollowedResponse(&r, kQueryFollowedResponse2));
  ASSERT_EQ("v-V-", r.last_key());
  ASSERT(r.has_headers());
  ASSERT_EQ(3, r.headers().version());
  ASSERT_EQ(3, r.viewpoints_size());
  ASSERT_EQ("v-7-v", r.viewpoints(0).id().server_id());
  ASSERT_EQ(2, r.viewpoints(0).user_id());
  ASSERT_EQ(1, r.viewpoints(0).update_seq());
  ASSERT_EQ(0, r.viewpoints(0).viewed_seq());
  ASSERT(r.viewpoints(0).label_admin());
  ASSERT(r.viewpoints(0).label_contribute());
  ASSERT(r.viewpoints(0).label_autosave());
  ASSERT_EQ("v-77M", r.viewpoints(1).id().server_id());
  ASSERT_EQ(3, r.viewpoints(1).user_id());
  ASSERT_EQ(2, r.viewpoints(1).update_seq());
  ASSERT_EQ(4, r.viewpoints(1).sharing_user_id());
  ASSERT_EQ(0, r.viewpoints(1).viewed_seq());
  ASSERT(r.viewpoints(1).label_contribute());
  ASSERT(r.viewpoints(1).has_label_admin());
  ASSERT(!r.viewpoints(1).label_admin());
  ASSERT(r.viewpoints(1).has_label_autosave());
  ASSERT(!r.viewpoints(1).label_autosave());
  ASSERT_EQ("v-V-", r.viewpoints(2).id().server_id());
  ASSERT_EQ(5, r.viewpoints(2).user_id());
  ASSERT_EQ(5, r.viewpoints(2).update_seq());
  ASSERT_EQ("hello", r.viewpoints(2).title());
  ASSERT_EQ("world", r.viewpoints(2).description());
  ASSERT_EQ("bar", r.viewpoints(2).name());
  ASSERT_EQ(4, r.viewpoints(2).viewed_seq());
  ASSERT(r.viewpoints(2).label_admin());
  ASSERT(r.viewpoints(2).label_contribute());
  ASSERT(!r.viewpoints(2).label_autosave());
}

TEST(ServerUtilsTest, ParseQueryNotificationsResponse) {
  const string kQueryNotificationsResponse1 =
      "{\n"
      "  \"last_key\" : \"0\"\n"
      "}\n";
  QueryNotificationsResponse r;
  NotificationSelection ns;
  EXPECT(ParseQueryNotificationsResponse(&r, &ns, 10, kQueryNotificationsResponse1));
  EXPECT_EQ("0", r.last_key());
  EXPECT_EQ("0", ns.last_key());
  EXPECT_EQ(true, ns.query_done());

  const string kQueryNotificationsResponse2 =
      "{\n"
      "  \"notifications\" : [\n"
      "    {\n"
      "      \"notification_id\" : 0,\n"
      "      \"name\" : \"share_new\",\n"
      "      \"sender_id\" : 1,\n"
      "      \"timestamp\" : 1.1,\n"
      "      \"invalidate\" : {\n"
      "        \"episodes\" : [\n"
      "          {\n"
      "            \"episode_id\" : \"eg01\",\n"
      "            \"get_attributes\" : true,\n"
      "            \"get_photos\" : true,\n"
      "            \"photo_start_key\" : \"p01\"\n"
      "          },\n"
      "          {\n"
      "            \"episode_id\" : \"eg02\",\n"
      "            \"get_attributes\" : true,\n"
      "            \"get_photos\" : true\n"
      "          }\n"
      "        ],\n"
      "        \"contacts\" : {\n"
      "          \"start_key\" : \"123\"\n"
      "        }\n"
      "      },\n"
      "      \"inline\" : {\n"
      "        \"activity\" : {\n"
      "          \"viewpoint_id\" : \"v1\",\n"
      "          \"activity_id\" : \"a1\",\n"
      "          \"user_id\" : 1,\n"
      "          \"timestamp\" : 1.0,\n"
      "          \"update_seq\" : 1,\n"
      "          \"share_new\" : {\n"
      "            \"episodes\" : [\n"
      "              {\n"
      "                \"episode_id\" : \"eg01\",\n"
      "                \"photo_ids\" : [\n"
      "                  \"pg03\",\n"
      "                  \"pg04\"\n"
      "                ]\n"
      "              },\n"
      "              {\n"
      "                \"episode_id\" : \"eg02\",\n"
      "                \"photo_ids\" : [\n"
      "                  \"pg05\",\n"
      "                  \"pg06\"\n"
      "                ]\n"
      "              }\n"
      "            ],\n"
      "            \"follower_ids\" : [\n"
      "              1,\n"
      "              2,\n"
      "              3\n"
      "            ]\n"
      "          }\n"
      "        },\n"
      "        \"viewpoint\" : {\n"
      "          \"viewpoint_id\" : \"v1\",\n"
      "          \"update_seq\" : 2,\n"
      "          \"viewed_seq\" : 1\n"
      "        },\n"
      "        \"user\" : {\n"
      "         \"usage\" : {\n"
      "            \"owned_by\" : {\n"
      "              \"num_photos\" : 1,\n"
      "              \"tn_size\" : 2,\n"
      "              \"med_size\" : 4,\n"
      "              \"full_size\" : 8,\n"
      "              \"orig_size\" : 16\n"
      "            },\n"
      "            \"shared_by\" : {\n"
      "              \"num_photos\" : 32,\n"
      "              \"tn_size\" : 64,\n"
      "              \"med_size\" : 128,\n"
      "              \"full_size\" : 256,\n"
      "              \"orig_size\" : 512\n"
      "            },\n"
      "            \"visible_to\" : {\n"
      "              \"num_photos\" : 1024,\n"
      "              \"tn_size\" : 2048,\n"
      "              \"med_size\" : 4096,\n"
      "              \"full_size\" : 8192,\n"
      "              \"orig_size\" : 16384\n"
      "            }\n"
      "          }\n"
      "        }\n"
      "      }\n"
      "    },\n"
      "    {\n"
      "      \"notification_id\" : 1,\n"
      "      \"name\" : \"update_episode\",\n"
      "      \"sender_id\" : 1,\n"
      "      \"op_id\" : \"bar\",\n"
      "      \"timestamp\" : 1.2,\n"
      "      \"invalidate\" : {\n"
      "        \"episodes\" : [\n"
      "          {\n"
      "            \"episode_id\" : \"eg03\",\n"
      "            \"get_attributes\" : true,\n"
      "            \"get_photos\" : false\n"
      "          }\n"
      "        ]\n"
      "      },\n"
      "      \"inline\" : {\n"
      "        \"activity\" : {\n"
      "          \"viewpoint_id\" : \"v1\",\n"
      "          \"activity_id\" : \"a2\",\n"
      "          \"user_id\" : 2,\n"
      "          \"timestamp\" : 1.2,\n"
      "          \"update_episode\" : {\n"
      "            \"episode_id\" : \"eg03\"\n"
      "          }\n"
      "        },\n"
      "        \"viewpoint\" : {\n"
      "          \"viewpoint_id\" : \"v1\",\n"
      "          \"update_seq\" : 25,\n"
      "          \"viewed_seq\" : 25\n"
      "        },\n"
      "        \"user\" : {\n"
      "        }\n"
      "      }\n"
      "    },\n"
      "    {\n"
      "      \"notification_id\" : 2,\n"
      "      \"name\" : \"upload_episode\",\n"
      "      \"sender_id\" : 2,\n"
      "      \"timestamp\" : 1.3,\n"
      "      \"invalidate\" : {\n"
      "        \"episodes\" : [\n"
      "          {\n"
      "            \"episode_id\" : \"eg04\",\n"
      "            \"get_attributes\" : false\n"
      "          }\n"
      "        ]\n"
      "      },\n"
      "      \"inline\" : {\n"
      "        \"activity\" : {\n"
      "          \"viewpoint_id\" : \"v2\",\n"
      "          \"activity_id\" : \"a3\",\n"
      "          \"user_id\" : 3,\n"
      "          \"timestamp\" : 1.3,\n"
      "          \"upload_episode\" : {\n"
      "            \"episode_id\" : \"eg04\",\n"
      "            \"photo_ids\" : [\n"
      "              \"pg07\",\n"
      "              \"pg08\",\n"
      "              \"pg09\"\n"
      "            ]\n"
      "          }\n"
      "        },\n"
      "        \"user\" : {\n"
      "         \"usage\" : {\n"
      "            \"owned_by\" : {\n"
      "              \"num_photos\" : 1,\n"
      "              \"tn_size\" : 2,\n"
      "              \"med_size\" : 4,\n"
      "              \"full_size\" : 8,\n"
      "              \"orig_size\" : 16\n"
      "            }\n"
      "          }\n"
      "        }\n"
      "      }\n"
      "    },\n"
      "    {\n"
      "      \"notification_id\" : 3,\n"
      "      \"name\" : \"add_followers\",\n"
      "      \"sender_id\" : 3,\n"
      "      \"timestamp\" : 1.4,\n"
      "      \"inline\" : {\n"
      "        \"activity\" : {\n"
      "          \"viewpoint_id\" : \"v3\",\n"
      "          \"activity_id\" : \"a4\",\n"
      "          \"user_id\" : 4,\n"
      "          \"timestamp\" : 1.4,\n"
      "          \"add_followers\" : {\n"
      "            \"follower_ids\" : [\n"
      "              1,\n"
      "              2,\n"
      "              3\n"
      "            ]\n"
      "          }\n"
      "        }\n"
      "      }\n"
      "    },\n"
      "    {\n"
      "      \"notification_id\" : 4,\n"
      "      \"name\" : \"post_comment\",\n"
      "      \"sender_id\" : 4,\n"
      "      \"timestamp\" : 1.5,\n"
      "      \"inline\" : {\n"
      "        \"activity\" : {\n"
      "          \"viewpoint_id\" : \"v4\",\n"
      "          \"activity_id\" : \"a5\",\n"
      "          \"user_id\" : 5,\n"
      "          \"timestamp\" : 1.5,\n"
      "          \"post_comment\" : {\n"
      "            \"comment_id\" : \"cg04\"\n"
      "          }\n"
      "        }\n"
      "      }\n"
      "    },\n"
      "    {\n"
      "      \"notification_id\" : 5,\n"
      "      \"name\" : \"update_viewpoint\",\n"
      "      \"sender_id\" : 5,\n"
      "      \"timestamp\" : 1.6,\n"
      "      \"invalidate\" : {\n"
      "        \"viewpoints\" : [\n"
      "          {\n"
      "            \"viewpoint_id\" : \"v5\",\n"
      "            \"get_attributes\" : true\n"
      "          }\n"
      "        ]\n"
      "      },\n"
      "      \"inline\" : {\n"
      "        \"activity\" : {\n"
      "          \"viewpoint_id\" : \"v5\",\n"
      "          \"activity_id\" : \"a5\",\n"
      "          \"user_id\" : 5,\n"
      "          \"timestamp\" : 1.5,\n"
      "          \"update_viewpoint\" : {\n"
      "            \"viewpoint_id\" : \"v5\"\n"
      "          }\n"
      "        }\n"
      "      }\n"
      "    },\n"
      "    {\n"
      "      \"notification_id\" : 6,\n"
      "      \"name\" : \"share_existing\",\n"
      "      \"sender_id\" : 6,\n"
      "      \"timestamp\" : 1.7,\n"
      "      \"invalidate\" : {\n"
      "        \"episodes\" : [\n"
      "          {\n"
      "            \"episode_id\" : \"eg6\",\n"
      "            \"get_attributes\" : true,\n"
      "            \"get_photos\" : true,\n"
      "            \"photo_start_key\" : \"p01\"\n"
      "          }\n"
      "        ]\n"
      "      },\n"
      "      \"inline\" : {\n"
      "        \"activity\" : {\n"
      "          \"viewpoint_id\" : \"v1\",\n"
      "          \"activity_id\" : \"a6\",\n"
      "          \"user_id\" : 1,\n"
      "          \"timestamp\" : 1.0,\n"
      "          \"update_seq\" : 6,\n"
      "          \"share_existing\" : {\n"
      "            \"episodes\" : [\n"
      "              {\n"
      "                \"episode_id\" : \"eg6\",\n"
      "                \"photo_ids\" : [\n"
      "                  \"p01\",\n"
      "                  \"p02\"\n"
      "                ]\n"
      "              }\n"
      "            ]\n"
      "          }\n"
      "        }\n"
      "      }\n"
      "    },\n"
      "    {\n"
      "      \"notification_id\" : 7,\n"
      "      \"name\" : \"unshare\",\n"
      "      \"sender_id\" : 7,\n"
      "      \"timestamp\" : 1.8,\n"
      "      \"invalidate\" : {\n"
      "        \"episodes\" : [\n"
      "          {\n"
      "            \"episode_id\" : \"eg6\",\n"
      "            \"get_attributes\" : true,\n"
      "            \"get_photos\" : true\n"
      "          }\n"
      "        ]\n"
      "      },\n"
      "      \"inline\" : {\n"
      "        \"activity\" : {\n"
      "          \"viewpoint_id\" : \"v1\",\n"
      "          \"activity_id\" : \"a7\",\n"
      "          \"user_id\" : 1,\n"
      "          \"timestamp\" : 1.1,\n"
      "          \"update_seq\" : 7,\n"
      "          \"unshare\" : {\n"
      "            \"episodes\" : [\n"
      "              {\n"
      "                \"episode_id\" : \"eg6\",\n"
      "                \"photo_ids\" : [\n"
      "                  \"p01\"\n"
      "                ]\n"
      "              }\n"
      "            ]\n"
      "          }\n"
      "        }\n"
      "      }\n"
      "    },\n"
      "    {\n"
      "      \"notification_id\" : 8,\n"
      "      \"name\" : \"unshare\",\n"
      "      \"inline\" : {\n"
      "        \"viewpoint\" : {\n"
      "          \"viewpoint_id\" : \"v10\",\n"
      "          \"update_seq\" : 2\n"
      "        }\n"
      "      }\n"
      "    },\n"
      "    {\n"
      "      \"notification_id\" : 9,\n"
      "      \"name\" : \"post_comment\",\n"
      "      \"sender_id\" : 7,\n"
      "      \"timestamp\" : 1.9,\n"
      "      \"inline\" : {\n"
      "        \"activity\" : {\n"
      "          \"viewpoint_id\" : \"v10\",\n"
      "          \"activity_id\" : \"a9\",\n"
      "          \"user_id\" : 1,\n"
      "          \"timestamp\" : 1.1,\n"
      "          \"update_seq\" : 8,\n"
      "          \"post_comment\" : {\n"
      "            \"comment_id\" : \"cg05\"\n"
      "          }\n"
      "        },\n"
      "        \"comment\" : {\n"
      "          \"user_id\" : 1,\n"
      "          \"viewpoint_id\" : \"v10\",\n"
      "          \"comment_id\" : \"cg05\",\n"
      "          \"asset_id\" : \"p01\",\n"
      "          \"timestamp\" : 1.1,\n"
      "          \"message\" : \"test message\"\n"
      "        }\n"
      "      }\n"
      "    }\n"
      "  ],\n"
      "  \"last_key\" : \"9\"\n"
      "}\n";
  r.Clear();
  ns.Clear();
  EXPECT(ParseQueryNotificationsResponse(&r, &ns, 100, kQueryNotificationsResponse2));
  EXPECT_EQ("9", r.last_key());
  EXPECT_EQ("9", ns.last_key());
  EXPECT_EQ(true, ns.query_done());

  EXPECT_EQ(10, r.notifications_size());
  const QueryNotificationsResponse::Notification* n = &r.notifications(0);
  EXPECT_EQ(0, n->notification_id());
  EXPECT_EQ("share_new", n->name());
  EXPECT_EQ(1, n->sender_id());
  EXPECT(!n->has_op_id());
  EXPECT_EQ(1.1, n->timestamp());
  EXPECT(n->has_invalidate());
  EXPECT_EQ(2, n->invalidate().episodes_size());
  EXPECT_EQ("eg01", n->invalidate().episodes(0).episode_id());
  EXPECT_EQ(true, n->invalidate().episodes(0).get_attributes());
  EXPECT_EQ(true, n->invalidate().episodes(0).get_photos());
  EXPECT_EQ("p01", n->invalidate().episodes(0).photo_start_key());
  EXPECT_EQ("eg02", n->invalidate().episodes(1).episode_id());
  EXPECT_EQ(true, n->invalidate().episodes(1).get_attributes());
  EXPECT_EQ(true, n->invalidate().episodes(1).get_photos());
  EXPECT_EQ(false, n->invalidate().episodes(1).has_photo_start_key());
  EXPECT_EQ("123", n->invalidate().contacts().start_key());
  EXPECT(!n->invalidate().contacts().has_all());
  EXPECT(n->has_inline_invalidate());
  EXPECT(n->inline_invalidate().has_activity());
  EXPECT_EQ("v1", n->inline_invalidate().activity().viewpoint_id().server_id());
  EXPECT_EQ("a1", n->inline_invalidate().activity().activity_id().server_id());
  EXPECT_EQ(1, n->inline_invalidate().activity().user_id());
  EXPECT_EQ(1.0, n->inline_invalidate().activity().timestamp());
  EXPECT_EQ(1, n->inline_invalidate().activity().update_seq());
  EXPECT(!n->inline_invalidate().activity().has_add_followers());
  EXPECT(!n->inline_invalidate().activity().has_post_comment());
  EXPECT(n->inline_invalidate().activity().has_share_new());
  EXPECT(!n->inline_invalidate().activity().has_share_existing());
  EXPECT(!n->inline_invalidate().activity().has_unshare());
  EXPECT(!n->inline_invalidate().activity().has_update_episode());
  EXPECT(!n->inline_invalidate().activity().has_update_viewpoint());
  EXPECT(!n->inline_invalidate().activity().has_upload_episode());
  EXPECT_EQ(2, n->inline_invalidate().activity().share_new().episodes_size());
  EXPECT_EQ("eg01", n->inline_invalidate().activity().share_new().episodes(0).episode_id().server_id());
  EXPECT_EQ(2, n->inline_invalidate().activity().share_new().episodes(0).photo_ids_size());
  EXPECT_EQ("pg03", n->inline_invalidate().activity().share_new().episodes(0).photo_ids(0).server_id());
  EXPECT_EQ("pg04", n->inline_invalidate().activity().share_new().episodes(0).photo_ids(1).server_id());
  EXPECT_EQ("eg02", n->inline_invalidate().activity().share_new().episodes(1).episode_id().server_id());
  EXPECT_EQ(2, n->inline_invalidate().activity().share_new().episodes(1).photo_ids_size());
  EXPECT_EQ("pg05", n->inline_invalidate().activity().share_new().episodes(1).photo_ids(0).server_id());
  EXPECT_EQ("pg06", n->inline_invalidate().activity().share_new().episodes(1).photo_ids(1).server_id());
  EXPECT_EQ(3, n->inline_invalidate().activity().share_new().contacts_size());
  EXPECT_EQ(1, n->inline_invalidate().activity().share_new().contacts(0).user_id());
  EXPECT_EQ(2, n->inline_invalidate().activity().share_new().contacts(1).user_id());
  EXPECT_EQ(3, n->inline_invalidate().activity().share_new().contacts(2).user_id());

  EXPECT(n->inline_invalidate().has_viewpoint());
  EXPECT_EQ("v1", n->inline_invalidate().viewpoint().viewpoint_id());
  EXPECT_EQ(2, n->inline_invalidate().viewpoint().update_seq());
  EXPECT_EQ(1, n->inline_invalidate().viewpoint().viewed_seq());

  EXPECT(n->inline_invalidate().has_usage());
  EXPECT(n->inline_invalidate().usage().has_owned_by());
  EXPECT(n->inline_invalidate().usage().has_shared_by());
  EXPECT(n->inline_invalidate().usage().has_visible_to());
  EXPECT_EQ(1, n->inline_invalidate().usage().owned_by().num_photos());
  EXPECT_EQ(2, n->inline_invalidate().usage().owned_by().tn_size());
  EXPECT_EQ(4, n->inline_invalidate().usage().owned_by().med_size());
  EXPECT_EQ(8, n->inline_invalidate().usage().owned_by().full_size());
  EXPECT_EQ(16, n->inline_invalidate().usage().owned_by().orig_size());
  EXPECT_EQ(32, n->inline_invalidate().usage().shared_by().num_photos());
  EXPECT_EQ(64, n->inline_invalidate().usage().shared_by().tn_size());
  EXPECT_EQ(128, n->inline_invalidate().usage().shared_by().med_size());
  EXPECT_EQ(256, n->inline_invalidate().usage().shared_by().full_size());
  EXPECT_EQ(512, n->inline_invalidate().usage().shared_by().orig_size());
  EXPECT_EQ(1024, n->inline_invalidate().usage().visible_to().num_photos());
  EXPECT_EQ(2048, n->inline_invalidate().usage().visible_to().tn_size());
  EXPECT_EQ(4096, n->inline_invalidate().usage().visible_to().med_size());
  EXPECT_EQ(8192, n->inline_invalidate().usage().visible_to().full_size());
  EXPECT_EQ(16384, n->inline_invalidate().usage().visible_to().orig_size());

  n = &r.notifications(1);
  EXPECT_EQ(1, n->notification_id());
  EXPECT_EQ("update_episode", n->name());
  EXPECT_EQ(1, n->sender_id());
  EXPECT_EQ(1.2, n->timestamp());
  EXPECT_EQ("bar", n->op_id());
  EXPECT(n->has_invalidate());
  EXPECT_EQ(1, n->invalidate().episodes_size());
  EXPECT_EQ("eg03", n->invalidate().episodes(0).episode_id());
  EXPECT_EQ(true, n->invalidate().episodes(0).get_attributes());
  EXPECT_EQ(false, n->invalidate().episodes(0).get_photos());
  EXPECT_EQ(false, n->invalidate().has_contacts());
  EXPECT(n->has_inline_invalidate());
  EXPECT(n->inline_invalidate().has_activity());
  EXPECT_EQ("v1", n->inline_invalidate().activity().viewpoint_id().server_id());
  EXPECT_EQ("a2", n->inline_invalidate().activity().activity_id().server_id());
  EXPECT_EQ(2, n->inline_invalidate().activity().user_id());
  EXPECT_EQ(1.2, n->inline_invalidate().activity().timestamp());
  EXPECT(!n->inline_invalidate().activity().has_add_followers());
  EXPECT(!n->inline_invalidate().activity().has_post_comment());
  EXPECT(!n->inline_invalidate().activity().has_share_new());
  EXPECT(!n->inline_invalidate().activity().has_share_existing());
  EXPECT(!n->inline_invalidate().activity().has_unshare());
  EXPECT(!n->inline_invalidate().activity().has_upload_episode());
  EXPECT(n->inline_invalidate().activity().has_update_episode());
  EXPECT_EQ("eg03", n->inline_invalidate().activity().update_episode().episode_id().server_id());
  EXPECT(!n->inline_invalidate().activity().has_update_viewpoint());

  EXPECT(n->inline_invalidate().has_viewpoint());
  EXPECT_EQ("v1", n->inline_invalidate().viewpoint().viewpoint_id());
  EXPECT_EQ(25, n->inline_invalidate().viewpoint().update_seq());
  EXPECT_EQ(25, n->inline_invalidate().viewpoint().viewed_seq());

  EXPECT(!n->inline_invalidate().has_usage());

  n = &r.notifications(2);
  EXPECT_EQ(2, n->notification_id());
  EXPECT_EQ("upload_episode", n->name());
  EXPECT_EQ(2, n->sender_id());
  EXPECT_EQ(1.3, n->timestamp());
  EXPECT(n->has_invalidate());
  EXPECT_EQ(1, n->invalidate().episodes_size());
  EXPECT_EQ("eg04", n->invalidate().episodes(0).episode_id());
  EXPECT_EQ(false, n->invalidate().episodes(0).get_attributes());
  EXPECT(!n->invalidate().episodes(0).has_get_photos());
  EXPECT(!n->invalidate().episodes(0).has_photo_start_key());
  EXPECT_EQ(false, n->invalidate().has_contacts());
  EXPECT(n->has_inline_invalidate());
  EXPECT(n->inline_invalidate().has_activity());
  EXPECT_EQ("v2", n->inline_invalidate().activity().viewpoint_id().server_id());
  EXPECT_EQ("a3", n->inline_invalidate().activity().activity_id().server_id());
  EXPECT_EQ(3, n->inline_invalidate().activity().user_id());
  EXPECT_EQ(1.3, n->inline_invalidate().activity().timestamp());
  EXPECT(!n->inline_invalidate().activity().has_add_followers());
  EXPECT(!n->inline_invalidate().activity().has_post_comment());
  EXPECT(!n->inline_invalidate().activity().has_update_episode());
  EXPECT(!n->inline_invalidate().activity().has_update_viewpoint());
  EXPECT(n->inline_invalidate().activity().has_upload_episode());
  EXPECT_EQ("eg04", n->inline_invalidate().activity().upload_episode().episode_id().server_id());
  EXPECT_EQ(3, n->inline_invalidate().activity().upload_episode().photo_ids_size());
  EXPECT_EQ("pg07", n->inline_invalidate().activity().upload_episode().photo_ids(0).server_id());
  EXPECT_EQ("pg08", n->inline_invalidate().activity().upload_episode().photo_ids(1).server_id());
  EXPECT_EQ("pg09", n->inline_invalidate().activity().upload_episode().photo_ids(2).server_id());

  EXPECT(n->inline_invalidate().has_usage());
  EXPECT(n->inline_invalidate().usage().has_owned_by());
  EXPECT(!n->inline_invalidate().usage().has_shared_by());
  EXPECT(!n->inline_invalidate().usage().has_visible_to());
  EXPECT_EQ(1, n->inline_invalidate().usage().owned_by().num_photos());
  EXPECT_EQ(2, n->inline_invalidate().usage().owned_by().tn_size());
  EXPECT_EQ(4, n->inline_invalidate().usage().owned_by().med_size());
  EXPECT_EQ(8, n->inline_invalidate().usage().owned_by().full_size());
  EXPECT_EQ(16, n->inline_invalidate().usage().owned_by().orig_size());

  n = &r.notifications(3);
  EXPECT_EQ(3, n->notification_id());
  EXPECT_EQ("add_followers", n->name());
  EXPECT_EQ(3, n->sender_id());
  EXPECT_EQ(1.4, n->timestamp());
  EXPECT(!n->has_invalidate());
  EXPECT(n->has_inline_invalidate());
  EXPECT(n->inline_invalidate().has_activity());
  EXPECT_EQ("v3", n->inline_invalidate().activity().viewpoint_id().server_id());
  EXPECT_EQ("a4", n->inline_invalidate().activity().activity_id().server_id());
  EXPECT_EQ(4, n->inline_invalidate().activity().user_id());
  EXPECT_EQ(1.4, n->inline_invalidate().activity().timestamp());
  EXPECT(n->inline_invalidate().activity().has_add_followers());
  EXPECT(!n->inline_invalidate().activity().has_post_comment());
  EXPECT(!n->inline_invalidate().activity().has_update_episode());
  EXPECT(!n->inline_invalidate().activity().has_update_viewpoint());
  EXPECT(!n->inline_invalidate().activity().has_upload_episode());
  EXPECT_EQ(3, n->inline_invalidate().activity().add_followers().contacts_size());
  EXPECT_EQ(1, n->inline_invalidate().activity().add_followers().contacts(0).user_id());
  EXPECT_EQ(2, n->inline_invalidate().activity().add_followers().contacts(1).user_id());
  EXPECT_EQ(3, n->inline_invalidate().activity().add_followers().contacts(2).user_id());

  n = &r.notifications(4);
  EXPECT_EQ(4, n->notification_id());
  EXPECT_EQ("post_comment", n->name());
  EXPECT_EQ(4, n->sender_id());
  EXPECT_EQ(1.5, n->timestamp());
  EXPECT(!n->has_invalidate());
  EXPECT(n->has_inline_invalidate());
  EXPECT(n->inline_invalidate().has_activity());
  EXPECT_EQ("v4", n->inline_invalidate().activity().viewpoint_id().server_id());
  EXPECT_EQ("a5", n->inline_invalidate().activity().activity_id().server_id());
  EXPECT_EQ(5, n->inline_invalidate().activity().user_id());
  EXPECT_EQ(1.5, n->inline_invalidate().activity().timestamp());
  EXPECT(!n->inline_invalidate().activity().has_add_followers());
  EXPECT(n->inline_invalidate().activity().has_post_comment());
  EXPECT(!n->inline_invalidate().activity().has_update_episode());
  EXPECT(!n->inline_invalidate().activity().has_update_viewpoint());
  EXPECT(!n->inline_invalidate().activity().has_upload_episode());
  EXPECT_EQ("cg04", n->inline_invalidate().activity().post_comment().comment_id().server_id());

  n = &r.notifications(5);
  EXPECT_EQ(5, n->notification_id());
  EXPECT_EQ("update_viewpoint", n->name());
  EXPECT_EQ(5, n->sender_id());
  EXPECT_EQ(1.6, n->timestamp());
  EXPECT(n->has_invalidate());
  EXPECT_EQ(0, n->invalidate().episodes_size());
  EXPECT_EQ(1, n->invalidate().viewpoints_size());
  EXPECT_EQ("v5", n->invalidate().viewpoints(0).viewpoint_id());
  EXPECT_EQ(true, n->invalidate().viewpoints(0).get_attributes());
  EXPECT_EQ(false, n->invalidate().viewpoints(0).get_episodes());
  EXPECT(!n->invalidate().viewpoints(0).has_get_followers());
  EXPECT_EQ(false, n->invalidate().has_contacts());
  EXPECT(n->has_inline_invalidate());
  EXPECT(n->inline_invalidate().has_activity());
  EXPECT_EQ("v5", n->inline_invalidate().activity().viewpoint_id().server_id());
  EXPECT_EQ("a5", n->inline_invalidate().activity().activity_id().server_id());
  EXPECT_EQ(5, n->inline_invalidate().activity().user_id());
  EXPECT_EQ(1.5, n->inline_invalidate().activity().timestamp());
  EXPECT(!n->inline_invalidate().activity().has_add_followers());
  EXPECT(!n->inline_invalidate().activity().has_post_comment());
  EXPECT(!n->inline_invalidate().activity().has_share_new());
  EXPECT(!n->inline_invalidate().activity().has_share_existing());
  EXPECT(!n->inline_invalidate().activity().has_unshare());
  EXPECT(!n->inline_invalidate().activity().has_update_episode());
  EXPECT(n->inline_invalidate().activity().has_update_viewpoint());
  EXPECT(!n->inline_invalidate().activity().has_upload_episode());
  EXPECT_EQ("v5", n->inline_invalidate().activity().update_viewpoint().viewpoint_id().server_id());

  n = &r.notifications(6);
  EXPECT_EQ(6, n->notification_id());
  EXPECT_EQ("share_existing", n->name());
  EXPECT_EQ(6, n->sender_id());
  EXPECT_EQ(1.7, n->timestamp());
  EXPECT(n->has_invalidate());
  EXPECT_EQ(1, n->invalidate().episodes_size());
  EXPECT_EQ("eg6", n->invalidate().episodes(0).episode_id());
  EXPECT_EQ(true, n->invalidate().episodes(0).get_attributes());
  EXPECT_EQ(true, n->invalidate().episodes(0).get_photos());
  EXPECT_EQ("p01", n->invalidate().episodes(0).photo_start_key());
  EXPECT(n->has_inline_invalidate());
  EXPECT(n->inline_invalidate().has_activity());
  EXPECT_EQ("v1", n->inline_invalidate().activity().viewpoint_id().server_id());
  EXPECT_EQ("a6", n->inline_invalidate().activity().activity_id().server_id());
  EXPECT_EQ(1, n->inline_invalidate().activity().user_id());
  EXPECT_EQ(1.0, n->inline_invalidate().activity().timestamp());
  EXPECT(n->has_inline_invalidate());
  EXPECT(n->inline_invalidate().has_activity());
  EXPECT(n->inline_invalidate().activity().has_share_existing());
  EXPECT_EQ(1, n->inline_invalidate().activity().share_existing().episodes_size());
  EXPECT_EQ("eg6", n->inline_invalidate().activity().share_existing().episodes(0).episode_id().server_id());
  EXPECT_EQ(2, n->inline_invalidate().activity().share_existing().episodes(0).photo_ids_size());
  EXPECT_EQ("p01", n->inline_invalidate().activity().share_existing().episodes(0).photo_ids(0).server_id());
  EXPECT_EQ("p02", n->inline_invalidate().activity().share_existing().episodes(0).photo_ids(1).server_id());

  n = &r.notifications(7);
  EXPECT_EQ(7, n->notification_id());
  EXPECT_EQ("unshare", n->name());
  EXPECT_EQ(7, n->sender_id());
  EXPECT_EQ(1.8, n->timestamp());
  EXPECT(n->has_invalidate());
  EXPECT_EQ(1, n->invalidate().episodes_size());
  EXPECT_EQ("eg6", n->invalidate().episodes(0).episode_id());
  EXPECT_EQ(true, n->invalidate().episodes(0).get_attributes());
  EXPECT_EQ(true, n->invalidate().episodes(0).get_photos());
  EXPECT(!n->invalidate().episodes(0).has_photo_start_key());
  EXPECT(n->has_inline_invalidate());
  EXPECT(n->inline_invalidate().has_activity());
  EXPECT_EQ("v1", n->inline_invalidate().activity().viewpoint_id().server_id());
  EXPECT_EQ("a7", n->inline_invalidate().activity().activity_id().server_id());
  EXPECT_EQ(1, n->inline_invalidate().activity().user_id());
  EXPECT_EQ(1.1, n->inline_invalidate().activity().timestamp());
  EXPECT(n->inline_invalidate().activity().has_unshare());
  EXPECT_EQ(1, n->inline_invalidate().activity().unshare().episodes_size());
  EXPECT_EQ("eg6", n->inline_invalidate().activity().unshare().episodes(0).episode_id().server_id());
  EXPECT_EQ(1, n->inline_invalidate().activity().unshare().episodes(0).photo_ids_size());
  EXPECT_EQ("p01", n->inline_invalidate().activity().unshare().episodes(0).photo_ids(0).server_id());

  n = &r.notifications(8);
  EXPECT_EQ(8, n->notification_id());
  EXPECT_EQ("unshare", n->name());
  EXPECT(!n->has_invalidate());
  EXPECT(n->has_inline_invalidate());
  EXPECT(!n->inline_invalidate().has_activity());
  EXPECT(n->inline_invalidate().has_viewpoint());
  EXPECT_EQ("v10", n->inline_invalidate().viewpoint().viewpoint_id());
  EXPECT_EQ(2, n->inline_invalidate().viewpoint().update_seq());

  n = &r.notifications(9);
  EXPECT_EQ(9, n->notification_id());
  EXPECT_EQ("post_comment", n->name());
  EXPECT(!n->has_invalidate());
  EXPECT(n->has_inline_invalidate());
  EXPECT(n->inline_invalidate().has_activity());
  EXPECT(!n->inline_invalidate().has_viewpoint());
  EXPECT(n->inline_invalidate().has_comment());
  EXPECT_EQ("v10", n->inline_invalidate().comment().viewpoint_id().server_id());
  EXPECT_EQ("cg05", n->inline_invalidate().comment().comment_id().server_id());
  EXPECT_EQ("p01", n->inline_invalidate().comment().asset_id());
  EXPECT_EQ(1.1, n->inline_invalidate().comment().timestamp());
  EXPECT_EQ("test message", n->inline_invalidate().comment().message());

  // Parse the same response again, this time with a limit of 10...
  // should result in query_done being set to false on the selection.
  r.Clear();
  ns.Clear();
  EXPECT(ParseQueryNotificationsResponse(&r, &ns, 10, kQueryNotificationsResponse2));
  EXPECT_EQ("9", r.last_key());
  EXPECT_EQ("9", ns.last_key());
  EXPECT_EQ(false, ns.query_done());

  // Test parsing of a notification with an unrecognized activity type.
  const string kUnknownActivityQueryNotificationsResponse =
      "{\n"
      "  \"notifications\" : [\n"
      "    {\n"
      "      \"notification_id\" : 3,\n"
      "      \"name\" : \"unknown\",\n"
      "      \"sender_id\" : 1,\n"
      "      \"timestamp\" : 2.0,\n"
      "      \"invalidate\" : {\n"
      "        \"episodes\" : [\n"
      "          {\n"
      "            \"episode_id\" : \"eg01\",\n"
      "            \"get_attributes\" : true,\n"
      "            \"get_photos\" : true,\n"
      "            \"photo_start_key\" : \"p01\"\n"
      "          }\n"
      "        ]\n"
      "      },\n"
      "      \"activity\" : {\n"
      "        \"viewpoint_id\" : \"v1\",\n"
      "        \"activity_id\" : \"a1\",\n"
      "        \"user_id\" : 1,\n"
      "        \"timestamp\" : 1.0,\n"
      "        \"unknown\" : {\n"
      "          \"random\" : [ 1, 2, 3 ]\n"
      "        }\n"
      "      }\n"
      "    }\n"
      "  ],\n"
      "  \"last_key\" : \"3\"\n"
      "}\n";
  r.Clear();
  ns.Clear();
  EXPECT(ParseQueryNotificationsResponse(
             &r, &ns, 10, kUnknownActivityQueryNotificationsResponse));
  EXPECT_EQ("3", r.last_key());
  EXPECT_EQ("3", ns.last_key());
  EXPECT_EQ(true, ns.query_done());

  EXPECT_EQ(1, r.notifications_size());
  n = &r.notifications(0);
  EXPECT_EQ(3, n->notification_id());
  EXPECT_EQ("unknown", n->name());
  EXPECT_EQ(1, n->sender_id());
  EXPECT_EQ(2.0, n->timestamp());
  EXPECT(n->has_invalidate());
  EXPECT_EQ(1, n->invalidate().episodes_size());
  EXPECT_EQ("eg01", n->invalidate().episodes(0).episode_id());
  EXPECT_EQ(true, n->invalidate().episodes(0).get_attributes());
  EXPECT_EQ(true, n->invalidate().episodes(0).get_photos());
  EXPECT_EQ("p01", n->invalidate().episodes(0).photo_start_key());
  EXPECT_EQ(false, n->invalidate().has_contacts());
  EXPECT(!n->has_inline_invalidate());

  // Test parsing of a notification with an unrecognized invalidation type.
  const string kUnknownInvalidateQueryNotificationsResponse =
      "{\n"
      "  \"notifications\" : [\n"
      "    {\n"
      "      \"notification_id\" : 4,\n"
      "      \"name\" : \"invalidate\",\n"
      "      \"sender_id\" : 1,\n"
      "      \"timestamp\" : 2.0,\n"
      "      \"invalidate\" : {\n"
      "        \"episodes\" : [\n"
      "          {\n"
      "            \"episode_id\" : \"eg01\",\n"
      "            \"get_attributes\" : true,\n"
      "            \"get_photos\" : true,\n"
      "            \"photo_start_key\" : \"p01\"\n"
      "          },\n"
      "          {\n"
      "            \"episode_id\" : \"eg02\",\n"
      "            \"get_attributes\" : false,\n"
      "            \"get_photos\" : true,\n"
      "            \"photo_start_key\" : \"pg01\",\n"
      "            \"unknown\" : \"unknown-value\"\n"
      "          }\n"
      "        ],\n"
      "        \"viewpoints\" : [\n"
      "          {\n"
      "            \"viewpoint_id\" : \"v1\",\n"
      "            \"get_attributes\" : true,\n"
      "            \"get_episodes\" : true,\n"
      "            \"episode_start_key\" : \"eg01\"\n"
      "          },\n"
      "          {\n"
      "            \"viewpoint_id\" : \"v2\",\n"
      "            \"get_attributes\" : false,\n"
      "            \"get_episodes\" : true,\n"
      "            \"episode_start_key\" : \"eg01\",\n"
      "            \"unknown\" : -1\n"
      "          }\n"
      "        ],\n"
      "        \"unknown\" : {\n"
      "          \"unknown-key\" : \"unknown-value\"\n"
      "        }\n"
      "      }\n"
      "    }\n"
      "  ],\n"
      "  \"last_key\" : \"4\"\n"
      "}\n";
  r.Clear();
  ns.Clear();
  EXPECT(ParseQueryNotificationsResponse(
             &r, &ns, 10, kUnknownInvalidateQueryNotificationsResponse));
  EXPECT_EQ("4", r.last_key());
  EXPECT_EQ("4", ns.last_key());
  EXPECT_EQ(true, ns.query_done());

  EXPECT_EQ(1, r.notifications_size());
  n = &r.notifications(0);
  EXPECT_EQ(4, n->notification_id());
  EXPECT_EQ("invalidate", n->name());
  EXPECT_EQ(1, n->sender_id());
  EXPECT_EQ(2.0, n->timestamp());
  EXPECT(n->has_invalidate());
  EXPECT_EQ(2, n->invalidate().episodes_size());
  EXPECT_EQ("eg01", n->invalidate().episodes(0).episode_id());
  EXPECT_EQ(true, n->invalidate().episodes(0).get_attributes());
  EXPECT_EQ(true, n->invalidate().episodes(0).get_photos());
  EXPECT_EQ("p01", n->invalidate().episodes(0).photo_start_key());
  EXPECT_EQ("eg02", n->invalidate().episodes(1).episode_id());
  EXPECT_EQ(false, n->invalidate().episodes(1).get_attributes());
  EXPECT_EQ(true, n->invalidate().episodes(1).get_photos());
  EXPECT_EQ("pg01", n->invalidate().episodes(1).photo_start_key());
  EXPECT_EQ(2, n->invalidate().viewpoints_size());
  EXPECT_EQ("v1", n->invalidate().viewpoints(0).viewpoint_id());
  EXPECT_EQ(true, n->invalidate().viewpoints(0).get_attributes());
  EXPECT_EQ(true, n->invalidate().viewpoints(0).get_episodes());
  EXPECT_EQ("eg01", n->invalidate().viewpoints(0).episode_start_key());
  EXPECT_EQ("v2", n->invalidate().viewpoints(1).viewpoint_id());
  EXPECT_EQ(false, n->invalidate().viewpoints(1).get_attributes());
  EXPECT_EQ(true, n->invalidate().viewpoints(1).get_episodes());
  EXPECT_EQ("eg01", n->invalidate().viewpoints(1).episode_start_key());
  EXPECT_EQ(false, n->invalidate().has_contacts());
}

// Verify nuclear invalidation directive in notifications.
TEST(ServerUtilsTest, ParseQueryNotificationsInvalidateAll) {
  const string kQueryNotificationsResponse1 =
      "{\n"
      "  \"last_key\" : \"1\",\n"
      "  \"notifications\" : [\n"
      "    {\n"
      "      \"notification_id\" : 1,\n"
      "      \"name\" : \"nuclear\",\n"
      "      \"sender_id\" : 1,\n"
      "      \"timestamp\" : 1.0,\n"
      "      \"invalidate\" : {\n"
      "        \"all\" : true\n"
      "      }\n"
      "    }\n"
      "  ]\n"
      "}\n";
  QueryNotificationsResponse r;
  NotificationSelection ns;
  EXPECT(ParseQueryNotificationsResponse(&r, &ns, 10, kQueryNotificationsResponse1));
  EXPECT_EQ("1", r.last_key());
  EXPECT_EQ("", ns.last_key());
  EXPECT_EQ(false, ns.query_done());

  // Try an invalidate all which is located _after_ some earlier
  // notifications.
  const string kQueryNotificationsResponse2 =
      "{\n"
      "  \"last_key\" : \"2\",\n"
      "  \"notifications\" : [\n"
      "    {\n"
      "      \"notification_id\" : 1,\n"
      "      \"name\" : \"update_episode\",\n"
      "      \"sender_id\" : 1,\n"
      "      \"timestamp\" : 1.0,\n"
      "      \"invalidate\" : {\n"
      "        \"episodes\" : [\n"
      "          {\n"
      "            \"episode_id\" : \"eg03\",\n"
      "            \"get_attributes\" : true,\n"
      "            \"get_photos\" : false\n"
      "          }\n"
      "        ]\n"
      "      },\n"
      "      \"inline\" : {\n"
      "        \"activity\" : {\n"
      "          \"viewpoint_id\" : \"v1\",\n"
      "          \"activity_id\" : \"a2\",\n"
      "          \"user_id\" : 2,\n"
      "          \"timestamp\" : 1.2,\n"
      "          \"update_episode\" : {\n"
      "            \"episode_id\" : \"eg03\"\n"
      "          }\n"
      "        }\n"
      "      }\n"
      "    },\n"
      "    {\n"
      "      \"notification_id\" : 2,\n"
      "      \"name\" : \"nuclear\",\n"
      "      \"sender_id\" : 1,\n"
      "      \"timestamp\" : 2.0,\n"
      "      \"invalidate\" : {\n"
      "        \"all\" : true\n"
      "      }\n"
      "    }\n"
      "  ]\n"
      "}\n";
  r.Clear();
  ns.Clear();
  EXPECT(ParseQueryNotificationsResponse(&r, &ns, 10, kQueryNotificationsResponse2));
  EXPECT_EQ("2", r.last_key());
  EXPECT_EQ("", ns.last_key());
  EXPECT_EQ(false, ns.query_done());
}

TEST(ServerUtilsTest, ParseQueryNotificationsInvalidateAllContacts) {
  const string kQueryNotificationsResponse =
      "{\n"
      "  \"last_key\" : \"3\",\n"
      "  \"notifications\" : [\n"
      "    {\n"
      "      \"notification_id\" : 3,\n"
      "      \"invalidate\" : {\n"
      "        \"contacts\": {\n"
      "          \"start_key\" : \"0\",\n"
      "          \"all\" : true\n"
      "        }\n"
      "      }\n"
      "    }\n"
      "  ]\n"
      "}\n";
  QueryNotificationsResponse r;
  NotificationSelection ns;
  ASSERT(ParseQueryNotificationsResponse(&r, &ns, 10, kQueryNotificationsResponse));
  EXPECT_EQ("0", r.notifications(0).invalidate().contacts().start_key());
  EXPECT(r.notifications(0).invalidate().contacts().all());
}

// Verify gap in notification sequence.
TEST(ServerUtilsTest, ParseQueryNotificationsGap) {
  const string kQueryNotificationsResponse1 =
      "{\n"
      "  \"last_key\" : \"3\",\n"
      "  \"notifications\" : [\n"
      "    {\n"
      "      \"notification_id\" : 3,\n"
      "      \"name\" : \"update_episode\",\n"
      "      \"sender_id\" : 1,\n"
      "      \"timestamp\" : 1.0,\n"
      "      \"invalidate\" : {\n"
      "        \"episodes\" : [\n"
      "          {\n"
      "            \"episode_id\" : \"eg03\",\n"
      "            \"get_attributes\" : true,\n"
      "            \"get_photos\" : false\n"
      "          }\n"
      "        ]\n"
      "      },\n"
      "      \"inline\" : {\n"
      "        \"activity\" : {\n"
      "          \"viewpoint_id\" : \"v1\",\n"
      "          \"activity_id\" : \"a2\",\n"
      "          \"user_id\" : 2,\n"
      "          \"timestamp\" : 1.2,\n"
      "          \"update_episode\" : {\n"
      "            \"episode_id\" : \"eg03\"\n"
      "          }\n"
      "        }\n"
      "      }\n"
      "    }\n"
      "  ]\n"
      "}\n";
  QueryNotificationsResponse r;
  NotificationSelection ns;
  // There's no perceived gap if "last_key" in the selection is empty.
  EXPECT(ParseQueryNotificationsResponse(&r, &ns, 10, kQueryNotificationsResponse1));
  EXPECT_EQ("3", r.last_key());
  EXPECT_EQ("3", ns.last_key());
  EXPECT_EQ(true, ns.query_done());

  // Also no gap if "last_key" matches appropriately.
  r.Clear();
  ns.Clear();
  ns.set_last_key("2");
  EXPECT(ParseQueryNotificationsResponse(&r, &ns, 10, kQueryNotificationsResponse1));
  EXPECT_EQ("3", r.last_key());
  EXPECT_EQ("3", ns.last_key());
  EXPECT_EQ(true, ns.query_done());

  // However, if there is a gap, total invalidation should be triggered.
  r.Clear();
  ns.Clear();
  ns.set_last_key("1");
  EXPECT(ParseQueryNotificationsResponse(&r, &ns, 10, kQueryNotificationsResponse1));
  EXPECT_EQ("3", r.last_key());
  EXPECT_EQ("", ns.last_key());
  EXPECT_EQ(false, ns.query_done());
}

// An empty notification query does not reset the last key to empty.
TEST(ServerUtilsTest, ParseQueryNotificationsEmptyResponse) {
  const string kQueryNotificationsResponse =
      "{\n"
      "  \"headers\" : {\n"
      "    \"version\" : 1,\n"
      "    \"min_required_version\" : 1\n"
      "  }\n"
      "}\n";
  QueryNotificationsResponse r;
  NotificationSelection ns;
  ns.set_last_key("10");
  ns.set_query_done(false);

  EXPECT(ParseQueryNotificationsResponse(&r, &ns, 10, kQueryNotificationsResponse));
  EXPECT(!r.has_last_key());
  EXPECT_EQ("10", ns.last_key());
  EXPECT_EQ(true, ns.query_done());
}

TEST(ServerUtilsTest, ParseQueryNotificationsWithUsers) {
  const string kQueryNotificationsResponse1 =
      "{\n"
      "  \"notifications\" : [\n"
      "    {\n"
      "      \"invalidate\": {\n"
      "        \"users\": [\n"
      "          42,\n"
      "          7\n"
      "        ]\n"
      "      }\n"
      "    }\n"
      "  ]\n"
      "}\n";

  QueryNotificationsResponse r;
  NotificationSelection ns;
  ASSERT(ParseQueryNotificationsResponse(&r, &ns, 10, kQueryNotificationsResponse1));
  ASSERT_EQ(r.notifications_size(), 1);
  ASSERT(r.notifications(0).has_invalidate());
  ASSERT_EQ(r.notifications(0).invalidate().users_size(), 2);
  EXPECT_EQ(r.notifications(0).invalidate().users(0).user_id(), 42);
  EXPECT_EQ(r.notifications(0).invalidate().users(1).user_id(), 7);
}

// Verify operation of query notifications in the face of protocol
// versions both understood and not understood by the client.
TEST(ServerUtilsTest, ParseQueryNotificationsWithVersions) {
  EXPECT_LT(AppState::protocol_version(), 1000);

  // Start with a response containing a comprehensible version.
  const string kQueryNotificationsResponse1 =
      "{\n"
      "  \"headers\" : {\n"
      "    \"version\" : 1000,\n"
      "    \"min_required_version\" : 1\n"
      "  },\n"
      "  \"last_key\" : \"1\",\n"
      "  \"notifications\" : [\n"
      "    {\n"
      "      \"notification_id\" : 1,\n"
      "      \"name\" : \"update_episode\",\n"
      "      \"sender_id\" : 1,\n"
      "      \"timestamp\" : 1.0,\n"
      "      \"invalidate\" : {\n"
      "        \"episodes\" : [\n"
      "          {\n"
      "            \"episode_id\" : \"eg03\",\n"
      "            \"get_attributes\" : true,\n"
      "            \"get_photos\" : false\n"
      "          }\n"
      "        ]\n"
      "      },\n"
      "      \"inline\" : {\n"
      "        \"activity\" : {\n"
      "          \"viewpoint_id\" : \"v1\",\n"
      "          \"activity_id\" : \"a2\",\n"
      "          \"user_id\" : 2,\n"
      "          \"timestamp\" : 1.2,\n"
      "          \"update_episode\" : {\n"
      "            \"episode_id\" : \"eg03\"\n"
      "          }\n"
      "        }\n"
      "      }\n"
      "    }\n"
      "  ]\n"
      "}\n";
  QueryNotificationsResponse r;
  NotificationSelection ns;
  EXPECT(ParseQueryNotificationsResponse(&r, &ns, 10, kQueryNotificationsResponse1));
  EXPECT_EQ("1", r.last_key());
  EXPECT_EQ("1", ns.last_key());
  EXPECT_EQ(true, ns.query_done());
  EXPECT(!ns.has_max_min_required_version());
  EXPECT(!ns.has_low_water_notification_id());

  // Now, try a response with a version not understood by the client.
  const string kQueryNotificationsResponse2 =
      "{\n"
      "  \"headers\" : {\n"
      "    \"version\" : 1000,\n"
      "    \"min_required_version\" : 1000\n"
      "  },\n"
      "  \"last_key\" : \"1\",\n"
      "  \"notifications\" : [\n"
      "    {\n"
      "      \"notification_id\" : 1,\n"
      "      \"name\" : \"update_episode\",\n"
      "      \"sender_id\" : 1,\n"
      "      \"timestamp\" : 1.0,\n"
      "      \"invalidate\" : {\n"
      "        \"episodes\" : [\n"
      "          {\n"
      "            \"episode_id\" : \"eg03\",\n"
      "            \"get_attributes\" : true,\n"
      "            \"get_photos\" : false\n"
      "          }\n"
      "        ]\n"
      "      },\n"
      "      \"inline\" : {\n"
      "        \"activity\" : {\n"
      "          \"viewpoint_id\" : \"v1\",\n"
      "          \"activity_id\" : \"a2\",\n"
      "          \"user_id\" : 2,\n"
      "          \"timestamp\" : 1.2,\n"
      "          \"update_episode\" : {\n"
      "            \"episode_id\" : \"eg03\"\n"
      "          }\n"
      "        }\n"
      "      }\n"
      "    }\n"
      "  ]\n"
      "}\n";
  r.Clear();
  ns.Clear();
  EXPECT(ParseQueryNotificationsResponse(&r, &ns, 10, kQueryNotificationsResponse2));
  EXPECT_EQ("1", r.last_key());
  EXPECT_EQ("1", ns.last_key());
  EXPECT_EQ(true, ns.query_done());
  EXPECT_EQ(1000, ns.max_min_required_version());
  EXPECT(ns.has_low_water_notification_id());
  EXPECT_EQ(0, ns.low_water_notification_id());
}

TEST(ServerUtilsTest, ParseQueryUsersResponse) {
  const string kQueryUsersResponse =
      "{\n"
      "  \"users\" : [\n"
      "    {\n"
      "      \"user_id\" : 2,\n"
      "      \"name\" : \"Peter Mattis\",\n"
      "      \"private\" : {\n"
      "        \"user_identities\" : [\n"
      "          {\n"
      "            \"identity\": \"Email:spencer@emailscrubbed.com\",\n"
      "            \"authority\": \"Google\"\n"
      "          },\n"
      "          {\n"
      "            \"identity\": \"Email:spencer.kimball@emailscrubbed.com\",\n"
      "            \"authority\": \"Viewfinder\"\n"
      "          },\n"
      "          {\n"
      "            \"identity\": \"Phone:6464174337\",\n"
      "            \"authority\": \"Viewfinder\"\n"
      "          },\n"
      "          {\n"
      "            \"identity\": \"FacebookGraph:602450\",\n"
      "            \"authority\": \"Facebook\"\n"
      "          },\n"
      "          {\n"
      "            \"identity\": \"Email:foo@aol.com\"\n"
      "          }\n"
      "        ],\n"
      "        \"subscriptions\" : [\n"
      "          {\n"
      "            \"transaction_id\": \"itunes:1234\",\n"
      "            \"subscription_id\": \"itunes:2345\",\n"
      "            \"timestamp\": 123456789,\n"
      "            \"expiration_ts\": 124000000,\n"
      "            \"product_type\": \"vf_plus\",\n"
      "            \"quantity\": 1,\n"
      "            \"payment_type\": \"itunes\"\n"
      "          },\n"
      "          {\n"
      "            \"transaction_id\": \"itunes:4567\"\n"
      "          }\n"
      "        ],\n"
      "        \"account_settings\" : {\n"
      "          \"email_alerts\" : \"on_share_new\",\n"
      "          \"storage_options\" : [\n"
      "            \"use_cloud\",\n"
      "            \"store_originals\"\n"
      "          ]\n"
      "        },\n"
      "        \"no_password\" : true\n"
      "      }\n"
      "    },\n"
      "    {\n"
      "      \"user_id\" : 15,\n"
      "      \"name\" : \"Kat Mattis\",\n"
      "      \"nickname\" : \"Honey Boo Boo\"\n"
      "    },\n"
      "    {\n"
      "      \"user_id\" : 6,\n"
      "      \"name\" : \"Brett Eisenman\",\n"
      "      \"family_name\" : \"Eisenman\",\n"
      "      \"labels\" : [\n"
      "        \"registered\",\n"
      "        \"friend\"\n"
      "      ]\n"
      "    },\n"
      "    {\n"
      "      \"user_id\" : 9,\n"
      "      \"name\" : \"Harry Clarke\",\n"
      "      \"given_name\" : \"Harry\",\n"
      "      \"labels\" : [\n"
      "        \"terminated\",\n"
      "        \"registered\"\n"
      "      ]\n"
      "    },\n"
      "    {\n"
      "      \"user_id\" : 12\n"
      "    },\n"
      "    {\n"
      "      \"user_id\" : 13,\n"
      "      \"labels\" : [\n"
      "        \"registered\"\n"
      "      ]\n"
      "    },\n"
      "    {\n"
      "      \"user_id\" : 14,\n"
      "      \"labels\" : [\n"
      "        \"friend\"\n"
      "      ]\n"
      "    }\n"
      "  ],\n"
      "  \"headers\" : {\n"
      "    \"version\" : 3\n"
      "  }\n"
      "}\n";
  QueryUsersResponse r;
  ASSERT(ParseQueryUsersResponse(&r, kQueryUsersResponse));
  ASSERT_EQ(3, r.headers().version());
  ASSERT_EQ(7, r.user_size());
  ASSERT_EQ(2, r.user(0).contact().user_id());
  ASSERT_EQ("Peter Mattis", r.user(0).contact().name());

  ASSERT_EQ(5, r.user(0).contact().identities_size());
  ASSERT_EQ("Email:spencer@emailscrubbed.com", r.user(0).contact().identities(0).identity());
  ASSERT_EQ("Email:spencer.kimball@emailscrubbed.com", r.user(0).contact().identities(1).identity());
  ASSERT_EQ("Phone:6464174337", r.user(0).contact().identities(2).identity());
  ASSERT_EQ("FacebookGraph:602450", r.user(0).contact().identities(3).identity());
  ASSERT_EQ("Email:foo@aol.com", r.user(0).contact().identities(4).identity());

  ASSERT_EQ(2, r.user(0).subscriptions_size());
  const ServerSubscriptionMetadata& sub1 = r.user(0).subscriptions(0);
  ASSERT_EQ("itunes:1234", sub1.transaction_id());
  ASSERT_EQ("itunes:2345", sub1.subscription_id());
  ASSERT_EQ(123456789, sub1.timestamp());
  ASSERT_EQ(124000000, sub1.expiration_ts());
  ASSERT_EQ("vf_plus", sub1.product_type());
  ASSERT_EQ(1, sub1.quantity());
  ASSERT_EQ("itunes", sub1.payment_type());
  const ServerSubscriptionMetadata& sub2 = r.user(0).subscriptions(1);
  ASSERT_EQ("itunes:4567", sub2.transaction_id());

  ASSERT(r.user(0).has_account_settings());
  ASSERT_EQ("on_share_new", r.user(0).account_settings().email_alerts());
  ASSERT_EQ("use_cloud", r.user(0).account_settings().storage_options(0));
  ASSERT_EQ("store_originals", r.user(0).account_settings().storage_options(1));

  ASSERT(r.user(0).has_no_password());
  ASSERT(r.user(0).no_password());
  ASSERT(!r.user(0).contact().need_query_user());

  ASSERT_EQ(15, r.user(1).contact().user_id());
  ASSERT_EQ(0, r.user(1).contact().identities_size());
  ASSERT_EQ(0, r.user(1).subscriptions_size());
  ASSERT(!r.user(1).has_no_password());
  ASSERT_EQ("Kat Mattis", r.user(1).contact().name());
  ASSERT_EQ("Honey Boo Boo", r.user(1).contact().nickname());
  ASSERT(!r.user(1).contact().has_label_registered());
  ASSERT(!r.user(1).contact().has_label_terminated());
  ASSERT(r.user(1).contact().need_query_user());
  ASSERT_EQ(6, r.user(2).contact().user_id());
  ASSERT_EQ("Brett Eisenman", r.user(2).contact().name());
  ASSERT_EQ("Eisenman", r.user(2).contact().last_name());
  ASSERT(r.user(2).contact().label_registered());
  ASSERT(!r.user(2).contact().label_terminated());
  ASSERT(r.user(2).contact().label_friend());
  ASSERT(!r.user(2).contact().need_query_user());
  ASSERT_EQ(9, r.user(3).contact().user_id());
  ASSERT_EQ("Harry Clarke", r.user(3).contact().name());
  ASSERT_EQ("Harry", r.user(3).contact().first_name());
  ASSERT(r.user(3).contact().label_registered());
  ASSERT(r.user(3).contact().label_terminated());
  ASSERT(r.user(3).contact().need_query_user());

  EXPECT_EQ(r.user(4).contact().user_id(), 12);
  EXPECT(r.user(4).contact().need_query_user());

  EXPECT_EQ(r.user(5).contact().user_id(), 13);
  EXPECT(r.user(5).contact().label_registered());
  EXPECT(!r.user(5).contact().label_friend());
  EXPECT(r.user(5).contact().need_query_user());

  EXPECT_EQ(r.user(6).contact().user_id(), 14);
  EXPECT(r.user(6).contact().label_friend());
  EXPECT(!r.user(6).contact().label_registered());
  EXPECT(r.user(6).contact().need_query_user());
}

TEST(ServerUtilsTest, ParseQueryViewpointsResponse) {
  const string kQueryViewpointsResponse =
      "{\n"
      "  \"viewpoints\" : [\n"
      "    {\n"
      "      \"viewpoint_id\" : \"v-7-v\",\n"
      "      \"type\" : \"event\",\n"
      "      \"user_id\" : 2,\n"
      "      \"cover_photo\" : {\n"
      "        \"photo_id\" : \"p1\",\n"
      "        \"episode_id\" : \"e1\"\n"
      "      },\n"
      "      \"labels\" : [\n"
      "        \"admin\",\n"
      "        \"contribute\",\n"
      "        \"autosave\",\n"
      "        \"hidden\",\n"
      "        \"muted\"\n"
      "      ],\n"
      "      \"episode_last_key\" : \"ejPYwHk29Dk\",\n"
      "      \"episodes\" : [\n"
      "        {\n"
      "          \"viewpoint_id\" : \"v-7-v\",\n"
      "          \"episode_id\" : \"ejPYwHk29Dk\",\n"
      "          \"parent_ep_id\" : \"ezzzDk\",\n"
      "          \"user_id\" : 2,\n"
      "          \"timestamp\" : 1112998836,\n"
      "          \"publish_timestamp\" : 1112998837\n"
      "        }\n"
      "      ],\n"
      "      \"comment_last_key\" : \"c2\",\n"
      "      \"comments\" : [\n"
      "        {\n"
      "          \"viewpoint_id\" : \"v-7-v\",\n"
      "          \"comment_id\" : \"c1\",\n"
      "          \"user_id\" : 2,\n"
      "          \"asset_id\" : \"p1\",\n"
      "          \"timestamp\" : 1112998836,\n"
      "          \"message\" : \"1st comment\"\n"
      "        },\n"
      "        {\n"
      "          \"viewpoint_id\" : \"v-7-v\",\n"
      "          \"comment_id\" : \"c2\",\n"
      "          \"user_id\" : 3,\n"
      "          \"asset_id\" : \"c1\",\n"
      "          \"timestamp\" : 1112998856,\n"
      "          \"message\" : \"2nd comment\"\n"
      "        }\n"
      "      ],\n"
      "      \"follower_last_key\" : \"15\",\n"
      "      \"followers\" : [\n"
      "        {\n"
      "          \"follower_id\" : 2\n"
      "        },\n"
      "        {\n"
      "          \"follower_id\" : 15,\n"
      "          \"labels\" : [\n"
      "            \"removed\",\n"
      "            \"unrevivable\"\n"
      "          ]\n"
      "        }\n"
      "      ]\n"
      "    },\n"
      "    {\n"
      "      \"viewpoint_id\" : \"v-73v\",\n"
      "      \"type\" : \"event\",\n"
      "      \"user_id\" : 3,\n"
      "      \"labels\" : [\n"
      "        \"admin\",\n"
      "        \"contribute\"\n"
      "      ],\n"
      "      \"episode_last_key\" : \"ega-kPF2ADk\",\n"
      "      \"episodes\" : [\n"
      "        {\n"
      "          \"user_id\" : 2,\n"
      "          \"viewpoint_id\" : \"v-73v\",\n"
      "          \"episode_id\" : \"ega-kPF2ADk\",\n"
      "          \"timestamp\" : 1302318998,\n"
      "          \"location\" : {\n"
      "            \"longitude\" : -73.9945,\n"
      "            \"latitude\" : 40.72783333333334,\n"
      "            \"accuracy\" : 0\n"
      "          },\n"
      "          \"publish_timestamp\" : 1302318999,\n"
      "          \"placemark\" : {\n"
      "            \"iso_country_code\" : \"US\",\n"
      "            \"locality\" : \"New York City\",\n"
      "            \"state\" : \"New York\",\n"
      "            \"subthoroughfare\" : \"684\",\n"
      "            \"country\" : \"United States\",\n"
      "            \"sublocality\" : \"Downtown\",\n"
      "            \"thoroughfare\" : \"Broadway\"\n"
      "          }\n"
      "        }\n"
      "      ],\n"
      "      \"activity_last_key\" : \"a2\",\n"
      "      \"activities\" : [\n"
      "        {\n"
      "          \"viewpoint_id\" : \"v1\",\n"
      "          \"activity_id\" : \"a1\",\n"
      "          \"user_id\" : 1,\n"
      "          \"timestamp\" : 1.0,\n"
      "          \"share_existing\" : {\n"
      "            \"episodes\" : [\n"
      "              {\n"
      "                \"episode_id\" : \"eg01\",\n"
      "                \"photo_ids\" : [\n"
      "                  \"pg03\",\n"
      "                  \"pg04\"\n"
      "                ]\n"
      "              }\n"
      "            ]\n"
      "          }\n"
      "        },\n"
      "        {\n"
      "          \"viewpoint_id\": \"v1\",\n"
      "          \"activity_id\": \"a2\",\n"
      "          \"user_id\" : 2,\n"
      "          \"timestamp\" : 2.0,\n"
      "          \"merge_accounts\": {\n"
      "            \"target_user_id\": 2,\n"
      "            \"source_user_id\": 3\n"
      "          }\n"
      "        }\n"
      "      ]\n"
      "    }\n"
      "  ],\n"
      "  \"headers\" : {\n"
      "    \"version\" : 3\n"
      "  }\n"
      "}\n";

  QueryViewpointsResponse r;
  ASSERT(ParseQueryViewpointsResponse(
             &r, NULL, 0, kQueryViewpointsResponse));
  ASSERT_EQ(3, r.headers().version());
  ASSERT_EQ(2, r.viewpoints_size());
  ASSERT_EQ("v-7-v", r.viewpoints(0).metadata().id().server_id());
  ASSERT_EQ("ejPYwHk29Dk", r.viewpoints(0).episode_last_key());
  ASSERT_EQ("event", r.viewpoints(0).metadata().type());
  ASSERT_EQ(2, r.viewpoints(0).metadata().user_id());
  ASSERT(r.viewpoints(0).metadata().has_cover_photo());
  ASSERT_EQ("p1", r.viewpoints(0).metadata().cover_photo().photo_id().server_id());
  ASSERT_EQ("e1", r.viewpoints(0).metadata().cover_photo().episode_id().server_id());
  ASSERT(r.viewpoints(0).metadata().label_admin());
  ASSERT(r.viewpoints(0).metadata().label_contribute());
  ASSERT(r.viewpoints(0).metadata().label_autosave());
  ASSERT(r.viewpoints(0).metadata().label_hidden());
  ASSERT(r.viewpoints(0).metadata().label_muted());
  ASSERT_EQ(1, r.viewpoints(0).episodes_size());
  ASSERT_EQ("v-7-v", r.viewpoints(0).episodes(0).viewpoint_id().server_id());
  ASSERT_EQ("ejPYwHk29Dk", r.viewpoints(0).episodes(0).id().server_id());
  ASSERT_EQ("ezzzDk", r.viewpoints(0).episodes(0).parent_id().server_id());
  ASSERT_EQ(1112998836, r.viewpoints(0).episodes(0).timestamp());
  ASSERT_EQ(1112998837, r.viewpoints(0).episodes(0).publish_timestamp());

  ASSERT_EQ("c2", r.viewpoints(0).comment_last_key());
  ASSERT_EQ(2, r.viewpoints(0).comments_size());
  ASSERT_EQ("v-7-v", r.viewpoints(0).comments(0).viewpoint_id().server_id());
  ASSERT_EQ("c1", r.viewpoints(0).comments(0).comment_id().server_id());
  ASSERT_EQ(2, r.viewpoints(0).comments(0).user_id());
  ASSERT_EQ("p1", r.viewpoints(0).comments(0).asset_id());
  ASSERT_EQ(1112998836, r.viewpoints(0).comments(0).timestamp());
  ASSERT_EQ("1st comment", r.viewpoints(0).comments(0).message());
  ASSERT_EQ("v-7-v", r.viewpoints(0).comments(1).viewpoint_id().server_id());
  ASSERT_EQ("c2", r.viewpoints(0).comments(1).comment_id().server_id());
  ASSERT_EQ(3, r.viewpoints(0).comments(1).user_id());
  ASSERT_EQ("c1", r.viewpoints(0).comments(1).asset_id());
  ASSERT_EQ(1112998856, r.viewpoints(0).comments(1).timestamp());
  ASSERT_EQ("2nd comment", r.viewpoints(0).comments(1).message());

  ASSERT_EQ("15", r.viewpoints(0).follower_last_key());
  ASSERT_EQ(2, r.viewpoints(0).followers_size());
  ASSERT_EQ(2, r.viewpoints(0).followers(0).follower_id());
  ASSERT(!r.viewpoints(0).followers(0).has_label_removed());
  ASSERT(!r.viewpoints(0).followers(0).has_label_unrevivable());
  ASSERT_EQ(15, r.viewpoints(0).followers(1).follower_id());
  ASSERT(r.viewpoints(0).followers(1).label_removed());
  ASSERT(r.viewpoints(0).followers(1).label_unrevivable());

  ASSERT_EQ("v-73v", r.viewpoints(1).metadata().id().server_id());
  ASSERT_EQ("ega-kPF2ADk", r.viewpoints(1).episode_last_key());
  ASSERT_EQ("event", r.viewpoints(1).metadata().type());
  ASSERT_EQ(3, r.viewpoints(1).metadata().user_id());
  ASSERT(!r.viewpoints(1).metadata().has_cover_photo());
  ASSERT(!r.viewpoints(1).metadata().label_autosave());
  ASSERT(!r.viewpoints(1).metadata().label_hidden());
  ASSERT(!r.viewpoints(1).metadata().label_muted());
  ASSERT_EQ(1, r.viewpoints(1).episodes_size());
  ASSERT_EQ("v-73v", r.viewpoints(1).episodes(0).viewpoint_id().server_id());
  ASSERT_EQ("ega-kPF2ADk", r.viewpoints(1).episodes(0).id().server_id());
  ASSERT_EQ(1302318998, r.viewpoints(1).episodes(0).timestamp());
  ASSERT_EQ(1302318999, r.viewpoints(1).episodes(0).publish_timestamp());

  ASSERT_EQ("a2", r.viewpoints(1).activity_last_key());
  ASSERT_EQ(2, r.viewpoints(1).activities_size());
  ASSERT_EQ("v1", r.viewpoints(1).activities(0).viewpoint_id().server_id());
  ASSERT_EQ("a1", r.viewpoints(1).activities(0).activity_id().server_id());
  ASSERT_EQ(1, r.viewpoints(1).activities(0).user_id());
  ASSERT_EQ(1.0, r.viewpoints(1).activities(0).timestamp());
  ASSERT(r.viewpoints(1).activities(0).has_share_existing());
  ASSERT_EQ(1, r.viewpoints(1).activities(0).share_existing().episodes_size());
  ASSERT_EQ("eg01", r.viewpoints(1).activities(0).share_existing().episodes(0).episode_id().server_id());
  ASSERT_EQ(2, r.viewpoints(1).activities(0).share_existing().episodes(0).photo_ids_size());
  ASSERT_EQ("pg03", r.viewpoints(1).activities(0).share_existing().episodes(0).photo_ids(0).server_id());
  ASSERT_EQ("pg04", r.viewpoints(1).activities(0).share_existing().episodes(0).photo_ids(1).server_id());
  ASSERT_EQ("v1", r.viewpoints(1).activities(1).viewpoint_id().server_id());
  ASSERT_EQ("a2", r.viewpoints(1).activities(1).activity_id().server_id());
  ASSERT_EQ(2, r.viewpoints(1).activities(1).user_id());
  ASSERT_EQ(2.0, r.viewpoints(1).activities(1).timestamp());
  ASSERT(r.viewpoints(1).activities(1).has_merge_accounts());
  ASSERT_EQ(2, r.viewpoints(1).activities(1).merge_accounts().target_user_id());
  ASSERT_EQ(3, r.viewpoints(1).activities(1).merge_accounts().source_user_id());
}

TEST(ServerUtilsTest, ParseResolveContactsResponse) {
  const string kResolveContactsResponse =
      "{\n"
      "  \"contacts\" : [\n"
      "    {\n"
      "      \"user_id\": 42,\n"
      "      \"identity\": \"ben@emailscrubbed.com\",\n"
      "      \"name\" : \"Ben Darnell\",\n"
      "      \"labels\": [ \"registered\" ]"
      "    }\n"
      "  ]\n"
      "}\n";

  ResolveContactsResponse r;
  ASSERT(ParseResolveContactsResponse(&r, kResolveContactsResponse));
  ASSERT_EQ(r.contacts_size(), 1);
  EXPECT_EQ(r.contacts(0).name(), "Ben Darnell");
  EXPECT_EQ(r.contacts(0).user_id(), 42);
  EXPECT_EQ(r.contacts(0).primary_identity(), "ben@emailscrubbed.com");
  EXPECT_EQ(r.contacts(0).identities_size(), 1);
  EXPECT_EQ(r.contacts(0).identities(0).identity(), "ben@emailscrubbed.com");
  EXPECT(r.contacts(0).label_registered());
  EXPECT(r.contacts(0).need_query_user());
}

}  // namespace

#endif  // TESTING

// local variables:
// mode: c++
// end:

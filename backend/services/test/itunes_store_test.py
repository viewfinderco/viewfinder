# Copyright 2012 Viewfinder Inc. All rights reserved.

__author__ = 'ben@emailscrubbed.com (Ben Darnell)'

import base64
import datetime
import functools
import json
import time

from tornado import options
from viewfinder.backend.base import base_options, secrets
from viewfinder.backend.base.testing import BaseTestCase, MockAsyncHTTPClient
from viewfinder.backend.services.itunes_store import ITunesStoreClient, ITunesStoreError

# Constants for expected values of various fields for our test data.
kProductId = 'vf_sub1_month'
kTransactionId = '1000000056588946'
kTransactionId2 = '1000000056589752'
kExpirationTime = 1349159462.502
kExpirationTime2 = 1349160962.000

# Sample receipt data for testing.  Note that while receipts are currently
# json, apple's docs warn that it is to be treated as an opaque blob,
# and decoded only by passing it to the store for verification.
# None of the tests care about this data, but it's here for reference.
# Verifying this data results in kVerifyResponseExpired.
kReceiptData = """\
{
    	"signature" = "Am7A11SyaJz20uV1wAKJmzmc2UH1lp3Wc4LJh7kdAUUH7jsEa3USs9XTw0G5jQuwPxcxI5+JcS2CxfUWGA0bnyUlQk0qrGhaNrCq3CRV89b9V0MNSyB6UBAko14wdfZQSXgirkdjJZhtcfJkTLwE/9bJv3DH2/FWNUZmfFkb5IMeAAADVzCCA1MwggI7oAMCAQICCGUUkU3ZWAS1MA0GCSqGSIb3DQEBBQUAMH8xCzAJBgNVBAYTAlVTMRMwEQYDVQQKDApBcHBsZSBJbmMuMSYwJAYDVQQLDB1BcHBsZSBDZXJ0aWZpY2F0aW9uIEF1dGhvcml0eTEzMDEGA1UEAwwqQXBwbGUgaVR1bmVzIFN0b3JlIENlcnRpZmljYXRpb24gQXV0aG9yaXR5MB4XDTA5MDYxNTIyMDU1NloXDTE0MDYxNDIyMDU1NlowZDEjMCEGA1UEAwwaUHVyY2hhc2VSZWNlaXB0Q2VydGlmaWNhdGUxGzAZBgNVBAsMEkFwcGxlIGlUdW5lcyBTdG9yZTETMBEGA1UECgwKQXBwbGUgSW5jLjELMAkGA1UEBhMCVVMwgZ8wDQYJKoZIhvcNAQEBBQADgY0AMIGJAoGBAMrRjF2ct4IrSdiTChaI0g8pwv/cmHs8p/RwV/rt/91XKVhNl4XIBimKjQQNfgHsDs6yju++DrKJE7uKsphMddKYfFE5rGXsAdBEjBwRIxexTevx3HLEFGAt1moKx509dhxtiIdDgJv2YaVs49B0uJvNdy6SMqNNLHsDLzDS9oZHAgMBAAGjcjBwMAwGA1UdEwEB/wQCMAAwHwYDVR0jBBgwFoAUNh3o4p2C0gEYtTJrDtdDC5FYQzowDgYDVR0PAQH/BAQDAgeAMB0GA1UdDgQWBBSpg4PyGUjFPhJXCBTMzaN+mV8k9TAQBgoqhkiG92NkBgUBBAIFADANBgkqhkiG9w0BAQUFAAOCAQEAEaSbPjtmN4C/IB3QEpK32RxacCDXdVXAeVReS5FaZxc+t88pQP93BiAxvdW/3eTSMGY5FbeAYL3etqP5gm8wrFojX0ikyVRStQ+/AQ0KEjtqB07kLs9QUe8czR8UGfdM1EumV/UgvDd4NwNYxLQMg4WTQfgkQQVy8GXZwVHgbE/UC6Y7053pGXBk51NPM3woxhd3gSRLvXj+loHsStcTEqe9pBDpmG5+sk4tw+GK3GMeEN5/+e1QT9np/Kl1nj+aBw7C0xsy0bFnaAd1cSS6xdory/CUvM6gtKsmnOOdqTesbp0bs8sn6Wqs0C9dgcxRHuOMZ2tm8npLUm7argOSzQ==";
    	"purchase-info" = "ewoJIm9yaWdpbmFsLXB1cmNoYXNlLWRhdGUtcHN0IiA9ICIyMDEyLTEwLTAxIDIzOjI2OjAzIEFtZXJpY2EvTG9zX0FuZ2VsZXMiOwoJInB1cmNoYXNlLWRhdGUtbXMiID0gIjEzNDkxNTkxNjI1MDIiOwoJInVuaXF1ZS1pZGVudGlmaWVyIiA9ICJiODRlYWFkMjVkZGMwODRmYWVjY2EwOWM0NGY3ZDYzYWRlN2E0NmEyIjsKCSJvcmlnaW5hbC10cmFuc2FjdGlvbi1pZCIgPSAiMTAwMDAwMDA1NjU4ODk0NiI7CgkiZXhwaXJlcy1kYXRlIiA9ICIxMzQ5MTU5NDYyNTAyIjsKCSJ0cmFuc2FjdGlvbi1pZCIgPSAiMTAwMDAwMDA1NjU4ODk0NiI7Cgkib3JpZ2luYWwtcHVyY2hhc2UtZGF0ZS1tcyIgPSAiMTM0OTE1OTE2MzMxMyI7Cgkid2ViLW9yZGVyLWxpbmUtaXRlbS1pZCIgPSAiMTAwMDAwMDAyNjI3MzMxNSI7CgkiYnZycyIgPSAiMyI7CgkiZXhwaXJlcy1kYXRlLWZvcm1hdHRlZC1wc3QiID0gIjIwMTItMTAtMDEgMjM6MzE6MDIgQW1lcmljYS9Mb3NfQW5nZWxlcyI7CgkiaXRlbS1pZCIgPSAiNTY0OTU5NTY2IjsKCSJleHBpcmVzLWRhdGUtZm9ybWF0dGVkIiA9ICIyMDEyLTEwLTAyIDA2OjMxOjAyIEV0Yy9HTVQiOwoJInByb2R1Y3QtaWQiID0gInRlc3Rfc3ViMV9tb250aCI7CgkicHVyY2hhc2UtZGF0ZSIgPSAiMjAxMi0xMC0wMiAwNjoyNjowMiBFdGMvR01UIjsKCSJvcmlnaW5hbC1wdXJjaGFzZS1kYXRlIiA9ICIyMDEyLTEwLTAyIDA2OjI2OjAzIEV0Yy9HTVQiOwoJImJpZCIgPSAiY28udmlld2ZpbmRlci5WaWV3ZmluZGVyIjsKCSJwdXJjaGFzZS1kYXRlLXBzdCIgPSAiMjAxMi0xMC0wMSAyMzoyNjowMiBBbWVyaWNhL0xvc19BbmdlbGVzIjsKCSJxdWFudGl0eSIgPSAiMSI7Cn0=";
    	"environment" = "Sandbox";
    	"pod" = "100";
    	"signing-status" = "0";
    }"""

# Sample responses from the server.
# A receipt which was valid, renewed at least once, then expired.
kVerifyResponseRenewedExpired = """\
{
  "status": 21006,
  "receipt": {
    "purchase_date_pst": "2012-10-01 23:26:02 America/Los_Angeles",
    "expires_date": "1349159462502",
    "product_id": "vf_sub1_month",
    "original_transaction_id": "1000000056588946",
    "unique_identifier": "b84eaad25ddc084faecca09c44f7d63ade7a46a2",
    "original_purchase_date_pst": "2012-10-01 23:26:03 America/Los_Angeles",
    "expires_date_formatted_pst": "2012-10-01 23:31:02 America/Los_Angeles",
    "original_purchase_date": "2012-10-02 06:26:03 Etc/GMT",
    "expires_date_formatted": "2012-10-02 06:31:02 Etc/GMT",
    "bvrs": "3",
    "original_purchase_date_ms": "1349159163313",
    "purchase_date": "2012-10-02 06:26:02 Etc/GMT",
    "web_order_line_item_id": "1000000026273315",
    "purchase_date_ms": "1349159162502",
    "item_id": "564959566",
    "bid": "co.viewfinder.Viewfinder",
    "transaction_id": "1000000056588946",
    "quantity": "1"
  },
  "latest_expired_receipt_info": {
    "purchase_date_pst": "2012-10-01 23:51:02 America/Los_Angeles",
    "expires_date": "1349160962000",
    "product_id": "vf_sub1_month",
    "original_transaction_id": "1000000056588946",
    "unique_identifier": "b84eaad25ddc084faecca09c44f7d63ade7a46a2",
    "original_purchase_date_pst": "2012-10-01 23:26:03 America/Los_Angeles",
    "expires_date_formatted_pst": "2012-10-01 23:56:02 America/Los_Angeles",
    "original_purchase_date": "2012-10-02 06:26:03 Etc/GMT",
    "expires_date_formatted": "2012-10-02 06:56:02 Etc/GMT",
    "bvrs": "3",
    "original_purchase_date_ms": "1349159163000",
    "purchase_date": "2012-10-02 06:51:02 Etc/GMT",
    "web_order_line_item_id": "1000000026273346",
    "purchase_date_ms": "1349160662000",
    "item_id": "564959566",
    "bid": "co.viewfinder.Viewfinder",
    "transaction_id": "1000000056589752",
    "quantity": "1"
  }
}
"""

# Construct several different responses using kVerifyResponseRenewedExpired
# as a reference.
def MakeRenewedExpiredResponse():
  """Returns a response for a subscription which expired after at least one
  renewal.
  """
  return kVerifyResponseRenewedExpired

def MakeNewResponse():
  """Returns a response for a subscription which has not been renewed
  or expired.  This is the expected case for subscriptions sent up by
  the client.
  """
  reference = json.loads(kVerifyResponseRenewedExpired)
  return json.dumps({'status': 0, 'receipt': reference['receipt']})

def MakeFreshResponse():
  """Returns a response for a subscription which has an expiration date in
  the future.  Note that the metadata here may be inconsistent, since only
  the expiration date is changed from an old receipt template.
  """
  reference = json.loads(kVerifyResponseRenewedExpired)
  new = {'status': 0, 'receipt': reference['receipt']}
  new['receipt']['expires_date'] = 1000.0 * (time.time() + datetime.timedelta(days=28).total_seconds())
  return json.dumps(new)

def MakeRenewedResponse():
  """Returns a response with an unexpired renewal."""
  reference = json.loads(kVerifyResponseRenewedExpired)
  return json.dumps({
      'status': 0,
      'receipt': reference['receipt'],
      'latest_receipt': base64.b64encode("fake encoded receipt"),
      'latest_expired_receipt_info': reference['latest_expired_receipt_info'],
      })

def MakeExpiredResponse():
  """Returns a response that expired without ever being renewed."""
  reference = json.loads(kVerifyResponseRenewedExpired)
  # just like the original, but no 'latest_expired_receipt_info'
  return json.dumps({'status': reference['status'], 'receipt': reference['receipt']})

def MakeBadSignatureResponse():
  """Returns a status code indicating an invalid signature."""
  return '{"status": 21003}'

def MakeServerErrorResponse():
  """Returns a status code indicating a (possibly transient) server error."""
  return '{"status": 21005}'

def MakeSandboxOnProdResponse():
  """Returns a status code indicating a sandbox receipt on the production
  iTunes server.
  """
  return '{"status": 21007}'

def MakeOtherAppResponse():
  """Make a response for a valid receipt from another app.

  iTunes just verifies that the receipt was issued by Apple; we need to
  verify that it came from our own app.
  """
  reference = json.loads(kVerifyResponseRenewedExpired)
  new = {'status': 0, 'receipt': reference['receipt']}
  new['receipt']['bid'] = 'com.angrybirds.AngryBirds'
  return json.dumps(new)

class ITunesStoreTest(BaseTestCase):
  def setUp(self):
    super(ITunesStoreTest, self).setUp()
    options.options.domain = 'goviewfinder.com'
    secrets.InitSecretsForTest()

  def VerifyReceipt(self, response, request):
    request_data = json.loads(request.body)
    self.assertEqual(sorted(request_data.keys()), ['password', 'receipt-data'])
    return response

  def GetResponse(self, raw_response):
    mock_http = MockAsyncHTTPClient()
    mock_http.map(r"https://.*\.itunes\.apple\.com/verifyReceipt",
                  functools.partial(self.VerifyReceipt, raw_response))
    client = ITunesStoreClient(http_client=mock_http)
    client.VerifyReceipt(kReceiptData, self.stop)
    response = self.wait()
    return response

  def test_verify_renewed_expired(self):
    response = self.GetResponse(MakeRenewedExpiredResponse())
    self.assertTrue(response.IsValid())
    self.assertEqual(response.GetProductId(), kProductId)
    # expiration time comes from the second receipt
    self.assertEqual(response.GetExpirationTime(), kExpirationTime2)
    self.assertTrue(response.IsExpired())
    self.assertFalse(response.IsRenewable())
    self.assertEqual(response.GetOriginalTransactionId(), kTransactionId)
    self.assertEqual(response.GetRenewalTransactionId(), kTransactionId2)

  def test_verify_new(self):
    response = self.GetResponse(MakeNewResponse())
    self.assertTrue(response.IsValid())
    self.assertEqual(response.GetProductId(), kProductId)
    self.assertEqual(response.GetExpirationTime(), kExpirationTime)
    self.assertTrue(response.IsRenewable())
    self.assertEqual(response.GetRenewalData(), kReceiptData)
    self.assertEqual(response.GetOriginalTransactionId(), kTransactionId)
    self.assertEqual(response.GetRenewalTransactionId(), kTransactionId)

  def test_verify_renewed(self):
    response = self.GetResponse(MakeRenewedResponse())
    self.assertTrue(response.IsValid())
    self.assertEqual(response.GetProductId(), kProductId)
    self.assertEqual(response.GetExpirationTime(), kExpirationTime2)
    self.assertTrue(response.IsRenewable())
    self.assertEqual(response.GetRenewalData(), "fake encoded receipt")
    self.assertEqual(response.GetOriginalTransactionId(), kTransactionId)
    self.assertEqual(response.GetRenewalTransactionId(), kTransactionId2)

  def test_verify_expired(self):
    response = self.GetResponse(MakeExpiredResponse())
    self.assertTrue(response.IsValid())
    self.assertEqual(response.GetProductId(), kProductId)
    self.assertEqual(response.GetExpirationTime(), kExpirationTime)
    self.assertTrue(response.IsExpired())
    self.assertFalse(response.IsRenewable())
    self.assertEqual(response.GetOriginalTransactionId(), kTransactionId)
    self.assertEqual(response.GetRenewalTransactionId(), kTransactionId)

  def test_verify_bad_signature(self):
    response = self.GetResponse(MakeBadSignatureResponse())
    self.assertFalse(response.IsValid())

  def test_verify_server_error(self):
    response = self.GetResponse(MakeServerErrorResponse())
    self.assertRaises(ITunesStoreError, response.IsValid)

  def test_verify_other_app(self):
    response = self.GetResponse(MakeOtherAppResponse())
    self.assertFalse(response.IsValid())

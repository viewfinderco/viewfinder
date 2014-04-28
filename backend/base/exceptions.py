# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Viewfinder exceptions.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

from viewfinder.backend.resources.message.error_messages import ErrorDef


class ViewfinderError(Exception):
  """Base class for viewfinder exceptions."""
  def __init__(self, error_def, **error_args):
    if isinstance(error_def, ErrorDef):
      self.id = error_def.id
      message = error_def.format % error_args
    else:
      assert isinstance(error_def, basestring)
      assert not error_args
      self.id = None
      message = error_def

    super(ViewfinderError, self).__init__(message)

class AdminAPIError(ViewfinderError):
  """Administration API failure."""
  pass

class IdentityUnreachableError(ViewfinderError):
  """Identity could not be contacted for invitation."""
  pass

class EmailError(ViewfinderError):
  """Failure to send email as specified."""
  pass

class SMSError(ViewfinderError):
  """Failure to send SMS as specified."""
  pass

class MigrationError(ViewfinderError):
  """Unable to upgrade database item."""
  pass

class HttpForbiddenError(ViewfinderError):
  """Errors derived from this will result in a 403 error being returned to the client.
  """

class PermissionError(HttpForbiddenError):
  """Permissions do not exist for intended action."""
  pass

class TooManyGuessesError(HttpForbiddenError):
  """Too many incorrect attempts have been made to guess a password or other secret."""
  pass

class ExpiredError(HttpForbiddenError):
  """The requested resource is no longer available because it has expired."""
  pass

class TooManyRetriesError(ViewfinderError):
  """An operation has retried too many times and is being aborted."""
  pass

class CannotReadEncryptedSecretError(ViewfinderError):
  """The secrets in the secrets directory require a passphrase for
  decryption.
  """
  pass

class TooManyOutstandingOpsError(ViewfinderError):
  """Too many operations are outstanding. This prevents the
  server running out of memory by enforcing flow control to
  requesting clients.
  """
  pass

class DBProvisioningExceededError(ViewfinderError):
  """The database limits on capacity units for a table were exceeded.
  The client should backoff and retry.
  """
  pass

class DBLimitExceededError(ViewfinderError):
  """The database limits on capacity units for a table were exceeded.
  The client should backoff and retry.
  """
  pass

class DBConditionalCheckFailedError(ViewfinderError):
  """The database cannot complete the request because a conditional
  check attached to the request failed.
  """
  pass

class InvalidRequestError(ViewfinderError):
  """The request contains disallowed or malformed fields or values. This
  error indicates a buggy or potentially malicious client.
  """
  pass

class NotFoundError(ViewfinderError):
  """The request references resources that cannot be found. This error indicates a buggy or
  malicious client.
  """
  pass

class CannotWaitError(ViewfinderError):
  """Cannot wait for the operation to complete, because another server
  is already running an operation for this user.
  """
  pass

class LockFailedError(ViewfinderError):
  """Cannot acquire lock because it has already been acquired by another
  agent.
  """
  pass

class FailpointError(ViewfinderError):
  """Operation failed due to a deliberately triggered failure (for testing purposes)."""
  def __init__(self, filename, lineno):
    super(FailpointError, self).__init__('Operation failpoint triggered.')
    self.filename = filename
    self.lineno = lineno

class ViewfinderConfigurationError(ViewfinderError):
  """There is something wrong with either server options and/or environmental
  configuration, such as viewfinder configuration stored in AWS metadata.
  """
  pass

class LimitExceededError(HttpForbiddenError):
  """Client request attempted some action which would have exceeded a limit.
  """
  pass

class ServiceUnavailableError(ViewfinderError):
  """The service is temporarily unavailable."""
  pass

class StopOperationError(ViewfinderError):
  """Stop the current operation in order to run a nested operation."""
  def __init__(self):
    super(StopOperationError, self).__init__('Current operation stopped.')

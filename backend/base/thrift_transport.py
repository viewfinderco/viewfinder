"""Non-blocking thrift (http://thrift.apache.com) transport.

This is an implementation of thrift's TTransportBase interface for use
with a Tornado web server. It uses an ioloop.IOLoop object for
processing async I/O, and greenlets for coroutine functionality used
to seamlessly jump the thread of execution from the blocking,
synchronous thrift call stack back out to the normal web application.
Callbacks registered with the IOLoop are invoked on thrift socket
activity, causing the paused greenlet to resume and continue
processing. When complete, the original greenlet will unwind its call
stack and return execution to the point where the original thrift call
was made.

This transport (indeed, any thrift transport) is not thread-safe.

Based on code in thrift/transport/TSocket.py and tornado/simple_httpclient.py
and on the explanation of marrying Tornado to Boto by Josh Haas:

http://blog.joshhaas.com/2011/06/marrying-boto-to-tornado-greenlets-bring-them-together/

  TTornadoTransport: asynchronous thrift client transport using IOLoop
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'


import functools
import greenlet
import logging
import socket
import time

from thrift.transport.TTransport import TTransportBase, TTransportException

from tornado import ioloop
from tornado.iostream import IOStream


def _wrap_transport(method):
  """Decorator to consistently check the underlying stream, setup the
  on-close callback, and create & remove a timeout expiration, if
  applicable.
  """
  @functools.wraps(method)
  def wrapper(self, *args, **kwargs):
    self._check_stream()
    self._stream.set_close_callback(functools.partial(
        self._on_close, gr=greenlet.getcurrent()))
    self._start_time = time.time()
    timeout = self._set_timeout()
    try:
      return method(self, *args, **kwargs)
    except TTransportException:
      self.close()
      raise
    finally:
      self._clear_timeout(timeout)
      if self._stream:
        self._stream.set_close_callback(functools.partial(
            self._on_close, gr=None))
  return wrapper


class TTornadoTransport(TTransportBase):
  """A non-blocking Thrift client.

  Example usage::

    import greenlet
    from tornado import ioloop
    from thrift.transport import TTransport
    from thrift.protocol import TBinaryProtocol

    from viewfinder.backend.thrift import TTornadoTransport

    transport = TTransport.TFramedTransport(TTornadoTransport('localhost', 9090))
    protocol = TBinaryProtocol.TBinaryProtocol(transport)
    client = Service.Client(protocol)
    ioloop.IOLoop.instance().start()

  Then, from within an asynchronous tornado request handler:

    class MyApp(tornado.web.RequestHandler):
      @tornado.web.asynchronous
      def post(self):
      def business_logic():
        ...any thrift calls...
        self.write(...stuff that gets returned to client...)
        self.finish() #end the asynchronous request
      gr = greenlet.greenlet(business_logic)
      gr.switch()
  """

  def __init__(self, host='localhost', port=9090):
    """Initialize a TTornadoTransport with a Tornado IOStream.

    @param host(str) The host to connect to.
    @param port(int) The (TCP) port to connect to.
    """
    self.host = host
    self.port = port
    self._stream = None
    self._io_loop = ioloop.IOLoop.current()
    self._timeout_secs = None

  def set_timeout(self, timeout_secs):
    """Sets a timeout for use with open/read/write operations."""
    self._timeout_secs = timeout_secs

  def isOpen(self):
    return self._stream is not None

  def open(self):
    """Creates a connection to host:port and spins up a tornado
    IOStream object to write requests and read responses from the
    thrift server. After making the asynchronous connect call to
    _stream, the current greenlet yields control back to the parent
    greenlet (presumably the "master" greenlet).
    """
    assert greenlet.getcurrent().parent is not None
    # TODO(spencer): allow ipv6? (af = socket.AF_UNSPEC)
    addrinfo = socket.getaddrinfo(self.host, self.port, socket.AF_INET,
                                  socket.SOCK_STREAM, 0, 0)
    af, socktype, proto, canonname, sockaddr = addrinfo[0]
    self._stream = IOStream(socket.socket(af, socktype, proto),
                            io_loop=self._io_loop)
    self._open_internal(sockaddr)

  def close(self):
    if self._stream:
      self._stream.set_close_callback(None)
      self._stream.close()
      self._stream = None

  @_wrap_transport
  def read(self, sz):
    logging.debug("reading %d bytes from %s:%d" % (sz, self.host, self.port))
    cur_gr = greenlet.getcurrent()
    def _on_read(buf):
      if self._stream:
        cur_gr.switch(buf)
    self._stream.read_bytes(sz, _on_read)
    buf = cur_gr.parent.switch()
    if len(buf) == 0:
      raise TTransportException(type=TTransportException.END_OF_FILE,
                                message='TTornadoTransport read 0 bytes')
    logging.debug("read %d bytes in %.2fms" %
                  (len(buf), (time.time() - self._start_time) * 1000))
    return buf

  @_wrap_transport
  def write(self, buf):
    logging.debug("writing %d bytes to %s:%d" % (len(buf), self.host, self.port))
    cur_gr = greenlet.getcurrent()
    def _on_write():
      if self._stream:
        cur_gr.switch()
    self._stream.write(buf, _on_write)
    cur_gr.parent.switch()
    logging.debug("wrote %d bytes in %.2fms" %
                  (len(buf), (time.time() - self._start_time) * 1000))

  @_wrap_transport
  def flush(self):
    pass

  @_wrap_transport
  def _open_internal(self, sockaddr):
    logging.debug("opening connection to %s:%d" % (self.host, self.port))
    cur_gr = greenlet.getcurrent()
    def _on_connect():
      if self._stream:
        cur_gr.switch()
    self._stream.connect(sockaddr, _on_connect)
    cur_gr.parent.switch()
    logging.info("opened connection to %s:%d" % (self.host, self.port))

  def _check_stream(self):
    if not self._stream:
      raise TTransportException(
        type=TTransportException.NOT_OPEN, message='transport not open')

  def _set_timeout(self):
    if self._timeout_secs:
      return self._io_loop.add_timeout(
        time.time() + self._timeout_secs, functools.partial(
          self._on_timeout, gr=greenlet.getcurrent()))
    return None

  def _clear_timeout(self, timeout):
    if timeout:
      self._io_loop.remove_timeout(timeout)

  def _on_timeout(self, gr):
    gr.throw(TTransportException(
        type=TTransportException.TIMED_OUT,
        message="connection timed out to %s:%d" % (self.host, self.port)))

  def _on_close(self, gr):
    self._stream = None
    message = "connection to %s:%d closed" % (self.host, self.port)
    if gr:
      gr.throw(TTransportException(
          type=TTransportException.NOT_OPEN, message=message))
    else:
      logging.error(message)

import logging
import os
import subprocess

def exec_cmd(cmd):
  logging.info("%s", ' '.join(cmd))

  try:
    p = subprocess.Popen(cmd, bufsize=-1,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    (out, err) = p.communicate()
  except Exception:
    logging.error("%s", err)
    raise
  if p.returncode:
    raise Exception('%s\n%s%s' % (' '.join(cmd), out, err))

def ensure_dir(dir):
  try:
    os.makedirs(dir)
  except:
    pass

def get_path(filename):
  return os.path.join(__path__[0], filename)

def get_stamp(source, gen_dir, ext):
  return os.path.join(gen_dir, os.path.splitext(source)[0] + ext)

def refresh(source, stamp, cmd):
  try:
    if os.path.getmtime(source) == os.path.getmtime(stamp):
      return
  except:
    pass

  try:
    exec_cmd(cmd)
    ensure_dir(os.path.dirname(stamp))
    open(stamp, 'a').close()  # ensure the stamp file exists
    os.utime(stamp, (os.path.getatime(source), os.path.getmtime(source)))
  except:
    logging.exception('unable to generate files')
    try:
      os.unlink(stamp)
    except:
      pass

def proto_gen_cmd(source, gen_type, gen_dir):
  ensure_dir(gen_dir)
  if gen_type == 'py':
    return ['protoc', source, '--python_out=%s' % os.path.dirname(source),
             '-I%s' % os.path.dirname(source)]

def proto_gen_py(source, gen_dir):
  stamp = get_path(get_stamp(source, gen_dir, '.py_stamp'))
  output_dir = os.path.join(gen_dir, os.path.dirname(source))
  source = get_path(source)
  refresh(source, stamp, proto_gen_cmd(source, 'py', output_dir))

def thrift_gen_cmd(source, gen_type, gen_dir):
  ensure_dir(gen_dir)
  return ['thrift', '-gen', gen_type, '-out', gen_dir, source]

def thrift_gen_py(source, gen_dir):
  stamp = get_path(get_stamp(source, gen_dir, '.py_stamp'))
  source = get_path(source)
  refresh(source, get_path(stamp),
          thrift_gen_cmd(source, 'py', get_path(gen_dir)))

def thrift_gen_js(source, gen_dir):
  stamp = get_path(get_stamp(source, gen_dir, '.js_stamp'))
  gen_dir = os.path.join(gen_dir, os.path.dirname(source))
  source = get_path(source)
  refresh(source, stamp,
          thrift_gen_cmd(source, 'js:jquery', get_path(gen_dir)))

# Automatically (re-)generate any thrift sources when the viewfinder module is
# first imported.
thrift_gen_dir = 'thrift_gen'
#thrift_gen_py('hbase/Hbase.thrift', thrift_gen_dir)
#thrift_gen_py('backend/www/operation.thrift', thrift_gen_dir)
#thrift_gen_js('backend/www/operation.thrift', thrift_gen_dir)

# Generate protocol buffer sources.
proto_gen_dir = 'proto_gen'
#proto_gen_py('backend/proto/server.proto', proto_gen_dir)


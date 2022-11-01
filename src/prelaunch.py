from __future__ import absolute_import
# Copyright 2011 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# The prelauncher's job is to delegate the quickopen commandline interface
# to an already "warmed-up" instance of quickopen launched by the quickopend.
#
# Importing python GUI libraries is actually quite slow. We want to give
# users of quickopen a nice snappy experience. So, the prelaunchd counterpart
# of this code keeps around a "warmed up" quickopen instance in the background.
#
# When a new quickopen comes around with a --use-prelaunch, it consults
# the daemon for prelaunched instance handle and then delegates its actual
# commandline to that instance (via magic).
from future import standard_library
standard_library.install_aliases()
from builtins import range
import os
import socket
import sys
import http.client
import time
import io

from .db_status import DBStatus

_is_prelaunched_process = False

def is_prelaunched_process():
  return _is_prelaunched_process

def wait_for_command(control_port):
  global _is_prelaunched_process
  _is_prelaunched_process = True

  s = socket.socket()
  try:
    bound = False
    for i in range(10):
      try:
        s.bind(("", control_port))
        bound = True
        break
      except socket.error:
        time.sleep(0.1)
    if not bound:
      raise Exception("could not bind!")

    s.listen(1)
    c, a = s.accept()
    f = c.makefile(mode="rw")

    # The commandline comes in as a repr'd array
    # Yes this is not very secure. Donations welcome.
    args = eval(f.readline(), {}, {})

    # We want to send the commandline args to quickopen's regular
    # main now, and redirect the stdout output over to the prelauncher.
    # We do this by overriding stdout to a StringIO. It works, though
    # we could technically do better.
    from . import quickopen
    import optparse
    old_stdout = sys.stdout
    new_stdout = io.StringIO()
    sys.stdout = new_stdout
    old_argv = sys.argv
    try:
      sys.argv = [sys.argv[0]]
      sys.argv.extend(args)
      parser = optparse.OptionParser(usage=quickopen.main_usage())
      quickopen.main(parser)
    except:
      sys.stdout = old_stdout
      import traceback
      traceback.print_exc()
    finally:
      sys.argv = old_argv
      sys.stdout = old_stdout

    # Finally, give the results back to the prelauncher so that
    # it can do its work. Pass the string via repr so we can use
    # a single readline command to do the heavy lifting for us. :)
    v = new_stdout.getvalue()
    f.write(repr(v))
    f.write("\n")
    f.close()
  finally:
    s.close()
    sys.exit(0)

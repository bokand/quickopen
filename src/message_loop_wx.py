from __future__ import print_function
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
import wx
import sys
import traceback
import unittest

_app = None
_current_main_loop_instance = 0
_wx_frame = None # keeps the message loop alive when there aren't any other frames :'(

_unittests_running = False
_active_test_result = None
_active_test = None
_quit_handlers = []

def init_main_loop():
  global _app
  if not _app:
    _app = wx.App(False)
    _app.SetAppName("QuickOpen")

    global _wx_frame
    _wx_frame = wx.Frame(None, -1, "KeepMainLoopAlive");

def post_task(cb, *args):
  init_main_loop()
  instance_at_post = _current_main_loop_instance
  def guarded():
    if _current_main_loop_instance != instance_at_post:
      return
    try:
      cb(*args)
    except Exception as e:
      if _active_test:
        exc_info = sys.exc_info()
        if isinstance(e, unittest.TestCase.failureException):
          _active_test_result.addFailure(_active_test, exc_info)
        else:
          if not str(e).startswith("_noprint"):
            print("Untrapped exception! Exiting message loop with exception.")
          _active_test_result.addError(_active_test, exc_info)
        quit_main_loop()
      else:
        traceback.print_exc()
  wx.CallAfter(guarded)

def post_delayed_task(cb, delay, *args):
  init_main_loop()
  main_loop_instance_at_post = _current_main_loop_instance
  def on_run():
    if _current_main_loop_instance == main_loop_instance_at_post:
      cb(*args)
  wx.CallLater(max(1, int(delay * 1000)), on_run)

def add_quit_handler(cb):
  _quit_handlers.insert(0, cb)

def set_unittests_running(running):
  global _unittests_running
  _unittests_running = running

def set_active_test(test, result):
  global _active_test
  global _active_test_result
  _active_test = test
  _active_test_result = result

def is_main_loop_running():
  if not _app:
    return False
  return _app.IsMainLoopRunning()

def run_main_loop():
  global _current_main_loop_instance
  if _unittests_running and not _active_test:
    _current_main_loop_instance += 1 # kill any enqueued tasks
    del _quit_handlers[:]
    raise Exception("UITestCase must be used for tests that use the message_loop.")

  global _app
  init_main_loop()

  assert not is_main_loop_running()

  try:
    _app.MainLoop()
  except:
    traceback.print_exc()
  finally:
    _current_main_loop_instance += 1

  _app.Destroy()
  _app = None

  global _quitting
  _quitting = False

_quitting = False
def quit_main_loop():
  global _current_main_loop_instance
  _current_main_loop_instance += 1
  global _quitting
  if _quitting:
    return
  _quitting = True

  def do_quit():
    global _wx_frame
    if _wx_frame:
      _wx_frame.Destroy()
      _wx_frame = None

    for cb in _quit_handlers:
      cb()
    del _quit_handlers[:]

    _app.ExitMainLoop()

  post_task(do_quit)

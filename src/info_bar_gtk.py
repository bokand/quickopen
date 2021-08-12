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
import gi
from gi.repository import Gtk, Gdk, Pango

from .event import *


class InfoBarGtk(Gtk.EventBox):
  """Represents a single horizontal bar of text, possibly with an
  icon, textual buttons, and a close button. Always visible."""
  def __init__(self, text = ""):
    Gtk.EventBox.__init__(self)
    self.modify_bg(Gtk.StateType.NORMAL, Gdk.color_parse("#FBE99C"))

    self._label = Gtk.Label()
    self._label.set_property('ellipsize', Pango.EllipsizeMode.END)
    self._label.set_text(text)
    self._label.set_tooltip_text(text)

    self._label.set_size_request(-1,36)

    self._hbox1 = Gtk.HBox()
    self._hbox2 = Gtk.HBox()
    self.add(self._hbox1)
    self._icon_bin = Gtk.Alignment()
    self._hbox1.pack_start(self._icon_bin, False, True, 5)
    self._hbox1.pack_start(self._label, True, True, 5)
    self._hbox1.pack_start(self._hbox2, False, True, 5)
    self._hbox1.show_all()

    self._has_close_button = False
    self._after_button_pressed = Event()

  def set_icon(self, image):
    if image == None:
      self._icon_bin.remove(Gtk._icon_bin.get_children()[0])
    else:
      image.set_valign(Gtk.Align.CENTER)
      self._icon_bin.add(image)

  def set_stock_icon(self, stock):
    if stock== None:
      self._icon_bin.remove(Gtk._icon_bin.get_children()[0])
    else:
      image = Gtk.Image.new_from_stock(stock, Gtk.IconSize.SMALL_TOOLBAR)
      image.set_valign(Gtk.Align.CENTER)
      self._icon_bin.add(image)

  def add_button(self, label, cb, *userdata):
    bn = Gtk.Button(label)
#    bn.set_property('relief', Gtk.RELIEF_NONE)
    bn.set_property('can-focus', False)
#    bn.modify_bg(Gtk.StateType.PRELIGHT, Gdk.color_parse("#E1D18C"))
#    bn.modify_bg(Gtk.StateType.NORMAL, Gdk.color_parse("#E1D18C"))
    self._hbox2.pack_start(self._mka(bn),False,False,2)
    def on_click(*args):
      cb(*userdata)
      self._after_button_pressed.fire()
    bn.connect('clicked', on_click)

  def add_close_button(self, cb = None, *userdata):
    assert self._has_close_button == False
    self._has_close_button = True
    bn = Gtk.Button()
    bn.set_property('relief', Gtk.ReliefStyle.NONE)
    bn.set_property('can-focus', False)
    bn.set_image(Gtk.Image.new_from_stock(Gtk.STOCK_CLOSE, Gtk.IconSize.SMALL_TOOLBAR))
    bn.modify_bg(Gtk.StateType.PRELIGHT, Gdk.color_parse("#E1D18C"))
    bn.modify_bg(Gtk.StateType.NORMAL, Gdk.color_parse("#E1D18C"))
    self._hbox1.pack_end(self._mka(bn),False,False,2)
    def on_click(*args):
      if cb:
        cb(*userdata)
      self._after_button_pressed.fire()
    bn.connect('clicked', on_click)

  @property
  def after_button_pressed(self):
    return self._after_button_pressed

  @property
  def has_close_button(self):
    return self._has_close_button

  @property
  def has_buttons(self):
    return len(self._hbox2.get_children()) != 0
  @property
  def text(self):
    return self._label.get_text()

  @text.setter
  def text(self, text):
    self._label.set_text(text)

  def _mka(self, bn):
    a = Gtk.Alignment(yalign=0.5)
    a.add(bn)
    return a


class _BSeparator(Gtk.EventBox):
  def __init__(self):
    Gtk.EventBox.__init__(self)
    self.modify_bg(Gtk.StateType.NORMAL, Gdk.color_parse("#FBE99C"))
    self.add(Gtk.HSeparator())

class InfoBarGtkCollection(Gtk.VBox):
  """A collection of butter bars"""
  def __init__(self):
    Gtk.VBox.__init__(self)
    self._num_bars = 0

  def has_bar(self, bar):
    return bar.get_parent() in self.get_children()

  def close_bar(self, bar):
    self.remove(bar.get_parent())
    self._num_bars -= 1

    if self._num_bars > 0:
      # remove the bsep from the topmost bar
      grp0 = self.get_children()[0]
      c0 = grp0.get_children()[0]
      if isinstance(c0, _BSeparator):
        grp0.remove(c0)

  def add_bar(self, bar):
    assert isinstance(bar,InfoBarGtk)
    if bar.has_close_button == False:
      bar.add_close_button(lambda: True)

    def close_bar():
      if bar.get_parent():
        self.close_bar(bar)

    bar.after_button_pressed.add_listener(close_bar)

    grp = Gtk.VBox()
    if self._num_bars >= 1:
      sep = _BSeparator()
      grp.pack_start(sep, True, True, 0)
    grp.pack_start(bar, True, True, 0)
    self.pack_start(grp, True, True, 0)
    grp.show_all()
    self._num_bars += 1

  def __len__(self):
    return self._num_bars
  def __getitem__(self,i):
    grp = self.get_children()[i]
    if isinstance(grp.get_children()[0], InfoBarGtk):
      return grp.get_children()[0]
    else:
      return grp.get_children()[1]

if __name__ == "__main__" and False:
  w = Gtk.Window()
  w.set_size_request(400,-1)
  b = InfoBarGtk()
  b.text = "blah blah blah"
  w.add(b)
  w.show_all()
  Gtk.main()

if __name__ == "__main__" and True:
  w = Gtk.Window()
  w.set_size_request(400,-1)
  bbc = InfoBarGtkCollection()

  # bb1
  bb = InfoBarGtk("blah blah blah")
  bbc.add_bar(bb)

  # bb1
  bb = InfoBarGtk("this is informational")
  bb.set_stock_icon(Gtk.STOCK_DIALOG_INFO)
  bbc.add_bar(bb)

  # bb1
  bb = InfoBarGtk("blah blah blah")
  bb.add_button("Accept", lambda: True)
  bbc.add_bar(bb)

  # bb1
  bb = InfoBarGtk("OMG you need to do somethnig")
  bb.set_stock_icon(Gtk.STOCK_DIALOG_WARNING)
  bb.add_button("Accept", lambda: True)
  bb.add_close_button(lambda: True)
  bbc.add_bar(bb)

  w.add(bbc)
  w.show_all()
  Gtk.main()

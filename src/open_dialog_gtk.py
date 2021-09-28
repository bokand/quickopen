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
from builtins import range
import gi
from gi.repository import Gdk
from gi.repository import Gtk
import time
import logging
import os

from .info_bar_gtk import *

from .open_dialog_base import OpenDialogBase

class OpenDialogGtk(Gtk.Dialog, OpenDialogBase):
  def __init__(self, options, db, initial_filter):
    Gtk.Dialog.__init__(self)
    OpenDialogBase.__init__(self, options, db, initial_filter)

    self.set_title("Quick open...")
    self.set_size_request(1000,400)
    self.add_button("_Open",Gtk.ResponseType.OK)
    self.add_button("Cancel",Gtk.ResponseType.CANCEL)

    model = Gtk.ListStore(object)

    treeview = Gtk.TreeView(model)
    treeview.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
    treeview.get_selection().connect('changed', self._on_treeview_selection_changed)

    self.connect('response', self.response)

    text_cell_renderer = Gtk.CellRendererText()

    def add_column(title,accessor_cb):
      column = Gtk.TreeViewColumn(title, text_cell_renderer)
      column.set_cell_data_func(text_cell_renderer, lambda column, cell, model, iter, data: cell.set_property('text', accessor_cb(model.get(iter,0)[0])))
      treeview.append_column(column)
      return column
    add_column("Rank",lambda obj: "{:.4}".format(obj[1]))
    add_column("File",lambda obj: os.path.basename(obj[0]))
    add_column("Path",lambda obj: os.path.dirname(obj[0]))

    self.connect('destroy', self.on_destroy)

    truncated_bar = InfoBarGtk()

    reindex_button = Gtk.Button("Reindex")
    reindex_button.connect('clicked', lambda *args: self.on_reindex_clicked())

    status_label = Gtk.Label()
    self.status_label = status_label

    filter_entry = Gtk.Entry()
    filter_entry.set_text(self._filter_text)

    filter_entry.connect('key_press_event', self._on_filter_entry_keypress)
    filter_entry.connect('changed', self._on_filter_text_changed)

    # attach everything up
    vbox = self.vbox
    table_vbox = Gtk.VBox()
    treeview_scroll_window = Gtk.ScrolledWindow()
    treeview_scroll_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    table_options_hbox = Gtk.HBox()
    button_hbox = Gtk.HBox()

    vbox.pack_start(table_vbox,True,True,1)
    table_vbox.pack_start(table_options_hbox,False,False,0)
    table_options_hbox.pack_start(status_label,False,False,10)
    table_options_hbox.pack_end(reindex_button,False,False,0)
    table_vbox.pack_start(treeview_scroll_window,True,True,0)
    table_vbox.pack_start(truncated_bar,False,True,0)
    table_vbox.pack_start(filter_entry,False,True,0)
    treeview_scroll_window.add(treeview)
    vbox.show_all()

    truncated_bar.hide()

    # remember things that need remembering
    self._treeview = treeview
    self._model = model
    self._truncated_bar = truncated_bar
    self._filter_entry = filter_entry

    filter_entry.grab_focus()
    if self.should_position_cursor_for_replace:
      filter_entry.set_position(0)
      filter_entry.select_region(0, len(self._filter_text))
    else:
      filter_entry.set_position(len(self._filter_text))

    self.show_all()

  def response(self, arg, *rest):
    canceled = len(rest) > 0 and rest[0] != Gtk.ResponseType.OK
    self.on_done(canceled)

  def on_destroy(self, *args):
    self.response(None, Gtk.ResponseType.CANCEL)

  def _on_filter_entry_keypress(self,entry,event):
    keyname = Gdk.keyval_name(event.keyval)

    if keyname in ("Up", "Down", "Page_Up", "Page_Down"):
      self.move_selection(keyname)
      return True
    elif keyname in ("Left", "Right"):
      self.scroll_tree_view(keyname)
      return True
    elif keyname == "space" and event.state & Gdk.ModifierType.CONTROL_MASK:
      self._treeview.get_selection().unselect_all()
      return True
    elif keyname == 'n' and event.state & Gdk.ModifierType.CONTROL_MASK:
      self.move_selection("Down")
      return True
    elif keyname == 'p' and event.state & Gdk.ModifierType.CONTROL_MASK:
      self.move_selection("Up")
      return True
    elif keyname == 'a' and event.state & Gdk.ModifierType.CONTROL_MASK:
      i = self._filter_entry.set_position(0)
      return True
    elif keyname == 'e' and event.state & Gdk.ModifierType.CONTROL_MASK:
      self._filter_entry.set_position(len(self._filter_entry.get_text()))
      return True
    elif keyname == 'f' and event.state & Gdk.ModifierType.CONTROL_MASK:
      i = self._filter_entry.get_position()
      i = min(i + 1, len(self._filter_entry.get_text()))
      self._filter_entry.set_position(i)
      return True
    elif keyname == 'b' and event.state & Gdk.ModifierType.CONTROL_MASK:
      i = self._filter_entry.get_position()
      if i >= 1:
        self._filter_entry.set_position(i - 1)
      return True
    elif keyname == 'k' and event.state & Gdk.ModifierType.CONTROL_MASK:
      i = self._filter_entry.get_position()
      t = self._filter_entry.get_text()[:i]
      self._filter_entry.set_text(t)
      self._filter_entry.set_position(len(t))
      return True
    elif keyname == 'Return':
      self.response(Gtk.ResponseType.OK)
      return True

  def _on_filter_text_changed(self,entry):
    text = entry.get_text()
    self.set_filter_text(text)

  def set_results_enabled(self, en):
    self._treeview.set_sensitive(en)
    self.set_response_sensitive(Gtk.ResponseType.OK, en)

  def status_changed(self):
    self.status_label.set_text(self.status_text)

  # update the model based on result
  def update_results_list(self, files, ranks):
    if len(files) == 0:
      self._model.clear()
      return

    start_time = time.time()
    self._treeview.freeze_child_notify()
    self._treeview.set_model(None)

    self._model.clear()

    for i in range(len(files)):
      row = self._model.append()
      self._model.set(row, 0, (files[i], float(ranks[i])))

    self._treeview.set_model(self._model)
    self._treeview.columns_autosize()
    self._treeview.thaw_child_notify()

    truncated = False
    if truncated:
      self._truncated_bar.text = "Search was truncated at %i items" % len(files)
      self._truncated_bar.show()
    else:
      self._truncated_bar.hide()

    elapsed = time.time() - start_time

    if len(self._model) > 0:
      if self._treeview.get_selection():
        self._treeview.get_selection().select_path((0,))

  def _on_treeview_selection_changed(self, selection):
    self.set_response_sensitive(Gtk.ResponseType.OK,selection.count_selected_rows() != 0)

  def scroll_tree_view(self, keyname):
    adjustment = self._treeview.get_hadjustment()
    increment = adjustment.get_step_increment()
    if keyname == "Left":
      increment = -increment
    elif not keyname == "Right":
      return
    adjustment.set_value(adjustment.get_value() + increment)

  def move_selection(self, keyname):
    selection = self._treeview.get_selection()
    selected_rows = selection.get_selected_rows()[1]
    visible_range = self._treeview.get_visible_range()

    if not selected_rows:
      if visible_range:
        selection.select_path(visible_range[0])
    else:
      page_size = (visible_range[1].get_indices()[0] -
                   visible_range[0].get_indices()[0])

      row = selected_rows[-1]
      selection.unselect_all()

      if keyname == "Up":
        row.prev()
      elif keyname == "Down":
        row.next()
      elif keyname == "Page_Up":
        for i in range(page_size):
          row.prev()
      elif keyname == "Page_Down":
        for i in range(page_size):
          row.next()

      selection.select_path(row)

      #Back up to the last row if we went past the end
      while not selection.path_is_selected(row):
        row.prev()
        selection.select_path(row)

      self._treeview.scroll_to_cell(row, None, False)

  def get_selected_indices(self):
    model,rows = self._treeview.get_selection().get_selected_rows()
    return [x[0] for x in rows]

  def set_selected_indices(self, indices):
    sel = self._treeview.get_selection()
    for i in self.get_selected_indices():
      sel.unselect_path((i,))
    for i in indices:
      sel.select_path((i,))

  def get_selected_items(self):
    model,rows = self._treeview.get_selection().get_selected_rows()

    files = []
    for path in rows:
      iter = model.get_iter(path)
      obj = model.get(iter,0)[0][0]
      files.append(obj)
    return files

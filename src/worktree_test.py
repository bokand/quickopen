# Copyright 2026 Google Inc.
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
from __future__ import absolute_import

import os
import shutil
import subprocess
import tempfile
import time
import unittest

from . import db_proxy
from .query import Query
from .query_result import QueryResult
from . import temporary_daemon
from . import worktree


def _make_file(path, content=""):
  os.makedirs(os.path.dirname(path), exist_ok=True)
  with open(path, "w") as f:
    f.write(content)


class WorktreeUnitTest(unittest.TestCase):
  def setUp(self):
    self.root = os.path.realpath(tempfile.mkdtemp(prefix="qo_wt_test_"))
    self.canonical_src = os.path.join(self.root, "chromium_base", "src")
    self.canonical_git = os.path.join(self.canonical_src, ".git")
    os.makedirs(os.path.join(self.canonical_git, "worktrees", "wt1"))

    self.wt_parent = os.path.join(self.root, "feature_wt")
    self.wt_src = os.path.join(self.wt_parent, "src")
    os.makedirs(os.path.join(self.wt_src, "chrome", "browser"))

  def tearDown(self):
    shutil.rmtree(self.root)

  def _setup_worktree(self, relative_commondir=True):
    wt_gitdir = os.path.join(self.canonical_git, "worktrees", "wt1")
    _make_file(os.path.join(self.wt_src, ".git"), "gitdir: %s\n" % wt_gitdir)
    commondir = "../.." if relative_commondir else self.canonical_git
    _make_file(os.path.join(wt_gitdir, "commondir"), commondir + "\n")

  def test_detects_worktree_relative_commondir(self):
    self._setup_worktree(relative_commondir=True)
    remapper = worktree.from_cwd(self.wt_src)
    self.assertIsNotNone(remapper)
    self.assertEqual(self.canonical_src, remapper.canonical_root)
    self.assertEqual(self.wt_src, remapper.local_root)

  def test_detects_worktree_absolute_commondir_from_subdir(self):
    self._setup_worktree(relative_commondir=False)
    subdir = os.path.join(self.wt_src, "chrome", "browser")
    remapper = worktree.from_cwd(subdir)
    self.assertIsNotNone(remapper)
    self.assertEqual(self.canonical_src, remapper.canonical_root)
    self.assertEqual(self.wt_src, remapper.local_root)

  def test_nested_subrepo_still_uses_outer_worktree(self):
    self._setup_worktree()
    v8_dir = os.path.join(self.wt_src, "v8")
    os.makedirs(os.path.join(v8_dir, ".git"))
    remapper = worktree.from_cwd(v8_dir)
    self.assertIsNotNone(remapper)
    self.assertEqual(self.wt_src, remapper.local_root)

  def test_ignores_git_submodule_without_commondir(self):
    submod_gitdir = os.path.join(self.canonical_git, "modules", "sub")
    os.makedirs(submod_gitdir)
    submod_dir = os.path.join(self.root, "standalone_repo", "sub")
    _make_file(os.path.join(submod_dir, ".git"), "gitdir: %s\n" % submod_gitdir)
    self.assertIsNone(worktree.from_cwd(submod_dir))

  def test_returns_none_for_canonical_or_non_git_dir(self):
    self._setup_worktree()
    self.assertIsNone(worktree.from_cwd(self.canonical_src))
    self.assertIsNone(worktree.from_cwd(self.root))

  def test_remap_query_and_result(self):
    self._setup_worktree()
    subdir = os.path.join(self.wt_src, "chrome")
    remapper = worktree.from_cwd(subdir)

    other_file = os.path.join(self.root, "config", "init.lua")
    orig_q = Query(
        "browser.cc",
        current_filename=os.path.join(self.wt_src, "chrome", "a.cc"),
        open_filenames=[os.path.join(self.wt_src, "base", "b.cc"), other_file],
        base_path=self.wt_parent,  # parent of 'src', as set by quickopen.vim
    )
    mapped_q = remapper.remap_query(orig_q)

    # Original query is not mutated.
    self.assertEqual(self.wt_parent, orig_q.base_path)

    self.assertEqual(
        os.path.join(self.canonical_src, "chrome", "a.cc"),
        mapped_q.current_filename)
    self.assertEqual(
        [os.path.join(self.canonical_src, "base", "b.cc"), other_file],
        mapped_q.open_filenames)
    self.assertEqual(self.canonical_src, mapped_q.base_path)

    # Subdirectory base_path inside worktree maps to matching canonical subdir.
    sub_q = remapper.remap_query(Query("x", base_path=subdir))
    self.assertEqual(os.path.join(self.canonical_src, "chrome"), sub_q.base_path)

    # Shared ancestor and unrelated base_path are left untouched.
    shared_q = remapper.remap_query(Query("x", base_path=self.root))
    self.assertEqual(self.root, shared_q.base_path)
    unrelated_q = remapper.remap_query(Query("x", base_path="/google"))
    self.assertEqual("/google", unrelated_q.base_path)

    # Results from canonical_src map to wt_src; other indexed dirs stay as-is.
    res = QueryResult(hits=[
        (os.path.join(self.canonical_src, "chrome", "browser.cc"), 5.0),
        (other_file, 4.0),
    ])
    remapper.remap_result(res)
    self.assertEqual([
        os.path.join(self.wt_src, "chrome", "browser.cc"),
        other_file,
    ], res.filenames)


class WorktreeIntegrationTest(unittest.TestCase):
  def setUp(self):
    self.root = os.path.realpath(tempfile.mkdtemp(prefix="qo_wt_int_"))
    self.canonical_src = os.path.join(self.root, "chromium_base", "src")
    self.canonical_git = os.path.join(self.canonical_src, ".git")
    wt_gitdir = os.path.join(self.canonical_git, "worktrees", "wt1")
    os.makedirs(wt_gitdir)

    _make_file(os.path.join(self.canonical_src, "chrome", "browser.cc"))
    _make_file(os.path.join(self.canonical_src, "chrome", "shared.h"))
    _make_file(os.path.join(self.canonical_src, "content", "shared.h"))

    self.other_dir = os.path.join(self.root, "config")
    _make_file(os.path.join(self.other_dir, "browser.cc"))

    self.wt_parent = os.path.join(self.root, "ios_worktree")
    self.wt_src = os.path.join(self.wt_parent, "src")
    os.makedirs(os.path.join(self.wt_src, "content"))
    _make_file(os.path.join(self.wt_src, ".git"), "gitdir: %s\n" % wt_gitdir)
    _make_file(os.path.join(wt_gitdir, "commondir"), self.canonical_git + "\n")

    self.daemon = temporary_daemon.TemporaryDaemon()
    self.quickopen_bin = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "quickopen"))

    # Index canonical subdirectories + unrelated config dir (mirrors real setup).
    self._run_qo(self.root, "add",
                 os.path.join(self.canonical_src, "chrome"),
                 os.path.join(self.canonical_src, "content"),
                 self.other_dir)
    self.daemon.db_proxy.sync()

  def tearDown(self):
    self.daemon.close()
    shutil.rmtree(self.root)

  def _run_qo(self, cwd, cmd, *args):
    full_args = [
        self.quickopen_bin,
        cmd,
        "--host=%s" % self.daemon.host,
        "--port=%s" % str(self.daemon.port),
        "--no_auto_start",
    ]
    full_args.extend(args)
    proc = subprocess.Popen(
        full_args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    self.assertEqual(b"", stderr)
    return [line for line in stdout.decode("utf-8").split("\n") if line]

  def test_worktree_search_remaps_and_filters_base_path(self):
    wt_subdir = os.path.join(self.wt_src, "content")

    # With --base-path set to wt_parent (like quickopen.vim), config/browser.cc
    # is filtered out and canonical chrome/browser.cc is returned under wt_src.
    hits = self._run_qo(
        wt_subdir, "rawsearch",
        "--base-path=%s" % self.wt_parent,
        "browser.cc")
    self.assertEqual([os.path.join(self.wt_src, "chrome", "browser.cc")], hits)

    # Exact match search (used by vim gf) also remaps to wt_src.
    exact_hits = self._run_qo(
        wt_subdir, "search",
        "--only-if-exact-match",
        "--base-path=%s" % self.wt_parent,
        "chrome/browser.cc")
    self.assertEqual([os.path.join(self.wt_src, "chrome", "browser.cc")], exact_hits)

  def test_worktree_current_filename_boosts_active_indexed_subdir(self):
    wt_subdir = os.path.join(self.wt_src, "content")
    hits = self._run_qo(
        wt_subdir, "rawsearch",
        "--base-path=%s" % self.wt_parent,
        "--current-filename=%s" % os.path.join(self.wt_src, "content", "foo.cc"),
        "shared.h")
    self.assertEqual([
        os.path.join(self.wt_src, "content", "shared.h"),
        os.path.join(self.wt_src, "chrome", "shared.h"),
    ], hits)

  def test_async_search_remaps_results(self):
    remapper = worktree.from_cwd(self.wt_src)
    proxy = db_proxy.DBProxy(self.daemon.host, self.daemon.port, remapper=remapper)
    async_search = proxy.search_async(Query("browser.cc", base_path=self.wt_parent))
    while not async_search.ready:
      time.sleep(0.02)
    self.assertEqual(
        [os.path.join(self.wt_src, "chrome", "browser.cc")],
        async_search.result.filenames)

  def test_non_worktree_dir_unaffected(self):
    hits = self._run_qo(
        self.other_dir, "rawsearch",
        "--base-path=%s" % self.other_dir,
        "browser.cc")
    self.assertEqual([os.path.join(self.other_dir, "browser.cc")], hits)

  def test_rmdir_deleted_directory(self):
    shutil.rmtree(self.other_dir)
    out = self._run_qo(self.root, "rmdir", self.other_dir)
    self.assertEqual(["%s removed" % self.other_dir], out)
    self.assertNotIn(self.other_dir, self._run_qo(self.root, "dirs"))


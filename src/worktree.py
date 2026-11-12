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

import copy
import os


class WorktreeRemapper(object):
  """Translates paths between a linked git worktree and its canonical repo."""

  def __init__(self, canonical_root, local_root, cwd=None):
    self.canonical_root = os.path.realpath(canonical_root).rstrip(os.sep)
    self.local_root = os.path.realpath(local_root).rstrip(os.sep)
    self.cwd = os.path.realpath(cwd) if cwd else None

  def _resolve(self, path):
    expanded = os.path.expandvars(os.path.expanduser(path))
    if self.cwd and not os.path.isabs(expanded):
      expanded = os.path.join(self.cwd, expanded)
    return os.path.realpath(expanded)

  def to_canonical(self, path):
    if not path:
      return path
    real_p = self._resolve(path)
    if real_p == self.local_root:
      return self.canonical_root
    if real_p.startswith(self.local_root + os.sep):
      return self.canonical_root + real_p[len(self.local_root):]
    return path

  def to_canonical_base_path(self, base_path):
    if not base_path:
      return base_path
    real_base = self._resolve(base_path).rstrip(os.sep)
    if real_base == self.local_root or real_base.startswith(self.local_root + os.sep):
      return self.canonical_root + real_base[len(self.local_root):]
    # quickopen.vim sets --base-path to the parent directory of 'src'
    # (e.g. .../btrfs_mount/<worktree>). If base_path is an ancestor of
    # local_root that does not already contain canonical_root, scope the
    # search to canonical_root.
    if (self.local_root.startswith(real_base + os.sep) and
        not self.canonical_root.startswith(real_base + os.sep)):
      return self.canonical_root
    return base_path

  def to_local(self, path):
    if not path:
      return path
    if path == self.canonical_root:
      return self.local_root
    if path.startswith(self.canonical_root + os.sep):
      return self.local_root + path[len(self.canonical_root):]
    return path

  def remap_query(self, query):
    remapped = copy.copy(query)
    if remapped.text and remapped.text.startswith(self.local_root + os.sep):
      remapped.text = self.canonical_root + remapped.text[len(self.local_root):]
    if remapped.current_filename:
      remapped.current_filename = self.to_canonical(remapped.current_filename)
    if remapped.open_filenames:
      remapped.open_filenames = [self.to_canonical(f) for f in remapped.open_filenames]
    if remapped.base_path:
      remapped.base_path = self.to_canonical_base_path(remapped.base_path)
    return remapped

  def remap_result(self, result):
    result._filenames = [self.to_local(f) for f in result.filenames]
    return result


def _parse_worktree_canonical_root(candidate_dir):
  dot_git = os.path.join(candidate_dir, '.git')
  try:
    if not os.path.isfile(dot_git):
      return None
    with open(dot_git, 'r') as f:
      first_line = f.readline().strip()
  except OSError:
    return None

  if not first_line.startswith('gitdir:'):
    return None

  raw_gitdir = first_line[len('gitdir:'):].strip()
  gitdir = os.path.normpath(os.path.join(candidate_dir, raw_gitdir))

  # Linked worktrees have a 'commondir' file pointing to the main .git dir
  # (unlike git submodules, which point into .git/modules/... without commondir).
  commondir_file = os.path.join(gitdir, 'commondir')
  try:
    if not os.path.isfile(commondir_file):
      return None
    with open(commondir_file, 'r') as f:
      raw_commondir = f.read().strip()
  except OSError:
    return None

  if not raw_commondir:
    return None

  common_git_dir = os.path.realpath(os.path.join(gitdir, raw_commondir))
  if os.path.basename(common_git_dir) != '.git' or not os.path.isdir(common_git_dir):
    return None

  return os.path.dirname(common_git_dir)


def from_cwd(cwd):
  """If cwd is inside a linked git worktree, returns a WorktreeRemapper."""
  if not cwd:
    return None
  try:
    real_cwd = os.path.realpath(os.path.expanduser(cwd))
  except OSError:
    return None

  # Walk ancestors outermost-first so nested sub-repos (e.g. src/v8) still
  # resolve to the enclosing top-level worktree (e.g. src).
  ancestors = []
  cur = real_cwd
  while True:
    ancestors.append(cur)
    parent = os.path.dirname(cur)
    if parent == cur:
      break
    cur = parent
  ancestors.reverse()

  for candidate in ancestors:
    canonical_root = _parse_worktree_canonical_root(candidate)
    if canonical_root:
      local_root = os.path.realpath(candidate)
      if canonical_root != local_root:
        return WorktreeRemapper(canonical_root, local_root, cwd=real_cwd)
  return None

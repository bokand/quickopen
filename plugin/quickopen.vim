" Copyright 2011 Google Inc.
"
" Licensed under the Apache License, Version 2.0 (the "License");
" you may not use this file except in compliance with the License.
" You may obtain a copy of the License at
"
"      http://www.apache.org/licenses/LICENSE-2.0
"
" Unless required by applicable law or agreed to in writing, software
" distributed under the License is distributed on an "AS IS" BASIS,
" WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
" See the License for the specific language governing permissions and
" limitations under the License.

if exists("loaded_quickopen")
  finish
endif
let loaded_quickopen = 1

let s:QuickOpenFile = resolve(expand("<sfile>"))
let s:QuickOpenDir = strpart(s:QuickOpenFile, 0, strridx(s:QuickOpenFile,"/plugin"))
let s:QuickOpenApp = s:QuickOpenDir . "/quickopen"

function! s:GetDefaultBasePath()
    let cwd = getcwd()

    let dirs = split(cwd, "/")
    let ix = index(dirs, "src")
    if ix < 0
      return ""
    endif

    return "/" . join(dirs[0:ix-1], "/")
endfunction

function! s:RunQuickOpen(args)
  let source_path = s:GetDefaultBasePath()
  let base_path_arg = ""
  if source_path != ""
    let base_path_arg = " --base-path=" . source_path
  endif

  let res = system(s:QuickOpenApp . " " . a:args . " --current-file=" . expand("%:p") . base_path_arg)
  if v:shell_error
    echohl ErrorMsg
    echo substitute(escape(res, "\""), "\n$", "", "g")
    echohl None
    return []
  endif
  return split(res, "\n", 0)
endfunction

function! s:OpenFileInTab(file)
  let fullpath = fnamemodify(a:file, ':p')
  for i in range(1, tabpagenr('$'))
    for buf in tabpagebuflist(i)
      if expand('#' . buf . ':p') == fullpath
        exe 'tabnext ' . i
        return
      endif
    endfor
  endfor
  " If the current tab has an empty unnamed buffer (e.g. on first run), reuse
  " it instead of opening a new tab.
  if bufname('%') == '' && line('$') == 1 && getline(1) == '' && !&modified
    exe 'edit ' . fnameescape(a:file)
  else
    exe 'tabedit ' . fnameescape(a:file)
  endif
endfunction

let s:TermCallback = {}
function! s:TermCallback.on_exit(id, code, event)
  exe "bdel!"
  call s:OpenFiles(s:ReadResults(self.resultsfile))
endfunction

function! s:ReadResults(resultsfile)
  let b = filereadable(a:resultsfile)
  if b
    let files = readfile(a:resultsfile)
    let b = delete(a:resultsfile)
  else
    let files = []
  endif
  return files
endfunction

function! s:QuickOpenPrompt(query)
  if has("gui_running")
    return s:RunQuickOpen("prelaunch search " . a:query)
  endif

  let resultsfile = tempname()

  exe "new __quickopen__"

  setlocal buftype=nofile
  setlocal bufhidden=hide
  setlocal noswapfile
  setlocal buflisted
  let source_path = s:GetDefaultBasePath()
  let base_path_arg = ""
  if source_path != ""
    let base_path_arg = " --base-path=" . source_path
  endif

  let quickOpenCmd = s:QuickOpenApp . " search --curses --results-file=" . resultsfile . " --current-file=" . expand("%:p") . base_path_arg . " " . a:query
  if !has("nvim")
    exec("silent! !" . l:quickOpenCmd)
    exe "bdel"
    exec(":redraw!")
    return s:ReadResults(resultsfile)
  endif

  setlocal statusline=quickopen
  setlocal nonumber
  let s:TermCallback.resultsfile = l:resultsfile
  call termopen(l:quickOpenCmd, copy(s:TermCallback))
  startinsert
  return []
endfunction

function! s:QuickOpenSingle(query)
  let res = s:RunQuickOpen("search --only-if-exact-match " . a:query)
  if empty(res) || res[0] == ""
    call QuickFind(a:query)
    return
  endif
  call s:OpenFileInTab(res[0])
endfunction

function! s:OpenFiles(files_to_open)
  for f in a:files_to_open
    if f != ""
      call s:OpenFileInTab(f)
    endif
  endfor
endfunction

function! QuickFind(query)
  let files_to_open = s:QuickOpenPrompt(a:query)
  call s:OpenFiles(l:files_to_open)
endfunction

com! -nargs=* O call QuickFind(<q-args>)

nnoremap <silent> gf :call <sid>QuickOpenSingle(expand('<cfile>'))<cr>
nnoremap <silent> <c-w>gf :call <sid>QuickOpenSingle(expand('<cfile>'))<cr>

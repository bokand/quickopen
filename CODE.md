# Quickopen Developer Guide

## What It Is

Quickopen is a fuzzy file search tool. You run a daemon that indexes directory trees, then query it from your editor (vim/emacs) or the command line to quickly open files by typing partial names. Results appear in a live-updating GUI (GTK, wxWidgets, or curses fallback).

---

## High-Level Architecture

The system is split into a **client** and a **background daemon** that communicate over HTTP on localhost.

```
┌─────────────────────────────────────────────┐
│  quickopen CLI (client)                     │
│  src/quickopen.py                           │
│                                             │
│  UI (GTK / curses / wx)                     │
│  src/open_dialog*.py + message_loop*.py     │
│            │                                │
│  DBProxy (HTTP client)                      │
│  src/db_proxy.py                            │
└────────────────┬────────────────────────────┘
                 │ HTTP (JSON)
┌────────────────▼────────────────────────────┐
│  quickopend daemon                          │
│  src/quickopend.py                          │
│            │                                │
│  Daemon (HTTP server + event loop)          │
│  src/daemon.py                              │
│            │                                │
│  DBStub (HTTP routes → DB)                  │
│  src/db_stub.py                             │
│            │                                │
│  DB (core: dirs, ignores, search)           │
│  src/db.py                                  │
│            │                                │
│  DBShardManager (multi-process search)      │
│  src/db_shard_manager.py                    │
│      │              │                       │
│  DBIndexShard   DBIndexShard  …             │
│  src/db_index_shard.py                      │
└─────────────────────────────────────────────┘
```

---

## Entry Points

### `src/bootstrap.py`
The real entry point for both executables. It parses `--main-name` (either `quickopen` or `quickopend`), sets up logging/verbosity, then calls `main()` in the named module.

### `src/quickopen.py` — client CLI
Sub-commands:
- `search` (default) — show the fuzzy search UI
- `rawsearch` — print results to stdout without UI
- `edit` — search then open selection in `$EDITOR`
- `add` / `dirs` / `rmdir` — manage indexed directories
- `ignore` / `ignores` / `unignore` — manage ignore patterns
- `status` / `reindex` / `prelaunch`

### `src/quickopend.py` — daemon
Sub-commands: `run` (default), `stop`, `status`, `restart`.

---

## The Daemon (`src/daemon.py`)

`Daemon` extends Python's `http.server.HTTPServer`. It runs a **custom event loop** (not `HTTPServer.serve_forever`) built on `select()`.

Key design points:
- Routes are registered as `(regex, handler)` pairs.
- All request/response bodies are JSON.
- A `heapq`-based priority queue provides delayed task scheduling (`add_delayed_task(cb, delay_secs)`).
- `/ping` and `/exit` are built-in routes.

---

## Database & Indexing

### `src/db.py` — core database
Holds the list of watched directories (`DBDir` objects) and ignore patterns. Persisted via `Settings`. Key methods:

- `add_dir(d)` / `delete_dir(d)` — manage directories
- `ignore(pat)` / `unignore(pat)` — manage ignore globs
- `step_indexer()` — called repeatedly by the daemon to advance indexing incrementally
- `search(*args)` — delegates to `Query.execute()`

Default ignores: `.*`, `*.o`, `*.obj`, `*.pyc`, `*.pyo`, `*.o.d`, `#*`

### `src/db_stub.py` — HTTP ↔ DB bridge
Registers HTTP routes on the daemon and calls through to `db.py`. Drives incremental indexing: when the DB signals it needs work, `db_stub` schedules `_index_a_bit_more()` via the daemon's delayed-task queue (every 250 ms).

### `src/db_indexer.py` — abstract indexer
Factory `Create()` returns either:
- **`FindBasedDBIndexer`** (`find_based_db_indexer.py`) — uses `find(1)` with non-blocking streaming via `select()`. Preferred.
- **`ListdirBasedDBIndexer`** (`listdir_based_db_indexer.py`) — pure Python fallback using `os.listdir`.

Both produce a `files_by_basename` dict and expose `complete` / `progress` properties.

### `src/db_shard_manager.py` — parallel search
Splits the basename index across 1–4 worker processes using `multiprocessing.Pool`. `search_basenames(query)` fans out to all shards and unions the results.

### `src/db_index_shard.py` — one search shard
Searches a chunk of basenames using four strategies in priority order:
1. **Exact match** — query exactly matches a basename
2. **Word-start match** — query letters match word/camelCase boundaries
3. **Substring match** — query is a substring
4. **Fuzzy match** — fallback, only used when nothing better found

Returns `(hits, truncated)`.

---

## Query & Ranking

### `src/query.py`
`Query` encapsulates: `text`, `max_hits`, `exact_match`, `current_filename`, `open_filenames`, `base_path`.

`execute()` flow:
1. Check `QueryCache` (256-entry LRU).
2. Split query on `/` → directory part + basename part.
3. Call `DBShardManager.search_basenames(basename_query)`.
4. For each hit, find matching full paths and filter by dir part.
5. Rank via `BasenameRanker`.
6. Apply global rank boost for currently-open files/directories.
7. Filter by `base_path` if set.

### `src/basename_ranker.py`
Scores a query against a basename (0.0–7.0, floored to 0.1). Rewards:
- **Word-start hits** (score 2.0 per letter) — letters matching after `_`, `-`, `.`, `/`, or uppercase boundaries in camelCase.
- **Consecutive runs** — longer consecutive matches score better.
- **Word hit percentage** — matching all words gives a 4x bonus.

Uses memoized recursion to try all order-preserving letter alignments and pick the best.

### `src/query_result.py`
Container: `filenames[]`, `ranks[]`, `truncated`. JSON-serialisable via `as_dict()` / `from_dict()`.

### `src/query_cache.py`
LRU cache keyed on `"query_text@max_hits"`.

---

## Client ↔ Daemon Communication

### `src/db_proxy.py`
Client-side mirror of `db_stub.py`. Speaks HTTP to the daemon. Key extras:
- Auto-starts the daemon if it isn't running.
- `search_async()` returns an `AsyncSearch` object that uses a non-blocking HTTP connection so the UI can poll without blocking.

### `src/async_http_connection.py`
Non-blocking HTTP client using `select()`. States: `IDLE → REQUEST_PENDING → SOCKET_READABLE → IDLE`.

---

## UI System

### `src/message_loop.py` — toolkit abstraction
Detects which GUI toolkit is available (GTK3 → wxWidgets → curses) and imports the right backend as the module-level interface. Provides:

- `post_task(cb)` — schedule callback immediately
- `post_delayed_task(cb, delay)` — schedule with delay
- `run_main_loop()` / `quit_main_loop()`
- `add_quit_handler(cb)`

Backends: `message_loop_gtk.py`, `message_loop_wx.py`, `message_loop_curses.py`.

The **curses backend** runs its own `select()`-based loop with a `heapq` for delayed tasks; it does not rely on any GUI library.

### `src/open_dialog.py` — dialog factory
Picks the right dialog class and calls `run(options, db, initial_filter, callback)`.

### `src/open_dialog_base.py` — base dialog logic
Framework-agnostic polling engine. A **tick** fires every:
- 5 ms while a search is in flight
- 25 ms when the index is up to date
- 200 ms when indexing is still running

Each tick: check if the async search finished → update results list; check if filter text changed → start a new async search.

Subclasses implement: `update_results_list()`, `get_selected_items()`, `frontend_status` (property).

### `src/open_dialog_gtk.py`
`Gtk.Dialog` with a `Gtk.TreeView` (columns: rank, basename, dirname). Keyboard shortcuts: `C-n/p` (move selection), `C-k` (clear), `Escape` (cancel).

### `src/open_dialog_curses.py`
Full-screen terminal UI. Layout: status line (top) → results list (middle) → query input (bottom). Supports readline-like editing and `?`/`^G` for help.

---

## Prelaunch System

GTK and wx have slow import times. The prelaunch system keeps warm quickopen processes ready so the UI appears instantly.

- **`src/prelaunchd.py`** — runs inside the daemon; maintains a pool of pre-warmed quickopen processes. Handles `GET /existing_quickopen/{display}`.
- **`src/prelaunch.py`** — runs inside each warm instance; listens on a Unix socket for a command, executes `quickopen.main()`, and returns output.
- **`src/prelaunch_client.py`** — client side; contacts the daemon to get a warm instance address, then sends args to it.

---

## Supporting Modules

| Module | Purpose |
|---|---|
| `src/settings.py` | Persistent key-value store (PSON format, `~/.quickopend`, mode 0600). Supports typed settings with change callbacks. |
| `src/event.py` | Simple observer: `add_listener`, `fire`, `fire_silent`. Pickle-safe. |
| `src/dir_cache.py` | Caches `os.listdir` results with mtime-based invalidation; applies ignore patterns. |
| `src/pson.py` | Python-object-notation serialiser. Uses `eval()` — not safe for untrusted input. |
| `src/fixed_size_dict.py` | LRU dict backing the query cache. |
| `src/local_pool.py` | Thread-pool wrapper used in the main process to avoid fork issues. |
| `src/db_status.py` | Simple status DTO: `is_up_to_date`, `has_index`, `status` string. |
| `src/db_exception.py` | Custom exception for DB-layer errors. |
| `src/silent_exception.py` | Exception subclass that suppresses daemon-level logging. |
| `src/info_bar_gtk.py` | GTK info bar shown when results are truncated. |
| `src/default_port.py` | The default TCP port constant for the daemon. |

---

## Testing

- `*_test.py` files alongside each module for unit tests.
- `src/ui_test_case.py` — base class for UI tests.
- `src/quickopen_test_base.py` — shared utilities for integration tests.
- `src/temporary_daemon.py` — spins up a real daemon for tests and tears it down.
- `src/test_runner.py` — discovers and runs all tests.
- The daemon accepts a `--test` flag that installs extra HTTP hooks for test control.

---

## Key Data Flow: Search

```
User types in the query box
        │
on_filter_text_changed() in open_dialog_gtk/curses
        │
open_dialog_base.on_tick() sees filter changed
        │
db.search_async(Query(...))          ← DBProxy HTTP POST /search
        │
daemon routes to DBStub.search()
        │
DB.search() → Query.execute()
        │
        ├─ cache hit? → return immediately
        │
        └─ cache miss:
              DBShardManager.search_basenames()
                 multiprocessing fan-out to DBIndexShard workers
              collect hits, find full paths, filter by dir
              BasenameRanker scores each result
              apply open-file rank boosts
              store in QueryCache
        │
AsyncSearch.result → QueryResult (JSON over HTTP)
        │
on_tick() calls update_results_list()
        │
UI redraws ranked file list
```

---

## Key Data Flow: Indexing

```
DB.add_dir(d) or begin_reindex()
        │
DB._set_dirty() → needs_indexing.fire()
        │
DBStub.on_db_needs_indexing()
        │
daemon.add_delayed_task(_index_a_bit_more, 0.05s)
        │
_index_a_bit_more():
    DB.step_indexer()
        │
        ├─ create DBIndexer (find-based or listdir-based)
        └─ call indexer.index_a_bit_more()
              streams output from `find` in 1000-line chunks
              populates files_by_basename dict
        │
    re-schedule at 0.25s until complete
        │
    when complete: build DBShardManager → searchable
```

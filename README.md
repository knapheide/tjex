# Tabular Json EXplorer

Navigate through complex json files by interactively building up a [jq](https://jqlang.org) filter.

![demo gif](demo/demo.gif)

## Usage

```shell
tjex example.json
```

If no file is given, `tjex` will try to read json from stdin.
You will start out in the table panel.
Use the arrow keys to navigate around the table and press `<return>` to descend into the currently selected cell.
The prompt at the bottom will update to show the current path.
Use `ESC` or `C-_` to undo prompt changes, i.e. to navigate back up the hierarchy.

`M-o` switches between the table panel and the jq prompt.
The prompt accepts any valid jq filters.
Changes are immediately reflected in the table panel.
When you are done, exit with `C-g`.

For a full list of hotkeys, look at the example configuration in `~/.config/tjex/config.toml` which is automatically generated upon first invocation of tjex.

## Installation

### Requirements

* [python](https://www.python.org) __≥3.12__
* [jq](https://jqlang.org) (or [jaq](https://github.com/01mf02/jaq), [gojq](https://github.com/itchyny/gojq))
* If [atuin](https://atuin.sh) is available, the current prompt can be appended to the history with `M-<return>`.

To use jaq or gojq, set `jq_command` in `~/.config/tjex/config.toml`.

### With pipx

```shell
pipx install tjex
```

or, to get the latest version directly from github:

```shell
pipx install git+https://github.com/knapheide/tjex.git
```

## Hotkeys

### Global
| Key | Function | Description |
| --- | --- | --- |
| `C-g` <br> `C-d` | quit |  |
| `M-o` <br> `C-o` | toggle_active | Toggle active panel between prompt and table |
| `C-_` <br> `ESC` | undo |  |
| `M-_` | redo |  |
| `M-\n` | add_to_history | Append tjex call with current command to shell's history |
| `g` <br> `\n` | reload | Re-run the current filter. |

### In Prompt
| Key | Function | Description |
| --- | --- | --- |
| `C-_` | undo |  |
| `M-_` | redo |  |
| `M-w` | copy | Copy current prompt to clipboard |
| `C-k` | kill_line | Delete everything to the right of the cursor |
| `KEY_DC` <br> `C-d` | delete_next_char |  |
| `M-KEY_DC` <br> `M-d` <br> `C-<delete>` | delete_next_word |  |
| `KEY_BACKSPACE` | delete_prev_char |  |
| `M-KEY_BACKSPACE` <br> `C-<backspace>` | delete_prev_word |  |
| `KEY_RIGHT` <br> `C-f` | forward_char |  |
| `M-KEY_RIGHT` <br> `C-<right>` <br> `M-<right>` <br> `M-f` | forward_word |  |
| `KEY_LEFT` <br> `C-b` | backward_char |  |
| `M-KEY_LEFT` <br> `C-<left>` <br> `M-<left>` <br> `M-b` | backward_word |  |
| `KEY_END` <br> `C-e` | end |  |
| `KEY_HOME` <br> `C-a` | home |  |
| `C-y` | yank |  |
| `M-y` | rotate |  |

### In Table
| Key | Function | Description |
| --- | --- | --- |
| `KEY_UP` <br> `p` <br> `C-p` | up |  |
| `KEY_DOWN` <br> `n` <br> `C-n` | down |  |
| `KEY_LEFT` <br> `b` <br> `C-b` | left |  |
| `KEY_RIGHT` <br> `f` <br> `C-f` | right |  |
| `M-<` | first_row | Jump to first row |
| `M->` | last_row | Jump to last row |
| `KEY_NPAGE` | next_page |  |
| `KEY_PPAGE` | prev_page |  |
| `KEY_END` <br> `C-e` | last_col | Jump to last column |
| `KEY_HOME` <br> `C-a` | first_col | Jump to first column |
| `l` | full_width | Toggle: rendering all cells with their full width vs. max_cell_width |
| `+` | inc_width | Increase max_cell_width by one |
| `-` | dec_width | Decrease max_cell_width by one |
| `M-w` | copy_content | Copy output of current command to clipboard |
| `\n` | enter_cell | Enter highlighted cell by appending selector to jq prompt |
| `M-\n` | enter_row | Enter highlighted cell's row by appending selector to jq prompt |
| `w` | copy_cell_content | Copy content of the current cell to clipboard. If content is a string, copy the plain value, not the json representation.  |
| `E` | expand_row | Expand the selected row |
| `e` | expand_col | Expand the selected column |
| `K` | delete_row | Delete the selected row |
| `k` | delete_col | Delete the selected column |
| `m` | select_col | Enter the selected column |
| `s` | sort_by_col | Sort rows by the selected column. Works only for arrays right now.  |

## Configuration

The default location for the configuration file is `~/.config/tjex/config.toml`.
An example configuration is automatically created when tjex is run for the first time.

### Key bindings

Key bindings can be customized as illustrated in the example configuration.

Key names are taken from the curses library's `keyname` function.
To find the name of a key, press it in tjex and watch the log output:

```shell
# In one terminal:
tjex --logfile=tjex.log []
# In another terminal:
tail -f tjex.log
# Now in the first terminal, press the desired key and look for a line of the form
# DEBUG:tjex:key='...'
```

## Alternatives

* [jless](https://github.com/PaulJuliusMartinez/jless)
  is a command-line json viewer that basically displays the indented and syntax-highlighted json file.
  To get a better overview of the structure, individual objects and arrays can be collapsed or expanded.
* [jnv](https://github.com/ynqa/jnv) provides an interactive jq prompt together with a jless-style viewer.
  However, the prompt is not updated when browsing through the viewer.
* [fx](https://fx.wtf/getting-started) has an interactive mode with a prompt.
  This prompt appears to be limited to path expressions and only influences the cursor position in the displayed json file.
* [nushell](https://www.nushell.sh)'s [explore](https://www.nushell.sh/book/explore.html) command displays data in a tabular form similar to tjex.
  It has a `:try` sub-command that provides a nushell prompt.

## TODO
* Separate persistent command history for TextEditPanel
* Multi-line cells
* Transpose `TablePanel` (without changing the underlying data)
* Configurable number formatting
  * More precision for small numbers
  * Hexadecimal integers
* Raw view
* Per-panel dirty flag
* Status message animation (for pending jq process)
* Nix flake
* Plain-text search in table
* Handle large data sets more gracefully.
  Getting unusably slow is fine, but tjex should never lock up or run out of memory.
  * Option to abort switch from prompt to table.
    Currently, tjex waits for the jq call to finish and there is no way to abort.
  * Option to toggle between global / local formatting
* `--watch` option to automatically re-run filter.
  Probably using [watchdog](https://github.com/gorakhargosh/watchdog).
* Cleaner way to get up-to-date config into subprocess

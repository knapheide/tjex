# Tabular Json EXplorer

Navigate through complex json files by interactively building up a [jq](https://jqlang.org) filter.

![demo image](doc/demo.png)

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
pipx install git+https://github.com/knapheide/tjex.git
```

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
* Mini history just for the table view
  * ESC to go one level up / return to the prompt
* Multi-line cells
* Kill ring for TextEditPanel
* Transpose `TablePanel` (without changing the underlying data)
* Configurable number formatting
  * More precision for small numbers
* Raw view
* Better demo picture / animation in README
* Per-panel dirty flag
* Status message animation (for pending jq process)
* Nix flake
* Plain-text search in table
* Publish to PyPI
* CI
* When applying transformations, try to keep the cursor position
* Improve performance / support larger data sets.
  The limiting factor should be the call to jq, not the python code.
  * Option to abort current `update` call
  * Toggle between global / local formatting
* `--watch` option to automatically re-run filter.
  Probably using [watchdog](https://github.com/gorakhargosh/watchdog).
* Variable status panel height.
  `jaq` error messages are rather big.

# Tabular Json EXplorer

Navigate through complex json files by interactively building up a [jq](https://jqlang.org) filter.

![demo image](doc/demo.png)

## Usage

```shell
tjex example.json
```

If no file is given, `tjex` will try to read json from stdin.
You will start out at the prompt at the bottom of the table.
Enter a `jq` filter and the table will immediately update to show its output.
Use `M-o` to switch to interactive navigation through the table.
Exit with `C-g`.

In the table view, you can navigate using the arrow keys and use `<return>` to descend into the currently selected cell.
Use `ESC` or `C-_` to undo prompt changes.

For a full list of hotkeys, look at the example configuration in `~/.config/tjex/config.toml` which is automatically generated upon first invocation of tjex.

## Installation

### Requirements

* [python](https://www.python.org) __≥3.12__
* [jq](https://jqlang.org) __≥1.7__
* If [atuin](https://atuin.sh) is available, the current prompt can be appended to the history with `M-<return>`.

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

## TODO
* Separate persistent command history for TextEditPanel
* Mini history just for the table view
  * ESC to go one level up / return to the prompt
* Multi-line cells
* Bunch of transformation hotkeys:
  * Delete row
  * Select column
  * Delete column
  * Expand dict into column
    * Can only do this if the parent is a dict as well
  * Sort by
* Kill ring for TextEditPanel
* Transpose `TablePanel` (without changing the underlying data)
* Configurable number formatting
* Raw view
* better demo picture / animation in README
* Per-panel dirty flag
* Status message animation (for pending jq process)
* Regression tests
* Should i specify a build system?
* nix flake
* Plain-text search in table

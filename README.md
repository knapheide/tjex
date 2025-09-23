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

## Installation

### Requirements

* [python](https://www.python.org) __≥3.12__
* [jq](https://jqlang.org) __≥1.7__
* If [atuin](https://atuin.sh) is available, the current prompt can be appended to the history with `M-<return>`.

### With pipx

```shell
pipx install git+https://github.com/knapheide/tjex.git
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
* Configurable history append command
* Test copy through screen / tmux etc. (probably wont work)
* Raw view
* Documentation
* Per-panel dirty flag
* Status message animation (for pending jq process)
* Regression tests
* Should i specify a build system?
* nix flake
* Hotkey to copy current cell
* Plain-text search in table
* Key binding aliases

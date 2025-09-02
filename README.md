# Tabular Json EXplorer

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
* Config file
  * key bindings
  * history append command
  * copy command
* Test copy through screen / tmux etc. (probably wont work)
* Raw view
* Documentation

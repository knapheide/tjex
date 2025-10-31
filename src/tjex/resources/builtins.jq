def is_iterable:
  type | in({"object":1, "array":1});

def expand($key; $prefix):
  if
    (($key | type) == "number" and type == "array")
    or (($key | type) == "string" and type == "object")
  then
    to_entries
    | map(if .key==$key and (.value | is_iterable)
          then (.value | to_entries | map(.key = "\($prefix).\(.key)"))
          else [.]
          end)
    | flatten(1)
    | map(.key = "\(.key)")
    | from_entries
  end;

def expand($key):
  expand($key; $key);

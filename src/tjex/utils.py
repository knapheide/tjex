from contextlib import ExitStack, contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile


class TjexError(Exception):
    def __init__(self, msg: str):
        super().__init__(msg)
        self.msg: str = msg


@contextmanager
def TmpFiles():
    with ExitStack() as stack:

        def tmpfile(s: str):
            buffered = stack.enter_context(
                NamedTemporaryFile(mode="w", delete_on_close=False, delete=True)
            )
            _ = buffered.write(s)
            buffered.close()
            return Path(buffered.name)

        yield tmpfile

class TjexError(Exception):
    def __init__(self, msg: str):
        super().__init__(msg)
        self.msg: str = msg

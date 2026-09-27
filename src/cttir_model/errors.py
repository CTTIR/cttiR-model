class ProjectError(Exception):
    """Expected failure, with a safe message that contains no input content."""

    def __init__(self, code: str, message: str, exit_code: int = 2):
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code

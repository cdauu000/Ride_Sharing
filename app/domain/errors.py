class DomainError(Exception):
    def __init__(self, code: str, message: str = "", status: int = 409) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.status = status

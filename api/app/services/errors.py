"""Errors that services raise. The interfaces map them to HTTP statuses and MCP tool errors."""


class ServiceError(Exception):
    """Base for the errors below. The message is safe to show to the caller."""


class NotFoundError(ServiceError):
    """The thing doesn't exist, or it belongs to another company (REST 404)."""


class StateError(ServiceError):
    """The quote is in a state that doesn't allow the action (REST 409)."""


class InvalidRequestError(ServiceError):
    """The arguments are well-formed but can't be used, e.g. an unknown diet tag (REST 422)."""


class InvalidLinesError(InvalidRequestError):
    """Quote lines with input errors (#106): no quote is made. `problems` holds
    (line_id, reason code) for each; the message names the field and the fix."""

    def __init__(self, message: str, problems: list[tuple[str, str]]) -> None:
        super().__init__(message)
        self.problems = problems

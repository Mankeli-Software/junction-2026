"""Errors that services raise. The interfaces map them to HTTP statuses and MCP tool errors."""


class ServiceError(Exception):
    """Base for the errors below. The message is safe to show to the caller."""


class NotFoundError(ServiceError):
    """The thing doesn't exist, or it belongs to another company (REST 404)."""


class StateError(ServiceError):
    """The quote is in a state that doesn't allow the action (REST 409)."""

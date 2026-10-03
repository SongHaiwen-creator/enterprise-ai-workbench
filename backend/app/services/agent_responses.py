from app.schemas.agent_routing import UnsupportedOutcome

UNSUPPORTED_MESSAGE = "This request is outside the configured Agent capabilities."


def unsupported_outcome() -> UnsupportedOutcome:
    return UnsupportedOutcome(status="unsupported", message=UNSUPPORTED_MESSAGE)

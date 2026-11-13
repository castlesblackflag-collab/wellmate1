"""Safety checks that run around the model, starting with the crisis screen."""

from safety.crisis import CrisisScreen


def get_crisis_screen() -> CrisisScreen | None:
    """The crisis screen Sage uses for every message.

    Returns None until the real screen is built (WS5). While it's None, /v1/chat refuses to
    run even if CHAT_ENABLED is true. That's deliberate: Sage doesn't talk to anyone without
    the screen in place. When the screen exists, return an instance of it here.
    """
    return None

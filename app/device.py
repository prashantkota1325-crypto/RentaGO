"""Request-device helpers for limited mobile participant access."""

import re


MOBILE_USER_AGENT = re.compile(
    r"android|iphone|ipad|ipod|mobile|tablet|windows phone|opera mini",
    re.IGNORECASE,
)


def is_mobile_request(request) -> bool:
    return bool(MOBILE_USER_AGENT.search(request.headers.get("user-agent", "")))

"""Constants for Config Export."""

import re

DOMAIN = "config_export"
SERVICE_MARKDOWN = "markdown"

SECTIONS = [
    "overview",
    "floors",
    "areas",
    "labels",
    "integrations",
    "devices",
    "entities",
    "automations",
    "scripts",
    "helpers",
    "dashboards",
]

# Storage-based helper collections, read read-only from .storage/<key>
HELPER_STORAGE_KEYS = [
    "input_boolean",
    "input_button",
    "input_datetime",
    "input_number",
    "input_select",
    "input_text",
    "counter",
    "timer",
    "schedule",
]

REDACTED = "**REDACTED**"
SECRET_KEY_RE = re.compile(
    r"(pass(word|wd)?|token|secret|api[_-]?key|apikey|auth|credential|"
    r"private|webhook_id|pin|client_id|client_secret)",
    re.IGNORECASE,
)

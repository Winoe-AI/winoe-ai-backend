from __future__ import annotations

from tests.unit.template_health_test_helpers import *

def test_decode_contents_base64_with_newlines():
    content = "workflow: test"
    encoded = base64.encodebytes(content.encode("utf-8")).decode("ascii")
    payload = {"content": encoded, "encoding": "base64"}
    assert _decode_contents(payload) == content

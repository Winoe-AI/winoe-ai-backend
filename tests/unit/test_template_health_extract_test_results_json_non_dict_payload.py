from __future__ import annotations

from tests.unit.template_health_test_helpers import *

def test_extract_test_results_json_non_dict_payload():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            f"{template_health.TEST_ARTIFACT_NAMESPACE}.json",
            "[]",
        )
    assert template_health._extract_test_results_json(buf.getvalue()) is None

from __future__ import annotations

from tests.unit.storage_media_extra_test_helpers import *

def test_s3_provider_get_object_metadata_404_returns_none(monkeypatch):
    provider = _build_s3_provider()

    def _raise_404(request, timeout):
        del request, timeout
        raise HTTPError(
            url="https://example.com", code=404, msg="Not Found", hdrs=None, fp=None
        )

    monkeypatch.setattr(s3_module, "urlopen", _raise_404)
    metadata = provider.get_object_metadata(
        "candidate-sessions/3/tasks/7/recordings/missing.mp4"
    )
    assert metadata is None

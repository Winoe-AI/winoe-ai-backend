from __future__ import annotations

from tests.unit.storage_media_extra_test_helpers import *

def test_s3_provider_delete_object_handles_success_and_missing(monkeypatch):
    provider = _build_s3_provider()

    class _DeleteResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

    monkeypatch.setattr(
        s3_module, "urlopen", lambda request, timeout: _DeleteResponse()
    )
    provider.delete_object("candidate-sessions/3/tasks/7/recordings/object.mp4")

    def _raise_404(request, timeout):
        del request, timeout
        raise HTTPError(
            url="https://example.com", code=404, msg="Not Found", hdrs=None, fp=None
        )

    monkeypatch.setattr(s3_module, "urlopen", _raise_404)
    provider.delete_object("candidate-sessions/3/tasks/7/recordings/missing.mp4")

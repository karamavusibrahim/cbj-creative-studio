"""Shared test setup: no unit test may reach a real video reader over the network. reference.video_client() tries
Gemini first (2026-10-16); here its factory always fails as a missing key would, so a test that does not pass its own
client falls through to the NVIDIA client it fakes (tests/test_gemini.py tests the Gemini client with HTTP mocked)."""
import pytest


@pytest.fixture(autouse=True)
def _no_real_gemini(monkeypatch):
    from cbj import reference

    def no_gemini():
        raise ValueError("no GEMINI_API_KEY in unit tests")
    monkeypatch.setattr(reference, "_gemini_client", no_gemini)


@pytest.fixture(autouse=True)
def _fresh_gemini_quota(monkeypatch):
    """Each test starts with no Gemini model marked out of its daily quota (gemini.EXHAUSTED lasts the process)."""
    from cbj import gemini
    monkeypatch.setattr(gemini, "EXHAUSTED", {})

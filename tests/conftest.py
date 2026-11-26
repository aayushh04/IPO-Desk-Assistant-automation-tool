"""Shared pytest fixtures."""
import pytest

from ipodesk.sample_data import make_sample_rhp_pdf


@pytest.fixture(scope="session")
def sample_pdf_bytes(tmp_path_factory) -> bytes:
    """Bytes of the generated sample RHP PDF."""
    path = make_sample_rhp_pdf(tmp_path_factory.mktemp("rhp") / "sample_rhp.pdf")
    return path.read_bytes()

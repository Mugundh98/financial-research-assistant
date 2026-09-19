import pytest

from src.ingestion.corpus import Corpus


@pytest.fixture(scope="session")
def corpus():
    return Corpus.load()

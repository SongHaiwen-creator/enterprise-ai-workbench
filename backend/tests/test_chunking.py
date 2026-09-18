from app.services.chunking import CHUNK_OVERLAP, CHUNK_SIZE, split_document_text


def test_chunking_is_deterministic_and_preserves_overlap() -> None:
    text = "a" * CHUNK_SIZE + "b" * 500

    first = split_document_text(text)
    second = split_document_text(text)

    assert first == second
    assert first == ["a" * CHUNK_SIZE, "a" * CHUNK_OVERLAP + "b" * 500]


def test_chunking_discards_whitespace_only_input() -> None:
    assert split_document_text(" \n\n\t ") == []

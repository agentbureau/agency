from agency.utils.embedding import embed, cosine_similarity


def test_embed_returns_list_of_floats():
    vec = embed("this is a test role component")
    assert isinstance(vec, list)
    assert all(isinstance(x, float) for x in vec)
    assert len(vec) == 384  # all-MiniLM-L6-v2 dimension


def test_similar_strings_have_high_similarity():
    v1 = embed("evaluate task quality")
    v2 = embed("assess task performance")
    assert cosine_similarity(v1, v2) > 0.7


def test_different_strings_have_lower_similarity():
    v1 = embed("evaluate task quality")
    v2 = embed("boil water for pasta")
    sim = cosine_similarity(v1, v2)
    assert sim < 0.7

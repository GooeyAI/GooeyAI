import pytest

from daras_ai_v2.search_ref import (
    CitationStyles,
    format_citations,
    generate_footnote_symbol,
    parse_refs,
)

REFERENCES = [
    {
        "url": f"https://example.com/{i}",
        "title": f"Example {i}",
        "snippet": "",
        "score": 1.0,
    }
    for i in range(1, 4)
]


def test_ref_parser():
    text = "This is a [1, 2, 3]. test. [4, 5] [6] [7, 8, 9]"
    references = [
        {
            "url": "https://example.com/1",
            "title": "Example 1",
            "snippet": "Example 1",
            "score": 1.0,
        },
        {
            "url": "https://example.com/2",
            "title": "Example 2",
            "snippet": "Example 2",
            "score": 1.0,
        },
        {
            "url": "https://example.com/3",
            "title": "Example 3",
            "snippet": "Example 3",
            "score": 1.0,
        },
        {
            "url": "https://example.com/4",
            "title": "Example 4",
            "snippet": "Example 4",
            "score": 1.0,
        },
        {
            "url": "https://example.com/5",
            "title": "Example 5",
            "snippet": "Example 5",
            "score": 1.0,
        },
        {
            "url": "https://example.com/6",
            "title": "Example 6",
            "snippet": "Example 6",
            "score": 1.0,
        },
        {
            "url": "https://example.com/7",
            "title": "Example 7",
            "snippet": "Example 7",
            "score": 1.0,
        },
        {
            "url": "https://example.com/8",
            "title": "Example 8",
            "snippet": "Example 8",
            "score": 1.0,
        },
        {
            "url": "https://example.com/9",
            "title": "Example 9",
            "snippet": "Example 9",
            "score": 1.0,
        },
    ]

    assert list(parse_refs(text, references)) == [
        (
            "This is a",
            {
                1: {
                    "url": "https://example.com/1",
                    "title": "Example 1",
                    "snippet": "Example 1",
                    "score": 1.0,
                },
                2: {
                    "url": "https://example.com/2",
                    "title": "Example 2",
                    "snippet": "Example 2",
                    "score": 1.0,
                },
                3: {
                    "url": "https://example.com/3",
                    "title": "Example 3",
                    "snippet": "Example 3",
                    "score": 1.0,
                },
            },
        ),
        (
            ". test.",
            {
                4: {
                    "url": "https://example.com/4",
                    "title": "Example 4",
                    "snippet": "Example 4",
                    "score": 1.0,
                },
                5: {
                    "url": "https://example.com/5",
                    "title": "Example 5",
                    "snippet": "Example 5",
                    "score": 1.0,
                },
                6: {
                    "url": "https://example.com/6",
                    "title": "Example 6",
                    "snippet": "Example 6",
                    "score": 1.0,
                },
                7: {
                    "url": "https://example.com/7",
                    "title": "Example 7",
                    "snippet": "Example 7",
                    "score": 1.0,
                },
                8: {
                    "url": "https://example.com/8",
                    "title": "Example 8",
                    "snippet": "Example 8",
                    "score": 1.0,
                },
                9: {
                    "url": "https://example.com/9",
                    "title": "Example 9",
                    "snippet": "Example 9",
                    "score": 1.0,
                },
            },
        ),
    ]


@pytest.mark.parametrize(
    "text, raw",
    [
        (
            "Here is the breakdown:\n"
            "- **Coverage:** varies by coverage levels. [1]\n"
            "- **Estimated returns:** higher for girls. [2]\n"
            "- **Coverage notes:** see estimates. [3]\n\n"
            "**For planning:** talk to an advisor.",
            "Here is the breakdown:\n"
            "- **Coverage:** varies by coverage levels.\n"
            "- **Estimated returns:** higher for girls.\n"
            "- **Coverage notes:** see estimates.\n\n"
            "**For planning:** talk to an advisor.",
        ),
        (
            "## Costs [1]\nBody text here [2]\n\n1. First item [1]\n2. Second item [3]\n3. Third",
            "## Costs\nBody text here\n\n1. First item\n2. Second item\n3. Third",
        ),
        (
            "The Hoover Dam is 726 feet tall [1]. It was finished in 1936 [2].",
            "The Hoover Dam is 726 feet tall. It was finished in 1936.",
        ),
        (
            "According to the docs [1] the dam is tall [2].",
            "According to the docs the dam is tall.",
        ),
    ],
    ids=["bullets", "heading-and-numbered-list", "single-paragraph", "mid-sentence"],
)
def test_citations_keep_markdown_blocks(text, raw):
    """A [n] marker ending a markdown block must not eat the next block's newline."""
    _, formatted = format_citations(text, REFERENCES, CitationStyles.number)
    assert formatted == text
    # same join as harness.py uses for raw_output_text and raw_tts_text
    assert "".join(snippet for snippet, _ in parse_refs(text, REFERENCES)) == raw


def test_generate_footnote_symbol():
    assert generate_footnote_symbol(0) == "*"
    assert generate_footnote_symbol(1) == "†"
    assert generate_footnote_symbol(13) == "✡"
    assert generate_footnote_symbol(14) == "**"
    assert generate_footnote_symbol(15) == "††"
    assert generate_footnote_symbol(27) == "✡✡"
    assert generate_footnote_symbol(28) == "***"
    assert generate_footnote_symbol(29) == "†††"
    assert generate_footnote_symbol(41) == "✡✡✡"
    assert generate_footnote_symbol(70) == "******"
    assert generate_footnote_symbol(71) == "††††††"

    # testing with non-integer index
    with pytest.raises(TypeError):
        generate_footnote_symbol(1.5)

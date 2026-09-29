from app.chunking import chunk_text


def test_auto_chunks_are_bounded_and_overlap():
    body = ("第一段内容。" * 180) + "\n第二段。"
    chunks = chunk_text(body)
    assert len(chunks) > 1
    assert all(len(chunk.text) <= 800 for chunk in chunks)
    assert chunks[0].offset_basis == "body_text"
    assert chunks[1].start_offset < chunks[0].end_offset
    assert body[chunks[0].start_offset : chunks[0].end_offset] == chunks[0].text


def test_custom_strategy_honors_limits_and_preprocessing_basis():
    body = "第一句。\n第二句。" + "更多内容。" * 30
    chunks = chunk_text(
        body,
        strategy="custom",
        max_chars=100,
        overlap_chars=20,
        separators=("。",),
        collapse_whitespace=True,
    )
    assert chunks
    assert all(len(chunk.text) <= 100 for chunk in chunks)
    assert all(chunk.offset_basis == "normalized" for chunk in chunks)


def test_hierarchy_keeps_markdown_heading_in_section():
    body = "# 第一章\n正文一\n## 第二章\n正文二"
    chunks = chunk_text(body, strategy="hierarchy", max_chars=800, overlap_chars=80)
    assert [chunk.index for chunk in chunks] == [0, 1]
    assert chunks[0].text.startswith("# 第一章")
    assert chunks[1].text.startswith("## 第二章")
    assert body[chunks[1].start_offset : chunks[1].end_offset] == chunks[1].text

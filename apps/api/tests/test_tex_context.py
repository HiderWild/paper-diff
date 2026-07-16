"""Unit tests for tex_context parser (no TestClient needed)."""

from __future__ import annotations

from app.domain.tex_context import build_tex_context, parse_aux, parse_bbl


def test_parse_aux_bibcite():
    citations, labels = parse_aux("\\bibcite{lee2023}{7}\n")
    assert citations == {"lee2023": "7"}
    assert labels == {}


def test_parse_aux_newlabel():
    citations, labels = parse_aux("\\newlabel{sec:intro}{{1}{1}}\n")
    assert citations == {}
    assert labels == {"sec:intro": {"number": "1", "page": "1"}}


def test_parse_aux_newlabel_no_page():
    citations, labels = parse_aux("\\newlabel{eq:x}{{2}}\n")
    assert labels == {"eq:x": {"number": "2", "page": None}}


def test_parse_aux_newlabel_empty_number():
    """hyperref occasionally emits \\newlabel{key}{{}{page}} (empty number)."""
    citations, labels = parse_aux("\\newlabel{foo}{{}{1}}\n")
    assert labels == {"foo": {"number": "", "page": "1"}}


def test_parse_aux_biblatex_abx_cite():
    citations, labels = parse_aux("\\abx@aux@cite{key1}{3}\n")
    assert citations == {"key1": "3"}
    assert labels == {}


def test_parse_aux_biblatex_abx_number():
    citations, labels = parse_aux("\\abx@aux@number{key2}{5}\n")
    assert citations == {"key2": "5"}


def test_parse_aux_empty():
    assert parse_aux("") == ({}, {})


def test_parse_aux_garbage_lines():
    citations, labels = parse_aux("random text\nno matches here\n%%% latex log\n")
    assert citations == {}
    assert labels == {}


def test_build_tex_context_with_aux():
    aux = "\\bibcite{lee2023}{7}\n\\newlabel{sec:intro}{{1}{1}}\n"
    ctx = build_tex_context(aux, None)
    assert ctx["compiled"] is True
    assert ctx["citations"] == {"lee2023": "7"}
    assert ctx["labels"] == {"sec:intro": {"number": "1", "page": "1"}}
    assert ctx["bibliography"] is None


def test_build_tex_context_no_aux():
    ctx = build_tex_context(None, None)
    assert ctx["compiled"] is False
    assert ctx["citations"] == {}
    assert ctx["labels"] == {}
    assert ctx["bibliography"] is None


def test_build_tex_context_with_bbl():
    bbl = "\\begin{thebibliography}\n\\bibitem{key1}\nstuff\n\\bibitem{key2}\nmore\n\\end{thebibliography}\n"
    ctx = build_tex_context("\\bibcite{x}{1}\n", bbl)
    assert ctx["bibliography"] == {"key1": "", "key2": ""}


def test_parse_bbl_basic():
    out = parse_bbl("\\bibitem{a}\n\\bibitem{b}\n")
    assert out == {"a": "", "b": ""}

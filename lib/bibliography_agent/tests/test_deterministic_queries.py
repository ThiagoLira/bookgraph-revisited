"""Unit tests for deterministic query generation."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from lib.bibliography_agent.deterministic_queries import (
    generate_queries_deterministic,
    _strip_subtitle,
    _strip_leading_article,
    _extract_last_name,
    _swap_comma_format,
    _strip_particles,
    _get_alias_variants,
)
from lib.bibliography_agent.events import SearchQuery


# --- Helper function tests ---


class TestStripSubtitle:
    def test_colon_separator(self):
        assert _strip_subtitle("The Two Cultures: And A Second Look") == "The Two Cultures"

    def test_em_dash_separator(self):
        assert _strip_subtitle("Being and Time — A Translation") == "Being and Time"

    def test_en_dash_separator(self):
        assert _strip_subtitle("Critique of Pure Reason – Second Edition") == "Critique of Pure Reason"

    def test_hyphen_separator(self):
        assert _strip_subtitle("Godel, Escher, Bach - An Eternal Golden Braid") == "Godel, Escher, Bach"

    def test_no_subtitle(self):
        assert _strip_subtitle("The Republic") is None

    def test_empty_string(self):
        assert _strip_subtitle("") is None


class TestStripLeadingArticle:
    def test_english_the(self):
        assert _strip_leading_article("The Republic") == "Republic"

    def test_english_a(self):
        assert _strip_leading_article("A Treatise on Human Nature") == "Treatise on Human Nature"

    def test_english_an(self):
        assert _strip_leading_article("An Essay Concerning Human Understanding") == "Essay Concerning Human Understanding"

    def test_french_le(self):
        assert _strip_leading_article("Le Scribe") == "Scribe"

    def test_french_la(self):
        assert _strip_leading_article("La Nausée") == "Nausée"

    def test_german_der(self):
        assert _strip_leading_article("Der Prozess") == "Prozess"

    def test_german_die(self):
        assert _strip_leading_article("Die Verwandlung") == "Verwandlung"

    def test_german_das(self):
        assert _strip_leading_article("Das Kapital") == "Kapital"

    def test_no_article(self):
        assert _strip_leading_article("Republic") is None

    def test_case_insensitive(self):
        assert _strip_leading_article("the republic") == "republic"

    def test_article_only(self):
        # "The" alone with nothing after shouldn't return empty
        assert _strip_leading_article("The") is None


class TestExtractLastName:
    def test_two_word_name(self):
        assert _extract_last_name("Arthur Schopenhauer") == "Schopenhauer"

    def test_three_word_name(self):
        assert _extract_last_name("Georg Wilhelm Friedrich Hegel") == "Hegel"

    def test_single_word(self):
        assert _extract_last_name("Plato") is None

    def test_with_initials(self):
        assert _extract_last_name("B. Mandelbrot") == "Mandelbrot"


class TestSwapCommaFormat:
    def test_simple_swap(self):
        assert _swap_comma_format("Chomsky, Noam") == "Noam Chomsky"

    def test_no_comma(self):
        assert _swap_comma_format("Noam Chomsky") is None

    def test_with_middle_name(self):
        assert _swap_comma_format("Dostoevsky, Fyodor M.") == "Fyodor M. Dostoevsky"


class TestStripParticles:
    def test_de(self):
        result = _strip_particles("Simone de Beauvoir")
        assert result is not None
        assert "Beauvoir" in result

    def test_von(self):
        result = _strip_particles("Johann Wolfgang von Goethe")
        assert result is not None
        assert "Goethe" in result

    def test_no_particle(self):
        assert _strip_particles("Arthur Schopenhauer") is None

    def test_leading_particle(self):
        result = _strip_particles("de Beauvoir")
        assert result == "Beauvoir"


class TestGetAliasVariants:
    def setup_method(self):
        # Build alias mapping like CitationWorkflow does
        raw = {
            "Arthur Schopenhauer": ["Schopenhauer"],
            "Simone de Beauvoir": ["de Beauvoir", "Beauvoir"],
            "Friedrich Nietzsche": ["Nietzche"],
        }
        self.aliases = {}
        for canonical, variants in raw.items():
            self.aliases[canonical.lower()] = canonical
            for v in variants:
                self.aliases[v.lower()] = canonical

    def test_variant_to_canonical(self):
        variants = _get_alias_variants("Schopenhauer", self.aliases)
        assert any("Arthur Schopenhauer" in v for v in variants)

    def test_canonical_to_variants(self):
        variants = _get_alias_variants("Arthur Schopenhauer", self.aliases)
        assert any("Schopenhauer" in v for v in variants)

    def test_no_match(self):
        variants = _get_alias_variants("Unknown Author", self.aliases)
        assert variants == []

    def test_empty_aliases(self):
        variants = _get_alias_variants("Schopenhauer", {})
        assert variants == []


# --- Main function tests ---


class TestGenerateQueriesDeterministicBook:
    """Tests for book mode (has title + author)."""

    def setup_method(self):
        raw = {
            "Arthur Schopenhauer": ["Schopenhauer"],
            "Simone de Beauvoir": ["de Beauvoir", "Beauvoir"],
        }
        self.aliases = {}
        for canonical, variants in raw.items():
            self.aliases[canonical.lower()] = canonical
            for v in variants:
                self.aliases[v.lower()] = canonical

    def test_basic_book_query(self):
        citation = {"title": "The Republic", "author": "Plato"}
        queries = generate_queries_deterministic(citation)
        assert len(queries) >= 1
        assert queries[0].title == "The Republic"
        assert queries[0].author == "Plato"

    def test_subtitle_removal(self):
        citation = {"title": "The Two Cultures: And A Second Look", "author": "C.P. Snow"}
        queries = generate_queries_deterministic(citation)
        titles = [q.title for q in queries]
        assert "The Two Cultures" in titles

    def test_article_removal(self):
        citation = {"title": "The Republic", "author": "Plato"}
        queries = generate_queries_deterministic(citation)
        titles = [q.title for q in queries]
        assert "Republic" in titles

    def test_last_name_only(self):
        citation = {"title": "The Republic", "author": "Benjamin Jowett"}
        queries = generate_queries_deterministic(citation)
        authors = [q.author for q in queries]
        assert "Jowett" in authors

    def test_alias_expansion(self):
        citation = {"title": "The World as Will", "author": "Schopenhauer"}
        queries = generate_queries_deterministic(citation, self.aliases)
        authors = [q.author for q in queries]
        assert any("Arthur Schopenhauer" in a for a in authors if a)

    def test_comma_format_swap(self):
        citation = {"title": "Syntactic Structures", "author": "Chomsky, Noam"}
        queries = generate_queries_deterministic(citation)
        authors = [q.author for q in queries]
        assert "Noam Chomsky" in authors

    def test_particle_removal(self):
        citation = {"title": "The Second Sex", "author": "Simone de Beauvoir"}
        queries = generate_queries_deterministic(citation, self.aliases)
        authors = [q.author for q in queries if q.author]
        # Should have a variant without "de"
        assert any("de" not in a.lower().split() for a in authors)

    def test_canonical_author_used(self):
        citation = {
            "title": "Fractals",
            "author": "B. Mandelbrot",
            "canonical_author": "Benoit Mandelbrot",
        }
        queries = generate_queries_deterministic(citation)
        authors = [q.author for q in queries]
        assert "Benoit Mandelbrot" in authors

    def test_no_duplicates(self):
        citation = {"title": "The Republic", "author": "Plato"}
        queries = generate_queries_deterministic(citation)
        seen = set()
        for q in queries:
            key = ((q.title or "").lower(), (q.author or "").lower())
            assert key not in seen, f"Duplicate query: {key}"
            seen.add(key)


class TestGenerateQueriesDeterministicAuthor:
    """Tests for author-only mode (empty title)."""

    def setup_method(self):
        raw = {
            "Arthur Schopenhauer": ["Schopenhauer"],
        }
        self.aliases = {}
        for canonical, variants in raw.items():
            self.aliases[canonical.lower()] = canonical
            for v in variants:
                self.aliases[v.lower()] = canonical

    def test_basic_author_query(self):
        citation = {"title": "", "author": "Aristotle"}
        queries = generate_queries_deterministic(citation)
        assert len(queries) >= 1
        assert queries[0].author == "Aristotle"
        assert queries[0].title is None

    def test_author_last_name(self):
        citation = {"title": "", "author": "Arthur Schopenhauer"}
        queries = generate_queries_deterministic(citation, self.aliases)
        authors = [q.author for q in queries]
        assert "Schopenhauer" in authors

    def test_author_alias_expansion(self):
        citation = {"title": "", "author": "Schopenhauer"}
        queries = generate_queries_deterministic(citation, self.aliases)
        authors = [q.author for q in queries]
        assert any("Arthur Schopenhauer" in a for a in authors if a)

    def test_canonical_author_used(self):
        citation = {
            "title": "",
            "author": "B. Mandelbrot",
            "canonical_author": "Benoit Mandelbrot",
        }
        queries = generate_queries_deterministic(citation)
        authors = [q.author for q in queries]
        assert "Benoit Mandelbrot" in authors

    def test_no_duplicates(self):
        citation = {"title": "", "author": "Arthur Schopenhauer"}
        queries = generate_queries_deterministic(citation, self.aliases)
        seen = set()
        for q in queries:
            key = ((q.title or "").lower(), (q.author or "").lower())
            assert key not in seen, f"Duplicate query: {key}"
            seen.add(key)

    def test_comma_format_swap(self):
        citation = {"title": "", "author": "Chomsky, Noam"}
        queries = generate_queries_deterministic(citation)
        authors = [q.author for q in queries]
        assert "Noam Chomsky" in authors


class TestEdgeCases:
    def test_empty_citation(self):
        citation = {"title": "", "author": ""}
        queries = generate_queries_deterministic(citation)
        assert queries == []

    def test_none_fields(self):
        citation = {"title": None, "author": None}
        queries = generate_queries_deterministic(citation)
        assert queries == []

    def test_missing_fields(self):
        citation = {}
        queries = generate_queries_deterministic(citation)
        assert queries == []

    def test_title_only_no_author(self):
        citation = {"title": "The Republic", "author": ""}
        queries = generate_queries_deterministic(citation)
        # Should still generate title variants even without author
        assert len(queries) >= 1
        titles = [q.title for q in queries]
        assert "The Republic" in titles

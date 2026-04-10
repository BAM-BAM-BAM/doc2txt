"""Text quality scoring for pdf2txt."""

import math
import re

from pdf2txt_models import QualityMetrics


class TextQualityScorer:
    """Score text quality for comparison between extractions."""

    # Top 500 common English words (condensed set)
    COMMON_WORDS: frozenset = frozenset([
        "the", "be", "to", "of", "and", "a", "in", "that", "have", "i",
        "it", "for", "not", "on", "with", "he", "as", "you", "do", "at",
        "this", "but", "his", "by", "from", "they", "we", "say", "her", "she",
        "or", "an", "will", "my", "one", "all", "would", "there", "their", "what",
        "so", "up", "out", "if", "about", "who", "get", "which", "go", "me",
        "when", "make", "can", "like", "time", "no", "just", "him", "know", "take",
        "people", "into", "year", "your", "good", "some", "could", "them", "see", "other",
        "than", "then", "now", "look", "only", "come", "its", "over", "think", "also",
        "back", "after", "use", "two", "how", "our", "work", "first", "well", "way",
        "even", "new", "want", "because", "any", "these", "give", "day", "most", "us",
        "is", "are", "was", "were", "been", "has", "had", "did", "does", "done",
        "said", "made", "found", "used", "called", "may", "each", "own", "should", "here",
        "where", "more", "very", "through", "long", "little", "own", "while", "still", "find",
        "part", "being", "much", "too", "many", "those", "such", "before", "same", "right",
        "mean", "different", "move", "between", "must", "need", "might", "try", "world", "again",
        "place", "great", "show", "every", "last", "never", "old", "under", "keep", "let",
        "begin", "seem", "help", "always", "home", "both", "around", "off", "end", "against",
        "high", "few", "important", "until", "next", "without", "public", "another", "read", "number",
        "word", "page", "chapter", "section", "figure", "table", "document", "file", "data", "information",
        "system", "process", "method", "result", "analysis", "example", "following", "based", "using", "include",
        "however", "therefore", "although", "within", "during", "since", "provide", "according", "available", "report",
        "form", "service", "case", "study", "research", "development", "program", "company", "business", "market",
        "product", "customer", "management", "project", "support", "review", "application", "user", "group", "level",
        "value", "change", "control", "test", "performance", "quality", "standard", "policy", "issue", "problem",
    ])

    # Precompiled patterns for gibberish detection
    REPEATED_CHARS = re.compile(r'(.)\1{3,}')
    CONSONANT_CLUSTER = re.compile(r'[bcdfghjklmnpqrstvwxz]{5,}', re.IGNORECASE)
    NO_VOWELS = re.compile(r'\b[bcdfghjklmnpqrstvwxz]{5,}\b', re.IGNORECASE)
    ENCODING_ARTIFACTS = re.compile(r'â€|Ã©|Ã¨|Ã |ï»¿|\ufffd|\\x[0-9a-f]{2}', re.IGNORECASE)
    NON_PRINTABLE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')
    WORD_PATTERN = re.compile(r'\b[a-zA-Z]+\b')
    SENTENCE_END = re.compile(r'[.!?]')

    def score(self, text: str) -> QualityMetrics:
        """Score text quality and return detailed metrics."""
        if not text or not text.strip():
            return QualityMetrics()

        words = self.WORD_PATTERN.findall(text.lower())
        word_count = len(words)

        if word_count == 0:
            return QualityMetrics(word_count=0)

        # Real word ratio (weight: 0.35)
        common_count = sum(1 for w in words if w in self.COMMON_WORDS)
        real_word_ratio = common_count / word_count

        # Content score - log-scaled word count (weight: 0.30)
        content_score = min(1.0, math.log10(word_count + 1) / 4.0)

        # Gibberish penalty (weight: -0.20)
        gibberish_count = 0
        gibberish_count += len(self.REPEATED_CHARS.findall(text))
        gibberish_count += len(self.CONSONANT_CLUSTER.findall(text))
        gibberish_count += len(self.NO_VOWELS.findall(text))
        gibberish_count += len(self.ENCODING_ARTIFACTS.findall(text))
        gibberish_count += len(self.NON_PRINTABLE.findall(text))
        gibberish_penalty = min(1.0, gibberish_count / max(word_count / 10, 1))

        # Punctuation score - sentence structure (weight: 0.15)
        sentence_ends = len(self.SENTENCE_END.findall(text))
        expected_sentences = word_count / 15  # Average sentence ~15 words
        if expected_sentences > 0:
            punctuation_score = min(1.0, sentence_ends / expected_sentences)
        else:
            punctuation_score = 0.0

        # Calculate total weighted score
        total_score = (
            real_word_ratio * 0.35 +
            content_score * 0.30 -
            gibberish_penalty * 0.20 +
            punctuation_score * 0.15
        )
        total_score = max(0.0, min(1.0, total_score))

        return QualityMetrics(
            real_word_ratio=real_word_ratio,
            content_score=content_score,
            gibberish_penalty=gibberish_penalty,
            punctuation_score=punctuation_score,
            total_score=total_score,
            word_count=word_count
        )

    def compare(self, existing: str, new: str) -> tuple[bool, QualityMetrics, QualityMetrics]:
        """Compare existing and new text, return (is_new_better, old_metrics, new_metrics)."""
        old_metrics = self.score(existing)
        new_metrics = self.score(new)
        is_better = new_metrics.total_score > old_metrics.total_score
        return is_better, old_metrics, new_metrics


def strip_markdown_metadata(md_text: str) -> str:
    """Remove title, source line, and page markers from markdown for fair comparison."""
    lines = md_text.split('\n')
    content_lines = []
    for line in lines:
        # Skip: # Title, > Source:, ---, *Page N*
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if stripped.startswith('>'):
            continue
        if stripped == '---':
            continue
        if stripped.startswith('*Page') and stripped.endswith('*'):
            continue
        content_lines.append(line)
    return '\n'.join(content_lines)


# Global scorer instance
_quality_scorer = TextQualityScorer()

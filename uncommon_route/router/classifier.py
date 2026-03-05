"""Script-Agnostic Classifier v6.

Architecture:
  Level 0: Trivial Override (greeting/empty/very long)
  Level 1: Model prediction on structured features + Unicode blocks
           Model learns optimal weights from data — no hand-tuned boundaries
  Level 2: Rule-based fallback (only when model is unavailable)

The model input is 39 script-agnostic features:
  - 12 structural scores (enumeration, sentences, code, math, intent, ...)
  - 15 Unicode block proportions (latin, cjk, hangul, arabic, ...)
  - 12 keyword scores (multilingual vocabulary, minor signal)
  + optional n-gram features (same-script boost, auto-downweighted)

This replaces hand-tuned weights with data-learned weights.
Keywords still contribute as features but the model decides how much to trust them.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from uncommon_route.router.types import (
    ScoringConfig,
    ScoringResult,
    Tier,
)
from uncommon_route.router.structural import (
    estimate_tokens,
    extract_structural_features,
    extract_unicode_block_features,
)
from uncommon_route.router.keywords import extract_keyword_features
from uncommon_route.router.learned import ScriptAgnosticClassifier

_model: ScriptAgnosticClassifier | None = None
_model_load_attempted = False

def _get_online_model_path() -> Path:
    return Path.home() / ".uncommon-route" / "model_online.json"


def _ensure_model_loaded() -> None:
    global _model, _model_load_attempted
    if _model_load_attempted:
        return
    _model_load_attempted = True
    online = _get_online_model_path()
    default = Path(__file__).parent / "model.json"
    if online.exists():
        _model = ScriptAgnosticClassifier()
        _model.load(online)
    elif default.exists():
        _model = ScriptAgnosticClassifier()
        _model.load(default)


def load_learned_model(path: str | None = None) -> None:
    global _model
    p = Path(path) if path else (Path(__file__).parent / "model.json")
    if p.exists():
        _model = ScriptAgnosticClassifier()
        _model.load(p)


def extract_features(prompt: str, system_prompt: str | None = None) -> dict[str, float]:
    """Public API: extract the full 39-dim feature vector for a prompt."""
    _ensure_model_loaded()
    full_text = f"{system_prompt or ''} {prompt}".strip()
    return _extract_all_features(prompt, full_text)


def update_model(features: dict[str, float], correct_tier: str) -> bool:
    """Apply one online Perceptron update. Returns True if model exists."""
    _ensure_model_loaded()
    if _model is None:
        return False
    _model.update(features, correct_tier)
    return True


def save_online_model(path: Path | None = None) -> None:
    """Persist current weights to the online model file."""
    if _model is None:
        return
    p = path or _get_online_model_path()
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _model.save(p)


def rollback_online_model() -> bool:
    """Delete online weights and reload base model. Returns True if file was deleted."""
    global _model, _model_load_attempted
    p = _get_online_model_path()
    deleted = False
    if p.exists():
        p.unlink()
        deleted = True
    _model = None
    _model_load_attempted = False
    _ensure_model_loaded()
    return deleted


def _extract_all_features(prompt: str, full_text: str) -> dict[str, float]:
    """Extract the complete feature vector for model input."""
    # Structural features (12 dims)
    struct_dims = extract_structural_features(full_text)
    structural_scores = {d.name: d.score for d in struct_dims}

    # Unicode block features (15 dims)
    unicode_blocks = extract_unicode_block_features(full_text)

    # Keyword features (12 dims)
    kw_dims = extract_keyword_features(prompt)
    keyword_scores = {d.name: d.score for d in kw_dims}

    # Build combined feature vector
    if _model is not None:
        return _model._build_features(structural_scores, unicode_blocks, keyword_scores, prompt)

    # Fallback: manual construction
    features: dict[str, float] = {}
    for name, score in structural_scores.items():
        features[f"s_{name}"] = score
    for name, prop in unicode_blocks.items():
        features[f"u_{name}"] = prop
    for name, score in keyword_scores.items():
        features[f"k_{name}"] = score
    return features


def train_and_save_model(data_path: str, out_path: str | None = None) -> None:
    """Train model from JSONL data."""
    import json

    cases = []
    with open(data_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))

    # Extract features for each case
    feature_sets: list[tuple[dict[str, float], str]] = []
    model = ScriptAgnosticClassifier(use_ngrams=True)

    for case in cases:
        prompt = case["prompt"]
        sys_prompt = case.get("system_prompt")
        full_text = f"{sys_prompt or ''} {prompt}".strip()

        struct_dims = extract_structural_features(full_text)
        structural_scores = {d.name: d.score for d in struct_dims}
        unicode_blocks = extract_unicode_block_features(full_text)
        kw_dims = extract_keyword_features(prompt)
        keyword_scores = {d.name: d.score for d in kw_dims}

        features = model._build_features(structural_scores, unicode_blocks, keyword_scores, prompt)
        feature_sets.append((features, case["expected_tier"]))

    model.train(feature_sets, epochs=12)

    save_to = Path(out_path) if out_path else Path(__file__).parent / "model.json"
    model.save(save_to)
    print(f"Trained on {len(cases)} cases, saved to {save_to}")

    correct = sum(1 for feats, tier in feature_sets if model.predict(feats)[0] == tier)
    print(f"Training accuracy: {correct}/{len(cases)} ({correct/len(cases)*100:.1f}%)")


# ─── Trivial Override ───

_GREETING_PATTERN = re.compile(
    r"^(?:hi|hello|hey|thanks|thank you|ok|yes|no|help"
    r"|你好|谢谢|好的|是|否"
    r"|привет|спасибо|да|нет"
    r"|hola|gracias|sí"
    r"|こんにちは|ありがとう"
    r"|안녕하세요|감사합니다"
    r"|नमस्ते|धन्यवाद"
    r"|merhaba|teşekkür"
    r"|\?\?+|!+|\.+)\s*$",
    re.IGNORECASE,
)


def _check_trivial(prompt: str, tokens: int) -> Tier | None:
    lower = prompt.lower().strip()
    if len(lower) < 20 and _GREETING_PATTERN.match(lower):
        return Tier.SIMPLE
    if tokens <= 2:
        return Tier.SIMPLE
    if tokens > 100_000:
        return Tier.COMPLEX
    return None


# ─── Rule-based fallback (when model unavailable) ───

def _sigmoid(distance: float, steepness: float) -> float:
    clamped = max(-50.0, min(50.0, steepness * distance))
    return 1.0 / (1.0 + math.exp(-clamped))


def _rule_based_classify(
    all_features: dict[str, float],
    config: ScoringConfig,
) -> tuple[Tier, float]:
    """Fallback classification using hand-tuned weights when model is not available."""
    sw = config.structural_weights
    kw = config.keyword_weights
    weight_map = {
        "s_normalized_length": sw.normalized_length,
        "s_enumeration_density": sw.enumeration_density,
        "s_sentence_count": sw.sentence_count,
        "s_code_markers": sw.code_markers,
        "s_math_symbols": sw.math_symbols,
        "s_nesting_depth": sw.nesting_depth,
        "s_vocabulary_diversity": sw.vocabulary_diversity,
        "s_avg_word_length": sw.avg_word_length,
        "s_alphabetic_ratio": sw.alphabetic_ratio,
        "s_functional_intent": sw.functional_intent,
        "s_unique_concept_density": sw.unique_concept_density,
        "s_requirement_phrases": sw.requirement_phrases,
        "k_code_presence": kw.code_presence,
        "k_reasoning_markers": kw.reasoning_markers,
        "k_technical_terms": kw.technical_terms,
        "k_creative_markers": kw.creative_markers,
        "k_simple_indicators": kw.simple_indicators,
        "k_imperative_verbs": kw.imperative_verbs,
        "k_constraint_count": kw.constraint_count,
        "k_output_format": kw.output_format,
        "k_domain_specificity": kw.domain_specificity,
        "k_analytical_verbs": kw.analytical_verbs,
        "k_agentic_task": kw.agentic_task,
        "k_multi_step_patterns": kw.multi_step_patterns,
    }

    score = sum(all_features.get(k, 0.0) * w for k, w in weight_map.items())

    bounds = config.tier_boundaries
    if score < bounds.simple_medium:
        tier, dist = Tier.SIMPLE, bounds.simple_medium - score
    elif score < bounds.medium_complex:
        tier = Tier.MEDIUM
        dist = min(score - bounds.simple_medium, bounds.medium_complex - score)
    elif score < bounds.complex_reasoning:
        tier = Tier.COMPLEX
        dist = min(score - bounds.medium_complex, bounds.complex_reasoning - score)
    else:
        tier, dist = Tier.REASONING, score - bounds.complex_reasoning

    confidence = _sigmoid(dist, config.confidence_steepness)
    return tier, confidence


# ─── Main Entry ───

def classify(
    prompt: str,
    system_prompt: str | None = None,
    config: ScoringConfig | None = None,
) -> ScoringResult:
    if config is None:
        config = ScoringConfig()

    full_text = f"{system_prompt or ''} {prompt}".strip()
    estimated_tokens = estimate_tokens(full_text)

    _ensure_model_loaded()

    # Level 0: Trivial
    trivial = _check_trivial(prompt, estimated_tokens)
    if trivial is not None:
        return ScoringResult(
            score=0.0, tier=trivial, confidence=0.95,
            signals=[f"trivial:{trivial.value}"], agentic_score=0.0,
        )

    # Extract all features
    all_features = _extract_all_features(prompt, full_text)

    # Agentic score
    agentic_score = all_features.get("k_agentic_task", 0.0)

    # Level 1: Model prediction (primary)
    if _model is not None:
        tier_str, confidence = _model.predict(all_features)
        tier = Tier(tier_str)
        signals = [f"model:{tier_str}({confidence:.2f})"]
        return ScoringResult(
            score=0.0, tier=tier, confidence=confidence,
            signals=signals, agentic_score=agentic_score,
        )

    # Level 2: Rule-based fallback
    tier, confidence = _rule_based_classify(all_features, config)
    struct_dims = extract_structural_features(full_text)
    kw_dims = extract_keyword_features(prompt)
    all_dims = struct_dims + kw_dims
    signals = [d.signal for d in all_dims if d.signal is not None]
    signals.append("rule-fallback")

    if confidence < config.confidence_threshold:
        return ScoringResult(
            score=0.0, tier=None, confidence=confidence,
            signals=signals, dimensions=all_dims, agentic_score=agentic_score,
        )

    return ScoringResult(
        score=0.0, tier=tier, confidence=confidence,
        signals=signals, dimensions=all_dims, agentic_score=agentic_score,
    )

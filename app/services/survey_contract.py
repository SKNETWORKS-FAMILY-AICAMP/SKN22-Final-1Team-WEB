from __future__ import annotations

from collections.abc import Mapping

from app.api.v1.recommendation_logic import (
    canonical_front_styling,
    canonical_gender_branch,
    canonical_length,
    canonical_parting,
)


QUESTION_KEYS = tuple(f"q{index}" for index in range(1, 7))


def _normalize_text_value(value: object) -> str:
    return str(value or "").strip()


def _compact_text(value: object) -> str:
    return (
        _normalize_text_value(value)
        .lower()
        .replace("-", "")
        .replace("_", "")
        .replace(" ", "")
    )


def _explicit_gender_branch(value: object) -> str | None:
    normalized = _compact_text(value)
    if normalized in {"m", "male", "man", "남", "남성"}:
        return "male"
    if normalized in {"f", "female", "woman", "여", "여성"}:
        return "female"
    return None


def extract_question_answers(payload: Mapping[str, object] | None) -> dict[str, str]:
    source = payload if isinstance(payload, Mapping) else {}
    survey_profile = source.get("survey_profile")
    survey_profile_mapping = survey_profile if isinstance(survey_profile, Mapping) else {}
    survey_profile_answers = survey_profile_mapping.get("question_answers")
    profile_mapping = survey_profile_answers if isinstance(survey_profile_answers, Mapping) else {}
    embedded_answers = source.get("question_answers")
    embedded_mapping = embedded_answers if isinstance(embedded_answers, Mapping) else {}

    answers = {
        key: _normalize_text_value(profile_mapping.get(key))
        for key in QUESTION_KEYS
    }
    for key in QUESTION_KEYS:
        embedded_value = embedded_mapping.get(key)
        if embedded_value is None:
            continue
        answers[key] = _normalize_text_value(embedded_value)
    for key in QUESTION_KEYS:
        direct_value = source.get(key)
        if direct_value is None:
            continue
        answers[key] = _normalize_text_value(direct_value)
    return answers


def _canonical_two_block(value: object) -> str | None:
    normalized = _compact_text(value)
    if normalized in {"strong", "확실한투블럭"}:
        return "strong"
    if normalized in {"soft", "자연스러운투블럭"}:
        return "soft"
    if normalized in {"none", "투블럭없이연결감있게", "연결감있게"}:
        return "none"
    return None


def _target_length_from_text(value: object) -> str | None:
    normalized = _compact_text(value)
    if not normalized:
        return None
    if any(token in normalized for token in ("짧", "숏", "쇼트", "short", "crop", "크롭")):
        return "short"
    if any(token in normalized for token in ("길이감", "길게", "롱", "long")):
        return "long"
    if any(token in normalized for token in ("유지", "중간", "미디", "medium", "자연스럽게")):
        return "medium"
    canonical = canonical_length(_normalize_text_value(value))
    return None if canonical == "unknown" else canonical


def _male_front_styling_from_text(value: object) -> str | None:
    return canonical_front_styling(_normalize_text_value(value))


def _male_parting_from_text(value: object) -> str | None:
    return canonical_parting(_normalize_text_value(value))


def _female_survey_profile(*, answers: dict[str, str]) -> dict:
    q1 = answers.get("q1", "")
    q2 = answers.get("q2", "")
    q3 = answers.get("q3", "")
    q4 = answers.get("q4", "")
    q5 = answers.get("q5", "")
    q6 = answers.get("q6", "")

    target_length = {
        "짧게": "short",
        "중간 길이": "medium",
        "길게": "long",
        "유지": "medium",
    }.get(q1, "medium")
    target_vibe = {
        "내추럴한": "natural",
        "세련된": "chic",
        "사랑스러운": "cute",
        "고급스러운": "elegant",
    }.get(q5, "natural")
    scalp_type = {
        "생머리 느낌": "straight",
        "끝선 위주 자연스러운 컬": "waved",
        "전체적으로 웨이브감": "curly",
    }.get(q4, "waved")

    if q6 == "확실히 이미지 변신하고 싶음":
        if q5 == "세련된":
            hair_colour = "ash"
        elif q5 == "고급스러운":
            hair_colour = "black"
        else:
            hair_colour = "brown"
    elif q6 == "적당히 변화를 주고 싶음":
        if q5 == "세련된":
            hair_colour = "ash"
        elif q5 == "고급스러운":
            hair_colour = "black"
        else:
            hair_colour = "brown"
    else:
        if q5 == "고급스러운":
            hair_colour = "black"
        elif q5 == "세련된":
            hair_colour = "brown"
        else:
            hair_colour = "brown"

    budget_score = 0
    if target_length == "long":
        budget_score += 1
    if q2 in {"레이어감 있는 스타일", "볼륨감 있는 스타일"}:
        budget_score += 1
    if scalp_type == "waved":
        budget_score += 1
    elif scalp_type == "curly":
        budget_score += 2
    if q6 == "적당히 변화를 주고 싶음":
        budget_score += 1
    elif q6 == "확실히 이미지 변신하고 싶음":
        budget_score += 2
    if q5 == "고급스러운":
        budget_score += 1

    if budget_score <= 1:
        budget_range = "low"
    elif budget_score <= 3:
        budget_range = "mid"
    else:
        budget_range = "high"

    return {
        "gender_branch": "female",
        "question_answers": answers,
        "style_axes": {
            "silhouette": {
                "일자 느낌": "straight_line",
                "레이어감 있는 스타일": "layered",
                "볼륨감 있는 스타일": "voluminous",
            }.get(q2, "balanced"),
            "bang_preference": {
                "앞머리 없이": "no_bangs",
                "시스루·가벼운 앞머리": "light_bangs",
                "존재감 있는 앞머리": "statement_bangs",
            }.get(q3, "balanced"),
            "change_intensity": {
                "최대한 무난하게": "soft",
                "적당히 변화를 주고 싶음": "medium",
                "확실히 이미지 변신하고 싶음": "bold",
            }.get(q6, "medium"),
        },
        "derived_preferences": {
            "target_length": target_length,
            "target_vibe": target_vibe,
            "scalp_type": scalp_type,
            "hair_colour": hair_colour,
            "budget_range": budget_range,
        },
    }


def _male_survey_profile(*, answers: dict[str, str]) -> dict:
    q1 = answers.get("q1", "")
    q2 = answers.get("q2", "")
    q3 = answers.get("q3", "")
    q4 = answers.get("q4", "")
    q5 = answers.get("q5", "")
    q6 = answers.get("q6", "")

    target_length = _target_length_from_text(q1)
    front_styling = _male_front_styling_from_text(q3)
    parting = _male_parting_from_text(q4)
    if not target_length:
        if q2 == "확실한 투블럭" or front_styling == "lifted":
            target_length = "short"
        elif parting in {"side_part", "center_part"} or front_styling == "down":
            target_length = "medium"
        else:
            target_length = "medium"

    target_vibe = {
        "단정한": "natural",
        "세련된": "chic",
        "부드러운": "natural",
        "트렌디한": "chic",
    }.get(q6, "natural")
    if parting in {"side_part", "center_part"} and target_vibe == "natural":
        target_vibe = "chic"

    scalp_type = {
        "펌 없이 깔끔하게": "straight",
        "자연스러운 볼륨 정도": "waved",
        "컬감이 느껴지는 스타일": "curly",
    }.get(q5, "straight")

    if q6 == "트렌디한":
        hair_colour = "ash"
    elif q6 == "세련된":
        hair_colour = "brown"
    elif q6 == "부드러운":
        hair_colour = "brown"
    else:
        hair_colour = "black"

    budget_score = 0
    if target_length == "long":
        budget_score += 1
    if q2 == "확실한 투블럭":
        budget_score += 1
    if parting in {"side_part", "center_part"}:
        budget_score += 1
    if scalp_type == "waved":
        budget_score += 1
    elif scalp_type == "curly":
        budget_score += 2
    if q6 in {"세련된", "트렌디한"}:
        budget_score += 1

    if budget_score <= 1:
        budget_range = "low"
    elif budget_score <= 3:
        budget_range = "mid"
    else:
        budget_range = "high"

    style_axes = {
        "two_block": {
            "확실한 투블럭": "strong",
            "자연스러운 투블럭": "soft",
            "투블럭 없이 연결감 있게": "none",
        }.get(q2, "soft"),
    }
    if front_styling:
        style_axes["front_styling"] = front_styling
    if parting:
        style_axes["parting"] = parting

    return {
        "gender_branch": "male",
        "question_answers": answers,
        "style_axes": style_axes,
        "derived_preferences": {
            "target_length": target_length,
            "target_vibe": target_vibe,
            "scalp_type": scalp_type,
            "hair_colour": hair_colour,
            "budget_range": budget_range,
        },
    }


def _normalized_style_axes(
    style_axes: Mapping[str, object] | None,
    *,
    gender_branch: str,
) -> dict[str, str]:
    if not isinstance(style_axes, Mapping):
        return {}

    normalized: dict[str, str] = {}
    for raw_key, raw_value in style_axes.items():
        key = _normalize_text_value(raw_key)
        if not key:
            continue
        if key == "front_styling":
            front_styling = canonical_front_styling(raw_value)
            if front_styling:
                normalized[key] = front_styling
            continue
        if key == "parting":
            parting = canonical_parting(raw_value)
            if parting:
                normalized[key] = parting
            continue
        if key == "two_block" and gender_branch == "male":
            two_block = _canonical_two_block(raw_value)
            if two_block:
                normalized[key] = two_block
            continue

        value = _normalize_text_value(raw_value)
        if value:
            normalized[key] = value
    return normalized


def normalize_survey_contract(
    payload: Mapping[str, object] | None,
    *,
    fallback_gender_branch: str | None = None,
) -> dict:
    source = dict(payload or {})
    question_answers = extract_question_answers(source)
    existing_survey_profile = dict(source.get("survey_profile") or {})

    gender_branch = (
        _explicit_gender_branch(source.get("gender_branch") or source.get("gender"))
        or _explicit_gender_branch(existing_survey_profile.get("gender_branch"))
        or _explicit_gender_branch(fallback_gender_branch)
        or canonical_gender_branch(fallback_gender_branch)
    )
    derived_survey_profile = (
        _male_survey_profile(answers=question_answers)
        if gender_branch == "male" and any(question_answers.values())
        else _female_survey_profile(answers=question_answers)
        if any(question_answers.values())
        else {}
    )
    derived_preferences = dict(derived_survey_profile.get("derived_preferences") or {})

    survey_profile = dict(existing_survey_profile)
    for key, value in derived_survey_profile.items():
        if key in {"question_answers", "style_axes", "gender_branch"}:
            continue
        survey_profile[key] = value

    normalized_style_axes = _normalized_style_axes(survey_profile.get("style_axes"), gender_branch=gender_branch)
    normalized_style_axes.update(
        _normalized_style_axes(derived_survey_profile.get("style_axes"), gender_branch=gender_branch)
    )

    survey_profile["gender_branch"] = gender_branch
    survey_profile["question_answers"] = question_answers
    survey_profile["style_axes"] = normalized_style_axes

    target_length = (
        _target_length_from_text(source.get("target_length"))
        or derived_preferences.get("target_length")
    )

    return {
        "target_length": target_length or source.get("target_length"),
        "target_vibe": source.get("target_vibe") or derived_preferences.get("target_vibe"),
        "scalp_type": source.get("scalp_type") or derived_preferences.get("scalp_type"),
        "hair_colour": source.get("hair_colour") or derived_preferences.get("hair_colour"),
        "budget_range": source.get("budget_range") or derived_preferences.get("budget_range"),
        "gender_branch": gender_branch,
        "question_answers": question_answers,
        "survey_profile": survey_profile,
    }

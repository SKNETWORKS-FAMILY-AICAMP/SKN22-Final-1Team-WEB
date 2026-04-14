from dataclasses import dataclass
from typing import Iterable


FACE_WEIGHT = 40.0
RATIO_WEIGHT = 20.0
PREFERENCE_WEIGHT = 40.0
VECTOR_DIMENSION = 20


@dataclass(frozen=True)
class ScoringWeights:
    face_weight: float
    ratio_weight: float
    preference_weight: float
    profile: str

    def as_dict(self) -> dict:
        return {
            "face_weight": self.face_weight,
            "ratio_weight": self.ratio_weight,
            "preference_weight": self.preference_weight,
            "profile": self.profile,
        }


DEFAULT_SCORING_WEIGHTS = ScoringWeights(
    face_weight=FACE_WEIGHT,
    ratio_weight=RATIO_WEIGHT,
    preference_weight=PREFERENCE_WEIGHT,
    profile="initial",
)

RETRY_SCORING_WEIGHTS = ScoringWeights(
    face_weight=20.0,
    ratio_weight=10.0,
    preference_weight=70.0,
    profile="retry_preference_dominant",
)


@dataclass(frozen=True)
class StyleProfile:
    style_id: int
    fallback_name: str
    fallback_description: str
    fallback_sample_image_url: str
    keywords: tuple[str, ...]
    face_shapes: tuple[str, ...]
    ratio_modes: tuple[str, ...]
    length_tags: tuple[str, ...]
    vibe_tags: tuple[str, ...]
    scalp_tags: tuple[str, ...]
    color_tags: tuple[str, ...]
    budget_tags: tuple[str, ...]
    gender_branches: tuple[str, ...] = ("female", "male")
    style_axes: tuple[str, ...] = ()


STYLE_CATALOG: tuple[StyleProfile, ...] = (
    StyleProfile(
        style_id=201,
        fallback_name="Side-Parted Lob",
        fallback_description="Rounded cheeks are balanced with a longer side silhouette.",
        fallback_sample_image_url="styles/201.jpg",
        keywords=("lob", "side part", "balance"),
        face_shapes=("round", "oval"),
        ratio_modes=("cover", "balanced"),
        length_tags=("bob", "medium"),
        vibe_tags=("chic", "natural"),
        scalp_tags=("straight", "waved"),
        color_tags=("black", "brown", "ash"),
        budget_tags=("mid", "high"),
        gender_branches=("female",),
        style_axes=("silhouette:straight_line", "bang_preference:no_bangs", "change_intensity:medium"),
    ),
    StyleProfile(
        style_id=202,
        fallback_name="Textured C-Curl Bob",
        fallback_description="Soft texture helps reduce heaviness around the jaw line.",
        fallback_sample_image_url="styles/202.jpg",
        keywords=("bob", "texture", "soft"),
        face_shapes=("round", "square", "oval"),
        ratio_modes=("cover", "balanced"),
        length_tags=("short", "bob"),
        vibe_tags=("natural", "cute"),
        scalp_tags=("straight", "damaged"),
        color_tags=("black", "brown"),
        budget_tags=("low", "mid"),
        gender_branches=("female",),
        style_axes=("silhouette:straight_line", "bang_preference:light_bangs", "change_intensity:soft"),
    ),
    StyleProfile(
        style_id=203,
        fallback_name="Soft Hush Layer",
        fallback_description="Layer placement adds movement while preserving a light front line.",
        fallback_sample_image_url="styles/203.jpg",
        keywords=("layer", "soft", "movement"),
        face_shapes=("square", "long", "oval"),
        ratio_modes=("cover", "balanced"),
        length_tags=("medium", "long"),
        vibe_tags=("natural", "elegant"),
        scalp_tags=("waved", "curly", "damaged"),
        color_tags=("brown", "ash", "bleach"),
        budget_tags=("mid", "high"),
        gender_branches=("female",),
        style_axes=("silhouette:layered", "bang_preference:light_bangs", "change_intensity:medium"),
    ),
    StyleProfile(
        style_id=204,
        fallback_name="Sleek Mini Bob",
        fallback_description="A compact silhouette works best when facial balance is already strong.",
        fallback_sample_image_url="styles/204.jpg",
        keywords=("mini bob", "sleek", "clean"),
        face_shapes=("oval", "long"),
        ratio_modes=("expose", "balanced"),
        length_tags=("short", "bob"),
        vibe_tags=("chic", "elegant"),
        scalp_tags=("straight",),
        color_tags=("black", "brown", "ash"),
        budget_tags=("mid", "high"),
        gender_branches=("female",),
        style_axes=("silhouette:straight_line", "bang_preference:no_bangs", "change_intensity:medium"),
    ),
    StyleProfile(
        style_id=205,
        fallback_name="Elegant S-Curl Medium",
        fallback_description="Front softness and side volume help soften strong contours.",
        fallback_sample_image_url="styles/205.jpg",
        keywords=("s curl", "volume", "elegant"),
        face_shapes=("square", "triangle", "round"),
        ratio_modes=("cover", "balanced"),
        length_tags=("medium",),
        vibe_tags=("elegant", "natural"),
        scalp_tags=("waved", "curly"),
        color_tags=("brown", "ash"),
        budget_tags=("high",),
        gender_branches=("female",),
        style_axes=("silhouette:voluminous", "bang_preference:light_bangs", "change_intensity:medium"),
    ),
    StyleProfile(
        style_id=206,
        fallback_name="Full Layer Long Wave",
        fallback_description="Long layers give vertical flow while keeping side balance.",
        fallback_sample_image_url="styles/206.jpg",
        keywords=("long wave", "layer", "flow"),
        face_shapes=("triangle", "square", "oval"),
        ratio_modes=("balanced", "expose"),
        length_tags=("long",),
        vibe_tags=("elegant", "natural"),
        scalp_tags=("waved", "curly"),
        color_tags=("brown", "ash", "bleach"),
        budget_tags=("high",),
        gender_branches=("female",),
        style_axes=("silhouette:layered", "bang_preference:no_bangs", "change_intensity:bold"),
    ),
    StyleProfile(
        style_id=207,
        fallback_name="Airy Short Bob",
        fallback_description="Airy volume around the crown reduces flatness without adding weight.",
        fallback_sample_image_url="styles/207.jpg",
        keywords=("short bob", "airy", "crown volume"),
        face_shapes=("round", "square"),
        ratio_modes=("cover",),
        length_tags=("short", "bob"),
        vibe_tags=("cute", "natural"),
        scalp_tags=("straight", "damaged"),
        color_tags=("black", "brown"),
        budget_tags=("low", "mid"),
        gender_branches=("female",),
        style_axes=("silhouette:voluminous", "bang_preference:light_bangs", "change_intensity:soft"),
    ),
    StyleProfile(
        style_id=301,
        fallback_name="Clean Crop Two-Block",
        fallback_description="A crisp short crop keeps the side line tidy while avoiding a rounded bob silhouette.",
        fallback_sample_image_url="styles/301.jpg",
        keywords=("crop", "two-block", "clean"),
        face_shapes=("round", "oval", "square"),
        ratio_modes=("cover", "balanced"),
        length_tags=("short",),
        vibe_tags=("natural", "chic"),
        scalp_tags=("straight", "waved"),
        color_tags=("black", "brown"),
        budget_tags=("low", "mid"),
        gender_branches=("male",),
        style_axes=("two_block:strong", "front_styling:up", "parting:non_parted"),
    ),
    StyleProfile(
        style_id=302,
        fallback_name="Soft Down Perm",
        fallback_description="Soft front weight and controlled curl create a masculine down style without widening the cheek line.",
        fallback_sample_image_url="styles/302.jpg",
        keywords=("down perm", "soft", "male"),
        face_shapes=("round", "square", "oval"),
        ratio_modes=("cover", "balanced"),
        length_tags=("short", "medium"),
        vibe_tags=("natural", "chic"),
        scalp_tags=("waved", "curly"),
        color_tags=("black", "brown", "ash"),
        budget_tags=("mid", "high"),
        gender_branches=("male",),
        style_axes=("two_block:soft", "front_styling:down", "parting:non_parted"),
    ),
    StyleProfile(
        style_id=303,
        fallback_name="Classic Side Part",
        fallback_description="A clean parted line suits strong facial balance while keeping the outline masculine and controlled.",
        fallback_sample_image_url="styles/303.jpg",
        keywords=("side part", "classic", "male"),
        face_shapes=("oval", "long", "square"),
        ratio_modes=("balanced", "expose"),
        length_tags=("short", "medium"),
        vibe_tags=("chic", "elegant"),
        scalp_tags=("straight", "waved"),
        color_tags=("black", "brown", "ash"),
        budget_tags=("mid", "high"),
        gender_branches=("male",),
        style_axes=("two_block:none", "front_styling:up", "parting:parted"),
    ),
    StyleProfile(
        style_id=304,
        fallback_name="Textured Short Crop",
        fallback_description="Short texture on top adds shape without drifting into a feminine rounded line.",
        fallback_sample_image_url="styles/304.jpg",
        keywords=("textured crop", "short", "masculine"),
        face_shapes=("round", "square", "triangle"),
        ratio_modes=("cover", "balanced"),
        length_tags=("short",),
        vibe_tags=("natural", "chic"),
        scalp_tags=("straight", "damaged"),
        color_tags=("black", "brown"),
        budget_tags=("low", "mid"),
        gender_branches=("male",),
        style_axes=("two_block:none", "front_styling:down", "parting:non_parted"),
    ),
    StyleProfile(
        style_id=305,
        fallback_name="Natural Curl Two-Block",
        fallback_description="Natural curl texture is kept compact on the side so the result reads as a male two-block, not a bob.",
        fallback_sample_image_url="styles/305.jpg",
        keywords=("curly", "two-block", "natural"),
        face_shapes=("square", "oval", "round"),
        ratio_modes=("cover", "balanced"),
        length_tags=("short", "medium"),
        vibe_tags=("natural", "chic"),
        scalp_tags=("curly", "waved"),
        color_tags=("black", "brown", "ash"),
        budget_tags=("mid", "high"),
        gender_branches=("male",),
        style_axes=("two_block:soft", "front_styling:down", "parting:non_parted"),
    ),
    StyleProfile(
        style_id=306,
        fallback_name="Tapered Slick Part",
        fallback_description="A tapered part line keeps the forehead open and works best when the facial ratio already reads balanced.",
        fallback_sample_image_url="styles/306.jpg",
        keywords=("taper", "slick part", "sharp"),
        face_shapes=("oval", "long", "triangle"),
        ratio_modes=("expose", "balanced"),
        length_tags=("short", "medium"),
        vibe_tags=("chic", "elegant"),
        scalp_tags=("straight",),
        color_tags=("black", "brown", "ash"),
        budget_tags=("mid", "high"),
        gender_branches=("male",),
        style_axes=("two_block:none", "front_styling:up", "parting:parted"),
    ),
    StyleProfile(
        style_id=307,
        fallback_name="Medium Flow Layer",
        fallback_description="A controlled medium flow keeps length through the top while staying clearly in the male salon range.",
        fallback_sample_image_url="styles/307.jpg",
        keywords=("flow", "medium", "layer"),
        face_shapes=("oval", "triangle", "long"),
        ratio_modes=("balanced", "expose"),
        length_tags=("medium", "long"),
        vibe_tags=("natural", "chic"),
        scalp_tags=("straight", "waved"),
        color_tags=("black", "brown", "ash"),
        budget_tags=("high",),
        gender_branches=("male",),
        style_axes=("two_block:none", "front_styling:flexible", "parting:either"),
    ),
)


def _normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace("-", "").replace("_", "").replace(" ", "")


def _contains_any(value: str, keywords: Iterable[str]) -> bool:
    return any(keyword in value for keyword in keywords)


def canonical_length(value: str | None) -> str:
    value = _normalize_text(value)
    if _contains_any(value, ("숏", "쇼트", "short")):
        return "short"
    if _contains_any(value, ("보브", "단발", "bob", "lob")):
        return "bob"
    if _contains_any(value, ("중단발", "미디", "medium", "semilong", "semi")):
        return "medium"
    if _contains_any(value, ("롱", "긴머리", "long")):
        return "long"
    return "unknown"


def canonical_vibe(value: str | None) -> str:
    value = _normalize_text(value)
    if _contains_any(value, ("청순", "큐트", "cute")):
        return "cute"
    if _contains_any(value, ("시크", "chic")):
        return "chic"
    if _contains_any(value, ("자연", "내추럴", "natural", "casual")):
        return "natural"
    if _contains_any(value, ("우아", "엘레강", "elegant", "섹시", "sexy")):
        return "elegant"
    return "unknown"


def canonical_scalp(value: str | None) -> str:
    value = _normalize_text(value)
    if _contains_any(value, ("직모", "straight")):
        return "straight"
    if _contains_any(value, ("웨이브", "wave")):
        return "waved"
    if _contains_any(value, ("곱슬", "curl")):
        return "curly"
    if _contains_any(value, ("손상", "damaged")):
        return "damaged"
    return "unknown"


def canonical_color(value: str | None) -> str:
    value = _normalize_text(value)
    if _contains_any(value, ("흑발", "검정", "black")):
        return "black"
    if _contains_any(value, ("브라운", "brown")):
        return "brown"
    if _contains_any(value, ("애쉬", "ash")):
        return "ash"
    if _contains_any(value, ("브리치", "탈색", "bleach")):
        return "bleach"
    return "unknown"


def canonical_budget(value: str | None) -> str:
    value = _normalize_text(value)
    if value in {"low", "mid", "high"}:
        return value
    if _contains_any(value, ("3만원이하", "3만이하", "below3")):
        return "low"
    if _contains_any(value, ("3만5만", "3만에서5만", "5만원이하", "from3to5")):
        return "mid"
    if _contains_any(value, ("5만10만", "5만에서10만", "10만원이하", "from5to10", "10만")):
        return "high"
    if _contains_any(value, ("10만원이상", "10만이상", "over10")):
        return "high"
    return "unknown"


def canonical_face_shape(value: str | None) -> str:
    value = _normalize_text(value)
    if _contains_any(value, ("둥근", "round")):
        return "round"
    if _contains_any(value, ("계란", "타원", "oval")):
        return "oval"
    if _contains_any(value, ("긴", "long")):
        return "long"
    if _contains_any(value, ("각진", "square")):
        return "square"
    if _contains_any(value, ("역삼각", "triangle", "heart")):
        return "triangle"
    return "unknown"


def canonical_gender_branch(value: str | None) -> str:
    normalized = _normalize_text(value)
    if normalized in {"m", "male", "man", "남", "남성"}:
        return "male"
    if normalized in {"f", "female", "woman", "여", "여성"}:
        return "female"
    return "female"


def _field_value(source, key: str, default=None):
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _survey_profile_dict(survey) -> dict:
    value = _field_value(survey, "survey_profile")
    return value if isinstance(value, dict) else {}


def _survey_gender_branch(survey) -> str:
    survey_profile = _survey_profile_dict(survey)
    return canonical_gender_branch(
        _field_value(survey, "gender_branch")
        or survey_profile.get("gender_branch")
    )


def _survey_style_signal_tags(survey) -> set[str]:
    survey_profile = _survey_profile_dict(survey)
    style_axes = survey_profile.get("style_axes")
    if not isinstance(style_axes, dict):
        return set()
    return {
        f"{key}:{value}"
        for key, value in style_axes.items()
        if str(key).strip() and str(value).strip()
    }


def build_preference_vector(
    *,
    target_length: str | None,
    target_vibe: str | None,
    scalp_type: str | None,
    hair_colour: str | None,
    budget_range: str | None,
) -> list[float]:
    vector: list[float] = []
    vector.extend(_one_hot(canonical_length(target_length), ("short", "bob", "medium", "long")))
    vector.extend(_one_hot(canonical_vibe(target_vibe), ("cute", "chic", "natural", "elegant")))
    vector.extend(_one_hot(canonical_scalp(scalp_type), ("straight", "waved", "curly", "damaged")))
    vector.extend(_one_hot(canonical_color(hair_colour), ("black", "brown", "ash", "bleach")))
    vector.extend(_one_hot(canonical_budget(budget_range), ("low", "mid", "high", "unknown")))
    return vector[:VECTOR_DIMENSION]


def _one_hot(value: str, order: tuple[str, ...]) -> list[float]:
    vector = [0.0] * len(order)
    if value in order:
        vector[order.index(value)] = 1.0
    return vector


def infer_ratio_mode(score: float | None) -> str:
    if score is None:
        return "balanced"
    if score >= 0.9:
        return "expose"
    if score >= 0.82:
        return "balanced"
    return "cover"


def ratio_message(score: float | None) -> str:
    mode = infer_ratio_mode(score)
    if mode == "expose":
        return "Your facial balance is strong enough to suit styles that reveal the face line more clearly."
    if mode == "cover":
        return "A style with softer framing will help balance the side line and contour."
    return "A balanced silhouette is likely to feel more natural than a highly exposed line."


def score_recommendations(
    *,
    survey,
    analysis,
    styles_by_id: dict[int, object] | None = None,
    scoring_weights: ScoringWeights | None = None,
) -> list[dict]:
    styles_by_id = styles_by_id or {}
    scoring_weights = scoring_weights or DEFAULT_SCORING_WEIGHTS
    face_shape = canonical_face_shape(_field_value(analysis, "face_shape"))
    ratio_score = _field_value(analysis, "golden_ratio_score")
    ratio_mode = infer_ratio_mode(ratio_score)

    length_tag = canonical_length(_field_value(survey, "target_length"))
    vibe_tag = canonical_vibe(_field_value(survey, "target_vibe"))
    scalp_tag = canonical_scalp(_field_value(survey, "scalp_type"))
    color_tag = canonical_color(_field_value(survey, "hair_colour"))
    budget_tag = canonical_budget(_field_value(survey, "budget_range"))
    gender_branch = _survey_gender_branch(survey)
    style_signal_tags = _survey_style_signal_tags(survey)

    results: list[dict] = []

    candidate_profiles = [
        profile
        for profile in STYLE_CATALOG
        if gender_branch in profile.gender_branches
    ] or list(STYLE_CATALOG)

    for profile in candidate_profiles:
        face_score = _score_face(face_shape, profile, scoring_weights=scoring_weights)
        ratio_component = _score_ratio(ratio_mode, profile, scoring_weights=scoring_weights)
        preference_score, match_labels, matched_style_axes = _score_preference(
            length_tag=length_tag,
            vibe_tag=vibe_tag,
            scalp_tag=scalp_tag,
            color_tag=color_tag,
            budget_tag=budget_tag,
            style_signal_tags=style_signal_tags,
            profile=profile,
            scoring_weights=scoring_weights,
        )
        penalty = _score_penalty(
            length_tag=length_tag,
            vibe_tag=vibe_tag,
            profile=profile,
            preference_score=preference_score,
        )
        total = max(0.0, min(100.0, round(face_score + ratio_component + preference_score - penalty, 1)))

        style_model = styles_by_id.get(profile.style_id)
        style_name = getattr(style_model, "name", None) or profile.fallback_name
        style_description = getattr(style_model, "description", None) or profile.fallback_description
        sample_image_url = getattr(style_model, "image_url", None) or profile.fallback_sample_image_url
        explanation = build_llm_explanation(
            style_name=style_name,
            style_description=style_description,
            face_shape=face_shape,
            matched_labels=match_labels,
            ratio_score=ratio_score,
        )

        client_key = _field_value(survey, "client_id", _field_value(survey, "client", "0"))
        results.append(
            {
                "source": "generated",
                "style_id": profile.style_id,
                "style_name": style_name,
                "style_description": style_description,
                "keywords": list(profile.keywords),
                "sample_image_url": sample_image_url,
                "simulation_image_url": f"/media/synthetic/{client_key}_{profile.style_id}.jpg",
                "synthetic_image_url": f"/media/synthetic/{client_key}_{profile.style_id}.jpg",
                "llm_explanation": explanation,
                "reasoning": (
                    f"face {face_score:.1f}/{scoring_weights.face_weight:.0f} | "
                    f"ratio {ratio_component:.1f}/{scoring_weights.ratio_weight:.0f} | "
                    f"preference {preference_score:.1f}/{scoring_weights.preference_weight:.0f}"
                )
                + (f" | penalty -{penalty:.1f}" if penalty else ""),
                "reasoning_snapshot": {
                    "summary": (
                        f"face {face_score:.1f}/{scoring_weights.face_weight:.0f} | "
                        f"ratio {ratio_component:.1f}/{scoring_weights.ratio_weight:.0f} | "
                        f"preference {preference_score:.1f}/{scoring_weights.preference_weight:.0f}"
                    )
                    + (f" | penalty -{penalty:.1f}" if penalty else ""),
                    "face_shape": face_shape,
                    "ratio_mode": ratio_mode,
                    "face_score": round(face_score, 1),
                    "ratio_score": round(ratio_component, 1),
                    "preference_score": round(preference_score, 1),
                    "penalty": round(penalty, 1),
                    "total_score": total,
                    "matched_labels": match_labels,
                    "gender_branch": gender_branch,
                    "matched_style_axes": matched_style_axes,
                    "style_keywords": list(profile.keywords),
                    "scoring_profile": scoring_weights.profile,
                    "scoring_weights": scoring_weights.as_dict(),
                },
                "match_score": total,
            }
        )

    results.sort(key=lambda item: (-item["match_score"], item["style_id"]))
    for rank, item in enumerate(results[:5], start=1):
        item["rank"] = rank
    return results[:5]


def build_llm_explanation(
    *,
    style_name: str,
    style_description: str,
    face_shape: str,
    matched_labels: list[str],
    ratio_score: float | None,
) -> str:
    face_label = {
        "round": "둥근형",
        "oval": "계란형",
        "long": "긴형",
        "square": "각진형",
        "triangle": "역삼각형",
        "unknown": "중립형",
    }.get(face_shape, "중립형")
    if matched_labels:
        preference_text = "The style also aligns well with your preference signals (" + ", ".join(matched_labels) + ")."
    else:
        preference_text = "Preference data is limited, so the face analysis score carries more weight in this result."
    return (
        f"{style_name} is recommended as a strong match for a {face_label} profile. "
        f"{style_description} {preference_text} {ratio_message(ratio_score)}"
    )


def _score_face(face_shape: str, profile: StyleProfile, *, scoring_weights: ScoringWeights) -> float:
    baseline = round(scoring_weights.face_weight * 0.45, 1)
    if face_shape == "unknown":
        return baseline
    if face_shape in profile.face_shapes:
        return scoring_weights.face_weight
    if "oval" in profile.face_shapes:
        return round(scoring_weights.face_weight * 0.55, 1)
    return baseline


def _score_ratio(ratio_mode: str, profile: StyleProfile, *, scoring_weights: ScoringWeights) -> float:
    if ratio_mode in profile.ratio_modes:
        return scoring_weights.ratio_weight
    if "balanced" in profile.ratio_modes:
        return round(scoring_weights.ratio_weight * 0.6, 1)
    return round(scoring_weights.ratio_weight * 0.4, 1)


def _score_preference(
    *,
    length_tag: str,
    vibe_tag: str,
    scalp_tag: str,
    color_tag: str,
    budget_tag: str,
    style_signal_tags: set[str],
    profile: StyleProfile,
    scoring_weights: ScoringWeights,
) -> tuple[float, list[str], list[str]]:
    score = 0.0
    labels: list[str] = []
    weight_scale = scoring_weights.preference_weight / PREFERENCE_WEIGHT

    if length_tag in profile.length_tags:
        score += 14.0 * weight_scale
        labels.append("length")
    if vibe_tag in profile.vibe_tags:
        score += 12.0 * weight_scale
        labels.append("vibe")
    if scalp_tag in profile.scalp_tags:
        score += 6.0 * weight_scale
        labels.append("condition")
    if color_tag in profile.color_tags:
        score += 4.0 * weight_scale
        labels.append("color")
    if budget_tag in profile.budget_tags:
        score += 4.0 * weight_scale
        labels.append("budget")

    matched_style_axes = sorted(tag for tag in style_signal_tags if tag in profile.style_axes)
    if matched_style_axes:
        score += min(4.0, len(matched_style_axes) * 2.0) * weight_scale
        labels.append("styling")

    return min(scoring_weights.preference_weight, round(score, 1)), labels, matched_style_axes


def _score_penalty(*, length_tag: str, vibe_tag: str, profile: StyleProfile, preference_score: float) -> float:
    penalty = 0.0
    if length_tag != "unknown" and length_tag not in profile.length_tags:
        penalty += 6.0
    if vibe_tag != "unknown" and vibe_tag not in profile.vibe_tags:
        penalty += 4.0
    if preference_score < 10.0:
        penalty += 2.0
    return penalty

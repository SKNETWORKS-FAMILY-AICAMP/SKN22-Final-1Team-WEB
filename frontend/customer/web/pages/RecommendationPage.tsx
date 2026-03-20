import { useNavigate, useLocation } from "react-router";
import { MirrLayout } from "../components/MirrLayout";
import { Sparkles, RotateCcw, Home } from "lucide-react";

const HAIR_STYLES = [
  {
    id: 1,
    name: "클래식 레이어드 컷",
    nameEn: "Classic Layered Cut",
    match: 98,
    description: "자연스러운 레이어와 볼륨감으로 세련된 분위기를 연출합니다.",
    tags: ["중단발", "내추럴", "직모"],
    imageUrl:
      "https://images.unsplash.com/photo-1712213396688-c6f2d536671f?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&w=400",
    priceRange: "5~10만원",
    duration: "60분",
  },
  {
    id: 2,
    name: "소프트 웨이브 펌",
    nameEn: "Soft Wave Perm",
    match: 92,
    description: "부드럽고 자연스러운 웨이브로 여성스러운 매력을 더해줍니다.",
    tags: ["단발", "청순", "웨이브"],
    imageUrl:
      "https://images.unsplash.com/photo-1657830474906-2e505ad0440c?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&w=400",
    priceRange: "10~20만원",
    duration: "90분",
  },
  {
    id: 3,
    name: "애쉬 브라운 컬러",
    nameEn: "Ash Brown Color",
    match: 87,
    description: "트렌디한 애쉬 톤으로 시크하고 현대적인 감성을 표현합니다.",
    tags: ["롱", "시크", "애쉬"],
    imageUrl:
      "https://images.unsplash.com/photo-1740198321840-398cec9cb256?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&w=400",
    priceRange: "10~20만원",
    duration: "120분",
  },
  {
    id: 4,
    name: "텍스처드 숏컷",
    nameEn: "Textured Short Cut",
    match: 81,
    description: "모던하고 개성 있는 숏컷으로 새로운 스타일 변화를 경험하세요.",
    tags: ["숏", "캐주얼", "직모"],
    imageUrl:
      "https://images.unsplash.com/photo-1616226784481-fe333408ae3f?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&w=400",
    priceRange: "5만원 이하",
    duration: "45분",
  },
  {
    id: 5,
    name: "글로시 C컬 펌",
    nameEn: "Glossy C-Curl Perm",
    match: 76,
    description: "단정한 C컬 라인으로 얼굴형을 부드럽게 보완하고 윤기 있는 인상을 만듭니다.",
    tags: ["중단발", "내추럴", "C컬"],
    imageUrl:
      "https://images.unsplash.com/photo-1524504388940-b1c1722653e1?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&w=400",
    priceRange: "10~20만원",
    duration: "70분",
  },
];

export function RecommendationPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as {
    customerName?: string;
    selections?: Record<string, string>;
  } | null;

  const customerName = state?.customerName || "고객";
  const selections = state?.selections;

  return (
    <MirrLayout
      showBack
      backTo="/survey"
      progress={{ current: 5, total: 5 }}
    >
      <div className="flex-1 flex flex-col px-6 py-6 overflow-y-auto">
        {/* Header section */}
        <div style={{ marginBottom: "24px" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              marginBottom: "8px",
            }}
          >
            <Sparkles size={14} color="#C4963C" />
            <p
              style={{
                fontSize: "11px",
                color: "#C4963C",
                letterSpacing: "3px",
                fontFamily: "'Noto Sans KR', sans-serif",
              }}
            >
              AI 추천 결과
            </p>
          </div>
          <h2
            style={{
              fontSize: "20px",
              color: "#EED9B0",
              fontFamily: "'Noto Sans KR', sans-serif",
              fontWeight: 500,
              lineHeight: 1.5,
            }}
          >
            {customerName}님을 위한{" "}
            <span style={{ color: "#C4963C" }}>맞춤 헤어스타일</span>
          </h2>
        </div>

        {/* Selections summary */}
        {selections && (
          <div
            style={{
              padding: "14px 16px",
              backgroundColor: "rgba(196,150,60,0.05)",
              border: "1px solid rgba(196,150,60,0.15)",
              marginBottom: "20px",
            }}
          >
            <p
              style={{
                fontSize: "11px",
                color: "#5C5040",
                letterSpacing: "2px",
                marginBottom: "8px",
                fontFamily: "'Noto Sans KR', sans-serif",
              }}
            >
              선택된 취향
            </p>
            <div className="flex flex-wrap gap-2">
              {Object.entries(selections)
                .filter(([, v]) => v)
                .map(([k, v]) => (
                  <span
                    key={k}
                    style={{
                      padding: "4px 10px",
                      backgroundColor: "rgba(196,150,60,0.1)",
                      border: "1px solid rgba(196,150,60,0.25)",
                      color: "#C4963C",
                      fontSize: "11px",
                      fontFamily: "'Noto Sans KR', sans-serif",
                      letterSpacing: "0.5px",
                    }}
                  >
                    {v}
                  </span>
                ))}
            </div>
          </div>
        )}

        {/* Style cards */}
        <div className="flex flex-col gap-4">
          {HAIR_STYLES.map((style, idx) => (
            <div
              key={style.id}
              style={{
                backgroundColor: "#1A1610",
                border:
                  idx === 0
                    ? "1px solid rgba(196,150,60,0.4)"
                    : "1px solid #3A3020",
                overflow: "hidden",
                transition: "border-color 0.2s",
                cursor: "pointer",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLDivElement).style.borderColor =
                  "rgba(196,150,60,0.4)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLDivElement).style.borderColor =
                  idx === 0 ? "rgba(196,150,60,0.4)" : "#3A3020";
              }}
            >
              <div style={{ display: "flex", alignItems: "stretch" }}>
                {/* Image */}
                <div
                  style={{
                    width: "110px",
                    minHeight: "130px",
                    flexShrink: 0,
                    overflow: "hidden",
                    position: "relative",
                  }}
                >
                  <img
                    src={style.imageUrl}
                    alt={style.name}
                    style={{
                      width: "100%",
                      height: "100%",
                      objectFit: "cover",
                      display: "block",
                      filter: "brightness(0.85) saturate(0.9)",
                    }}
                  />
                  {idx === 0 && (
                    <div
                      style={{
                        position: "absolute",
                        top: "8px",
                        left: "8px",
                        padding: "3px 8px",
                        backgroundColor: "#C4963C",
                        color: "#0C0A07",
                        fontSize: "9px",
                        fontFamily: "'Noto Sans KR', sans-serif",
                        fontWeight: 600,
                        letterSpacing: "1px",
                      }}
                    >
                      BEST
                    </div>
                  )}
                </div>

                {/* Content */}
                <div style={{ flex: 1, padding: "16px" }}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "flex-start",
                      marginBottom: "6px",
                    }}
                  >
                    <div>
                      <p
                        style={{
                          fontSize: "15px",
                          color: "#EED9B0",
                          fontFamily: "'Noto Sans KR', sans-serif",
                          fontWeight: 500,
                          marginBottom: "2px",
                        }}
                      >
                        {style.name}
                      </p>
                      <p
                        style={{
                          fontSize: "10px",
                          color: "#5C5040",
                          fontFamily: "'Cormorant Garamond', serif",
                          letterSpacing: "1px",
                        }}
                      >
                        {style.nameEn}
                      </p>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <p
                        style={{
                          fontSize: "18px",
                          color: "#C4963C",
                          fontFamily: "'Cormorant Garamond', serif",
                          fontWeight: 500,
                          lineHeight: 1,
                        }}
                      >
                        {style.match}%
                      </p>
                      <p
                        style={{
                          fontSize: "9px",
                          color: "#5C5040",
                          fontFamily: "'Noto Sans KR', sans-serif",
                          letterSpacing: "1px",
                          marginTop: "2px",
                        }}
                      >
                        매칭률
                      </p>
                    </div>
                  </div>

                  <p
                    style={{
                      fontSize: "12px",
                      color: "#9A8B6A",
                      fontFamily: "'Noto Sans KR', sans-serif",
                      lineHeight: 1.6,
                      marginBottom: "10px",
                    }}
                  >
                    {style.description}
                  </p>

                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <div className="flex gap-1 flex-wrap">
                      {style.tags.map((tag) => (
                        <span
                          key={tag}
                          style={{
                            padding: "2px 8px",
                            backgroundColor: "rgba(196,150,60,0.08)",
                            border: "1px solid rgba(196,150,60,0.2)",
                            color: "#9A8B6A",
                            fontSize: "10px",
                            fontFamily: "'Noto Sans KR', sans-serif",
                          }}
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                    <div style={{ textAlign: "right", flexShrink: 0, marginLeft: "8px" }}>
                      <p
                        style={{
                          fontSize: "11px",
                          color: "#C4963C",
                          fontFamily: "'Noto Sans KR', sans-serif",
                        }}
                      >
                        {style.priceRange}
                      </p>
                      <p
                        style={{
                          fontSize: "10px",
                          color: "#5C5040",
                          fontFamily: "'Noto Sans KR', sans-serif",
                        }}
                      >
                        {style.duration}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Action buttons */}
        <div className="flex gap-3 mt-6 mb-2">
          <button
            onClick={() => navigate("/survey", { state })}
            style={{
              flex: 1,
              padding: "16px",
              backgroundColor: "transparent",
              border: "1px solid #3A3020",
              color: "#9A8B6A",
              fontFamily: "'Noto Sans KR', sans-serif",
              fontSize: "13px",
              letterSpacing: "1px",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "8px",
              transition: "all 0.2s",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.borderColor =
                "rgba(196,150,60,0.4)";
              (e.currentTarget as HTMLButtonElement).style.color = "#EED9B0";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.borderColor = "#3A3020";
              (e.currentTarget as HTMLButtonElement).style.color = "#9A8B6A";
            }}
          >
            <RotateCcw size={14} />
            설문 다시하기
          </button>
          <button
            onClick={() => navigate("/")}
            style={{
              flex: 1,
              padding: "16px",
              backgroundColor: "#C4963C",
              border: "none",
              color: "#0C0A07",
              fontFamily: "'Noto Sans KR', sans-serif",
              fontSize: "13px",
              fontWeight: 500,
              letterSpacing: "2px",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "8px",
              transition: "background-color 0.2s",
            }}
            onMouseEnter={(e) =>
              ((e.currentTarget as HTMLButtonElement).style.backgroundColor =
                "#D4A84D")
            }
            onMouseLeave={(e) =>
              ((e.currentTarget as HTMLButtonElement).style.backgroundColor =
                "#C4963C")
            }
          >
            <Home size={14} />
            처음으로
          </button>
        </div>
      </div>
    </MirrLayout>
  );
}

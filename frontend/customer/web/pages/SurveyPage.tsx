import { useState } from "react";
import { useNavigate, useLocation } from "react-router";
import { MirrLayout, GoldButton } from "../components/MirrLayout";

type Selections = {
  기장: string;
  분위기: string;
  모발상태: string;
  컬러: string;
  예산: string;
};

const SURVEY_CATEGORIES = [
  {
    key: "기장" as keyof Selections,
    label: "희망 길이",
    options: ["숏", "단발", "중단발", "롱"],
  },
  {
    key: "분위기" as keyof Selections,
    label: "분위기",
    options: ["청순", "시크", "캐주얼", "내추럴"],
  },
  {
    key: "모발상태" as keyof Selections,
    label: "모발 상태",
    options: ["직모", "웨이브", "곱슬", "손상모"],
  },
  {
    key: "컬러" as keyof Selections,
    label: "컬러",
    options: ["흑발", "브라운", "애쉬", "블리치"],
  },
  {
    key: "예산" as keyof Selections,
    label: "예산",
    options: ["5만원 이하", "5~10만", "10~20만", "20만 이상"],
  },
];

export function SurveyPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const passedState = location.state as Record<string, unknown> | null;

  const [selections, setSelections] = useState<Selections>({
    기장: "",
    분위기: "",
    모발상태: "",
    컬러: "",
    예산: "",
  });

  const totalSelected = Object.values(selections).filter(Boolean).length;
  const allSelected = totalSelected === 5;

  const toggle = (key: keyof Selections, value: string) => {
    setSelections((prev) => ({
      ...prev,
      [key]: prev[key] === value ? "" : value,
    }));
  };

  const handleConfirm = () => {
    navigate("/recommendation", {
      state: { ...passedState, selections },
    });
  };

  return (
    <MirrLayout
      showBack
      backTo="/dashboard"
      progress={{ current: 2, total: 5 }}
      footer={
        <div className="flex flex-col gap-2">
          <div className="flex justify-between items-center mb-1">
            <span
              style={{
                fontSize: "12px",
                color: "#9A8B6A",
                fontFamily: "'Noto Sans KR', sans-serif",
              }}
            >
              {totalSelected} / 5 항목 선택됨
            </span>
            {!allSelected && (
              <span
                style={{
                  fontSize: "11px",
                  color: "#5C5040",
                  fontFamily: "'Noto Sans KR', sans-serif",
                }}
              >
                모든 항목을 선택해주세요
              </span>
            )}
          </div>
          {/* Progress bar */}
          <div
            style={{
              width: "100%",
              height: "2px",
              backgroundColor: "#3A3020",
              marginBottom: "12px",
              borderRadius: "1px",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                height: "100%",
                width: `${(totalSelected / 5) * 100}%`,
                backgroundColor: "#C4963C",
                transition: "width 0.3s ease",
              }}
            />
          </div>
          <GoldButton onClick={handleConfirm} disabled={!allSelected}>
            확정
          </GoldButton>
        </div>
      }
    >
      <div className="flex-1 flex flex-col px-6 py-6 gap-0 overflow-y-auto">
        {/* Section title */}
        <div style={{ marginBottom: "24px" }}>
          <p
            style={{
              fontSize: "11px",
              color: "#9A8B6A",
              letterSpacing: "3px",
              marginBottom: "8px",
              fontFamily: "'Noto Sans KR', sans-serif",
            }}
          >
            취향 설문
          </p>
          <h2
            style={{
              fontSize: "20px",
              color: "#EED9B0",
              fontFamily: "'Noto Sans KR', sans-serif",
              fontWeight: 500,
            }}
          >
            최근의 취향은 어떠신가요?
          </h2>
        </div>

        {/* Categories */}
        <div className="flex flex-col gap-6">
          {SURVEY_CATEGORIES.map((category, idx) => (
            <div key={category.key}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "10px",
                  marginBottom: "12px",
                }}
              >
                <span
                  style={{
                    fontSize: "11px",
                    color: "rgba(196,150,60,0.5)",
                    fontFamily: "'Noto Sans KR', sans-serif",
                    letterSpacing: "1px",
                    minWidth: "16px",
                  }}
                >
                  {String(idx + 1).padStart(2, "0")}
                </span>
                <span
                  style={{
                    fontSize: "14px",
                    color: selections[category.key] ? "#EED9B0" : "#9A8B6A",
                    fontFamily: "'Noto Sans KR', sans-serif",
                    letterSpacing: "1px",
                    transition: "color 0.2s",
                  }}
                >
                  {category.label}
                </span>
                {selections[category.key] && (
                  <span
                    style={{
                      fontSize: "11px",
                      color: "#C4963C",
                      fontFamily: "'Noto Sans KR', sans-serif",
                      marginLeft: "4px",
                    }}
                  >
                    · {selections[category.key]}
                  </span>
                )}
              </div>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
                  gap: "8px",
                }}
              >
                {category.options.map((option) => {
                  const isSelected = selections[category.key] === option;
                  return (
                    <button
                      key={option}
                      onClick={() => toggle(category.key, option)}
                      style={{
                        width: "100%",
                        padding: "12px 0",
                        backgroundColor: isSelected
                          ? "rgba(196,150,60,0.15)"
                          : "#1A1610",
                        border: isSelected
                          ? "1px solid #C4963C"
                          : "1px solid #3A3020",
                        color: isSelected ? "#C4963C" : "#9A8B6A",
                        fontFamily: "'Noto Sans KR', sans-serif",
                        fontSize: "13px",
                        fontWeight: isSelected ? 500 : 400,
                        cursor: "pointer",
                        letterSpacing: "1px",
                        transition: "all 0.2s",
                        textAlign: "center",
                      }}
                      onMouseEnter={(e) => {
                        if (!isSelected) {
                          (e.currentTarget as HTMLButtonElement).style.borderColor =
                            "rgba(196,150,60,0.4)";
                          (e.currentTarget as HTMLButtonElement).style.color =
                            "#EED9B0";
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (!isSelected) {
                          (e.currentTarget as HTMLButtonElement).style.borderColor =
                            "#3A3020";
                          (e.currentTarget as HTMLButtonElement).style.color =
                            "#9A8B6A";
                        }
                      }}
                    >
                      {option}
                    </button>
                  );
                })}
              </div>

              {idx < SURVEY_CATEGORIES.length - 1 && (
                <div
                  style={{
                    height: "1px",
                    backgroundColor: "rgba(58,48,32,0.5)",
                    marginTop: "20px",
                  }}
                />
              )}
            </div>
          ))}
        </div>
      </div>
    </MirrLayout>
  );
}

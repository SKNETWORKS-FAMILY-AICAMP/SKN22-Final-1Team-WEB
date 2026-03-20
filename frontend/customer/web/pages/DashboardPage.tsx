import { useNavigate, useLocation } from "react-router";
import { MirrLayout } from "../components/MirrLayout";
import { Sparkles, ClipboardList } from "lucide-react";

export function DashboardPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as {
    name?: string;
    gender?: string;
    phone?: string;
    isNew?: boolean;
  } | null;

  const customerName = state?.name || "고객";
  const isNew = state?.isNew ?? true;

  return (
    <MirrLayout>
      <div className="flex-1 flex flex-col px-6 py-8 gap-6">
        {/* Welcome section */}
        <div
          style={{
            padding: "28px 24px",
            border: "1px solid rgba(196,150,60,0.2)",
            backgroundColor: "rgba(26,22,16,0.8)",
            position: "relative",
            overflow: "hidden",
          }}
        >
          {/* Decorative corner */}
          <div
            style={{
              position: "absolute",
              top: 0,
              right: 0,
              width: "80px",
              height: "80px",
              borderLeft: "1px solid rgba(196,150,60,0.15)",
              borderBottom: "1px solid rgba(196,150,60,0.15)",
            }}
          />
          <p
            style={{
              fontSize: "11px",
              color: "#9A8B6A",
              letterSpacing: "3px",
              marginBottom: "10px",
              fontFamily: "'Noto Sans KR', sans-serif",
            }}
          >
            {isNew ? "WELCOME · 신규 고객" : "WELCOME BACK · 재방문 고객"}
          </p>
          <h2
            style={{
              fontSize: "22px",
              color: "#EED9B0",
              fontFamily: "'Noto Sans KR', sans-serif",
              fontWeight: 500,
              lineHeight: 1.5,
              marginBottom: "4px",
            }}
          >
            어서 오세요,{" "}
            <span style={{ color: "#C4963C" }}>{customerName}</span> 고객님!
          </h2>
          {!isNew && (
            <p
              style={{
                fontSize: "13px",
                color: "#9A8B6A",
                fontFamily: "'Noto Sans KR', sans-serif",
                marginTop: "6px",
              }}
            >
              이전 상담 이력을 불러왔습니다.
            </p>
          )}
        </div>

        {/* Service options */}
        <div>
          <p
            style={{
              fontSize: "11px",
              color: "#5C5040",
              letterSpacing: "3px",
              marginBottom: "16px",
              fontFamily: "'Noto Sans KR', sans-serif",
            }}
          >
            서비스 선택
          </p>

          <div className="flex flex-col gap-4">
            {/* Survey option */}
            <button
              onClick={() =>
                navigate("/survey", { state: { customerName, ...state } })
              }
              style={{
                width: "100%",
                padding: "24px",
                backgroundColor: "#1A1610",
                border: "1px solid #3A3020",
                color: "#EED9B0",
                fontFamily: "'Noto Sans KR', sans-serif",
                cursor: "pointer",
                transition: "all 0.2s",
                textAlign: "left",
                display: "flex",
                alignItems: "center",
                gap: "16px",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.borderColor =
                  "rgba(196,150,60,0.4)";
                (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                  "#231E14";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.borderColor =
                  "#3A3020";
                (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                  "#1A1610";
              }}
            >
              <div
                style={{
                  width: "44px",
                  height: "44px",
                  borderRadius: "50%",
                  backgroundColor: "rgba(196,150,60,0.1)",
                  border: "1px solid rgba(196,150,60,0.3)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                }}
              >
                <ClipboardList size={20} color="#C4963C" />
              </div>
              <div>
                <p
                  style={{
                    fontSize: "15px",
                    fontWeight: 500,
                    letterSpacing: "1px",
                    marginBottom: "4px",
                  }}
                >
                  현재 취향 입력
                </p>
                <p
                  style={{
                    fontSize: "12px",
                    color: "#9A8B6A",
                    letterSpacing: "0.5px",
                  }}
                >
                  설문 조사 페이지로 이동합니다
                </p>
              </div>
              <span style={{ marginLeft: "auto", color: "#9A8B6A", fontSize: "20px" }}>
                →
              </span>
            </button>

            {/* Recommendation option */}
            <button
              onClick={() =>
                navigate("/recommendation", { state: { customerName, ...state } })
              }
              style={{
                width: "100%",
                padding: "24px",
                backgroundColor: "rgba(196,150,60,0.06)",
                border: "1px solid rgba(196,150,60,0.25)",
                color: "#EED9B0",
                fontFamily: "'Noto Sans KR', sans-serif",
                cursor: "pointer",
                transition: "all 0.2s",
                textAlign: "left",
                display: "flex",
                alignItems: "center",
                gap: "16px",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                  "rgba(196,150,60,0.1)";
                (e.currentTarget as HTMLButtonElement).style.borderColor =
                  "rgba(196,150,60,0.5)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                  "rgba(196,150,60,0.06)";
                (e.currentTarget as HTMLButtonElement).style.borderColor =
                  "rgba(196,150,60,0.25)";
              }}
            >
              <div
                style={{
                  width: "44px",
                  height: "44px",
                  borderRadius: "50%",
                  backgroundColor: "rgba(196,150,60,0.15)",
                  border: "1px solid rgba(196,150,60,0.4)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                }}
              >
                <Sparkles size={20} color="#C4963C" />
              </div>
              <div>
                <p
                  style={{
                    fontSize: "15px",
                    fontWeight: 500,
                    letterSpacing: "1px",
                    marginBottom: "4px",
                    color: "#C4963C",
                  }}
                >
                  헤어 스타일 추천
                </p>
                <p
                  style={{
                    fontSize: "12px",
                    color: "#9A8B6A",
                    letterSpacing: "0.5px",
                  }}
                >
                  AI가 최적의 헤어스타일을 추천합니다
                </p>
              </div>
              <span style={{ marginLeft: "auto", color: "#C4963C", fontSize: "20px" }}>
                →
              </span>
            </button>
          </div>
        </div>

        {/* Customer info summary */}
        {state?.phone && (
          <div
            style={{
              marginTop: "auto",
              padding: "14px 18px",
              backgroundColor: "rgba(26,22,16,0.5)",
              border: "1px solid #3A3020",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <p
              style={{
                fontSize: "12px",
                color: "#5C5040",
                fontFamily: "'Noto Sans KR', sans-serif",
              }}
            >
              {state.phone}
            </p>
            <button
              onClick={() => navigate("/")}
              style={{
                fontSize: "12px",
                color: "#5C5040",
                fontFamily: "'Noto Sans KR', sans-serif",
                background: "none",
                border: "none",
                cursor: "pointer",
                letterSpacing: "1px",
              }}
            >
              종료
            </button>
          </div>
        )}
      </div>
    </MirrLayout>
  );
}

import { useNavigate } from "react-router";
import { MirrLayout, GoldButton, OutlineButton } from "../components/MirrLayout";

const SALON_NAME = "헤어살롱 루미";

export function ServiceStartPage() {
  const navigate = useNavigate();

  return (
    <MirrLayout>
      <div className="flex-1 flex flex-col px-6 py-8 gap-6">
        {/* Welcome card */}
        <div
          style={{
            padding: "28px 24px",
            border: "1px solid rgba(196,150,60,0.2)",
            backgroundColor: "rgba(26,22,16,0.8)",
          }}
        >
          <p
            style={{
              fontSize: "11px",
              color: "#9A8B6A",
              letterSpacing: "3px",
              marginBottom: "12px",
              fontFamily: "'Noto Sans KR', sans-serif",
            }}
          >
            WELCOME
          </p>
          <h2
            style={{
              fontSize: "22px",
              color: "#EED9B0",
              fontFamily: "'Noto Sans KR', sans-serif",
              fontWeight: 500,
              lineHeight: 1.6,
              marginBottom: "6px",
            }}
          >
            어서 오세요, 고객님!
          </h2>
          <p
            style={{
              fontSize: "15px",
              color: "#9A8B6A",
              fontFamily: "'Noto Sans KR', sans-serif",
              lineHeight: 1.6,
            }}
          >
            <span style={{ color: "#C4963C" }}>{SALON_NAME}</span> AI 디자이너입니다.
          </p>
        </div>

        {/* Instructions */}
        <div
          style={{
            padding: "20px",
            backgroundColor: "rgba(196,150,60,0.05)",
            border: "1px solid rgba(196,150,60,0.12)",
          }}
        >
          <p
            style={{
              fontSize: "13px",
              color: "#9A8B6A",
              fontFamily: "'Noto Sans KR', sans-serif",
              lineHeight: 1.8,
              textAlign: "center",
              letterSpacing: "0.5px",
            }}
          >
            AI 상담이 필요하시다면
            <br />
            아래 버튼을 선택해 시작해주세요
          </p>
        </div>

        {/* Divider */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "12px",
          }}
        >
          <div style={{ flex: 1, height: "1px", backgroundColor: "#3A3020" }} />
          <span style={{ fontSize: "11px", color: "#5C5040", letterSpacing: "2px" }}>
            선택
          </span>
          <div style={{ flex: 1, height: "1px", backgroundColor: "#3A3020" }} />
        </div>

        {/* Action buttons */}
        <div className="flex flex-col gap-4">
          <div>
            <p
              style={{
                fontSize: "11px",
                color: "#5C5040",
                letterSpacing: "2px",
                marginBottom: "10px",
                fontFamily: "'Noto Sans KR', sans-serif",
              }}
            >
              기존 고객
            </p>
            <GoldButton onClick={() => navigate("/existing")}>
              기존 고객 ID (전화번호) 입력
            </GoldButton>
          </div>

          <div>
            <p
              style={{
                fontSize: "11px",
                color: "#5C5040",
                letterSpacing: "2px",
                marginBottom: "10px",
                fontFamily: "'Noto Sans KR', sans-serif",
              }}
            >
              신규 고객
            </p>
            <OutlineButton onClick={() => navigate("/register")}>
              신규 고객 회원가입 바로가기
            </OutlineButton>
          </div>
        </div>

        {/* Bottom note */}
        <div style={{ marginTop: "auto", paddingTop: "24px" }}>
          <div
            style={{
              padding: "16px 18px",
              backgroundColor: "rgba(26,22,16,0.6)",
              border: "1px solid #3A3020",
            }}
          >
            <p
              style={{
                fontSize: "12px",
                color: "#5C5040",
                fontFamily: "'Noto Sans KR', sans-serif",
                lineHeight: 1.8,
              }}
            >
              개인정보는 암호화 저장되며 헤어 상담 목적으로만 사용됩니다.
              <br />
              동의 후 진행해주세요.
            </p>
          </div>
        </div>
      </div>
    </MirrLayout>
  );
}

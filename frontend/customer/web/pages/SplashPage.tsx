import { useNavigate } from "react-router";
import { useEffect } from "react";

export function SplashPage() {
  const navigate = useNavigate();

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, []);

  return (
    <div
      className="min-h-screen w-full flex flex-col items-center justify-center relative overflow-hidden"
      style={{
        background: "linear-gradient(160deg, #0C0A07 0%, #1A1610 60%, #0C0A07 100%)",
        fontFamily: "'Noto Sans KR', sans-serif",
        width: "100vw",
        minHeight: "100vh",
        padding: "24px 16px",
      }}
    >
      {/* Decorative rings */}
      <div
        className="absolute pointer-events-none"
        style={{
          width: "700px",
          height: "700px",
          borderRadius: "50%",
          border: "1px solid rgba(196,150,60,0.08)",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
        }}
      />
      <div
        className="absolute pointer-events-none"
        style={{
          width: "500px",
          height: "500px",
          borderRadius: "50%",
          border: "1px solid rgba(196,150,60,0.07)",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
        }}
      />
      <div
        className="absolute pointer-events-none"
        style={{
          width: "340px",
          height: "340px",
          borderRadius: "50%",
          border: "1px solid rgba(196,150,60,0.06)",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
        }}
      />
      {/* Top-right accent */}
      <div
        className="absolute pointer-events-none"
        style={{
          width: "280px",
          height: "280px",
          borderRadius: "50%",
          border: "1px solid rgba(196,150,60,0.1)",
          top: "-80px",
          right: "10%",
        }}
      />
      {/* Bottom-left accent */}
      <div
        className="absolute pointer-events-none"
        style={{
          width: "200px",
          height: "200px",
          borderRadius: "50%",
          border: "1px solid rgba(196,150,60,0.08)",
          bottom: "-60px",
          left: "8%",
        }}
      />

      {/* Main content */}
      <div
        className="flex flex-col items-center relative z-10"
        style={{ width: "100%", maxWidth: "520px", padding: "0 40px", margin: "0 auto" }}
      >
        {/* Thin top line accent */}
        <div
          style={{
            width: "40px",
            height: "1px",
            backgroundColor: "rgba(196,150,60,0.5)",
            marginBottom: "40px",
          }}
        />

        {/* Logo */}
        <h1
          style={{
            fontFamily: "'Cormorant Garamond', serif",
            fontSize: "80px",
            fontWeight: 400,
            color: "#C4963C",
            letterSpacing: "4px",
            lineHeight: 1,
            marginBottom: "12px",
            textAlign: "center",
          }}
        >
          MirrAI
        </h1>

        {/* Subtitle */}
        <p
          style={{
            fontSize: "12px",
            color: "#9A8B6A",
            letterSpacing: "4px",
            textAlign: "center",
            marginBottom: "4px",
          }}
        >
          AI 헤어스타일 추천 서비스
        </p>
        <p
          style={{
            fontSize: "11px",
            color: "#5C5040",
            letterSpacing: "2px",
            textAlign: "center",
          }}
        >
          미용 지원 인공지능 서비스
        </p>

        {/* Divider */}
        <div
          style={{
            width: "60px",
            height: "1px",
            backgroundColor: "rgba(196,150,60,0.3)",
            margin: "40px 0",
          }}
        />

        {/* Buttons */}
        <div className="flex flex-col gap-4 w-full">
          <button
            onClick={() => navigate("/service")}
            style={{
              width: "100%",
              padding: "20px",
              backgroundColor: "#C4963C",
              color: "#0C0A07",
              fontSize: "15px",
              fontWeight: 500,
              letterSpacing: "4px",
              border: "none",
              cursor: "pointer",
              fontFamily: "'Noto Sans KR', sans-serif",
              transition: "background-color 0.2s",
            }}
            onMouseEnter={(e) =>
              ((e.currentTarget as HTMLButtonElement).style.backgroundColor = "#D4A84D")
            }
            onMouseLeave={(e) =>
              ((e.currentTarget as HTMLButtonElement).style.backgroundColor = "#C4963C")
            }
          >
            매장 서비스 개시
          </button>

          <button
            onClick={() => navigate("/admin")}
            style={{
              width: "100%",
              padding: "16px",
              backgroundColor: "transparent",
              color: "rgba(196,150,60,0.7)",
              fontSize: "13px",
              letterSpacing: "3px",
              border: "1px solid rgba(196,150,60,0.3)",
              cursor: "pointer",
              fontFamily: "'Noto Sans KR', sans-serif",
              transition: "all 0.2s",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.borderColor =
                "rgba(196,150,60,0.7)";
              (e.currentTarget as HTMLButtonElement).style.color = "#C4963C";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.borderColor =
                "rgba(196,150,60,0.3)";
              (e.currentTarget as HTMLButtonElement).style.color = "rgba(196,150,60,0.7)";
            }}
          >
            관리자 로그인
          </button>
        </div>
      </div>
    </div>
  );
}

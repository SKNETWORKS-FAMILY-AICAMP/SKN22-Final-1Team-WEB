import { useState } from "react";
import { useNavigate } from "react-router";
import { Eye, EyeOff } from "lucide-react";

export function AdminPage() {
  const navigate = useNavigate();
  const [salonId, setSalonId] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");

  const handleLogin = () => {
    if (salonId === "admin" && password === "1234") {
      navigate("/");
    } else {
      setError("아이디 또는 비밀번호가 올바르지 않습니다.");
    }
  };

  return (
    <div
      className="min-h-screen w-full flex flex-col items-center justify-center relative overflow-hidden"
      style={{
        background: "linear-gradient(160deg, #0C0A07 0%, #1A1610 60%, #0C0A07 100%)",
        fontFamily: "'Noto Sans KR', sans-serif",
      }}
    >
      {/* Decorative rings */}
      <div
        className="absolute pointer-events-none"
        style={{
          width: "600px",
          height: "600px",
          borderRadius: "50%",
          border: "1px solid rgba(196,150,60,0.06)",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
        }}
      />
      <div
        className="absolute pointer-events-none"
        style={{
          width: "420px",
          height: "420px",
          borderRadius: "50%",
          border: "1px solid rgba(196,150,60,0.05)",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
        }}
      />

      <div
        className="w-full relative z-10"
        style={{ maxWidth: "440px", padding: "0 40px" }}
      >
        {/* Logo */}
        <div style={{ textAlign: "center", marginBottom: "40px" }}>
          <h1
            style={{
              fontFamily: "'Cormorant Garamond', serif",
              fontSize: "48px",
              fontWeight: 400,
              color: "#C4963C",
              letterSpacing: "4px",
              marginBottom: "8px",
            }}
          >
            MirrAI
          </h1>
          <p
            style={{
              fontSize: "11px",
              color: "#5C5040",
              letterSpacing: "3px",
            }}
          >
            관리자 로그인
          </p>
        </div>

        {/* Form */}
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <label
              style={{
                fontSize: "13px",
                color: "#9A8B6A",
                letterSpacing: "1px",
              }}
            >
              매장 ID
            </label>
            <input
              type="text"
              placeholder="매장 아이디를 입력해주세요"
              value={salonId}
              onChange={(e) => {
                setSalonId(e.target.value);
                setError("");
              }}
              style={{
                width: "100%",
                padding: "16px 18px",
                backgroundColor: "#1A1610",
                border: "1px solid #3A3020",
                color: "#EED9B0",
                fontSize: "15px",
                outline: "none",
                fontFamily: "'Noto Sans KR', sans-serif",
                transition: "border-color 0.2s",
              }}
              onFocus={(e) => {
                e.currentTarget.style.borderColor = "rgba(196,150,60,0.6)";
              }}
              onBlur={(e) => {
                e.currentTarget.style.borderColor = "#3A3020";
              }}
            />
          </div>

          <div className="flex flex-col gap-2">
            <label
              style={{
                fontSize: "13px",
                color: "#9A8B6A",
                letterSpacing: "1px",
              }}
            >
              비밀번호
            </label>
            <div style={{ position: "relative" }}>
              <input
                type={showPw ? "text" : "password"}
                placeholder="비밀번호를 입력해주세요"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  setError("");
                }}
                style={{
                  width: "100%",
                  padding: "16px 48px 16px 18px",
                  backgroundColor: "#1A1610",
                  border: error ? "1px solid rgba(180,60,60,0.6)" : "1px solid #3A3020",
                  color: "#EED9B0",
                  fontSize: "15px",
                  outline: "none",
                  fontFamily: "'Noto Sans KR', sans-serif",
                  transition: "border-color 0.2s",
                }}
                onFocus={(e) => {
                  if (!error)
                    e.currentTarget.style.borderColor = "rgba(196,150,60,0.6)";
                }}
                onBlur={(e) => {
                  if (!error) e.currentTarget.style.borderColor = "#3A3020";
                }}
                onKeyDown={(e) => e.key === "Enter" && handleLogin()}
              />
              <button
                onClick={() => setShowPw((v) => !v)}
                style={{
                  position: "absolute",
                  right: "14px",
                  top: "50%",
                  transform: "translateY(-50%)",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "#5C5040",
                  display: "flex",
                  alignItems: "center",
                }}
              >
                {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          {error && (
            <p
              style={{
                fontSize: "12px",
                color: "rgba(220,100,100,0.8)",
                fontFamily: "'Noto Sans KR', sans-serif",
              }}
            >
              {error}
            </p>
          )}

          <button
            onClick={handleLogin}
            disabled={!salonId || !password}
            style={{
              width: "100%",
              padding: "18px",
              marginTop: "8px",
              backgroundColor: salonId && password ? "#C4963C" : "#3A3020",
              color: salonId && password ? "#0C0A07" : "#5C5040",
              fontSize: "14px",
              fontWeight: 500,
              letterSpacing: "3px",
              border: "none",
              cursor: salonId && password ? "pointer" : "not-allowed",
              fontFamily: "'Noto Sans KR', sans-serif",
              transition: "background-color 0.2s",
            }}
            onMouseEnter={(e) => {
              if (salonId && password)
                (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                  "#D4A84D";
            }}
            onMouseLeave={(e) => {
              if (salonId && password)
                (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                  "#C4963C";
            }}
          >
            로그인
          </button>
        </div>

        {/* Back link */}
        <div style={{ textAlign: "center", marginTop: "28px" }}>
          <button
            onClick={() => navigate("/")}
            style={{
              background: "none",
              border: "none",
              color: "#5C5040",
              fontSize: "12px",
              fontFamily: "'Noto Sans KR', sans-serif",
              cursor: "pointer",
              letterSpacing: "1px",
              transition: "color 0.2s",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.color = "#9A8B6A";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.color = "#5C5040";
            }}
          >
            ← 메인으로 돌아가기
          </button>
        </div>

        {/* Demo hint */}
        <div
          style={{
            marginTop: "32px",
            padding: "12px 16px",
            backgroundColor: "rgba(26,22,16,0.5)",
            border: "1px solid rgba(58,48,32,0.5)",
            textAlign: "center",
          }}
        >
          <p
            style={{
              fontSize: "11px",
              color: "#5C5040",
              fontFamily: "'Noto Sans KR', sans-serif",
              letterSpacing: "0.5px",
            }}
          >
            테스트: ID <span style={{ color: "#9A8B6A" }}>admin</span> / PW{" "}
            <span style={{ color: "#9A8B6A" }}>1234</span>
          </p>
        </div>
      </div>
    </div>
  );
}

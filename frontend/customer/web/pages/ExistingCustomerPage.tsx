import { useState } from "react";
import { useNavigate } from "react-router";
import { MirrLayout, GoldButton } from "../components/MirrLayout";

const MOCK_CUSTOMERS = [
  { name: "김갑환", phone: "01098746541", gender: "남성" },
  { name: "이지은", phone: "01012345678", gender: "여성" },
  { name: "박서준", phone: "01087654321", gender: "남성" },
  { name: "최수연", phone: "01056789012", gender: "여성" },
];

export function ExistingCustomerPage() {
  const navigate = useNavigate();
  const [phone, setPhone] = useState("");
  const [error, setError] = useState("");
  const [found, setFound] = useState<(typeof MOCK_CUSTOMERS)[0] | null>(null);

  const handlePhoneChange = (v: string) => {
    setPhone(v);
    setError("");
    setFound(null);
    const customer = MOCK_CUSTOMERS.find((c) => c.phone === v.replace(/-/g, ""));
    if (customer) setFound(customer);
  };

  const handleLogin = () => {
    const customer = MOCK_CUSTOMERS.find(
      (c) => c.phone === phone.replace(/-/g, "")
    );
    if (customer) {
      navigate("/dashboard", {
        state: { name: customer.name, phone: customer.phone, gender: customer.gender, isNew: false },
      });
    } else {
      setError("등록된 고객 정보를 찾을 수 없습니다. 신규 회원가입을 이용해주세요.");
    }
  };

  return (
    <MirrLayout
      showBack
      backTo="/service"
      progress={{ current: 1, total: 5 }}
      footer={
        <GoldButton onClick={handleLogin} disabled={phone.length < 10}>
          로그인
        </GoldButton>
      }
    >
      <div className="flex-1 flex flex-col px-6 py-8 gap-6">
        {/* Section title */}
        <div>
          <p
            style={{
              fontSize: "11px",
              color: "#9A8B6A",
              letterSpacing: "3px",
              marginBottom: "8px",
              fontFamily: "'Noto Sans KR', sans-serif",
            }}
          >
            기존 고객 로그인
          </p>
          <h2
            style={{
              fontSize: "20px",
              color: "#EED9B0",
              fontFamily: "'Noto Sans KR', sans-serif",
              fontWeight: 500,
            }}
          >
            고객 정보 조회
          </h2>
        </div>

        {/* Instructions */}
        <p
          style={{
            fontSize: "13px",
            color: "#9A8B6A",
            fontFamily: "'Noto Sans KR', sans-serif",
            lineHeight: 1.8,
          }}
        >
          등록하신 전화번호를 입력하시면 이전 상담 이력을 불러올 수 있습니다.
        </p>

        {/* Phone input */}
        <div className="flex flex-col gap-2">
          <label
            style={{
              fontSize: "14px",
              color: "#9A8B6A",
              letterSpacing: "1px",
              fontFamily: "'Noto Sans KR', sans-serif",
            }}
          >
            연락처 (ID)
          </label>
          <input
            type="tel"
            placeholder="010-0000-0000"
            value={phone}
            onChange={(e) => handlePhoneChange(e.target.value)}
            style={{
              width: "100%",
              padding: "16px 18px",
              backgroundColor: "#1A1610",
              border: error ? "1px solid rgba(180,60,60,0.6)" : "1px solid #3A3020",
              color: "#EED9B0",
              fontFamily: "'Noto Sans KR', sans-serif",
              fontSize: "18px",
              outline: "none",
              letterSpacing: "2px",
              transition: "border-color 0.2s",
            }}
            onFocus={(e) => {
              if (!error) e.currentTarget.style.borderColor = "rgba(196,150,60,0.6)";
            }}
            onBlur={(e) => {
              if (!error) e.currentTarget.style.borderColor = "#3A3020";
            }}
          />
        </div>

        {/* Found customer preview */}
        {found && (
          <div
            style={{
              padding: "16px 18px",
              backgroundColor: "rgba(196,150,60,0.08)",
              border: "1px solid rgba(196,150,60,0.3)",
              display: "flex",
              alignItems: "center",
              gap: "12px",
            }}
          >
            <div
              style={{
                width: "36px",
                height: "36px",
                borderRadius: "50%",
                backgroundColor: "rgba(196,150,60,0.2)",
                border: "1px solid rgba(196,150,60,0.4)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <span style={{ color: "#C4963C", fontSize: "14px" }}>
                {found.name[0]}
              </span>
            </div>
            <div>
              <p
                style={{
                  fontSize: "13px",
                  color: "#9A8B6A",
                  fontFamily: "'Noto Sans KR', sans-serif",
                  marginBottom: "2px",
                }}
              >
                고객 정보 확인
              </p>
              <p
                style={{
                  fontSize: "15px",
                  color: "#EED9B0",
                  fontFamily: "'Noto Sans KR', sans-serif",
                  fontWeight: 500,
                }}
              >
                {found.name} ({found.gender})
              </p>
            </div>
            <button
              onClick={handleLogin}
              style={{
                marginLeft: "auto",
                padding: "8px 14px",
                backgroundColor: "rgba(196,150,60,0.15)",
                border: "1px solid rgba(196,150,60,0.4)",
                color: "#C4963C",
                fontFamily: "'Noto Sans KR', sans-serif",
                fontSize: "12px",
                cursor: "pointer",
                letterSpacing: "1px",
                transition: "all 0.2s",
                whiteSpace: "nowrap",
              }}
            >
              이력 불러오기 →
            </button>
          </div>
        )}

        {/* Error */}
        {error && (
          <p
            style={{
              fontSize: "13px",
              color: "rgba(220,100,100,0.8)",
              fontFamily: "'Noto Sans KR', sans-serif",
              lineHeight: 1.6,
            }}
          >
            {error}
          </p>
        )}

        {/* Demo hint */}
        <div
          style={{
            marginTop: "auto",
            padding: "14px 16px",
            backgroundColor: "rgba(26,22,16,0.5)",
            border: "1px solid rgba(58,48,32,0.5)",
          }}
        >
          <p
            style={{
              fontSize: "11px",
              color: "#5C5040",
              fontFamily: "'Noto Sans KR', sans-serif",
              lineHeight: 1.8,
              letterSpacing: "0.5px",
            }}
          >
            테스트: 01098746541 (김갑환) · 01012345678 (이지은)
          </p>
        </div>
      </div>
    </MirrLayout>
  );
}

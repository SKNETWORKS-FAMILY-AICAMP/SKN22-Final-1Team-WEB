import { useState } from "react";
import { useNavigate } from "react-router";
import { MirrLayout, GoldButton, MirrInput } from "../components/MirrLayout";

export function NewCustomerPage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [gender, setGender] = useState<"남성" | "여성" | "">("");
  const [phone, setPhone] = useState("");

  const isValid = name.trim() && gender && phone.trim().length >= 10;

  const handleSubmit = () => {
    if (!isValid) return;
    navigate("/dashboard", {
      state: { name, gender, phone, isNew: true },
    });
  };

  return (
    <MirrLayout
      showBack
      backTo="/service"
      progress={{ current: 1, total: 5 }}
      footer={
        <GoldButton onClick={handleSubmit} disabled={!isValid}>
          가입 완료
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
            STEP 1 · 회원가입
          </p>
          <h2
            style={{
              fontSize: "20px",
              color: "#EED9B0",
              fontFamily: "'Noto Sans KR', sans-serif",
              fontWeight: 500,
            }}
          >
            고객 정보 입력
          </h2>
        </div>

        {/* Form */}
        <div className="flex flex-col gap-5">
          <MirrInput
            label="이름"
            placeholder="이름을 입력해주세요"
            value={name}
            onChange={setName}
          />

          {/* Gender toggle */}
          <div className="flex flex-col gap-2">
            <label
              style={{
                fontSize: "14px",
                color: "#9A8B6A",
                letterSpacing: "1px",
                fontFamily: "'Noto Sans KR', sans-serif",
              }}
            >
              성별
            </label>
            <div className="flex gap-3">
              {(["남성", "여성"] as const).map((g) => (
                <button
                  key={g}
                  onClick={() => setGender(g)}
                  style={{
                    flex: 1,
                    padding: "14px",
                    backgroundColor:
                      gender === g ? "#C4963C" : "#1A1610",
                    color: gender === g ? "#0C0A07" : "#9A8B6A",
                    border:
                      gender === g
                        ? "1px solid #C4963C"
                        : "1px solid #3A3020",
                    fontFamily: "'Noto Sans KR', sans-serif",
                    fontSize: "14px",
                    fontWeight: gender === g ? 500 : 400,
                    cursor: "pointer",
                    letterSpacing: "2px",
                    transition: "all 0.2s",
                  }}
                >
                  {g}
                </button>
              ))}
            </div>
          </div>

          <MirrInput
            label="전화번호 (ID)"
            placeholder="010-0000-0000"
            value={phone}
            onChange={setPhone}
            type="tel"
          />
        </div>

        {/* Privacy notice */}
        <div
          style={{
            marginTop: "8px",
            padding: "16px 18px",
            backgroundColor: "#1A1610",
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
            동의 후 진행해주세요.
          </p>
        </div>
      </div>
    </MirrLayout>
  );
}

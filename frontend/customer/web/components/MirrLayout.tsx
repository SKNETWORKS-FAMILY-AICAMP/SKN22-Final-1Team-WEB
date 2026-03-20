import { useLocation, useNavigate } from "react-router";
import { ChevronLeft } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

interface MirrLayoutProps {
  children: ReactNode;
  showBack?: boolean;
  backTo?: string;
  progress?: { current: number; total: number };
  footer?: ReactNode;
}

export function MirrLayout({
  children,
  showBack = false,
  backTo,
  progress,
  footer,
}: MirrLayoutProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const contentRef = useRef<HTMLDivElement>(null);

  const handleBack = () => {
    if (backTo) navigate(backTo);
    else navigate(-1);
  };

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    if (contentRef.current) {
      contentRef.current.scrollTop = 0;
    }
  }, [location.pathname]);

  return (
    <div
      className="min-h-screen w-full flex flex-col items-center justify-start relative overflow-hidden"
      style={{ backgroundColor: "#0C0A07", fontFamily: "'Noto Sans KR', sans-serif" }}
    >
      <div
        className="absolute pointer-events-none"
        style={{
          width: "600px",
          height: "600px",
          borderRadius: "50%",
          border: "1px solid rgba(196,150,60,0.08)",
          top: "-200px",
          right: "-200px",
        }}
      />
      <div
        className="absolute pointer-events-none"
        style={{
          width: "400px",
          height: "400px",
          borderRadius: "50%",
          border: "1px solid rgba(196,150,60,0.06)",
          bottom: "-150px",
          left: "-150px",
        }}
      />
      <div
        className="absolute pointer-events-none"
        style={{
          width: "900px",
          height: "900px",
          borderRadius: "50%",
          border: "1px solid rgba(196,150,60,0.04)",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
        }}
      />

      <div
        className="w-full flex flex-col relative z-10"
        style={{ maxWidth: "540px", minHeight: "100vh" }}
      >
        <div className="px-6 py-5" style={{ borderBottom: "1px solid rgba(58,48,32,0.8)" }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              position: "relative",
              minHeight: "32px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "flex-start", minWidth: "56px" }}>
              {showBack ? (
                <button
                  onClick={handleBack}
                  className="transition-opacity hover:opacity-70 active:opacity-50"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: "32px",
                    height: "32px",
                    borderRadius: "999px",
                    border: "1px solid rgba(196,150,60,0.35)",
                    color: "#9A8B6A",
                    backgroundColor: "rgba(196,150,60,0.06)",
                    cursor: "pointer",
                  }}
                  aria-label="뒤로 가기"
                  title="뒤로 가기"
                >
                  <ChevronLeft size={16} />
                </button>
              ) : (
                <div style={{ width: "32px", height: "32px" }} />
              )}
            </div>

            <button
              onClick={() => navigate("/")}
              style={{
                position: "absolute",
                left: "50%",
                transform: "translateX(-50%)",
                fontFamily: "'Cormorant Garamond', serif",
                fontSize: "24px",
                fontWeight: 500,
                color: "#C4963C",
                letterSpacing: "1px",
                background: "transparent",
                border: "none",
                padding: 0,
                cursor: "pointer",
              }}
              aria-label="홈으로 이동"
              title="홈으로 이동"
            >
              MirrAI
            </button>

            <div style={{ display: "flex", justifyContent: "flex-end", minWidth: "56px" }}>
              {progress ? (
                <span
                  style={{
                    fontSize: "14px",
                    color: "#9A8B6A",
                    letterSpacing: "1px",
                    minWidth: "56px",
                    textAlign: "right",
                  }}
                >
                  <span style={{ color: "#C4963C" }}>{progress.current}</span>
                  {" / "}
                  {progress.total}
                </span>
              ) : (
                <div style={{ minWidth: "56px" }} />
              )}
            </div>
          </div>
        </div>

        <div ref={contentRef} className="flex-1 flex flex-col overflow-y-auto">
          {children}
        </div>

        {footer && (
          <div
            style={{
              borderTop: "1px solid rgba(58,48,32,0.8)",
              padding: "16px 24px",
              backgroundColor: "#0C0A07",
            }}
          >
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

export function GoldButton({
  children,
  onClick,
  disabled = false,
  fullWidth = true,
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  fullWidth?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="transition-all active:scale-[0.98]"
      style={{
        width: fullWidth ? "100%" : "auto",
        padding: "18px 24px",
        backgroundColor: disabled ? "#3A3020" : "#C4963C",
        color: disabled ? "#5C5040" : "#0C0A07",
        fontFamily: "'Noto Sans KR', sans-serif",
        fontSize: "16px",
        fontWeight: 500,
        letterSpacing: "3px",
        border: "none",
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "background-color 0.2s",
      }}
      onMouseEnter={(e) => {
        if (!disabled)
          (e.currentTarget as HTMLButtonElement).style.backgroundColor = "#D4A84D";
      }}
      onMouseLeave={(e) => {
        if (!disabled)
          (e.currentTarget as HTMLButtonElement).style.backgroundColor = "#C4963C";
      }}
    >
      {children}
    </button>
  );
}

export function OutlineButton({
  children,
  onClick,
}: {
  children: ReactNode;
  onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="transition-all active:scale-[0.98]"
      style={{
        width: "100%",
        padding: "16px 24px",
        backgroundColor: "transparent",
        color: "#C4963C",
        fontFamily: "'Noto Sans KR', sans-serif",
        fontSize: "14px",
        fontWeight: 400,
        letterSpacing: "3px",
        border: "1px solid rgba(196,150,60,0.4)",
        cursor: "pointer",
        transition: "all 0.2s",
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLButtonElement).style.borderColor =
          "rgba(196,150,60,0.8)";
        (e.currentTarget as HTMLButtonElement).style.color = "#D4A84D";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLButtonElement).style.borderColor =
          "rgba(196,150,60,0.4)";
        (e.currentTarget as HTMLButtonElement).style.color = "#C4963C";
      }}
    >
      {children}
    </button>
  );
}

export function MirrInput({
  label,
  placeholder,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  placeholder?: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
}) {
  return (
    <div className="flex flex-col gap-2">
      <label
        style={{
          fontSize: "14px",
          color: "#9A8B6A",
          letterSpacing: "1px",
          fontFamily: "'Noto Sans KR', sans-serif",
        }}
      >
        {label}
      </label>
      <input
        type={type}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          width: "100%",
          padding: "16px 18px",
          backgroundColor: "#1A1610",
          border: "1px solid #3A3020",
          color: "#EED9B0",
          fontFamily: "'Noto Sans KR', sans-serif",
          fontSize: "16px",
          outline: "none",
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
  );
}

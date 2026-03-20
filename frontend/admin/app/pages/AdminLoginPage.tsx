import { useNavigate } from 'react-router';

export function AdminLoginPage() {
  const navigate = useNavigate();

  return (
    <div
      className="admin-page flex flex-col min-h-screen"
      style={{
        background:
          'radial-gradient(1200px 700px at 30% 20%, rgba(196,154,60,0.05), transparent 70%), #0A0A0A',
        fontFamily: "'Noto Sans KR', sans-serif",
      }}
    >
      <header className="admin-content px-8 pt-5 pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span
              style={{
                fontFamily: "'Cormorant Garamond', serif",
                fontSize: '36px',
                lineHeight: 1,
                color: '#C49A3C',
              }}
            >
              MirrAI
            </span>
            <span
              style={{
                color: 'rgba(196,154,60,0.55)',
                letterSpacing: '0.18em',
                fontSize: '14px',
                marginTop: '4px',
              }}
            >
              PARTNER
            </span>
          </div>
          <span style={{ color: '#6A6055', fontSize: '13px', letterSpacing: '0.05em' }}>
            AI 헤어스타일 추천 서비스
          </span>
        </div>
        <div
          style={{
            height: '1px',
            marginTop: '20px',
            background: 'linear-gradient(90deg, transparent, rgba(196,154,60,0.22), transparent)',
          }}
        />
      </header>

      <main className="admin-content flex-1 px-8 py-6 flex items-center">
        <div
          className="w-full mx-auto"
          style={{
            display: 'grid',
            maxWidth: '1140px',
            gridTemplateColumns: 'minmax(0, 1fr) minmax(360px, 430px)',
            gap: '56px',
            alignItems: 'center',
          }}
        >
          <section className="flex flex-col justify-center">
            <p style={{ color: '#C49A3C', letterSpacing: '0.18em', fontSize: '11px', marginBottom: '22px' }}>
              PARTNER MANAGEMENT SYSTEM
            </p>
            <h1
              style={{
                color: '#ECE6DB',
                fontSize: 'clamp(42px, 3.8vw, 62px)',
                lineHeight: 1.15,
                fontWeight: 500,
                marginBottom: '20px',
              }}
            >
              안녕하세요,
              <br />
              <span style={{ color: '#D6B176' }}>디자이너 님.</span>
            </h1>
            <p style={{ color: '#8F8576', fontSize: 'clamp(13px, 0.9vw, 16px)', lineHeight: 1.75 }}>
              MirrAI 파트너 관리 시스템에 오신 것을 환영합니다.
              <br />
              고객 관리, 취향 분석, 트렌드 리포트를 한 곳에서.
            </p>
            <div className="mt-10 flex items-center gap-4">
              <div style={{ width: '44px', height: '1px', background: '#C49A3C' }} />
              <span style={{ color: '#8C7B62', letterSpacing: '0.14em', fontSize: '11px' }}>
                BEAUTY · AI · TECHNOLOGY
              </span>
            </div>
          </section>

          <section className="flex items-center justify-end">
            <div
              style={{
                width: '100%',
                maxWidth: '430px',
                padding: '40px 32px',
                background: 'rgba(19,19,18,0.88)',
                border: '1px solid rgba(196,154,60,0.18)',
                borderRadius: '20px',
                backdropFilter: 'blur(6px)',
              }}
            >
              <p style={{ textAlign: 'center', color: '#8D867D', fontSize: '15px', marginBottom: '24px' }}>
                파트너 계정으로 시작하세요
              </p>

              <div className="flex flex-col gap-4">
                <button
                  onClick={() => navigate('/dashboard')}
                  style={{
                    width: '100%',
                    padding: '14px 18px',
                    border: 'none',
                    borderRadius: '11px',
                    background: 'linear-gradient(180deg, #B80050 0%, #920043 100%)',
                    color: '#FFFFFF',
                    fontSize: '15px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    boxShadow: '0 12px 22px rgba(184,0,80,0.25)',
                  }}
                >
                  기존 고객 로그인
                </button>

                <button
                  onClick={() => navigate('/dashboard')}
                  style={{
                    width: '100%',
                    padding: '14px 18px',
                    border: 'none',
                    borderRadius: '11px',
                    background: 'linear-gradient(180deg, #E50074 0%, #BB005D 100%)',
                    color: '#FFFFFF',
                    fontSize: '15px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    boxShadow: '0 12px 22px rgba(229,0,116,0.22)',
                  }}
                >
                  회원가입
                </button>
              </div>

              <div className="flex items-center gap-4 mt-8 mb-7">
                <div style={{ flex: 1, height: '1px', background: 'rgba(196,154,60,0.2)' }} />
                <span style={{ color: '#6A6055', fontSize: '15px' }}>or</span>
                <div style={{ flex: 1, height: '1px', background: 'rgba(196,154,60,0.2)' }} />
              </div>

              <button
                onClick={() => navigate('/customer-list')}
                style={{
                  width: '100%',
                  border: 'none',
                  background: 'none',
                  color: '#A28B63',
                  fontSize: '14px',
                  textDecoration: 'underline',
                  textUnderlineOffset: '6px',
                  cursor: 'pointer',
                  padding: '6px',
                }}
              >
                고객 상담 시작하기
              </button>
            </div>
          </section>
        </div>
      </main>
      <footer className="admin-content px-8 pb-3">
        <p style={{ textAlign: 'center', color: '#4E473D', fontSize: '12px' }}>
          © 2026 MirrAI · AI 헤어스타일 추천 서비스
        </p>
      </footer>
    </div>
  );
}

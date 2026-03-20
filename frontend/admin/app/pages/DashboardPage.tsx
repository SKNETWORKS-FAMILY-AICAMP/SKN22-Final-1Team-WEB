import { useNavigate } from 'react-router';
import { Users, Search, TrendingUp, Sparkles } from 'lucide-react';

export function DashboardPage() {
  const navigate = useNavigate();

  const now = new Date();
  const dateStr = now.toLocaleDateString('ko-KR', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  });

  return (
    <div
      className="admin-page flex flex-col min-h-screen"
      style={{ background: '#0A0A0A', fontFamily: "'Noto Sans KR', sans-serif" }}
    >
      {/* Top bar */}
      <div
        className="admin-content flex items-center justify-between px-10 py-4 border-b"
        style={{ borderColor: '#1E1E1E' }}
      >
        <div className="flex items-center gap-3">
          <span
            className="text-2xl tracking-widest"
            style={{ color: '#C49A3C', fontFamily: 'serif', letterSpacing: '0.18em' }}
          >
            MirrAI
          </span>
          <span
            className="text-xs px-2 py-0.5 rounded"
            style={{ background: '#1C1C1C', color: '#6A6055', border: '1px solid #2A2A2A' }}
          >
            BEAUTY TECH
          </span>
        </div>
        <div className="text-right">
          <p className="text-sm" style={{ color: '#6A6055' }}>
            {dateStr}
          </p>
          <p className="text-xs" style={{ color: '#4A4035' }}>
            Stylist Management Console
          </p>
        </div>
      </div>

      {/* Hero area */}
      <div className="admin-content flex-1 flex flex-col items-center justify-center px-16 py-12">
        {/* Brand */}
        <div className="text-center mb-16">
          <div className="flex items-center justify-center gap-3 mb-4">
            <div
              className="w-px h-12"
              style={{ background: 'linear-gradient(to bottom, transparent, #C49A3C, transparent)' }}
            />
            <div>
              <h1
                className="text-6xl tracking-widest mb-1"
                style={{
                  color: '#C49A3C',
                  fontFamily: 'serif',
                  letterSpacing: '0.2em',
                  textShadow: '0 0 40px rgba(196, 154, 60, 0.3)',
                }}
              >
                MirrAI
              </h1>
              <p className="text-sm tracking-[0.4em]" style={{ color: '#6A6055' }}>
                AI BEAUTY CONSULTATION SYSTEM
              </p>
            </div>
            <div
              className="w-px h-12"
              style={{ background: 'linear-gradient(to bottom, transparent, #C49A3C, transparent)' }}
            />
          </div>
          <div className="flex items-center justify-center gap-2 mt-4">
            <Sparkles size={12} style={{ color: '#C49A3C' }} />
            <p className="text-xs tracking-widest" style={{ color: '#4A4035' }}>
              STYLIST CONSOLE — PROFESSIONAL EDITION
            </p>
            <Sparkles size={12} style={{ color: '#C49A3C' }} />
          </div>
        </div>

        {/* Navigation cards */}
        <div className="grid grid-cols-3 gap-6 w-full max-w-4xl mb-10">
          {/* 점내 고객 목록 */}
          <button
            onClick={() => navigate('/customer-list')}
            className="group relative flex flex-col items-start p-8 rounded-2xl transition-all duration-300 hover:scale-[1.02] active:scale-[0.98]"
            style={{
              background: 'linear-gradient(135deg, #1C1C1C 0%, #141414 100%)',
              border: '1px solid #2A2A2A',
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.borderColor = '#C49A3C';
              (e.currentTarget as HTMLElement).style.boxShadow = '0 0 30px rgba(196, 154, 60, 0.1)';
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.borderColor = '#2A2A2A';
              (e.currentTarget as HTMLElement).style.boxShadow = 'none';
            }}
          >
            <div
              className="w-12 h-12 rounded-xl flex items-center justify-center mb-5"
              style={{ background: '#0D7FA320', border: '1px solid #0D7FA340' }}
            >
              <Users size={22} style={{ color: '#0D7FA3' }} />
            </div>
            <h2 className="text-lg mb-2" style={{ color: '#EDE8DE' }}>
              점내 고객 목록
            </h2>
            <p className="text-xs leading-relaxed" style={{ color: '#6A6055' }}>
              현재 방문 중인 고객 목록과 오늘의 AI 추천 스타일을 확인합니다
            </p>
            <div
              className="absolute bottom-6 right-6 text-xs tracking-widest"
              style={{ color: '#3A3025' }}
            >
              →
            </div>
          </button>

          {/* 고객 조회 */}
          <button
            onClick={() => navigate('/customer-search')}
            className="group relative flex flex-col items-start p-8 rounded-2xl transition-all duration-300 hover:scale-[1.02] active:scale-[0.98]"
            style={{
              background: 'linear-gradient(135deg, #1C1C1C 0%, #141414 100%)',
              border: '1px solid #2A2A2A',
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.borderColor = '#AE0F52';
              (e.currentTarget as HTMLElement).style.boxShadow = '0 0 30px rgba(174, 15, 82, 0.1)';
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.borderColor = '#2A2A2A';
              (e.currentTarget as HTMLElement).style.boxShadow = 'none';
            }}
          >
            <div
              className="w-12 h-12 rounded-xl flex items-center justify-center mb-5"
              style={{ background: '#AE0F5220', border: '1px solid #AE0F5240' }}
            >
              <Search size={22} style={{ color: '#AE0F52' }} />
            </div>
            <h2 className="text-lg mb-2" style={{ color: '#EDE8DE' }}>
              고객 조회
            </h2>
            <p className="text-xs leading-relaxed" style={{ color: '#6A6055' }}>
              이름 또는 전화번호로 고객 정보 및 방문 이력을 빠르게 검색합니다
            </p>
            <div
              className="absolute bottom-6 right-6 text-xs"
              style={{ color: '#3A3025' }}
            >
              →
            </div>
          </button>

          {/* 매장 트렌드 리포트 */}
          <button
            onClick={() => navigate('/trend-report')}
            className="group relative flex flex-col items-start p-8 rounded-2xl transition-all duration-300 hover:scale-[1.02] active:scale-[0.98]"
            style={{
              background: 'linear-gradient(135deg, #1C1C1C 0%, #141414 100%)',
              border: '1px solid #2A2A2A',
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.borderColor = '#7B1232';
              (e.currentTarget as HTMLElement).style.boxShadow = '0 0 30px rgba(123, 18, 50, 0.12)';
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.borderColor = '#2A2A2A';
              (e.currentTarget as HTMLElement).style.boxShadow = 'none';
            }}
          >
            <div
              className="w-12 h-12 rounded-xl flex items-center justify-center mb-5"
              style={{ background: '#7B123220', border: '1px solid #7B123240' }}
            >
              <TrendingUp size={22} style={{ color: '#C8405A' }} />
            </div>
            <h2 className="text-lg mb-2" style={{ color: '#EDE8DE' }}>
              매장 트렌드 리포트
            </h2>
            <p className="text-xs leading-relaxed" style={{ color: '#6A6055' }}>
              금일 매장의 스타일 트렌드와 고객 선호 분석 리포트를 확인합니다
            </p>
            <div
              className="absolute bottom-6 right-6 text-xs"
              style={{ color: '#3A3025' }}
            >
              →
            </div>
          </button>
        </div>

        {/* Status indicators */}
        <div
          className="flex items-center gap-8 px-8 py-4 rounded-xl"
          style={{ background: '#111111', border: '1px solid #1E1E1E' }}
        >
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full" style={{ background: '#2ECC71' }} />
            <span className="text-xs" style={{ color: '#6A6055' }}>
              AI 엔진 연결됨
            </span>
          </div>
          <div
            className="w-px h-4"
            style={{ background: '#1E1E1E' }}
          />
          <div className="flex items-center gap-2">
            <span className="text-xs" style={{ color: '#6A6055' }}>
              오늘 방문 고객
            </span>
            <span className="text-sm" style={{ color: '#C49A3C' }}>
              4명
            </span>
          </div>
          <div className="w-px h-4" style={{ background: '#1E1E1E' }} />
          <div className="flex items-center gap-2">
            <span className="text-xs" style={{ color: '#6A6055' }}>
              신규 등록
            </span>
            <span className="text-sm" style={{ color: '#E53535' }}>
              1명
            </span>
          </div>
          <div className="w-px h-4" style={{ background: '#1E1E1E' }} />
          <div className="flex items-center gap-2">
            <span className="text-xs" style={{ color: '#6A6055' }}>
              추천 완료
            </span>
            <span className="text-sm" style={{ color: '#0D7FA3' }}>
              3건
            </span>
          </div>
        </div>
      </div>

      {/* Bottom bar */}
      <div
        className="px-10 py-3 border-t flex items-center justify-between"
        style={{ borderColor: '#1E1E1E' }}
      >
        <p className="text-xs" style={{ color: '#3A3025' }}>
          © 2026 MirrAI Beauty Tech — Stylist Management System v2.4.1
        </p>
        <p className="text-xs" style={{ color: '#3A3025' }}>
          데이터는 암호화 저장되며 헤어 상담 목적으로만 사용됩니다
        </p>
      </div>
    </div>
  );
}

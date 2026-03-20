import { useState } from 'react';
import { useNavigate } from 'react-router';
import { ChevronDown, ChevronUp, Plus } from 'lucide-react';
import { NavBar } from '../components/NavBar';
import { CustomerAvatar } from '../components/CustomerAvatar';
import { customers } from '../data/mockData';

export function CustomerListPage() {
  const navigate = useNavigate();
  const [showMore, setShowMore] = useState(false);

  const visibleCustomers = showMore ? customers : customers.slice(0, 4);

  return (
    <div
      className="admin-page flex flex-col min-h-screen"
      style={{ background: '#0A0A0A', fontFamily: "'Noto Sans KR', sans-serif" }}
    >
      <NavBar />

      <div className="admin-content flex flex-1 px-10 py-8 gap-8">
        {/* Left column: title + customer list */}
        <div className="flex-1 flex flex-col gap-0">
          {/* Title bar */}
          <div
            className="flex items-center justify-between px-8 py-5 rounded-t-2xl"
            style={{
              background: 'linear-gradient(90deg, #0D7FA3 0%, #0A6A8A 100%)',
              border: '1px solid #0D7FA360',
            }}
          >
            <h1 className="text-2xl tracking-wide" style={{ color: '#FFFFFF' }}>
              점내 고객 목록
            </h1>
            <div className="flex items-center gap-3">
              <span
                className="text-xs px-3 py-1 rounded-full"
                style={{ background: 'rgba(255,255,255,0.15)', color: '#FFFFFF' }}
              >
                총 {customers.length}명
              </span>
              <button
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm transition-all hover:opacity-80"
                style={{ background: 'rgba(255,255,255,0.2)', color: '#FFFFFF' }}
              >
                <Plus size={14} />
                신규 등록
              </button>
            </div>
          </div>

          {/* Customer list */}
          <div
            className="rounded-b-2xl overflow-hidden"
            style={{ border: '1px solid #1E1E1E', borderTop: 'none' }}
          >
            {visibleCustomers.map((customer, idx) => (
              <div
                key={customer.id}
                className="flex items-center gap-5 px-6 py-5 cursor-pointer transition-all hover:opacity-90"
                style={{
                  background: idx % 2 === 0 ? '#141414' : '#111111',
                  borderBottom: idx < visibleCustomers.length - 1 ? '1px solid #1C1C1C' : 'none',
                }}
                onClick={() => navigate(`/customer/${customer.id}`)}
              >
                {/* Avatar */}
                <CustomerAvatar gender={customer.gender} size={60} isNew={customer.isNew} />

                {/* Name / Phone */}
                <div
                  className="flex-1 px-6 py-4 rounded-xl cursor-pointer"
                  style={{
                    background: customer.isNew
                      ? 'linear-gradient(90deg, #8B1535 0%, #6E1028 100%)'
                      : 'linear-gradient(90deg, #AE0F52 0%, #8E0D42 100%)',
                    border: `1px solid ${customer.isNew ? '#B51A3A' : '#C01060'}`,
                  }}
                >
                  <div className="flex items-center gap-3 mb-1">
                    <span className="text-base" style={{ color: '#FFFFFF' }}>
                      {customer.name}
                    </span>
                    <span className="text-sm" style={{ color: 'rgba(255,255,255,0.7)' }}>
                      /
                    </span>
                    <span className="text-sm" style={{ color: 'rgba(255,255,255,0.8)' }}>
                      {customer.phone}
                    </span>
                    {customer.isNew && (
                      <span
                        className="text-xs px-2 py-0.5 rounded-full"
                        style={{ background: '#E53535', color: '#FFFFFF' }}
                      >
                        신규
                      </span>
                    )}
                  </div>
                  {customer.isNew && (
                    <p className="text-xs" style={{ color: 'rgba(255,255,255,0.55)' }}>
                      신규 등록 고객 — 초기 AI 분석 완료
                    </p>
                  )}
                </div>

                {/* 금일 추천 button */}
                <button
                  className="px-6 py-4 rounded-xl text-sm whitespace-nowrap transition-all hover:opacity-85 active:scale-95"
                  style={{
                    background: 'linear-gradient(135deg, #0D7FA3 0%, #0A6080 100%)',
                    color: '#FFFFFF',
                    border: '1px solid #0D7FA360',
                    minWidth: '110px',
                  }}
                  onClick={(e) => {
                    e.stopPropagation();
                    navigate(`/customer/${customer.id}/recommendation`);
                  }}
                >
                  <div className="text-center">
                    <div>금일 추천</div>
                    <div className="text-xs mt-0.5" style={{ color: 'rgba(255,255,255,0.65)' }}>
                      조회하기
                    </div>
                  </div>
                </button>
              </div>
            ))}
          </div>

          {/* More button */}
          {customers.length > 4 && (
            <div className="flex justify-center mt-6">
              <button
                onClick={() => setShowMore(!showMore)}
                className="flex items-center justify-center w-14 h-14 rounded-full transition-all hover:opacity-80 active:scale-95"
                style={{
                  background: 'linear-gradient(135deg, #7B1232 0%, #5A0D25 100%)',
                  border: '1px solid #9B1A42',
                }}
              >
                {showMore ? (
                  <ChevronUp size={22} style={{ color: '#FFFFFF' }} />
                ) : (
                  <ChevronDown size={22} style={{ color: '#FFFFFF' }} />
                )}
              </button>
            </div>
          )}
        </div>

        {/* Right column: today summary */}
        <div className="w-72 flex flex-col gap-4">
          <div
            className="p-5 rounded-2xl"
            style={{ background: '#141414', border: '1px solid #1E1E1E' }}
          >
            <h3 className="text-xs tracking-widest mb-4" style={{ color: '#6A6055' }}>
              TODAY'S SUMMARY
            </h3>
            <div className="space-y-3">
              {[
                { label: '전체 방문', value: `${customers.length}명`, color: '#EDE8DE' },
                { label: '신규 고객', value: `${customers.filter((c) => c.isNew).length}명`, color: '#E53535' },
                { label: 'AI 추천 완료', value: '3건', color: '#0D7FA3' },
                { label: '상담 종료', value: '2건', color: '#6A6055' },
              ].map((item) => (
                <div key={item.label} className="flex items-center justify-between">
                  <span className="text-xs" style={{ color: '#6A6055' }}>
                    {item.label}
                  </span>
                  <span className="text-sm" style={{ color: item.color }}>
                    {item.value}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div
            className="p-5 rounded-2xl"
            style={{ background: '#141414', border: '1px solid #1E1E1E' }}
          >
            <h3 className="text-xs tracking-widest mb-4" style={{ color: '#6A6055' }}>
              금일 인기 스타일
            </h3>
            <div className="space-y-2">
              {['레이어드 미디엄 웨이브', '클래식 밥 스타일', '소프트 레이어 펌'].map((style, i) => (
                <div key={style} className="flex items-center gap-3">
                  <span
                    className="text-xs w-5 h-5 rounded flex items-center justify-center"
                    style={{ background: i === 0 ? '#C49A3C20' : '#1C1C1C', color: i === 0 ? '#C49A3C' : '#4A4035' }}
                  >
                    {i + 1}
                  </span>
                  <span className="text-xs" style={{ color: i === 0 ? '#EDE8DE' : '#6A6055' }}>
                    {style}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <button
            onClick={() => navigate('/trend-report')}
            className="w-full py-4 rounded-2xl text-sm transition-all hover:opacity-85"
            style={{
              background: 'linear-gradient(135deg, #1C1C1C 0%, #141414 100%)',
              border: '1px solid #2A2A2A',
              color: '#C49A3C',
            }}
          >
            매장 트렌드 리포트 →
          </button>
        </div>
      </div>
    </div>
  );
}

import { useState } from 'react';
import { useNavigate } from 'react-router';
import { Search, X } from 'lucide-react';
import { NavBar } from '../components/NavBar';
import { CustomerAvatar } from '../components/CustomerAvatar';
import { customers } from '../data/mockData';

export function CustomerSearchPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');

  const filtered = query.trim()
    ? customers.filter(
        (c) =>
          c.name.includes(query.trim()) || c.phone.replace(/-/g, '').includes(query.trim().replace(/-/g, ''))
      )
    : customers;

  return (
    <div
      className="admin-page flex flex-col min-h-screen"
      style={{ background: '#0A0A0A', fontFamily: "'Noto Sans KR', sans-serif" }}
    >
      <NavBar />

      <div className="admin-content flex flex-1 px-10 py-8 gap-8">
        {/* Main content */}
        <div className="flex-1 flex flex-col gap-0">
          {/* Title bar */}
          <div
            className="px-8 py-5 rounded-t-2xl"
            style={{
              background: 'linear-gradient(90deg, #0D7FA3 0%, #0A6A8A 100%)',
              border: '1px solid #0D7FA360',
            }}
          >
            <h1 className="text-2xl tracking-wide" style={{ color: '#FFFFFF' }}>
              고객 조회
            </h1>
          </div>

          {/* Search bar */}
          <div
            className="px-6 py-4"
            style={{
              background: 'linear-gradient(90deg, #AE0F52 0%, #8E0D42 100%)',
              border: '1px solid #C01060',
              borderTop: 'none',
            }}
          >
            <div className="flex items-center gap-3">
              <Search size={18} style={{ color: 'rgba(255,255,255,0.7)' }} />
              <input
                type="text"
                placeholder="이름 또는 전화번호로 검색..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="flex-1 bg-transparent outline-none text-base placeholder-opacity-60"
                style={{ color: '#FFFFFF' }}
              />
              {query && (
                <button onClick={() => setQuery('')}>
                  <X size={16} style={{ color: 'rgba(255,255,255,0.7)' }} />
                </button>
              )}
            </div>
          </div>

          {/* Results */}
          <div
            className="flex-1 rounded-b-2xl overflow-hidden"
            style={{
              background: '#111111',
              border: '1px solid #1E1E1E',
              borderTop: 'none',
            }}
          >
            {filtered.length === 0 ? (
              <div className="flex items-center justify-center h-64">
                <div className="text-center">
                  <p className="text-base mb-2" style={{ color: '#4A4035' }}>
                    검색 결과가 없습니다
                  </p>
                  <p className="text-sm" style={{ color: '#3A3025' }}>
                    다른 이름이나 전화번호로 검색해 보세요
                  </p>
                </div>
              </div>
            ) : (
              <div className="p-4 space-y-2">
                {/* Table header */}
                <div
                  className="grid px-6 py-2 rounded-lg text-xs tracking-widest"
                  style={{
                    gridTemplateColumns: '60px 1fr 1fr 1fr 80px 120px',
                    color: '#6A6055',
                    background: '#0D0D0D',
                  }}
                >
                  <span></span>
                  <span>이름</span>
                  <span>전화번호</span>
                  <span>성별 / 나이</span>
                  <span>방문상태</span>
                  <span className="text-right">바로가기</span>
                </div>

                {filtered.map((customer) => (
                  <div
                    key={customer.id}
                    className="grid items-center px-6 py-4 rounded-xl cursor-pointer transition-all hover:opacity-85"
                    style={{
                      gridTemplateColumns: '60px 1fr 1fr 1fr 80px 120px',
                      background: '#171717',
                      border: '1px solid #202020',
                    }}
                    onClick={() => navigate(`/customer/${customer.id}`)}
                  >
                    <CustomerAvatar gender={customer.gender} size={44} isNew={customer.isNew} />

                    <div>
                      <span className="text-base" style={{ color: '#EDE8DE' }}>
                        {customer.name}
                      </span>
                    </div>

                    <span className="text-sm" style={{ color: '#9A8A7A' }}>
                      {customer.phone}
                    </span>

                    <span className="text-sm" style={{ color: '#9A8A7A' }}>
                      {customer.gender === 'F' ? '여성' : '남성'} / {customer.age}세
                    </span>

                    <div>
                      {customer.isNew ? (
                        <span
                          className="text-xs px-2 py-1 rounded-full"
                          style={{ background: '#E5353520', color: '#E53535', border: '1px solid #E5353540' }}
                        >
                          신규
                        </span>
                      ) : (
                        <span
                          className="text-xs px-2 py-1 rounded-full"
                          style={{ background: '#0D7FA320', color: '#0D7FA3', border: '1px solid #0D7FA340' }}
                        >
                          기존
                        </span>
                      )}
                    </div>

                    <div className="flex justify-end">
                      <button
                        className="text-xs px-4 py-2 rounded-lg transition-all hover:opacity-80"
                        style={{
                          background: 'linear-gradient(135deg, #AE0F52 0%, #8E0D42 100%)',
                          color: '#FFFFFF',
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/customer/${customer.id}`);
                        }}
                      >
                        상세보기
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right sidebar */}
        <div className="w-64 flex flex-col gap-4">
          <div
            className="p-5 rounded-2xl"
            style={{ background: '#141414', border: '1px solid #1E1E1E' }}
          >
            <h3 className="text-xs tracking-widest mb-4" style={{ color: '#6A6055' }}>
              검색 TIP
            </h3>
            <div className="space-y-3">
              {[
                '이름 일부만 입력해도 검색됩니다',
                '전화번호 일부 입력 가능합니다',
                '하이픈(-) 없이 입력해도 됩니다',
              ].map((tip, i) => (
                <div key={i} className="flex items-start gap-2">
                  <span className="text-xs mt-0.5" style={{ color: '#C49A3C' }}>
                    •
                  </span>
                  <p className="text-xs" style={{ color: '#6A6055', lineHeight: 1.6 }}>
                    {tip}
                  </p>
                </div>
              ))}
            </div>
          </div>

          <div
            className="p-5 rounded-2xl"
            style={{ background: '#141414', border: '1px solid #1E1E1E' }}
          >
            <h3 className="text-xs tracking-widest mb-4" style={{ color: '#6A6055' }}>
              최근 조회
            </h3>
            <div className="space-y-2">
              {customers.slice(0, 3).map((c) => (
                <button
                  key={c.id}
                  className="w-full flex items-center gap-3 p-2 rounded-lg text-left transition-all hover:opacity-80"
                  style={{ background: '#0D0D0D' }}
                  onClick={() => navigate(`/customer/${c.id}`)}
                >
                  <CustomerAvatar gender={c.gender} size={32} />
                  <div>
                    <p className="text-xs" style={{ color: '#EDE8DE' }}>
                      {c.name}
                    </p>
                    <p className="text-xs" style={{ color: '#4A4035' }}>
                      {c.phone}
                    </p>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

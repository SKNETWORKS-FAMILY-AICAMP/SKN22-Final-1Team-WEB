import { useState } from 'react';
import { useNavigate } from 'react-router';
import { NavBar } from '../components/NavBar';
import { hairstyles, trendReport } from '../data/mockData';

const FILTER_OPTIONS = {
  gender: ['전체', '여성', '남성', '유니섹스'],
  length: ['전체', '숏컷', '숏미디엄', '중단발', '단발', '장발'],
  age: ['전체', '10-20대', '30대', '40대', '50대+'],
  budget: ['전체', '5만원 이하', '5~8만원', '8~12만원', '12만원+'],
};

export function TrendReportPage() {
  const navigate = useNavigate();
  const [filters, setFilters] = useState({
    gender: '전체',
    length: '전체',
    age: '전체',
    budget: '전체',
  });

  return (
    <div
      className="admin-page flex flex-col min-h-screen"
      style={{ background: '#0A0A0A', fontFamily: "'Noto Sans KR', sans-serif" }}
    >
      <NavBar />

      <div className="admin-content px-10 py-8 flex gap-8 flex-1">
        {/* Main */}
        <div className="flex-1 flex flex-col gap-4">
          {/* Title */}
          <div
            className="flex items-center justify-between px-8 py-5 rounded-2xl"
            style={{
              background: 'linear-gradient(90deg, #0D7FA3 0%, #0A6A8A 100%)',
              border: '1px solid #0D7FA360',
            }}
          >
            <h1 className="text-xl" style={{ color: '#FFFFFF' }}>
              매장 트렌드 리포트
            </h1>
            <span className="text-sm" style={{ color: 'rgba(255,255,255,0.6)' }}>
              2026년 3월 12일 기준
            </span>
          </div>

          {/* Filter section */}
          <div
            className="px-6 py-5 rounded-2xl"
            style={{
              background: 'linear-gradient(135deg, #7B1232 0%, #5A0D25 100%)',
              border: '1px solid #9B1A42',
            }}
          >
            <p className="text-xs tracking-widest mb-4" style={{ color: 'rgba(255,255,255,0.6)' }}>
              키워드 필터링
            </p>
            <div className="grid grid-cols-4 gap-4">
              {(Object.keys(FILTER_OPTIONS) as Array<keyof typeof FILTER_OPTIONS>).map((key) => {
                const labels: Record<string, string> = {
                  gender: '성별',
                  length: '기장',
                  age: '연령',
                  budget: '금액',
                };
                return (
                  <div key={key}>
                    <p className="text-xs mb-2" style={{ color: 'rgba(255,255,255,0.5)' }}>
                      {labels[key]}
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {FILTER_OPTIONS[key].map((opt) => (
                        <button
                          key={opt}
                          onClick={() => setFilters((prev) => ({ ...prev, [key]: opt }))}
                          className="text-xs px-2 py-1 rounded transition-all"
                          style={{
                            background:
                              filters[key] === opt
                                ? 'rgba(255,255,255,0.25)'
                                : 'rgba(255,255,255,0.08)',
                            color: filters[key] === opt ? '#FFFFFF' : 'rgba(255,255,255,0.5)',
                            border: filters[key] === opt
                              ? '1px solid rgba(255,255,255,0.4)'
                              : '1px solid rgba(255,255,255,0.1)',
                          }}
                        >
                          {opt}
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Trend list */}
          <div className="flex flex-col gap-3">
            {trendReport.map((trend) => {
              const style = hairstyles.find((h) => h.id === trend.hairstyleId);
              if (!style) return null;
              return (
                <div
                  key={trend.id}
                  className="flex items-center gap-5 px-6 py-5 rounded-2xl cursor-pointer transition-all hover:opacity-90"
                  style={{
                    background: '#141414',
                    border: '1px solid #1E1E1E',
                  }}
                  onClick={() => navigate(`/hairstyle/${style.id}`)}
                >
                  {/* Rank + Image */}
                  <div className="flex items-center gap-4 flex-shrink-0">
                    <div
                      className="w-10 h-10 rounded-full flex items-center justify-center text-sm flex-shrink-0"
                      style={{
                        background:
                          trend.rank === 1
                            ? 'linear-gradient(135deg, #C49A3C, #8A6A28)'
                            : trend.rank === 2
                            ? 'linear-gradient(135deg, #888, #555)'
                            : trend.rank === 3
                            ? 'linear-gradient(135deg, #A0522D, #6B3520)'
                            : '#1C1C1C',
                        color: '#FFFFFF',
                        border:
                          trend.rank <= 3 ? 'none' : '1px solid #2A2A2A',
                      }}
                    >
                      {trend.rank}
                    </div>
                    <div
                      className="w-14 h-14 rounded-xl overflow-hidden flex-shrink-0"
                      style={{ border: '1px solid #2A2A2A' }}
                    >
                      <img
                        src={style.imageUrl}
                        alt={style.koreanName}
                        className="w-full h-full object-cover"
                        style={{ filter: 'brightness(0.82) saturate(0.9)' }}
                      />
                    </div>
                  </div>

                  {/* Universal name badge + style description */}
                  <div className="flex gap-4 flex-1 items-center">
                    <div
                      className="flex flex-col items-center justify-center px-4 py-3 rounded-xl flex-shrink-0"
                      style={{
                        background: 'linear-gradient(135deg, #AE0F52 0%, #8E0D42 100%)',
                        border: '1px solid #C01060',
                        minWidth: '120px',
                        textAlign: 'center',
                      }}
                    >
                      <p className="text-xs mb-1" style={{ color: 'rgba(255,255,255,0.6)' }}>
                        보편적 명칭
                      </p>
                      <p className="text-sm" style={{ color: '#FFFFFF' }}>
                        {style.koreanName}
                      </p>
                    </div>

                    <div
                      className="flex-1 px-6 py-4 rounded-xl"
                      style={{
                        background: 'linear-gradient(135deg, #AE0F52 0%, #8E0D42 100%)',
                        border: '1px solid #C01060',
                      }}
                    >
                      <div className="flex items-start justify-between">
                        <p className="text-sm" style={{ color: '#FFFFFF' }}>
                          {trend.description}
                        </p>
                        <div className="flex items-center gap-2 flex-shrink-0 ml-4">
                          <span
                            className="text-xs px-2 py-1 rounded"
                            style={{ background: 'rgba(255,255,255,0.15)', color: '#FFFFFF' }}
                          >
                            {trend.count}건
                          </span>
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-1 mt-2">
                        {style.keywords.slice(0, 4).map((k) => (
                          <span
                            key={k}
                            className="text-xs px-2 py-0.5 rounded"
                            style={{ background: 'rgba(255,255,255,0.1)', color: 'rgba(255,255,255,0.7)' }}
                          >
                            {k}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Arrow */}
                  <span style={{ color: '#3A3025' }}>→</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right sidebar */}
        <div className="w-64 flex flex-col gap-4">
          {/* Summary stats */}
          <div
            className="p-5 rounded-2xl"
            style={{ background: '#141414', border: '1px solid #1E1E1E' }}
          >
            <h3 className="text-xs tracking-widest mb-4" style={{ color: '#6A6055' }}>
              금주 통계
            </h3>
            <div className="space-y-3">
              {[
                { label: '총 추천 건수', value: '100건', color: '#EDE8DE' },
                { label: '여성 고객', value: '63%', color: '#C8406A' },
                { label: '남성 고객', value: '37%', color: '#0D7FA3' },
                { label: '평균 예산', value: '7.8만원', color: '#C49A3C' },
                { label: '고객 만족도', value: '4.6 / 5', color: '#C49A3C' },
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

          {/* Bar chart */}
          <div
            className="p-5 rounded-2xl"
            style={{ background: '#141414', border: '1px solid #1E1E1E' }}
          >
            <h3 className="text-xs tracking-widest mb-4" style={{ color: '#6A6055' }}>
              스타일 분포
            </h3>
            {trendReport.map((trend) => (
              <div key={trend.id} className="mb-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs truncate" style={{ color: '#6A6055', maxWidth: '140px' }}>
                    {hairstyles.find((h) => h.id === trend.hairstyleId)?.koreanName}
                  </span>
                  <span className="text-xs" style={{ color: '#9A8A7A' }}>
                    {trend.count}
                  </span>
                </div>
                <div className="w-full rounded-full overflow-hidden" style={{ height: '4px', background: '#1C1C1C' }}>
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${(trend.count / 34) * 100}%`,
                      background:
                        trend.rank === 1
                          ? '#C49A3C'
                          : trend.rank === 2
                          ? '#AE0F52'
                          : trend.rank === 3
                          ? '#0D7FA3'
                          : '#4A4035',
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

import { useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { NavBar } from '../components/NavBar';
import { StyleThumbnail } from '../components/CustomerAvatar';
import { customers, hairstyles } from '../data/mockData';

export function CustomerRecommendationPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [expandedStyle, setExpandedStyle] = useState<number | null>(null);

  const customer = customers.find((c) => c.id === Number(id));
  if (!customer) return null;

  const todayStyle = hairstyles.find((h) => h.id === customer.todayRecommendationId);

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
            className="px-8 py-5 rounded-2xl"
            style={{
              background: 'linear-gradient(90deg, #AE0F52 0%, #8E0D42 100%)',
              border: '1px solid #C01060',
            }}
          >
            <h1 className="text-xl" style={{ color: '#FFFFFF' }}>
              고객 추천 페이지
            </h1>
            <p className="text-sm mt-1" style={{ color: 'rgba(255,255,255,0.6)' }}>
              {customer.name} 고객 · AI 분석 기반 맞춤 헤어스타일 추천 결과
            </p>
          </div>

          {/* 최근 취향 설문 내역 */}
          <div
            className="px-6 py-5 rounded-2xl"
            style={{
              background: 'linear-gradient(90deg, #7B1232 0%, #5A0D25 100%)',
              border: '1px solid #9B1A42',
            }}
          >
            <p className="text-xs tracking-widest mb-4" style={{ color: 'rgba(255,255,255,0.6)' }}>
              최근 취향 설문 내역
            </p>
            <div className="grid grid-cols-4 gap-4">
              {[
                { label: '선호 분위기', value: customer.surveyResults.atmosphere },
                { label: '희망 길이', value: customer.surveyResults.length },
                { label: '예산', value: customer.surveyResults.budget },
                { label: '용도', value: customer.surveyResults.occasion },
              ].map((item) => (
                <div key={item.label} className="text-center">
                  <p className="text-xs mb-1" style={{ color: 'rgba(255,255,255,0.5)' }}>
                    {item.label}
                  </p>
                  <p className="text-sm" style={{ color: '#FFFFFF' }}>
                    {item.value}
                  </p>
                </div>
              ))}
            </div>
            <div className="flex items-center gap-2 mt-4">
              {customer.surveyResults.preferences.map((p) => (
                <span
                  key={p}
                  className="text-xs px-3 py-1 rounded-full"
                  style={{ background: 'rgba(255,255,255,0.15)', color: '#FFFFFF' }}
                >
                  #{p}
                </span>
              ))}
            </div>
          </div>

          {/* 금일 고객 선택 스타일 해설 */}
          {todayStyle && (
            <div
              className="px-6 py-5 rounded-2xl"
              style={{
                background: 'linear-gradient(90deg, #AE0F52 0%, #8E0D42 100%)',
                border: '1px solid #C01060',
              }}
            >
              <div className="flex items-start gap-5">
                <StyleThumbnail imageUrl={todayStyle.imageUrl} size={80} />
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <p className="text-base" style={{ color: '#FFFFFF' }}>
                      {todayStyle.koreanName}
                    </p>
                    <span
                      className="text-xs px-2 py-0.5 rounded"
                      style={{ background: 'rgba(255,255,255,0.2)', color: '#FFFFFF' }}
                    >
                      AI 매칭 {todayStyle.matchRate}%
                    </span>
                  </div>
                  <p className="text-xs leading-relaxed mb-3" style={{ color: 'rgba(255,255,255,0.7)' }}>
                    {todayStyle.description}
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {todayStyle.keywords.map((k) => (
                      <span
                        key={k}
                        className="text-xs px-2 py-0.5 rounded"
                        style={{ background: 'rgba(255,255,255,0.15)', color: 'rgba(255,255,255,0.8)' }}
                      >
                        {k}
                      </span>
                    ))}
                  </div>
                </div>
                <button
                  onClick={() => navigate(`/hairstyle/${todayStyle.id}`)}
                  className="px-4 py-2 rounded-xl text-xs transition-all hover:opacity-80 flex-shrink-0"
                  style={{
                    background: 'rgba(255,255,255,0.15)',
                    color: '#FFFFFF',
                    border: '1px solid rgba(255,255,255,0.25)',
                  }}
                >
                  상세보기
                </button>
              </div>
            </div>
          )}

          {/* 금일 고객 추천 스타일 전체 */}
          <div className="rounded-2xl overflow-hidden" style={{ border: '1px solid #1E1E1E' }}>
            <div
              className="px-6 py-4"
              style={{
                background: 'linear-gradient(90deg, #7B1232 0%, #5A0D25 100%)',
              }}
            >
              <p className="text-sm" style={{ color: '#FFFFFF' }}>
                금일 고객 추천 스타일 전체
              </p>
              <p className="text-xs mt-0.5" style={{ color: 'rgba(255,255,255,0.5)' }}>
                터치 시 확대 — AI 매칭 순
              </p>
            </div>
            <div className="p-5" style={{ background: '#111111' }}>
              <div className="grid grid-cols-4 gap-4">
                {hairstyles.map((style) => (
                  <button
                    key={style.id}
                    className="group relative rounded-2xl overflow-hidden text-left transition-all hover:scale-105"
                    style={{
                      border: expandedStyle === style.id ? '2px solid #C49A3C' : '1px solid #1E1E1E',
                    }}
                    onClick={() =>
                      setExpandedStyle(expandedStyle === style.id ? null : style.id)
                    }
                  >
                    <StyleThumbnail imageUrl={style.imageUrl} size={140} />
                    <div
                      className="absolute bottom-0 left-0 right-0 px-3 py-2"
                      style={{ background: 'linear-gradient(to top, rgba(0,0,0,0.85), transparent)' }}
                    >
                      <p className="text-xs" style={{ color: '#FFFFFF' }}>
                        {style.koreanName}
                      </p>
                      <p className="text-xs" style={{ color: '#C49A3C' }}>
                        {style.matchRate}% 매칭
                      </p>
                    </div>
                    {style.id === customer.todayRecommendationId && (
                      <div
                        className="absolute top-2 right-2 text-xs px-2 py-0.5 rounded"
                        style={{ background: '#C49A3C', color: '#FFFFFF' }}
                      >
                        선택됨
                      </div>
                    )}
                  </button>
                ))}
              </div>

              {expandedStyle !== null && (
                <div
                  className="mt-4 p-5 rounded-2xl"
                  style={{ background: '#171717', border: '1px solid #2A2A2A' }}
                >
                  {(() => {
                    const s = hairstyles.find((h) => h.id === expandedStyle);
                    if (!s) return null;
                    return (
                      <div className="flex gap-5">
                        <StyleThumbnail imageUrl={s.imageUrl} size={100} />
                        <div className="flex-1">
                          <div className="flex items-center gap-3 mb-2">
                            <h3 className="text-base" style={{ color: '#EDE8DE' }}>
                              {s.koreanName}
                            </h3>
                            <span
                              className="text-xs px-2 py-0.5 rounded"
                              style={{ background: '#C49A3C20', color: '#C49A3C' }}
                            >
                              {s.matchRate}%
                            </span>
                          </div>
                          <p className="text-xs leading-relaxed mb-3" style={{ color: '#6A6055' }}>
                            {s.description}
                          </p>
                          <button
                            onClick={() => navigate(`/hairstyle/${s.id}`)}
                            className="text-xs px-4 py-2 rounded-lg transition-all hover:opacity-80"
                            style={{
                              background: 'linear-gradient(135deg, #AE0F52 0%, #8E0D42 100%)',
                              color: '#FFFFFF',
                            }}
                          >
                            스타일 상세 →
                          </button>
                        </div>
                      </div>
                    );
                  })()}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right */}
        <div className="w-64 flex flex-col gap-4">
          <div
            className="p-5 rounded-2xl"
            style={{ background: '#141414', border: '1px solid #1E1E1E' }}
          >
            <h3 className="text-xs tracking-widest mb-4" style={{ color: '#6A6055' }}>
              고객 AI 프로파일
            </h3>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs" style={{ color: '#6A6055' }}>
                  얼굴형
                </span>
                <span className="text-sm" style={{ color: '#EDE8DE' }}>
                  {customer.faceShape}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs" style={{ color: '#6A6055' }}>
                  황금비율
                </span>
                <span className="text-sm" style={{ color: '#C49A3C' }}>
                  {customer.goldenRatio}
                </span>
              </div>
              <div
                className="w-full h-px"
                style={{ background: '#1E1E1E' }}
              />
              <p className="text-xs leading-relaxed" style={{ color: '#6A6055' }}>
                {customer.faceShape} 얼굴에 황금비율{' '}
                <span style={{ color: '#C49A3C' }}>{customer.goldenRatio}</span>으로 분석되었습니다.
                청순한 분위기의 웨이브 스타일이 최적입니다.
              </p>
            </div>
          </div>

          <button
            onClick={() => navigate(`/customer/${customer.id}`)}
            className="w-full py-4 rounded-2xl text-sm transition-all hover:opacity-85"
            style={{
              background: '#141414',
              border: '1px solid #2A2A2A',
              color: '#9A8A7A',
            }}
          >
            ← 고객 상세로 돌아가기
          </button>
        </div>
      </div>
    </div>
  );
}

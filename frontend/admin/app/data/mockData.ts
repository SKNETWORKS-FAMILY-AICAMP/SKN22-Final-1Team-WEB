export interface SurveyResult {
  preferences: string[];
  length: string;
  budget: string;
  occasion: string;
  atmosphere: string;
}

export interface RecommendationHistory {
  date: string;
  styleName: string;
  stylist: string;
  result: string;
  note?: string;
}

export interface Customer {
  id: number;
  name: string;
  phone: string;
  isNew: boolean;
  gender: 'M' | 'F';
  age: number;
  faceShape: string;
  goldenRatio: number;
  lastVisit: string;
  todayRecommendationId: number;
  todayRecommendationName: string;
  surveyResults: SurveyResult;
  recommendationHistory: RecommendationHistory[];
  designerNote?: string;
}

export interface Hairstyle {
  id: number;
  universalName: string;
  koreanName: string;
  keywords: string[];
  matchRate: number;
  description: string;
  faceRatioData: {
    golden: string;
    forehead: string;
    jaw: string;
    suitableFaces: string[];
  };
  priceRange: string;
  length: string;
  gender: 'female' | 'male' | 'unisex';
  imageUrl: string;
}

export const customers: Customer[] = [
  {
    id: 1,
    name: '김갑환',
    phone: '010-9874-6541',
    isNew: true,
    gender: 'M',
    age: 32,
    faceShape: '타원형',
    goldenRatio: 0.87,
    lastVisit: '2026-03-12',
    todayRecommendationId: 1,
    todayRecommendationName: '레이어드 미디엄 웨이브',
    surveyResults: {
      preferences: ['청순함', '자연스러움', '웨이브'],
      length: '중단발',
      budget: '8만원 이하',
      occasion: '일상/직장',
      atmosphere: '청순하고 부드러운 분위기',
    },
    recommendationHistory: [
      { date: '2026-01-15', styleName: '소프트 레이어 펌', stylist: '박지수 디자이너', result: '만족', note: '볼륨감 선호, 다음 방문 시 앞머리 고려' },
      { date: '2025-11-20', styleName: '내추럴 텍스처 컷', stylist: '이현아 디자이너', result: '매우 만족' },
      { date: '2025-09-03', styleName: '클래식 밥 스타일', stylist: '박지수 디자이너', result: '보통', note: '길이가 너무 짧았다고 피드백' },
    ],
    designerNote: '모발 약간 건조함. 트리트먼트 권유. 앞머리 가르마 오른쪽 선호.',
  },
  {
    id: 2,
    name: '이수진',
    phone: '010-5523-8812',
    isNew: false,
    gender: 'F',
    age: 28,
    faceShape: '둥근형',
    goldenRatio: 0.82,
    lastVisit: '2026-03-10',
    todayRecommendationId: 2,
    todayRecommendationName: '소프트 레이어 펌',
    surveyResults: {
      preferences: ['큐트', '활발함', '볼륨'],
      length: '숏컷',
      budget: '10만원 이하',
      occasion: '데일리',
      atmosphere: '발랄하고 귀여운 느낌',
    },
    recommendationHistory: [
      { date: '2026-02-08', styleName: '내추럴 텍스처 컷', stylist: '이현아 디자이너', result: '매우 만족' },
    ],
    designerNote: '두피 민감성. 약품 사용 시 주의. 모발 가늘고 숱 적음.',
  },
  {
    id: 3,
    name: '박민준',
    phone: '010-3341-5579',
    isNew: false,
    gender: 'M',
    age: 24,
    faceShape: '각진형',
    goldenRatio: 0.79,
    lastVisit: '2026-03-05',
    todayRecommendationId: 3,
    todayRecommendationName: '내추럴 텍스처 컷',
    surveyResults: {
      preferences: ['시크함', '모던', '깔끔함'],
      length: '숏미디엄',
      budget: '6만원 이하',
      occasion: '직장/비즈니스',
      atmosphere: '깔끔하고 단정한 인상',
    },
    recommendationHistory: [
      { date: '2026-01-20', styleName: '클래식 밥 스타일', stylist: '김민우 디자이너', result: '만족' },
      { date: '2025-10-15', styleName: '레이어드 미디엄 웨이브', stylist: '박지수 디자이너', result: '보통' },
    ],
    designerNote: '',
  },
  {
    id: 4,
    name: '정혜원',
    phone: '010-7789-2234',
    isNew: false,
    gender: 'F',
    age: 35,
    faceShape: '달걀형',
    goldenRatio: 0.91,
    lastVisit: '2026-03-01',
    todayRecommendationId: 4,
    todayRecommendationName: '클래식 밥 스타일',
    surveyResults: {
      preferences: ['우아함', '클래식', '세련됨'],
      length: '단발',
      budget: '12만원 이하',
      occasion: '특별한 날/행사',
      atmosphere: '성숙하고 세련된 느낌',
    },
    recommendationHistory: [
      { date: '2026-02-14', styleName: '소프트 레이어 펌', stylist: '이현아 디자이너', result: '매우 만족' },
      { date: '2025-12-20', styleName: '레이어드 미디엄 웨이브', stylist: '이현아 디자이너', result: '만족' },
      { date: '2025-10-05', styleName: '내추럴 텍스처 컷', stylist: '박지수 디자이너', result: '매우 만족' },
    ],
    designerNote: '모발 굵고 탄력 좋음. 염색 이력 없음. VIP 고객.',
  },
];

export const hairstyles: Hairstyle[] = [
  {
    id: 1,
    universalName: 'Layered Medium Wave',
    koreanName: '레이어드 미디엄 웨이브',
    keywords: ['청순함', '중단발', '웨이브', '레이어드', '자연스러움', '볼륨'],
    matchRate: 98,
    description:
      '타원형 얼굴에 최적화된 레이어드 중단발 웨이브 스타일입니다. 자연스러운 웨이브가 얼굴 라인을 부드럽게 감싸며, 레이어드 컷으로 볼륨감을 극대화합니다.',
    faceRatioData: {
      golden: '0.85~0.92',
      forehead: '3등분 중 상단 비율 적정',
      jaw: '하악 너비 대비 광대 1.05~1.15배',
      suitableFaces: ['타원형', '달걀형', '긴형'],
    },
    priceRange: '6~8만원',
    length: '중단발 (어깨 길이)',
    gender: 'female',
    imageUrl:
      'https://images.unsplash.com/photo-1661818302487-467621dd1c19?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&w=1080',
  },
  {
    id: 2,
    universalName: 'Soft Layer Perm',
    koreanName: '소프트 레이어 펌',
    keywords: ['큐트', '볼륨', '활발함', '펌', '부드러움'],
    matchRate: 94,
    description:
      '둥근 얼굴형에 세로 라인을 더해 얼굴을 갸름하게 보이게 하는 소프트 레이어 펌입니다. 풍성한 볼륨과 경쾌한 질감이 특징입니다.',
    faceRatioData: {
      golden: '0.78~0.86',
      forehead: '넓은 이마 커버에 효과적',
      jaw: '광대 너비 대비 세로 라인 강조',
      suitableFaces: ['둥근형', '사각형'],
    },
    priceRange: '8~10만원',
    length: '숏~숏미디엄',
    gender: 'unisex',
    imageUrl:
      'https://images.unsplash.com/photo-1599387737838-660b75526801?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&w=1080',
  },
  {
    id: 3,
    universalName: 'Natural Texture Cut',
    koreanName: '내추럴 텍스처 컷',
    keywords: ['모던', '시크함', '깔끔함', '텍스처', '자연스러움'],
    matchRate: 91,
    description:
      '각진 얼굴형의 날카로운 선을 완화하는 내추럴 텍스처 컷입니다. 자연스러운 질감과 볼륨이 균형 잡힌 인상을 만들어 줍니다.',
    faceRatioData: {
      golden: '0.75~0.82',
      forehead: '사각형 이마 완화',
      jaw: '하악 각도 커버',
      suitableFaces: ['각진형', '사각형', '긴형'],
    },
    priceRange: '5~6만원',
    length: '숏미디엄',
    gender: 'male',
    imageUrl:
      'https://images.unsplash.com/photo-1627238773196-423495d97424?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&w=1080',
  },
  {
    id: 4,
    universalName: 'Classic Bob',
    koreanName: '클래식 밥 스타일',
    keywords: ['우아함', '클래식', '세련됨', '단발', '정돈됨'],
    matchRate: 87,
    description:
      '달걀형 얼굴의 황금 비율을 더욱 부각시키는 클래식 밥 스타일입니다. 단정하고 세련된 라인이 전문적인 이미지를 완성합니다.',
    faceRatioData: {
      golden: '0.88~0.95',
      forehead: '황금 비율 얼굴 모든 형태에 적합',
      jaw: '턱선 라인을 깔끔하게 강조',
      suitableFaces: ['달걀형', '타원형', '둥근형'],
    },
    priceRange: '5~7만원',
    length: '단발 (턱선 길이)',
    gender: 'female',
    imageUrl:
      'https://images.unsplash.com/photo-1737652423535-c1b0096f9244?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&w=1080',
  },
];

export const trendReport = [
  {
    id: 1,
    rank: 1,
    universalName: 'Layered Medium Wave',
    koreanName: '레이어드 미디엄 웨이브',
    count: 34,
    description: '이번 주 가장 많이 선택된 스타일. 타원형·달걀형 고객에게 높은 만족도.',
    hairstyleId: 1,
  },
  {
    id: 2,
    rank: 2,
    universalName: 'Classic Bob',
    koreanName: '클래식 밥 스타일',
    count: 28,
    description: '세련되고 정돈된 느낌으로 30~40대 직장 여성층에서 인기.',
    hairstyleId: 4,
  },
  {
    id: 3,
    rank: 3,
    universalName: 'Soft Layer Perm',
    koreanName: '소프트 레이어 펌',
    count: 21,
    description: '20대 고객을 중심으로 큐트하고 활발한 이미지 연출에 선호.',
    hairstyleId: 2,
  },
  {
    id: 4,
    rank: 4,
    universalName: 'Natural Texture Cut',
    koreanName: '내추럴 텍스처 컷',
    count: 17,
    description: '남성 고객 중심. 직장·비즈니스 분위기에 최적화된 깔끔한 스타일.',
    hairstyleId: 3,
  },
];

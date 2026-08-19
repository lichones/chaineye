// =====================================================================
// ChainEye 프론트엔드 설정 (config)
// ---------------------------------------------------------------------
// 모든 값은 Vite 빌드타임 환경변수(import.meta.env.VITE_*)로 주입됩니다.
//
// API_BASE : FastAPI 백엔드의 베이스 URL.
//   - 기본값 '' (빈 문자열) = SAME ORIGIN(동일 출처). 백엔드가 빌드된 프론트를
//     정적 파일로 서빙하면 `POST /score` 는 배포 도메인 기준으로 해석됩니다.
//   - 별도 백엔드로 로컬 개발 시 VITE_API_BASE=http://localhost:8000 처럼 지정.
//
// USE_MOCK : true  -> 백엔드 없이 하드코딩된 샘플 데이터로 동작 (독립 데모)
//            false -> API_BASE 의 실제 백엔드를 호출 (프로덕션 기본값)
//   - 문자열 'true' 일 때만 mock. 기본값은 false(실제 API).
//   - .env.development 에서 VITE_USE_MOCK=true 로 두어 `npm run dev` 는
//     기본적으로 독립 mock 데모로 동작합니다.
// =====================================================================

// 빈 문자열('')이면 동일 출처(상대경로) 요청. 절대 URL이면 해당 호스트로 요청.
export const API_BASE = import.meta.env.VITE_API_BASE ?? ''

// 'true' 문자열일 때만 mock 모드. 그 외(미설정 포함)는 실제 백엔드 호출.
export const USE_MOCK = (import.meta.env.VITE_USE_MOCK ?? 'false') === 'true'

// 트레이스(자금 흐름 그래프) 조회 시 탐색할 홉(hop) 수
export const DEFAULT_HOPS = 2

// 입력창에 노출할 예시 트랜잭션 ID (클릭 시 즉시 분석)
export const EXAMPLE_TXIDS = [
  {
    txId: '70424581',
    label: '검토 후보', // 양성 2/6개와 후보 경로 1개가 보이는 공개 Elliptic 테스트 거래
  },
  {
    txId: '114498409',
    label: '낮은 위험', // 6개 노드 모두 임계값 미만인 licit 테스트 거래
  },
  {
    txId: '999999999999',
    label: '미평가', // 데이터 범위 밖: unknown/abstain 동작 확인
  },
]

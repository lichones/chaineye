// =====================================================================
// API 클라이언트 - USE_MOCK 값에 따라 mock 또는 실제 백엔드 호출을 분기.
// API_BASE 가 '' (빈 문자열)이면 동일 출처(상대경로)로 요청합니다.
//   예) API_BASE='' , path='/score'  ->  fetch('/score')  (same-origin)
//       API_BASE='http://localhost:8000' -> fetch('http://localhost:8000/score')
// =====================================================================
import { API_BASE, USE_MOCK, DEFAULT_HOPS } from './config'
import { mockScore, mockTrace, mockReport } from './mockData'

// mock 모드에서 실제 네트워크 지연처럼 보이게 하는 약간의 딜레이
function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

// API_BASE 의 후행 슬래시를 제거해 '//' 중복을 방지. path 는 항상 '/'로 시작.
function buildUrl(path) {
  const base = (API_BASE || '').replace(/\/+$/, '')
  return `${base}${path}`
}

async function postJson(path, body) {
  const res = await fetch(buildUrl(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    throw new Error(`API ${path} 오류: ${res.status} ${res.statusText}`)
  }
  return res.json()
}

async function getJson(path) {
  const res = await fetch(buildUrl(path))
  if (!res.ok) {
    throw new Error(`API ${path} 오류: ${res.status} ${res.statusText}`)
  }
  return res.json()
}

// GET /health — 서버가 확인한 provider mode를 화면의 기준으로 사용한다.
export async function fetchHealth() {
  if (USE_MOCK) {
    return { status: 'ok', modelLoaded: false, mode: 'mock' }
  }
  return getJson('/health')
}

// POST /score
export async function fetchScore(txId) {
  if (USE_MOCK) {
    await delay(300)
    return mockScore(txId)
  }
  return postJson('/score', { txId })
}

// POST /trace
export async function fetchTrace(txId, hops = DEFAULT_HOPS) {
  if (USE_MOCK) {
    await delay(350)
    return mockTrace(txId, hops)
  }
  return postJson('/trace', { txId, hops })
}

// POST /report
// 백엔드 ReportRequest 는 label(필수)을 요구하므로 반드시 함께 전송한다.
export async function fetchReport(
  txId,
  score,
  label,
  decisionThreshold,
  topFactors,
  graphStats,
) {
  if (USE_MOCK) {
    await delay(400)
    return mockReport(txId, score, label, decisionThreshold, topFactors, graphStats)
  }
  return postJson('/report', {
    txId,
    score,
    label,
    decisionThreshold,
    topFactors,
    graphStats,
  })
}

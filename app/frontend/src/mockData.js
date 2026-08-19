// =====================================================================
// MOCK 데이터 - USE_MOCK=true 일 때 사용되는 현실적인 샘플 응답.
// 백엔드가 아직 없어도 UI 전체를 데모할 수 있도록 구성.
// =====================================================================

// 입력한 txId 문자열로부터 0~1 사이의 결정적(deterministic) 유사난수 생성
function seededRandom(str, salt = 0) {
  let h = 2166136261 ^ salt
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  // 0~1 로 정규화
  return ((h >>> 0) % 100000) / 100000
}

function shortId(str, salt) {
  const r = Math.floor(seededRandom(str, salt) * 0xffffffff)
  return r.toString(16).padStart(8, '0')
}

// ---------------------------------------------------------------------
// POST /score
// ---------------------------------------------------------------------
export function mockScore(txId) {
  const base = seededRandom(txId, 7)
  const riskScore = Math.round(20 + base * 78) // 20~98 사이
  const illicit = riskScore >= 50

  const factorPool = [
    { feature: '믹싱 서비스(Tornado 유형) 경유 이력', impact: 0.28 },
    { feature: '다크웹 마켓 연관 주소와 근접', impact: 0.21 },
    { feature: '피어링(peeling chain) 구조 자금 분할', impact: 0.17 },
    { feature: '고위험 거래소 입금 패턴', impact: 0.14 },
    { feature: '짧은 시간 내 다중 홉 이동', impact: 0.11 },
    { feature: '신규 생성 주소로의 집중 송금', impact: 0.09 },
    { feature: '제재 대상(OFAC) 주소와의 간접 연결', impact: 0.24 },
    { feature: '정상 거래소 KYC 경유 (위험 완화)', impact: -0.12 },
  ]

  // txId 시드로 상위 요인 4개 선택
  const start = Math.floor(seededRandom(txId, 3) * factorPool.length)
  const topFactors = []
  for (let i = 0; i < 4; i++) {
    topFactors.push(factorPool[(start + i) % factorPool.length])
  }
  // impact 절대값 기준 정렬
  topFactors.sort((a, b) => Math.abs(b.impact) - Math.abs(a.impact))

  return {
    txId,
    riskScore,
    decisionThreshold: 50,
    label: illicit ? 'illicit' : 'licit',
    topFactors,
  }
}

// ---------------------------------------------------------------------
// POST /trace
// ---------------------------------------------------------------------
const HIGH_RISK = 50 // mock 모델 판정 임계값
const MAX_PATHS = 8

export function mockTrace(txId, hops = 2) {
  const focusId = txId
  const nodes = [{ id: focusId, risk: mockScore(txId).riskScore, focus: true }]
  const edges = []

  // 상위(입력측) 노드 2개
  const inA = shortId(txId, 11)
  const inB = shortId(txId, 12)
  // 하위(출력측) 노드 3개
  const outA = shortId(txId, 21)
  const outB = shortId(txId, 22)
  const outC = shortId(txId, 23)

  const mk = (id, salt) => ({
    id,
    risk: Math.round(seededRandom(id, salt) * 100),
    focus: false,
  })

  // 데모에서 항상 의심 경로가 보이도록 하위 체인(outA -> leafA)을 고위험으로 고정
  const outANode = { ...mk(outA, 3), risk: 88 }
  nodes.push(mk(inA, 1), mk(inB, 2), outANode, mk(outB, 4), mk(outC, 5))

  edges.push(
    { source: inA, target: focusId },
    { source: inB, target: focusId },
    { source: focusId, target: outA },
    { source: focusId, target: outB },
    { source: focusId, target: outC },
  )

  // 2홉 이상이면 하위 노드에서 한 단계 더 확장
  if (hops >= 2) {
    const leafA = shortId(txId, 31)
    const leafB = shortId(txId, 32)
    // leafA 도 고위험으로 고정 -> focus -> outA -> leafA 자금세탁 경로 형성
    nodes.push({ ...mk(leafA, 6), risk: 94 }, mk(leafB, 7))
    edges.push(
      { source: outA, target: leafA },
      { source: outB, target: leafB },
      { source: outC, target: leafA },
    )
  }

  // 각 노드에 모델 임계값 기준 modelPositive 플래그 부여
  for (const n of nodes) {
    n.modelPositive = n.risk >= HIGH_RISK
  }

  const candidatePaths = buildSuspiciousPaths(focusId, nodes, edges, hops)
  return { nodes, edges, candidatePaths, decisionThreshold: HIGH_RISK }
}

// focus 에서 시작해 고위험 노드에서 끝나는 방향성 경로(길이 2..hops+1) 탐색
function buildSuspiciousPaths(focus, nodes, edges, hops) {
  const riskMap = {}
  for (const n of nodes) riskMap[n.id] = n.risk
  const dadj = {}
  for (const e of edges) {
    ;(dadj[e.source] = dadj[e.source] || []).push(e.target)
  }
  const maxLenNodes = Math.max(Number(hops) || 1, 1) + 1
  const paths = []
  const seen = new Set()

  const walk = (node, path) => {
    if (paths.length >= MAX_PATHS || path.length >= maxLenNodes) return
    for (const nxt of dadj[node] || []) {
      if (path.includes(nxt)) continue
      const newPath = [...path, nxt]
      if ((riskMap[nxt] || 0) >= HIGH_RISK) {
        const key = newPath.join('>')
        if (!seen.has(key)) {
          seen.add(key)
          paths.push(newPath)
          if (paths.length >= MAX_PATHS) return
        }
      }
      walk(nxt, newPath)
      if (paths.length >= MAX_PATHS) return
    }
  }

  walk(focus, [focus])
  return paths
}

// ---------------------------------------------------------------------
// POST /report
// ---------------------------------------------------------------------
export function mockReport(txId, score, label, decisionThreshold, topFactors, graphStats) {
  const modelLabel = label === 'illicit' ? '모델 양성(illicit class)' : '모델 음성(licit class)'
  const priority = score >= decisionThreshold ? '우선 검토' : '낮은 우선순위'
  const factorLines = (topFactors || [])
    .map(
      (f, i) =>
        `${i + 1}. ${f.feature} — 기여도 ${(f.impact * 100).toFixed(1)}%`,
    )
    .join('\n')

  const stats = graphStats || {}

  return {
    generator: 'template',
    report: `# ChainEye AML 모델 검토 지원 보고서

## 1. 개요
- 대상 트랜잭션: \`${txId}\`
- 모델 점수: **${score}/100** (검토 임계값 ${decisionThreshold}, ${priority})
- 모델 판정: ${modelLabel}
- 분석 일시: ${new Date().toLocaleString('ko-KR')}
- 분석 엔진: ChainEye v0.1 (그래프 + ML 하이브리드)

## 2. 모델 기여도
${factorLines || '- 제공된 모델 기여도가 없습니다.'}

> 기여도는 모델 출력에 대한 설명이며 거래 증거가 아닙니다.

## 3. 그래프 관찰 사실
원본 데이터의 방향성 인접 관계로 총 ${stats.nodeCount ?? '-'}개 노드와 ${stats.edgeCount ?? '-'}개 엣지를 표시했습니다.
모델 임계값 이상 노드는 ${stats.highRiskCount ?? '-'}개입니다. 인접 관계만으로 동일 자금 이동,
주소 소유권 또는 범죄 관련성을 입증할 수 없습니다.

## 4. 권고 조치
- ${score >= decisionThreshold ? '독립 원천자료가 있다면 분석관의 우선 검토 대기열에 배치합니다.' : '모델 음성만으로 정상 또는 안전을 확정하지 않습니다.'}
- STR 작성·보고 여부는 내부 절차와 담당자의 최종 판단을 거쳐 결정합니다.

> ⚠️ Elliptic 벤치마크 모델 예측이며 실시간 주소 위험도나 범죄 사실이 아닙니다.
`,
  }
}

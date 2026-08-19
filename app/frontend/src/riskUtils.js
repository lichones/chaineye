// 모델 점수(0~100)를 검토 우선순위/색상으로 변환하는 공통 유틸

export function riskLevel(score, label, decisionThreshold = 50) {
  if (score == null || !Number.isFinite(Number(score))) {
    return { label: '미평가', color: '#94a3b8', key: 'unknown' }
  }
  if (label === 'illicit' || score >= decisionThreshold) {
    return { label: '우선 검토', color: '#ef4444', key: 'high' } // red
  }
  if (score >= Math.max(1, decisionThreshold / 2)) {
    return { label: '추가 검토', color: '#f59e0b', key: 'mid' } // amber
  }
  return { label: '낮은 우선순위', color: '#22c55e', key: 'low' } // green
}

// 그래프 노드용: 검증에서 선택한 모델 임계값 이상 여부
export function isHighRisk(score, decisionThreshold = 50) {
  return score != null && Number(score) >= decisionThreshold
}

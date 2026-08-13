// 위험 점수(0~100)를 라벨/색상으로 변환하는 공통 유틸

export function riskLevel(score) {
  if (score >= 70) {
    return { label: '위험', color: '#ef4444', key: 'high' } // red
  }
  if (score >= 40) {
    return { label: '주의', color: '#f59e0b', key: 'mid' } // amber
  }
  return { label: '안전', color: '#22c55e', key: 'low' } // green
}

// 그래프 노드용: 고위험(70+) 여부
export function isHighRisk(score) {
  return score >= 70
}

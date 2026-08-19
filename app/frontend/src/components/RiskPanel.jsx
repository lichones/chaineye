import React from 'react'
import { riskLevel } from '../riskUtils'

// 원형 게이지 (순수 SVG, 외부 라이브러리 불필요)
function Gauge({ score, label, decisionThreshold }) {
  const level = riskLevel(score, label, decisionThreshold)
  const size = 190
  const stroke = 16
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const pct = Math.max(0, Math.min(100, score)) / 100
  const dash = c * pct

  return (
    <div className="gauge-wrap">
      <svg width={size} height={size} className="gauge">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="#232a3a"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={level.color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${c - dash}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: 'stroke-dasharray 0.6s ease, stroke 0.3s' }}
        />
      </svg>
      <div className="gauge-center">
        <div className="gauge-score" style={{ color: level.color }}>
          {score}
        </div>
        <div className="gauge-max">/ 100</div>
      </div>
    </div>
  )
}

export default function RiskPanel({ result }) {
  if (!result) {
    return (
      <div className="panel risk-panel">
        <h2 className="panel-title">모델 검토 점수</h2>
        <div className="empty">트랜잭션을 분석하면 모델 점수가 표시됩니다.</div>
      </div>
    )
  }

  const { riskScore, decisionThreshold = 50, label, topFactors } = result

  if (label === 'unknown' || riskScore == null) {
    return (
      <div className="panel risk-panel">
        <h2 className="panel-title">모델 검토 점수</h2>
        <div className="unknown-result" role="status">
          <div className="unknown-result-title">평가 불가</div>
          <p>
            이 거래 ID는 현재 모델의 데이터 범위에 없어 모델 점수를 산출하지
            않았습니다.
          </p>
          <p>
            데이터 부재는 정상 거래의 근거가 아닙니다. 온체인 데이터 수집 또는
            별도 분석이 필요합니다.
          </p>
        </div>
      </div>
    )
  }

  const level = riskLevel(riskScore, label, decisionThreshold)

  return (
    <div className="panel risk-panel">
      <h2 className="panel-title">모델 검토 점수</h2>

      <Gauge
        score={riskScore}
        label={label}
        decisionThreshold={decisionThreshold}
      />

      <div className="decision-threshold">
        검토 임계값: {decisionThreshold}점
      </div>

      <div className="risk-badge" style={{ background: level.color }}>
        {level.label}
        <span className="risk-badge-sub">
          {label === 'illicit'
            ? '모델 양성 · 불법 확정 아님'
            : '모델 음성 · 정상 확정 아님'}
        </span>
      </div>

      <div className="factors">
        <div className="factors-title">모델 기여도 (SHAP)</div>
        <ul className="factors-list">
          {topFactors.map((f, i) => {
            const positive = f.impact >= 0
            return (
              <li key={i} className="factor-item">
                <span
                  className="factor-bar"
                  style={{
                    width: `${Math.min(100, Math.abs(f.impact) * 200)}%`,
                    background: positive ? '#ef4444' : '#22c55e',
                  }}
                />
                <span className="factor-text">{f.feature}</span>
                <span
                  className="factor-impact"
                  style={{ color: positive ? '#f87171' : '#4ade80' }}
                >
                  {positive ? '+' : ''}
                  {(f.impact * 100).toFixed(0)}%
                </span>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}

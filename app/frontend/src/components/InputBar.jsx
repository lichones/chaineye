import React from 'react'
import { EXAMPLE_TXIDS } from '../config'

// 상단 입력바: txId 입력 + 분석 버튼 + 예시 칩
export default function InputBar({ value, onChange, onAnalyze, loading }) {
  const handleKey = (e) => {
    if (e.key === 'Enter' && !loading) onAnalyze()
  }

  return (
    <div className="input-bar">
      <div className="input-row">
        <input
          className="tx-input"
          type="text"
          placeholder="비트코인 트랜잭션 ID(txId)를 입력하세요"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKey}
          spellCheck={false}
        />
        <button
          className="analyze-btn"
          onClick={onAnalyze}
          disabled={loading || !value.trim()}
        >
          {loading ? '분석 중…' : '분석'}
        </button>
      </div>
      <div className="chips">
        <span className="chips-label">예시:</span>
        {EXAMPLE_TXIDS.map((tx) => (
          <button
            key={tx}
            className="chip"
            title={tx}
            onClick={() => onChange(tx)}
            disabled={loading}
          >
            {tx.slice(0, 10)}…{tx.slice(-6)}
          </button>
        ))}
      </div>
    </div>
  )
}

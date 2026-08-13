import React, { useState, useCallback } from 'react'
import InputBar from './components/InputBar'
import RiskPanel from './components/RiskPanel'
import GraphPanel from './components/GraphPanel'
import ReportPanel from './components/ReportPanel'
import { fetchScore, fetchTrace, fetchReport } from './api'
import { USE_MOCK, DEFAULT_HOPS } from './config'
import { isHighRisk } from './riskUtils'

export default function App() {
  const [txId, setTxId] = useState('')
  const [loading, setLoading] = useState(false)
  const [reportLoading, setReportLoading] = useState(false)
  const [error, setError] = useState('')

  const [score, setScore] = useState(null) // /score 응답
  const [trace, setTrace] = useState(null) // /trace 응답
  const [report, setReport] = useState('') // /report 응답 텍스트

  const analyze = useCallback(async () => {
    const id = txId.trim()
    if (!id) return
    setLoading(true)
    setError('')
    setReport('')
    setReportLoading(true)
    try {
      // 1) 위험 점수 + 2) 자금 흐름 그래프를 병렬 호출
      const [scoreRes, traceRes] = await Promise.all([
        fetchScore(id),
        fetchTrace(id, DEFAULT_HOPS),
      ])
      setScore(scoreRes)
      setTrace(traceRes)

      // 3) 그래프 통계 계산 후 리포트 요청
      const graphStats = {
        nodeCount: traceRes.nodes.length,
        edgeCount: traceRes.edges.length,
        highRiskCount: traceRes.nodes.filter((n) => isHighRisk(n.risk)).length,
        hops: DEFAULT_HOPS,
      }
      const reportRes = await fetchReport(
        id,
        scoreRes.riskScore,
        scoreRes.label,
        scoreRes.topFactors,
        graphStats,
      )
      setReport(reportRes.report)
    } catch (e) {
      setError(e.message || '분석 중 오류가 발생했습니다.')
      setScore(null)
      setTrace(null)
    } finally {
      setLoading(false)
      setReportLoading(false)
    }
  }, [txId])

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <span className="logo">◈</span>
          <div>
            <div className="brand-name">
              ChainEye <span className="brand-ko">체인아이</span>
            </div>
            <div className="brand-sub">가상자산 자금세탁 탐지 · 추적 시스템</div>
          </div>
        </div>
        <div className={`mode-tag ${USE_MOCK ? 'mock' : 'live'}`}>
          {USE_MOCK ? 'MOCK 데모 모드' : 'LIVE API'}
        </div>
      </header>

      <InputBar
        value={txId}
        onChange={setTxId}
        onAnalyze={analyze}
        loading={loading}
      />

      {error && <div className="error-bar">⚠ {error}</div>}

      <main className="grid">
        <div className="col-left">
          <RiskPanel result={score} />
        </div>
        <div className="col-center">
          <GraphPanel trace={trace} />
        </div>
        <div className="col-right">
          <ReportPanel report={report} loading={reportLoading} />
        </div>
      </main>

      <footer className="app-footer">
        2026 금융 AI Challenge · ChainEye 프로토타입 — 방어적 분석 데모용
      </footer>
    </div>
  )
}

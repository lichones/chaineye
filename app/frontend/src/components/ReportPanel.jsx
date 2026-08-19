import React from 'react'

// 아주 가벼운 마크다운-유사 렌더러 (외부 라이브러리 없이).
// # 제목, ## 소제목, - 목록, > 인용, **굵게** 정도만 처리.
function renderInline(text, keyPrefix) {
  // **굵게** 처리
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
  return parts.map((p, i) => {
    if (/^\*\*[^*]+\*\*$/.test(p)) {
      return <strong key={`${keyPrefix}-b${i}`}>{p.slice(2, -2)}</strong>
    }
    if (/^`[^`]+`$/.test(p)) {
      return (
        <code key={`${keyPrefix}-c${i}`} className="inline-code">
          {p.slice(1, -1)}
        </code>
      )
    }
    return <span key={`${keyPrefix}-t${i}`}>{p}</span>
  })
}

function renderMarkdown(md) {
  const lines = md.split('\n')
  const out = []
  lines.forEach((line, idx) => {
    const key = `l${idx}`
    if (line.startsWith('# ')) {
      out.push(<h3 key={key} className="md-h1">{renderInline(line.slice(2), key)}</h3>)
    } else if (line.startsWith('## ')) {
      out.push(<h4 key={key} className="md-h2">{renderInline(line.slice(3), key)}</h4>)
    } else if (line.startsWith('> ')) {
      out.push(<blockquote key={key} className="md-quote">{renderInline(line.slice(2), key)}</blockquote>)
    } else if (/^\d+\.\s/.test(line)) {
      out.push(<div key={key} className="md-li ol">{renderInline(line, key)}</div>)
    } else if (line.startsWith('- ')) {
      out.push(<div key={key} className="md-li">• {renderInline(line.slice(2), key)}</div>)
    } else if (line.trim() === '') {
      out.push(<div key={key} className="md-gap" />)
    } else {
      out.push(<p key={key} className="md-p">{renderInline(line, key)}</p>)
    }
  })
  return out
}

const GENERATOR_LABELS = {
  claude: '생성 AI · Claude',
  openai: '생성 AI · OpenAI',
  template: '결정론적 템플릿',
  suppressed: '판단 거부 · 생성 억제',
}

export default function ReportPanel({ report, generator, loading }) {
  return (
    <div className="panel report-panel">
      <div className="report-head">
        <h2 className="panel-title">검토 지원 리포트</h2>
        <div className="report-actions">
          {generator && (
            <span className={`generator-tag ${generator}`}>
              {GENERATOR_LABELS[generator] || generator}
            </span>
          )}
          {report && (
            <button
              className="copy-btn"
              onClick={() => navigator.clipboard?.writeText(report)}
              title="리포트 원문 복사"
            >
              복사
            </button>
          )}
        </div>
      </div>
      {loading ? (
        <div className="empty">검토 리포트 생성 중…</div>
      ) : !report ? (
        <div className="empty">분석 완료 시 모델 검토 리포트가 생성됩니다.</div>
      ) : (
        <div className="report-body">{renderMarkdown(report)}</div>
      )}
    </div>
  )
}

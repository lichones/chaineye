import React, { useMemo, useRef, useEffect } from 'react'
import CytoscapeComponent from 'react-cytoscapejs'
import { isHighRisk } from '../riskUtils'

// candidatePaths(분석 검토 후보 경로)의 방향성 간선 집합 생성
function buildPathEdgeSet(trace) {
  const set = new Set()
  const paths = (trace && trace.candidatePaths) || []
  for (const path of paths) {
    for (let i = 0; i + 1 < path.length; i++) {
      set.add(`${path[i]}->${path[i + 1]}`)
    }
  }
  return set
}

// trace 응답 -> cytoscape elements 변환
function buildElements(trace) {
  if (!trace) return []
  const pathEdges = buildPathEdgeSet(trace)
  const nodes = trace.nodes.map((n) => {
    const scored = n.scored !== false && n.risk != null
    // 백엔드의 원시 확률 기반 판정을 우선하고, 구 응답만 표시값으로 보완
    const highRisk =
      n.modelPositive != null
        ? n.modelPositive
        : isHighRisk(n.risk, trace.decisionThreshold)
    let cls = 'normal'
    if (!scored) cls = n.focus ? 'unknown-focus' : 'unknown'
    else if (n.focus) cls = 'focus'
    else if (highRisk) cls = 'high'
    return {
      data: {
        id: n.id,
        label: `${n.id.slice(0, 6)}…`,
        risk: n.risk,
        cls,
      },
      classes: cls,
    }
  })
  const edges = trace.edges.map((e, i) => {
    const onPath = pathEdges.has(`${e.source}->${e.target}`)
    return {
      data: {
        id: `e${i}-${e.source}-${e.target}`,
        source: e.source,
        target: e.target,
        candidatePath: onPath,
      },
      classes: onPath ? 'candidate-path' : '',
    }
  })
  return [...nodes, ...edges]
}

const stylesheet = [
  {
    selector: 'node',
    style: {
      'background-color': '#6b7280', // gray - 정상
      label: 'data(label)',
      color: '#cbd5e1',
      'font-size': '9px',
      'text-valign': 'bottom',
      'text-halign': 'center',
      'text-margin-y': 4,
      width: 34,
      height: 34,
      'border-width': 2,
      'border-color': '#1f2430',
    },
  },
  {
    selector: 'node.unknown, node.unknown-focus',
    style: {
      'background-color': '#94a3b8',
      'border-color': '#e2e8f0',
      'border-style': 'dashed',
    },
  },
  {
    selector: 'node.unknown-focus',
    style: {
      'border-width': 4,
      width: 50,
      height: 50,
      'font-size': '11px',
      color: '#fff',
      'font-weight': 'bold',
    },
  },
  {
    selector: 'node.high',
    style: {
      'background-color': '#ef4444', // red - 고위험
      'border-color': '#7f1d1d',
    },
  },
  {
    selector: 'node.focus',
    style: {
      'background-color': '#dc2626', // red - 포커스(대상)
      'border-color': '#fca5a5',
      'border-width': 4,
      width: 50,
      height: 50,
      'font-size': '11px',
      color: '#fff',
      'font-weight': 'bold',
    },
  },
  {
    selector: 'edge',
    style: {
      width: 2,
      'line-color': '#3f4a5f',
      'target-arrow-color': '#3f4a5f',
      'target-arrow-shape': 'triangle',
      'curve-style': 'bezier',
      'arrow-scale': 1.1,
    },
  },
  {
    // 분석 검토 후보 경로에 속한 간선: 밝은 주황/빨강, 굵고 강조
    selector: 'edge.candidate-path',
    style: {
      width: 5,
      'line-color': '#f97316', // bright orange - 경보색
      'target-arrow-color': '#f97316',
      'arrow-scale': 1.5,
      'line-style': 'solid',
      'z-index': 20,
      'overlay-color': '#f97316',
      'overlay-opacity': 0.12,
      'overlay-padding': 3,
      // 흐름 방향으로 흐르는 "marching ants" 점선 (offset은 아래 rAF 루프가 구동)
      'line-dash-pattern': [10, 6],
      'line-dash-offset': 0,
    },
  },
]

const layout = {
  name: 'breadthfirst',
  directed: true,
  spacingFactor: 1.3,
  padding: 24,
  animate: true,
  animationDuration: 500,
}

export default function GraphPanel({ trace }) {
  const elements = useMemo(() => buildElements(trace), [trace])
  const animRef = useRef(null)

  // 의심 경로 간선에 marching-ants 애니메이션 적용
  const registerCy = (cy) => {
    if (!cy) return
    if (animRef.current) cancelAnimationFrame(animRef.current)
    let offset = 0
    const tick = () => {
      const eds = cy.edges('.candidate-path')
      if (eds.length) {
        offset = (offset - 1) % 32
        eds.style('line-dash-offset', offset)
      }
      animRef.current = requestAnimationFrame(tick)
    }
    animRef.current = requestAnimationFrame(tick)
  }

  useEffect(
    () => () => {
      if (animRef.current) cancelAnimationFrame(animRef.current)
    },
    [],
  )

  const pathCount =
    (trace && trace.candidatePaths && trace.candidatePaths.length) || 0
  const decisionThreshold = trace?.decisionThreshold ?? 50

  return (
    <div className="panel graph-panel">
      <h2 className="panel-title">거래 인접 그래프</h2>
      {!trace ? (
        <div className="empty">분석 시 원본 데이터의 방향성 인접 관계가 표시됩니다.</div>
      ) : (
        <>
          <div className="graph-canvas">
            <CytoscapeComponent
              key={trace.nodes.map((n) => n.id).join(',')}
              cy={registerCy}
              elements={elements}
              stylesheet={stylesheet}
              layout={layout}
              style={{ width: '100%', height: '100%' }}
              minZoom={0.3}
              maxZoom={2.5}
            />
          </div>
          <div className="graph-legend">
            <span>
              <i className="dot" style={{ background: '#dc2626' }} /> 대상 트랜잭션
            </span>
            <span>
              <i className="dot" style={{ background: '#ef4444' }} /> 모델 양성(
              {decisionThreshold}+)
            </span>
            <span>
              <i className="dot" style={{ background: '#6b7280' }} /> 일반
            </span>
            <span>
              <i className="dot" style={{ background: '#94a3b8' }} /> 미평가
            </span>
            <span>
              <i
                className="dot"
                style={{ background: '#f97316', borderRadius: 2 }}
              />{' '}
              검토 후보 인접 경로
              {pathCount > 0 ? ` (${pathCount})` : ''}
            </span>
          </div>
        </>
      )}
    </div>
  )
}

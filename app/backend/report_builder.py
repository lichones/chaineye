"""
Template-based Korean report generator for ChainEye (체인아이).

No external / paid LLM API is used here — this is the MVP compliance-report
generator. It renders a structured, professional FIU/compliance-style report
purely from the inputs.

TODO(claude-api): This template renderer can later be swapped for (or augmented
by) a Claude API call to produce richer narrative prose. When doing so, keep
this template as the deterministic fallback for offline / rate-limited use.
See the `claude-api` skill for model ids and SDK usage. DO NOT implement the
API call now (MVP requirement: template-based, no paid API).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List


# Human-readable Korean labels for known feature names.
_FEATURE_KO: Dict[str, str] = {
    "in_degree": "유입 거래 연결 수(in-degree)",
    "out_degree": "유출 거래 연결 수(out-degree)",
    "total_btc_received": "누적 수신 BTC 규모",
    "total_btc_sent": "누적 송신 BTC 규모",
    "unique_counterparties": "고유 거래상대방 수",
    "mixer_exposure_ratio": "믹서(자금세탁 서비스) 노출 비율",
    "peel_chain_depth": "필체인(peel chain) 분할 깊이",
    "fan_out_ratio": "다중 분산 송금(fan-out) 비율",
    "avg_hop_interval_sec": "홉 간 평균 이체 간격",
    "darkmarket_proximity": "다크마켓 근접도",
    "exchange_deposit_ratio": "거래소 입금 비율",
    "fresh_address_ratio": "신규 주소 사용 비율",
}


def _grade(score: int) -> str:
    """Map a 0-100 score to a Korean risk grade band."""
    if score >= 70:
        return "위험"
    if score >= 40:
        return "주의"
    return "안전"


def _feature_ko(feature: str) -> str:
    return _FEATURE_KO.get(feature, feature)


def _factor_sentence(factor: Dict[str, Any]) -> str:
    feature = str(factor.get("feature", "알수없음"))
    impact = float(factor.get("impact", 0.0))
    name = _feature_ko(feature)
    if impact >= 0:
        direction = "위험도를 높이는 방향"
    else:
        direction = "위험도를 낮추는 방향"
    return f"- {name}: 판단 기여도 {impact:+.3f} ({direction}으로 작용)"


def build_report(
    tx_id: str,
    score: int,
    label: str,
    top_factors: List[Dict[str, Any]],
    graph_stats: Dict[str, Any],
) -> str:
    """Render the full Korean investigation/compliance report as a string."""
    grade = _grade(int(score))
    label_ko = "불법(illicit) 의심" if str(label).lower() == "illicit" else "정상(licit) 추정"

    node_count = int(graph_stats.get("nodeCount", 0))
    edge_count = int(graph_stats.get("edgeCount", 0))
    # 프론트엔드는 고위험(위험도 70+) 이웃 수를 highRiskCount 로 전송한다.
    # illicitNeighbors(구 스키마)가 오면 우선 사용하고, 없으면 highRiskCount 로 폴백.
    illicit_neighbors = int(
        graph_stats.get("illicitNeighbors")
        or graph_stats.get("highRiskCount", 0)
    )
    # 초점 노드 자신이 고위험이면 이웃 카운트에서 제외 (자기 자신은 이웃이 아님)
    if illicit_neighbors > 0 and int(score) >= 70:
        illicit_neighbors = max(0, illicit_neighbors - 1)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 한 줄 요지
    if grade == "위험":
        summary_line = (
            "해당 거래는 자금세탁 위험이 높은 것으로 평가되며 즉시 심화 검토가 필요합니다."
        )
    elif grade == "주의":
        summary_line = (
            "해당 거래는 일부 위험 신호가 관측되어 추가 모니터링이 권고됩니다."
        )
    else:
        summary_line = (
            "해당 거래에서는 유의미한 자금세탁 위험 신호가 관측되지 않았습니다."
        )

    # 핵심 판단 근거 (상위 3~5개)
    if top_factors:
        factor_lines = [_factor_sentence(f) for f in top_factors[:5]]
        factors_block = "\n".join(factor_lines)
    else:
        factors_block = "- 제공된 판단 근거(topFactors)가 없습니다."

    # 자금흐름 관찰
    if node_count > 0:
        neighbor_ratio = (illicit_neighbors / node_count) * 100.0
    else:
        neighbor_ratio = 0.0
    flow_block = f"- 추적 그래프 내 연결 노드 수: 총 {node_count:,}개"
    if edge_count > 0:
        flow_block += f" / 자금 이동(엣지) {edge_count:,}건"
    flow_block += (
        f"\n- 위험(불법 의심) 이웃 노드 수: {illicit_neighbors:,}개 "
        f"(전체의 약 {neighbor_ratio:.1f}%)"
    )
    if illicit_neighbors > 0:
        flow_block += (
            "\n- 위험 이웃과의 직접 연결이 확인되어 자금 혼합·경유 가능성을 배제할 수 없습니다."
        )
    else:
        flow_block += "\n- 직접 연결된 위험 이웃은 확인되지 않았습니다."

    # 권고 조치 (등급별)
    if grade == "위험":
        action_block = (
            "- 의심거래보고(STR) 작성 및 보고 여부를 우선 검토하십시오.\n"
            "- 해당 주소/거래에 대한 계좌·지갑 모니터링을 강화하십시오.\n"
            "- 연결된 위험 이웃 노드를 포함하여 자금흐름을 수사 참고자료로 정리하십시오.\n"
            "- 필요 시 거래소 KYC 정보 및 트래블룰(Travel Rule) 대상 여부를 확인하십시오."
        )
    elif grade == "주의":
        action_block = (
            "- 거래 패턴을 일정 기간 지속 모니터링하고 임계치 초과 시 재평가하십시오.\n"
            "- 추가 거래 발생 시 상대방 주소의 위험도를 함께 점검하십시오.\n"
            "- 필요 시 고객확인(EDD, 강화된 고객확인) 절차를 검토하십시오."
        )
    else:
        action_block = (
            "- 별도의 즉각 조치는 불필요하나 정기 모니터링 대상에는 유지하십시오.\n"
            "- 향후 위험 신호 변화 시 재평가하십시오."
        )

    report = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 체인아이(ChainEye) 자금세탁 위험 분석 보고서
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 대상 거래 ID : {tx_id}
 위험 점수    : {int(score)} / 100  (등급: {grade})
 모델 판정    : {label_ko}
 생성 일시    : {generated_at}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【위험 요약】
등급: {grade} (위험 점수 {int(score)}점)
{summary_line}

【핵심 판단 근거】
{factors_block}

【자금흐름 관찰】
{flow_block}

【권고 조치】
{action_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 ※ 본 보고서는 체인아이 자동 분석 결과이며, 최종 판단과
    보고 여부 결정은 담당 분석관의 검토를 거쳐야 합니다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

    return report

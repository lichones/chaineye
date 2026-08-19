"""
Deterministic Korean report fallback for ChainEye (체인아이).

The API layer may use an explicitly configured LLM provider. This renderer is
the keyless/offline fallback and deliberately separates model output from
observed graph facts and analyst decisions.
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


def _grade(score: int, label: str, decision_threshold: int) -> str:
    """Map a score to an analyst-review priority, not a crime judgement."""
    if str(label).lower() == "illicit" or score >= decision_threshold:
        return "우선 검토"
    if score >= max(1, decision_threshold // 2):
        return "추가 검토"
    return "낮은 우선순위"


def _feature_ko(feature: str) -> str:
    return _FEATURE_KO.get(feature, feature)


def _factor_sentence(factor: Dict[str, Any]) -> str:
    feature = str(factor.get("feature", "알수없음"))
    impact = float(factor.get("impact", 0.0))
    name = _feature_ko(feature)
    if impact >= 0:
        direction = "모델 출력을 높이는 방향"
    else:
        direction = "모델 출력을 낮추는 방향"
    return f"- {name}: 모델 기여도 {impact:+.3f} ({direction})"


def build_report(
    tx_id: str,
    score: int,
    label: str,
    decision_threshold: int,
    top_factors: List[Dict[str, Any]],
    graph_stats: Dict[str, Any],
) -> str:
    """Render a model-review support report without asserting criminal facts."""
    grade = _grade(int(score), label, int(decision_threshold))
    label_ko = (
        "모델 양성(illicit class)"
        if str(label).lower() == "illicit"
        else "모델 음성(licit class)"
    )

    node_count = int(graph_stats.get("nodeCount", 0))
    edge_count = int(graph_stats.get("edgeCount", 0))
    # 프론트엔드는 모델 임계값 이상 이웃 수를 highRiskCount 로 전송한다.
    # illicitNeighbors(구 스키마)가 오면 우선 사용하고, 없으면 highRiskCount 로 폴백.
    illicit_neighbors = int(
        graph_stats.get("illicitNeighbors")
        or graph_stats.get("highRiskCount", 0)
    )
    # 초점 노드 자신이 고위험이면 이웃 카운트에서 제외 (자기 자신은 이웃이 아님)
    if illicit_neighbors > 0 and str(label).lower() == "illicit":
        illicit_neighbors = max(0, illicit_neighbors - 1)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 한 줄 요지: 임계값 통과는 검토 우선순위일 뿐, 불법 확정이 아니다.
    if grade == "우선 검토":
        summary_line = (
            "검증 세트에서 선택한 임계값 이상으로, 분석관의 우선 검토 대상입니다. "
            "불법 거래나 자금세탁을 확정하는 결과는 아닙니다."
        )
    elif grade == "추가 검토":
        summary_line = (
            "모델 출력이 임계값에 근접해 추가 자료 확인을 고려할 수 있습니다."
        )
    else:
        summary_line = (
            "현재 모델 출력은 임계값 미만입니다. 이는 정상 거래임을 입증하지 않습니다."
        )

    # 핵심 판단 근거 (상위 3~5개)
    if top_factors:
        factor_lines = [_factor_sentence(f) for f in top_factors[:5]]
        factors_block = "\n".join(factor_lines)
    else:
        factors_block = "- 제공된 판단 근거(topFactors)가 없습니다."

    # 그래프 관찰: 엣지는 원본 데이터의 방향성 인접 관계만 뜻한다.
    if node_count > 0:
        neighbor_ratio = (illicit_neighbors / node_count) * 100.0
    else:
        neighbor_ratio = 0.0
    flow_block = f"- 표시된 방향성 거래 인접 노드 수: 총 {node_count:,}개"
    if edge_count > 0:
        flow_block += f" / 원본 그래프 인접 엣지 {edge_count:,}건"
    flow_block += (
        f"\n- 모델 양성으로 분류된 이웃 거래 수: {illicit_neighbors:,}개 "
        f"(전체의 약 {neighbor_ratio:.1f}%)"
    )
    if illicit_neighbors > 0:
        flow_block += (
            "\n- 원본 그래프에서 직접 인접한 모델 양성 거래가 있습니다. "
            "동일 자금의 이동, 주소 소유권 또는 범죄 관련성을 입증하지는 않습니다."
        )
    else:
        flow_block += (
            "\n- 현재 표시 범위에는 직접 인접한 모델 양성 거래가 없습니다. "
            "안전하거나 정상이라는 의미는 아닙니다."
        )

    # 권고 조치: 자동 STR 결정을 내리지 않고 분석관 검토 단계를 명시한다.
    if grade == "우선 검토":
        action_block = (
            "- 독립 원천자료와 고객확인 정보가 있다면 분석관이 함께 검토하십시오.\n"
            "- 모델 기여도는 설명 자료로만 사용하고 실제 거래 증거로 해석하지 마십시오.\n"
            "- STR 작성·보고 여부는 내부 절차와 담당자의 최종 판단을 거쳐 결정하십시오."
        )
    elif grade == "추가 검토":
        action_block = (
            "- 추가 원천자료가 확보되면 재평가하십시오.\n"
            "- 업무 규칙상 필요할 때만 분석관 검토 대기열에 유지하십시오."
        )
    else:
        action_block = (
            "- 모델 음성만으로 종결하지 말고 기존 업무 규칙을 적용하십시오.\n"
            "- 새로운 독립 정보가 들어오면 다시 평가하십시오."
        )

    report = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 체인아이(ChainEye) AML 모델 검토 지원 보고서
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 대상 거래 ID : {tx_id}
 모델 점수    : {int(score)} / 100  (검토 임계값: {int(decision_threshold)}, 우선순위: {grade})
 모델 판정    : {label_ko}
 생성 일시    : {generated_at}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【모델 출력 요약】
검토 우선순위: {grade} (모델 점수 {int(score)}점, 검토 임계값 {int(decision_threshold)}점)
{summary_line}

【모델 기여도】
{factors_block}

【그래프 관찰 사실】
{flow_block}

【권고 조치】
{action_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 ※ 본 결과는 Elliptic 벤치마크 거래에 대한 모델 예측입니다.
    실시간 주소 위험도나 범죄 사실을 뜻하지 않으며, 최종 판단과
    보고 여부는 독립 자료를 확인한 담당 분석관이 결정해야 합니다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

    return report

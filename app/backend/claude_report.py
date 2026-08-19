"""
Claude API 기반 한글 AML 모델 검토 지원 보고서 생성기 (ChainEye / 체인아이).

`report_builder.py` 의 결정론적 템플릿을 대체(또는 보강)하는 LLM 경로입니다.
Anthropic 공식 Python SDK(`anthropic`)를 사용해 FIU/컴플라이언스 스타일의
전문 보고서를 생성합니다.

설계 원칙 — **반드시 우아하게 실패해야 함(graceful degradation)**:
- `anthropic` 패키지가 없거나(ImportError),
- `ANTHROPIC_API_KEY` 환경변수가 없거나,
- API 호출이 예외를 던지면
→ 예외를 전파하지 않고 `None` 을 반환합니다. 호출측(main.py)은 `None` 을 받으면
   `report_builder.build_report()` 템플릿 경로로 폴백합니다.

환경변수:
- `ANTHROPIC_API_KEY`      — API 키(없으면 LLM 경로 비활성, None 반환).
- `CHAINEYE_REPORT_MODEL`  — 사용할 모델 ID. 기본값 "claude-sonnet-5".
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("chaineye.claude_report")

# anthropic 패키지는 선택적 의존성이다. 없어도 import 시점에 절대 죽지 않는다.
try:
    import anthropic  # type: ignore

    _ANTHROPIC_AVAILABLE = True
except Exception as exc:  # noqa: BLE001 - ImportError 및 그 외 모두 흡수
    anthropic = None  # type: ignore
    _ANTHROPIC_AVAILABLE = False
    logger.info("anthropic SDK unavailable (%s) -> LLM report path disabled.", exc)


_DEFAULT_MODEL = "claude-sonnet-5"
_MAX_TOKENS = 2048


# report_builder 와 동일한 한글 피처 라벨(프롬프트 근거 제공용).
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
    if str(label).lower() == "illicit" or score >= decision_threshold:
        return "우선 검토"
    if score >= max(1, decision_threshold // 2):
        return "추가 검토"
    return "낮은 우선순위"


def _feature_ko(feature: str) -> str:
    return _FEATURE_KO.get(feature, feature)


def _format_factors(top_factors: List[Dict[str, Any]]) -> str:
    if not top_factors:
        return "- (제공된 판단 근거 없음)"
    lines = []
    for f in top_factors[:5]:
        feature = str(f.get("feature", "알수없음"))
        impact = float(f.get("impact", 0.0))
        direction = "모델 출력 상승" if impact >= 0 else "모델 출력 하락"
        lines.append(f"- {_feature_ko(feature)} (feature={feature}): 기여도 {impact:+.3f} ({direction})")
    return "\n".join(lines)


def _build_prompt(
    tx_id: str,
    score: int,
    label: str,
    decision_threshold: int,
    top_factors: List[Dict[str, Any]],
    graph_stats: Dict[str, Any],
) -> tuple[str, str]:
    """강한 한글 system/user 프롬프트를 구성해 (system, user) 튜플로 반환."""
    grade = _grade(int(score), label, int(decision_threshold))
    label_ko = (
        "모델 양성(illicit class)"
        if str(label).lower() == "illicit"
        else "모델 음성(licit class)"
    )

    node_count = int(graph_stats.get("nodeCount", 0))
    edge_count = int(graph_stats.get("edgeCount", 0))
    illicit_neighbors = int(
        graph_stats.get("illicitNeighbors") or graph_stats.get("highRiskCount", 0)
    )
    if illicit_neighbors > 0 and str(label).lower() == "illicit":
        illicit_neighbors = max(0, illicit_neighbors - 1)

    system = (
        "당신은 금융회사 AML 모델 검증 담당자를 지원하는 문서 작성 도구입니다. "
        "입력은 Elliptic 벤치마크 거래에 대한 모델 예측과 방향성 인접 그래프이며, "
        "실시간 주소 조회나 범죄 사실이 아닙니다.\n\n"
        "엄격한 규칙:\n"
        "1) 아래에 제공된 수치·라벨·그래프 통계만을 근거로 삼으십시오. 제공되지 않은 사실, "
        "수치, 거래소명, 인물, 지갑 주소를 절대 지어내지 마십시오(환각 금지).\n"
        "2) 모델 양성을 불법·자금세탁 확정으로, 모델 음성을 정상·안전으로 표현하지 마십시오.\n"
        "3) 그래프 인접성을 동일 자금 이동, 주소 소유권, 자금 혼합·계층화 또는 범죄 연관의 증거로 해석하지 마십시오.\n"
        "4) SHAP 기여도는 모델 설명이지 거래 증거가 아님을 유지하십시오.\n"
        "5) 보고서는 다음 4개 섹션만 사용하십시오: 【모델 출력 요약】, 【모델 기여도】, "
        "【그래프 관찰 사실】, 【권고 조치】.\n"
        "6) STR 여부는 자동 결정하지 말고 독립 자료를 확인한 담당 분석관의 결정으로 남기십시오.\n"
        "7) 전문적이고 간결하게 작성하며, 보고서 본문 외 설명은 출력하지 마십시오."
    )

    user = (
        "다음 데이터로 AML 모델 검토 지원 보고서를 작성하십시오.\n\n"
        f"- 대상 거래 ID: {tx_id}\n"
        f"- 모델 점수: {int(score)} / 100 (검토 우선순위: {grade})\n"
        f"- 모델 판정 임계값: {int(decision_threshold)} / 100\n"
        f"- 모델 판정: {label_ko}\n"
        "- 모델 기여도(topFactors, 거래 증거가 아님):\n"
        f"{_format_factors(top_factors)}\n"
        "- 자금흐름 그래프 통계:\n"
        f"  · 연결 노드 수: {node_count}개\n"
        f"  · 자금 이동(엣지) 수: {edge_count}건\n"
        f"  · 모델 양성 이웃 거래 수: {illicit_neighbors}개\n\n"
        "위 데이터만 사용해 지정된 4개 섹션으로 작성하십시오. 모델 출력과 관찰 사실, "
        "담당자의 최종 결정을 명확히 구분하십시오."
    )
    return system, user


def generate_report_llm(
    tx_id: str,
    score: int,
    label: str,
    decision_threshold: int,
    top_factors: List[Dict[str, Any]],
    graph_stats: Dict[str, Any],
) -> Optional[str]:
    """Claude API 로 한글 보고서를 생성해 문자열로 반환한다.

    아래의 어떤 경우에도 예외를 전파하지 않고 None 을 반환한다:
    - anthropic 패키지 미설치
    - ANTHROPIC_API_KEY 미설정
    - API 호출 중 임의의 예외

    None 이 반환되면 호출측은 template 경로로 폴백해야 한다.
    """
    if not _ANTHROPIC_AVAILABLE or anthropic is None:
        logger.info("LLM report skipped: anthropic SDK not available.")
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.info("LLM report skipped: ANTHROPIC_API_KEY not set.")
        return None

    model = os.environ.get("CHAINEYE_REPORT_MODEL", _DEFAULT_MODEL)

    try:
        system, user = _build_prompt(
            tx_id, score, label, decision_threshold, top_factors, graph_stats
        )
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # content 는 블록 리스트. text 블록만 이어붙인다.
        parts = [
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        ]
        text = "".join(parts).strip()
        if not text:
            logger.warning("LLM report returned empty content -> falling back.")
            return None
        logger.info("LLM report generated via model=%s.", model)
        return text
    except Exception as exc:  # noqa: BLE001 - 어떤 실패든 폴백을 위해 흡수
        logger.warning(
            "LLM report generation failed (%s: %s) -> falling back to template.",
            type(exc).__name__,
            exc,
        )
        return None

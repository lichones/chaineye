---
title: ChainEye
emoji: 🔗
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# ChainEye (체인아이) — 가상자산 자금세탁 탐지·추적 AI

2026 금융 AI Challenge 출품작. 비트코인 트랜잭션 그래프에서 자금세탁 의심 흐름을
탐지·추적하고, 수사·컴플라이언스 담당자를 위한 근거 기반 리포트를 자동 생성하는 웹서비스.

## 구성
- **모델**: LightGBM(독립 시간 테스트 불법 F1 0.711 / PR-AUC 0.674 / ROC-AUC 0.899, 라이브 추론) + GCN(실험) + SHAP(XAI)
- **백엔드**: FastAPI (`/score`, `/trace`, `/explain`, `/report`, `/health`) — `app/backend`
- **프론트엔드**: React + Cytoscape.js 자금흐름 그래프 — `app/frontend`
- **데이터**: Elliptic Data Set (203,769 tx / 234,355 edges / 166 features / 49 timesteps)

## 실행 (Docker)
```
docker build -t chaineye .
docker run -p 7860:7860 chaineye
# http://localhost:7860
```

## LLM 리포트 (선택)
키가 없으면 결정론적 템플릿 보고서로 100% 동작한다. 고급 보고서를 켜려면
Space Secret 또는 환경변수로:
- `ANTHROPIC_API_KEY` (기본 provider, 모델 `CHAINEYE_REPORT_MODEL`=claude-sonnet-5)
- 또는 `CHAINEYE_REPORT_PROVIDER=openai` + `OPENAI_API_KEY`

문서: `docs/01_기획서.md`, `docs/02_기능명세서.md`, `docs/03_배포가이드.md`

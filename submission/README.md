# 2026 금융 AI Challenge 제출 패키지

## 제출 파일

- `output/pdf/ChainEye_2026금융AIChallenge_기획서.pdf`
- `output/pdf/ChainEye_2026금융AIChallenge_기능명세서.pdf`
- 웹서비스 URL: `https://chaineye.onrender.com`
- 심사 증거: `submission/notebooks/ChainEye_judge_evidence.ipynb`

공식 제출 마감은 2026년 9월 7일 오전 10시다. DAKER의 `[제출 탭]`에서 기획서 PDF와 MVP 산출물(기능명세서 PDF, 웹서비스 URL)을 각각 제출한다. URL은 2026년 9월 7일 11:00부터 9월 11일 23:59까지 접근 가능해야 한다.

## 현재 제출 중단 조건

다음 항목이 남아 있으면 제출하지 않는다.

1. `ChainEye_judge_evidence.ipynb`의 public deployment parity gate가 FAIL이다.
2. 공개 URL의 `/health`가 `mode=model`을 반환하지 않는다.
3. 공개 URL의 `70424581` 결과가 로컬의 점수 29, 임계값 23, label illicit과 다르다.
4. 공개 URL의 `999999999999`가 평가 불가와 생성 억제를 표시하지 않는다.
5. 제출 URL 가용 시간의 모니터링 계획이 없다.

## 제출 직전 명령

```powershell
python app/ml/verify_inference.py
python app/backend/verify_api.py
Push-Location app/frontend
npm run build
Pop-Location
python tmp/execute_notebook.py
```

노트북 마지막 셀의 parity gate가 PASS인지 확인한 다음 PDF를 제출한다.

# 2단계 추론 구조 개선: 1차 구현과 검증 관문

현재 2단계(2·3회)이며 최초 실패 성적은 그대로 보존한다. 이 문서는 개선 개발 기록이지
새 최초 성적·학습 승인·후보 선정이 아니다.

## 사용자 지시와 사본

사용자 원문: “근본 해결 방안에 따른 작업을 시작해. 그리고 앞으로 테스트 2개를 병행할 때
각 회차 테스트에 p코어 2개와 e코어 2개씩 총 4개를 배정하도록 테스트 및 머신러닝 규칙을 변경해”

- [개발 지시·기준 코드/모델·최초 결과 SHA 연결](C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/performance-development-20260913/development.json)
- [2회 개발 사본](C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/performance-development-20260913/round_02/code/notebooks/project/src/pipeline.py)
- [3회 개발 사본](C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/performance-development-20260913/round_03/code/notebooks/project/src/pipeline.py)

두 사본은 독립 파일이며 현재 공통 개선의 코드와 weights가 동일하다.
기준은 기존 선정 remediation_12 추론 코드와 선택 bundle이다. 공용 weights, 저장소의
기본 추론 src, predict.ipynb와 최초 고정 release는 변경하지 않는다.

## 적용한 운영 규칙

CPU 정책 `mixed-p2e2-v1`:

| 작업 | 논리 CPU | 구성 |
|---|---|---|
| 2·4·6회 병행 슬롯 A | 0,1,4,5 | P2 + E2 |
| 3·5·7회 병행 슬롯 B | 2,3,6,7 | P2 + E2 |
| 1·8회 및 통합 단독 | 0,1,2,3 | 기존 P4 유지 |

모두 4스레드이며, 병행 후보 학습·누적 검증에도 동일 배정이다. 개발 교차 계측에서는
혼합 슬롯 하나만 따로 측정할 수 있으나 이를 병행 성능이나 1·8회 정식 조건으로 보고하지 않는다.
Windows CPU-set topology가 기존 P=0–3/E=4–7·8물리코어와 다르면 실행을 막는다.
정책·배정은 job/runtime에 기록하며 과거 runtime을 새 배정으로 수정하지 않는다.

새 오프라인 smoke는 `qualification_XX_mixed-p2e2-v1`에 생성한다. 과거 qualification은
보존하고 재사용하지 않는다. 1장 smoke는 오프라인/로딩 증거일 뿐이며 전체 성능 인증이 아니다.

실제 두 프로세스와 각각의 자식에 대한 [혼합 CPU 배정 확인](C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/performance-development-20260913/profiles/cpu-smoke-0c21a189ba1c48d0b9e0a04aefed2d95/result.json)이 통과했다.

## 구현된 개발 기능

1. **구간 계측:** detector/recognizer predictor를 감싸 wall·CPU 시간·입력 shape·결과 수·오류를 기록한다.
   generator를 소비하는 호출자 시간은 제외한다. pipeline 전체 시간과 하위 계측은 중첩되므로 단순 합산하지 않는다.
2. **보조 인식 모델 공유:** 기본 한국어 recognizer를 유지하고 보조 detector만 교체하는 직렬 view를 추가했다.
   예외가 나도 기존 detector를 복구한다. 중복 Korean predictor 로드를 줄이는 구현이며,
   신규 영역만 선별 인식하는 최종 구조까지 완료된 것은 아니다.
3. **기본 처리 우선:** 전체 입력의 기본 OCR을 먼저 수행하고, 관측한 불확실성에 따라
   문맥 재검출/행 복구/기하 복구 중 하나를 나중에 선택한다. 원본 OCR 결과를 다시 계산하지 않는다.
4. **예산·보존:** 선택 복구의 native 호출 수·crop 수·협력적 deadline을 제한한다.
   이미지별 journal과 원자적 partial CSV를 보존하고, 실제 기본 처리에 성공한 모든 입력이 모인 뒤 정식 CSV를 만든다.
   미처리 입력을 NONE으로 채우지 않는다. native 호출 자체를 즉시 중단하는 기능은 아니며 초과 시 timeout으로 기록한다.
5. **상태 전달:** 실행기는 출력 ID 전체/중복/형식과 pipeline 상태를 검사한다.
   timeout은 `inference_failed`와 비정상 worker 종료로 전달한다. 실패 상태도 채점 가능하고 최초 기록은 덮어쓰지 않는다.
   과거 `awaiting_user_review` 상태만으로 timeout 작업을 유효한 완료로 재사용하지 않는다.

실험 스위치는 **개발 사본에만** 있다. `ITDA_SHARE_RECOGNIZER=1`과
`ITDA_EXECUTION_POLICY=base-first-v1`은 별도로 비교한다. 노트북 CONFIG 셀은 그대로다.
운영 release와 공용 가중치에는 자동 반영하지 않는다.

## 실제 계측 방법

`profile_grouped_performance`는 이미 최초 OCR 완료 기록이 있는 다음 6장만 사용한다:
AMLT000226, AMLT000263, BMLT003522, AMLT000355, AMLT000375, AMLT000515.
원본 테스트 SHA와 완료 trace를 확인한다. 정답지는 추론에 전달하지 않으며 4~8회 입력은 사용하지 않는다.
AMLT000355는 라벨 논점이 있으므로 이 샘플의 출력 변경을 정답 개선으로 간주하지 않는다.

각 모드는 새 출력 디렉터리·깨끗한 제출 사본·새 kernel·로컬 모델·OS outbound 차단 아래
실제 predict.ipynb를 실행한다. 모델/코드/manifest/CPU/메모리 및 노트북 기동부터의 시간을 남긴다.
6장 계측은 500장/95% 달성 검증을 대신하지 않는다.

관리자 PowerShell 예시:

```powershell
& notebooks/project/scripts/run_offline_verification.ps1 -Action GroupProfile -DevelopmentRoot C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/performance-development-20260913 -ProfileMode legacy
& notebooks/project/scripts/run_offline_verification.ps1 -Action GroupProfile -DevelopmentRoot C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/performance-development-20260913 -ProfileMode shared
& notebooks/project/scripts/run_offline_verification.ps1 -Action GroupProfile -DevelopmentRoot C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/performance-development-20260913 -ProfileMode base-first
```

개발 단독 비교에는 `-ProfileSlot 2` 또는 `3`을 추가한다. 이는 각각 혼합 슬롯 A/B 단독이다.
병행 시작 기준은 가용 RAM 4GiB, 단독 계측은 2.5GiB이다. 이전 실제 두 작업 peak RSS 합
약 2.64GiB와 1GiB 이상의 여유를 고려한 보수적 개발 기준이며 성능 보증이 아니다.
계측 중 768MiB 미만이면 해당 계측의 소유 프로세스만 중단하고 실패·로그를 보존한다.
다른 앱은 자동 종료하지 않는다. 원래 정식 노트북의 2,400초 강제 종료 규칙도 바꾸지 않는다.

[첫 병행 시도 전 자원 차단](C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/performance-development-20260913/profiles/legacy-4c75af7e595644e1a8cde29df45a5a92/result.json):
가용 3,888,799,744 B < 4,294,967,296 B. OCR 프로세스 시작 전에 차단했고 최초 결과는 그대로다.

단독 6장 오프라인 계측의 관리자 실행 요청도 Windows에서 “사용자가 작업을 취소했습니다”로
종료됐다. [실행 상태](C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/performance-development-20260913/launch_status.json).
실모델 OCR 계측은 아직 실행되지 않았고 취소를 우회하거나 재요청하지 않았다.
관리자 오프라인 실행이 가능해진 뒤 단독 구성 비교부터 진행하며, 병행은 별도 RAM 관문을 유지한다.

## 아직 통과하지 않은 관문

### 코드 검증 결과

[최종 단위·회귀 테스트 기록](C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/performance-development-20260913/unit-verification-20260913-225636/result.json):
저장소 446개, 2회 개발 사본 446개, 동일 코드의 3회 개발 사본 추가 테스트 10개가 통과했다.
저장소 레이아웃 검사 2개는 실제 저장소에서 통과했으며, README/학습환경 부속 파일을
포함하지 않는 고정 추론 사본에서는 중복 실행하지 않는다. 이전 실패 로그는 보존했다.
별도 검증 스크립트의 Windows multiprocessing 진입점 보호 누락도 수정 후 다시 통과했다.
이 실패들은 실제 OCR 결과가 아닌 검사 환경/하네스 문제다.

[불변성 감사](C:/ITDA_OCR_WORKSPACE/grouped-8-rounds-v2/performance-development-20260913/implementation_audit.json)에서
최초 보고서·runtime·state·manifest·선정 release·공용 weights·노트북과 개발 모델 동일성을 확인했다.
단계는 2단계 그대로이고 새 학습은 없다. 실제 OCR 성능과 정확도 관문은 아래와 같이 남아 있다.

- 실모델 공유의 출력 동등성 및 정확한 메모리·시간 효과.
- 검출 해상도 960/1280 비교와 작은 날짜/문맥 보존, 필요한 신규 영역만 추가 인식.
- 새로운 기본 우선 정책의 전체 오답·문맥·선택 회귀 분석.
- 기존 216장 보호 정답 204건 및 확정된 추가 사례의 퇴행 0.
- 새 혼합 배정에서 두 작업을 동시에 실행한 각 500장 완주·노트북 전체 1,500초 이하·95%.

단위 테스트의 가짜 500장 완주와 실제 OCR 성능을 구분한다. 위 관문 전에는 개선 완료,
95% 달성 또는 다음 단계 완료로 표시하지 않는다. 학습은 별도 사용자 피드백·명시적 승인 이후다.

# 1회 시작을 위한 후속 준비

> 갱신: 관리자 오프라인 검증이 통과했다. 현재 1회 시작 준비가 완료됐으며,
> [방화벽 수정·실측 결과](firewall_path_fix.md)를 참조한다. 아래 관리자 실행 안내는 수행 이력으로 남긴다.

근거: 사용자가 제공한 `C:/Users/ujkio/Downloads/채점환경.md`.
원본 사본과 해시는 외부 작업 폴더의 official_environment.md로 보존한다.
공식 조건은 Standard 4-Core vCPU, 인터넷 차단, nbconvert Run All, timeout=2400이다.
Linux 자체는 명시되지 않았으며 특정 CPU·RAM 정보도 없다. 이전의 Linux 필수라는 설명을 정정한다.

## 1회 원본과 그룹

1회 원본 216쌍은 이미 SHA-256으로 연결됐다.
216장 전체를 9개 contact sheet로 시각 검토했다. 검토자는 assistant이며 사용자 승인으로 기록하지 않았다.
반복 이미지와 애매한 포장/맛 변형을 보수적으로 함께 배정해 152개 분할 그룹으로 정리했다.
이 그룹은 동일 제품이라는 전수 증명이 아니라 유사 제품이 서로 다른 분할에 들어가지 않게 하는 보수적 그룹이다.
후속 회차 원본을 편입할 때 기존 그룹과의 관계를 추가 검토해야 한다.

- 원본 분할 미리보기: optimizer_train 194장 / inner_validation 22장.
- 유효 인식 crop: 225개 / 34개.
- 분할 간 그룹 교집합: 0.
- AMLC000200, AMLC000209, AMLC000210은 현재 승인 pool에 사용 가능한 인식 crop이 없어 인식 학습에서 제외된다.
- 이 결과는 학습 release나 승인 생성이 아닌 사전검사다.

근거: round1-group-review/visual_decisions.json, verified_groups.json,
partition_preview.json, learning_preflight.json.
증강본 1,106건은 3회 이후 편입 전 해결할 작업이며 1회 테스트/학습 시작의 선행 조건은 아니다.

## 실제 학습 흐름 검증

보호 이미지 대신 생성한 합성 날짜 이미지 16개로 고정 초기 모델과 실제 CPU optimizer를 실행했다.
6 epoch·24 학습 step, 매 epoch validation 8개 전부 처리, checkpoint 저장·선정 및 patience=5 조기 종료를 확인했다.
Windows runtime이 마지막 학습 batch를 건너뛰는 동작을 발견해 adapter에서 보완했다.
선정된 학습 checkpoint를 실제 export하고 합성 이미지로 기존 파이프라인 로딩·추론까지 통과했다.
정식 원본 학습과 정식 모델 반영은 하지 않았다. 결과는 synthetic-runtime-smoke-full-batches/result.json 및 export_loading.json에 기록했다.
로컬 회귀검사 322개가 통과했다. 정답 없는 사본과 데이터 보존 검사 결과는 preparation_verification.json 및 preservation.json을 참조한다.

## 실행환경

현재 PC는 논리 CPU 8개, 비관리자 세션이다. Python 프로세스의 CPU affinity를 4개로 제한하는 검사는 통과했다.
현재 외부 TCP 접속은 가능하므로 아직 오프라인 검증 통과가 아니다.
관리자 실행용 run_offline_verification.ps1은 해당 Python 실행파일들에 임시 outbound 방화벽 규칙을 추가한다.
Python에서 단순 timeout이 아닌 OS의 WSAEACCES(10013)를 확인한 뒤 기존 개발 노출 이미지로 Run All을 수행한다.
규칙은 finally에서 제거한다. 실행 중 해당 실행파일을 쓰는 다른 Python 프로세스의 외부 통신도 제한된다.
정식 테스트 때도 동일한 차단·CPU 제한을 적용하고 현재 모델/코드가 검증 증거와 일치하는지 검사한다.

Windows의 4개 논리 CPU 재현은 명시된 자원 수와 오프라인 조건의 검사이며 운영진 서버와 CPU 성능이 같다는 인증은 아니다.
방화벽 및 affinity 구현 근거: [Microsoft Firewall](https://learn.microsoft.com/en-us/powershell/module/netsecurity/new-netfirewallrule),
[CPU affinity 상속](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setprocessaffinitymask).

## 남은 실행 단계

관리자 PowerShell에서 다음 준비 검증을 실행한다. 정식 1회 테스트는 실행하지 않는다.

```powershell
& 'C:\ITDA_OCR_CODE\notebooks\project\scripts\run_offline_verification.ps1'
```

실패 시 offline-notebook.log를 확인하고 성공을 가정하지 않는다.
성공하면 운영환경 증거가 저장되고 환경 준비 상태가 갱신된다.
그 뒤 실제 사용자 시작 지시로 정식 1회 테스트를 실행한다.
1회 학습은 테스트 결과보고서에 대한 명시적 학습 승인 후 진행한다.

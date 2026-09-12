# 오프라인 검증 방화벽 경로 수정

사용자가 관리자 PowerShell에서 실행했지만 두 외부 TCP 접속이 모두 성공했다.
ActiveStore에서 방화벽 세 프로필과 로컬 규칙 적용은 활성 상태였다.

Python의 `cpython-3.10-windows-x86_64-none` 디렉터리는
`cpython-3.10.20-windows-x86_64-none` 디렉터리를 가리키는 junction이었다.
기존 스크립트는 sys.executable과 sys._base_executable의 별칭 문자열만 등록해 물리 실행파일 경로를 놓쳤다.

수정 내용:

- 실행 중 모듈 경로도 확인하고 모든 실행파일 경로의 junction을 해소한다.
- 별칭과 물리 경로 모두 방화벽 대상으로 등록한다.
- ActiveStore의 규칙 활성 상태를 확인한다.
- 실행 결과와 임시 규칙 제거 여부를 외부 firewall-last-run.json에 기록한다.
- WSAEACCES(10013) 검사를 유지한다. 연결 성공이나 timeout을 차단 성공으로 바꾸지 않는다.

Microsoft WFP의 프로그램 필터는 실행파일 경로에서 애플리케이션 ID를 구성한다.
[Microsoft 필터 조건 문서](https://learn.microsoft.com/en-us/windows/win32/fwp/populating-filter-conditions).

최종 OS 차단 및 Run All 판정은 외부 작업 폴더의 firewall-last-run.json과
operating_environment_verified.json에 기록된 실제 재검증 결과를 따른다.

## 실제 재검증 결과

2026-09-12 19:25:57~19:26:11 KST 관리자 실행에서 통과했다.
물리 경로 추가 후 1.1.1.1:443과 8.8.8.8:443은 실행 전후 모두 WinError 10013으로 차단됐다.
CPU affinity [0,1,2,3]에서 기존 개발 이미지 BMLC002247의 원본 노트북 Run All을 완료했다.
측정 시간은 약 8.20초이며 한 장 준비 검증 값이다. 정식 회차 정확도·속도 결과는 아니다.
CSV는 기존 검증 결과와 동일했다. 임시 규칙 3개 제거 완료, cleanup_errors는 비어 있다.
정답 없는 제출 사본의 323개 회귀검사도 통과했다.

execution_readiness.json의 formal_environment_verified가 true로 갱신됐다.
정식 1회 테스트는 아직 실행하지 않았으며 실제 시작 지시를 기다린다.

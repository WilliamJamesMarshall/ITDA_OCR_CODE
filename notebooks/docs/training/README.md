# CPU 학습 환경

추론 환경은 루트 `requirements.txt`, 학습 환경은 `../../environment/requirements-train-cpu.lock.txt`를 사용합니다. 준비 스크립트 `../../../scripts/prepare_training_runtime.ps1`의 lock 경로를 새 위치로 갱신했습니다.

`src/`, `configs/`, `scripts/`, `tests/`, `weights/`, `training_runtime/` 위치와 학습 초기 가중치·문자 사전은 유지했습니다. Windows 작업 폴더의 기존 결과 경로는 외부 작업 저장소로 연결되므로 승인 이력 및 절대 경로 manifest를 다시 쓰지 않습니다.

새 PC에서 학습 자료를 복원할 때는 외부 저장소 백업과 이미지 경로를 함께 복원해야 합니다. 제출 추론에는 학습 자료나 이 호환 연결이 필요하지 않습니다. 현재 3단계는 사용자의 학습·평가 계획 수정사항을 받은 뒤 재개합니다. 실제 학습은 별도의 release gate를 통과해야 합니다.

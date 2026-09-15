# 6회차 최종 평가 실행 환경

현재 상태: Docker 구성 작성 완료, Ubuntu 네이티브 빌드/실행은 아직 미검증.
Windows 관리자 설치 작업이 실행 정책에 의해 차단되어 WSL/Docker 설치 완료 전이다.
6회차 입력으로 환경을 시험하지 말고, 별도 개발 표본으로 먼저 검증한다.

## 설치 (관리자 PowerShell)

Microsoft WSL 공식 설치 안내: https://learn.microsoft.com/windows/wsl/install
Docker 공식 설치 안내: https://docs.docker.com/desktop/setup/install/windows-install/

```powershell
wsl --install -d Ubuntu-22.04
```

재부팅이 요구되면 작업을 저장한 뒤 직접 재부팅한다. Ubuntu 최초 실행 시 계정을 만든다.
Docker Desktop을 설치하고 WSL 2 backend를 선택해 실행한다.
Docker에 8GB 컨테이너를 실행할 충분한 메모리를 제공한다.
Docker Desktop 설정/기존 `.wslconfig`가 있다면 다른 작업의 자원 설정을 확인한다.

```powershell
wsl -l -v
wsl -d Ubuntu-22.04 -- cat /etc/os-release
docker version
```

## 온라인 준비

제출할 커밋을 새 폴더에 clone하고 저장소 루트에서 실행한다.
로컬 데이터가 Docker build로 전송되지 않게 최소 context를 만든다 (WSL Bash).

```bash
context=$(mktemp -d)
git archive HEAD predict.ipynb requirements.txt download_weights.sh notebooks/environment/grading | tar -x -C "$context"
docker build --platform linux/amd64 -f "$context/notebooks/environment/grading/Dockerfile" -t itda-grading:round6 "$context"
docker run --rm --network none itda-grading:round6 python -m pip check
docker run --rm --network none itda-grading:round6 python -c 'import sys, cv2, paddle, paddleocr; print(sys.version); print(paddle.device.get_device())'
docker image inspect itda-grading:round6 --format '{{.Id}}'
```

Ubuntu 22.04의 Python 3.10 venv 안에 requirements.txt를 설치하고 빌드 중
download_weights.sh를 실행한다. 실제 설치 버전은 이미지의 `/opt/installed-requirements.txt`에 보존된다.
이 구성은 현재 패키지 설치 가능성 및 시스템 라이브러리 확인을 위해 실제 빌드 검증이 필요하다.

## 오프라인 최종 실행 (환경 검증 및 6회차 입력 확정 후)

아래 입력/출력 경로는 확정된 실제 절대 경로로 바꾼다. 새 출력 폴더를 사용한다.

```bash
mkdir -p /absolute/path/to/new-round6-output
docker run --name itda-round6 --platform linux/amd64 \
  --cpus=4 --memory=8g --memory-swap=8g --shm-size=512m --network=none \
  --mount type=bind,src=/absolute/path/to/round6-images,dst=/input,readonly \
  --mount type=bind,src=/absolute/path/to/new-round6-output,dst=/output \
  -e ITDA_INPUT_DIR=/input -e ITDA_OUTPUT_PATH=/output/submission.csv \
  itda-grading:round6
docker inspect itda-round6 --format '{{json .State}}'
docker inspect itda-round6 --format '{{json .HostConfig}}'
```

GPU는 전달하지 않으며 네트워크를 컨테이너 수준에서 차단한다. CPU는 4코어 분량의
시간 할당, RAM은 8GiB, swap은 금지한다. 운영진의 실제 CPU 모델/커널과 같은 하드웨어는 아니므로
시간이 완전히 동일함을 보증하지 않는다. Ubuntu 22.04 사용자 환경과 공지된 자원 제한을 재현한다.

내부 1470초 정책은 유지한다. 외부 실행 한도는 2400초이며 노트북 실행/CSV 검증 실패는
비정상 종료로 남는다. 출력은 지정한 호스트 폴더의 submission.csv이다.
500행/입력 ID 일치, 인덱스 없는 5열, 운영진 승인 부분 날짜 형식, 추론 오류 여부를 확인한다.
OOMKilled 및 종료코드도 확인하고, 원본 결과와 로그를 보존한다.

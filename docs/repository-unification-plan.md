# ITDA OCR 저장소·worktree 통합 운영안

## 목표 상태

- 이 컴퓨터의 유일한 활성 clone은 `C:\CODE_ITDA\ITDA_OCR_CODE`다.
- GitHub Desktop과 Codex·터미널은 모두 이 경로를 사용한다.
- `origin`은 `https://github.com/WilliamJamesMarshall/ITDA_OCR_CODE.git` 하나만 사용한다.
- 원본 데이터는 정본 clone에 로컬 전용으로 한 벌만 두고 Git에는 올리지 않는다.
- 각 작업자의 컴퓨터에는 그 작업자의 첫 작업을 시작할 때 본인 worktree 하나만 생성한다.
- 작업마다 worktree를 새로 만들지 않고, 같은 작업자 worktree에서 작업 브랜치만 교체한다.

## 2026-09-07 통합 결과

- GitHub Desktop이 보고 있던 `C:\CODE_ITDA\ITDA_OCR_CODE`를 정본으로 선택했다.
- 두 clone의 `origin`과 기준 HEAD가 동일함을 확인했다.
- 수정된 `Harness_README.md`, `.git-session.json`, `scripts/git-session-manager.mjs`를 정본에 통합했다.
- `images.zip`과 `상품사진입니다\`를 정본으로 이동했다.
- ZIP SHA-256 `ae50d6a1ecde0e3b1ab1151a62579d99afb02efff8b0e28b53fb17145b06a1ec`와 이미지 3,352개를 재검증했다.
- 데이터 두 항목이 `.gitignore`에 의해 제외되는 것을 확인했다.
- 잘못 일괄 생성했던 작업자 worktree 다섯 개는 모두 clean이고 고유 커밋이 0개임을 확인한 뒤 제거했다.

## 남은 로컬 경로 정리

`C:\ITDA_OCR_CODE`의 변경 내용과 데이터는 정본에 통합됐지만, 현재 프로세스가 디렉터리를 점유해 폴더 자체의 이동은 Windows가 거부했다. 강제 종료나 부분 삭제는 하지 않았다.

현재 작업이 끝나 점유가 해제된 뒤 다음 순서로 마무리한다.

1. 정본의 commit·push 및 원격 반영을 확인한다.
2. `C:\ITDA_OCR_CODE`에 새 변경이 없는지 다시 비교한다.
3. 기존 폴더를 `C:\CODE_ITDA\_migration_backup\ITDA_OCR_CODE_before_unification_20260907`로 이동한다.
4. 필요하면 `C:\ITDA_OCR_CODE`에 정본을 대상으로 하는 directory junction을 만든다.
5. junction 경로와 정본 경로에서 `git rev-parse --show-toplevel`, `origin`, HEAD가 동일하게 보이는지 확인한다.
6. 팀 운영이 안정된 뒤에만 백업 삭제 여부를 별도로 결정한다.

정리 전까지 `C:\ITDA_OCR_CODE`에서는 편집·commit·push하지 않는다.

## 컴퓨터별 worktree 수명주기

1. 작업자는 자신의 컴퓨터에 저장소를 clone하고 최신 `main`을 pull한다.
2. 관제 clone에서 본인 이름으로 `start`를 실행한다.
3. 해당 clone의 `.git/itda-local-worker`에 작업자 이름이 로컬 전용으로 고정된다.
4. 본인 worktree가 없으면 `<clone-parent>\ITDA_OCR_WORKTREES\<worker-slug>`에 하나만 생성된다.
5. `origin/main`에서 `worker/<worker-slug>/<task>` 작업 브랜치를 만들고 claim을 등록한다.
6. 다음 작업부터는 같은 worktree를 재사용한다. 다른 작업자의 worktree는 만들지 않는다.
7. 이전 작업이 active 또는 dirty면 새 작업을 차단한다.
8. PR 병합 후 claim을 해제하고 `workspace` 브랜치를 최신 `origin/main`으로 fast-forward한다.

예시:

```powershell
Set-Location '<각 작업자의 clone 경로>'
node scripts/git-session-manager.mjs start `
  --ai codex `
  --worker 이호연 `
  --task improve-date-parser `
  --path src/postprocess
```

## GitHub Desktop 반영 절차

1. Current repository가 `ITDA_OCR_CODE`이고 로컬 경로가 `C:\CODE_ITDA\ITDA_OCR_CODE`인지 확인한다.
2. Changes에서 다음 네 항목만 검토한다.
   - `Harness_README.md`
   - `.git-session.json`
   - `scripts/git-session-manager.mjs`
   - `docs/repository-unification-plan.md`
3. `images.zip`과 `상품사진입니다\`가 Changes에 나타나지 않는지 확인한다.
4. 커밋 제목은 `작업자별 지연 생성 worktree 하네스 도입`으로 한다.
5. `Commit to main` 후 `Push origin`을 실행한다.
6. 원격 `main`의 최신 커밋과 위 네 파일을 확인한다.

## 검증 기준

- `node --check scripts/git-session-manager.mjs`
- `node scripts/git-session-manager.mjs check-config`
- 첫 `start` 후 관제 clone과 본인 worktree만 존재
- 같은 작업 재호출 후 worktree 수 불변
- 같은 clone에서 다른 작업자 이름 사용 시 생성 전에 실패
- `git diff --check` 통과
- 원본 ZIP 해시와 이미지 수 유지
- GitHub Desktop Changes에 원본 데이터가 나타나지 않음

# 실행 코드

`src/`는 루트 predict.ipynb가 직접 import하는 OCR 코드입니다. 실험 노트북 선행 실행은 필요하지 않습니다.

저장소 루트에서:

```powershell
python notebooks/project/run.py unittest discover -s notebooks/project/tests -q
python notebooks/project/run.py scripts.train_recognition_cpu --preflight-only
python notebooks/project/run.py scripts.ocr_annotations serve --port 8767
python notebooks/project/run.py scripts.group_review_server --port 8768
```

추론 가중치는 루트 weights/paddle, 학습 설정은 notebooks/project/configs를 사용합니다. 개발 도구의 데이터·승인 기록은 보존된 기존 로컬 경로를 이용합니다. 제출 추론에는 그 데이터나 junction이 필요하지 않습니다. 기존 문서의 `python -m scripts.X`는 `python notebooks/project/run.py scripts.X`로 실행합니다.

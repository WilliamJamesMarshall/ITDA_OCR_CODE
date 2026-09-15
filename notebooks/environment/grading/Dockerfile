FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3.10-venv ca-certificates curl coreutils libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /submission
RUN python3.10 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
COPY requirements.txt ./
RUN python -m pip install -r requirements.txt && python -m pip check \
    && python -m pip freeze > /opt/installed-requirements.txt
COPY download_weights.sh ./
RUN bash download_weights.sh
COPY predict.ipynb ./
COPY notebooks/environment/grading/run.sh /opt/run-grading.sh
ENV ITDA_INPUT_DIR=/input ITDA_OUTPUT_PATH=/output/submission.csv
CMD ["bash", "/opt/run-grading.sh"]

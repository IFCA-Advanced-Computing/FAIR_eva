FROM python:3.11-slim AS base

RUN apt-get update -y && \
    apt-get install -y curl python3-pip python3-dev git vim lsof

COPY . /FAIR_eva
WORKDIR /FAIR_eva
RUN chmod +x scripts/entrypoint.sh
RUN pip3 install git+https://github.com/IFCA-Advanced-Computing/fair-eva-plugin-oai-pmh
RUN pip3 install -r requirements.txt
RUN pip3 install .

ARG FAIR_EVA_HOST=0.0.0.0
ARG FAIR_EVA_PORT=9090
ARG START_CMD="fair-eva"

ENV FAIR_EVA_HOST=${FAIR_EVA_HOST} \
    FAIR_EVA_PORT=${FAIR_EVA_PORT} \
    START_CMD=${START_CMD}

EXPOSE ${FAIR_EVA_PORT}
ENTRYPOINT ["/FAIR_eva/scripts/entrypoint.sh"]

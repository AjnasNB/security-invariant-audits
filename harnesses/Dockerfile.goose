FROM ajnas-open-harness-ordinary:20261001
COPY goose /usr/local/bin/goose
USER root
RUN chmod 755 /usr/local/bin/goose
USER 65534:65534
ENV GOOSE_PATH_ROOT=/tmp/goose GOOSE_TELEMETRY_OFF=1 GOOSE_DISABLE_KEYRING=1

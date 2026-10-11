# The pipeline Lambdas (brief §11.2): one image, one handler per step chosen by the function's
# command. Built for arm64. Dependencies are installed at the versions in uv.lock.
FROM public.ecr.aws/lambda/python:3.12

RUN pip install --no-cache-dir uv==0.12.24

WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project -o requirements.txt \
    && uv pip install --system --no-cache -r requirements.txt

COPY afterpass ./afterpass
COPY agent ./agent
RUN uv pip install --system --no-cache --no-deps . && rm -rf /build

WORKDIR ${LAMBDA_TASK_ROOT}
COPY lambdas/pipeline.py ./pipeline.py

# /tmp is the only writable place on Lambda.
ENV AFTERPASS_DATA_DIR=/tmp/afterpass \
    MPLCONFIGDIR=/tmp/matplotlib \
    HOME=/tmp

CMD ["pipeline.fetch_firms"]

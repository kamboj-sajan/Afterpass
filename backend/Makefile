# Build recipes that `sam build` calls for the zip-packaged Lambdas (BuildMethod: makefile).
# Each installs Linux arm64 wheels for the function's own requirements and copies its code in.

# The python3.12 Lambda runtime is Amazon Linux 2023 (glibc 2.34), so manylinux_2_28 wheels load.
PLATFORM := --python-platform aarch64-manylinux_2_28 --python-version 3.12 --no-build

build-AgentFunction:
	uv pip install --quiet $(PLATFORM) --target "$(ARTIFACTS_DIR)" -r lambdas/agent-requirements.txt
	cp -R agent "$(ARTIFACTS_DIR)/agent"
	rm -rf "$(ARTIFACTS_DIR)/agent/tests" "$(ARTIFACTS_DIR)/agent/__pycache__"

build-SubscribeFunction:
	cp lambdas/subscribe.py "$(ARTIFACTS_DIR)/subscribe.py"

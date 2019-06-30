SERVER := python -m hyperschedule.api
PROD_ARGS := debug=no
REALPROD_ARGS := host=0.0.0.0 kill_orphans=yes port="$${PORT}" snitch=no
IGNORE_FAIL := || true

.PHONY: docker
docker: ## Run shell with Hyperschedule source code and deps inside Docker
	scripts/docker.sh build . -f Dockerfile.dev --pull -t hyperschedule-api:dev
	scripts/docker.sh run -it --rm \
		-v "$${PWD}:/src" -p 127.0.0.1:3000:80 \
		hyperschedule-api:dev \
		sh -isc "source /src/scripts/docker-env.sh"

.PHONY: image
image: ## Build Docker image for production
	scripts/docker.sh build . --pull -t hyperschedule-api

.PHONY: watch
watch: ## Start Hyperschedule API server in development mode, with file watcher
	watchexec -r -e py "$(SERVER) $(ARGS) $(IGNORE_FAIL)"

.PHONY: dev
dev: ## Start Hyperschedule API server in development mode
	$(SERVER) $(ARGS) $(IGNORE_FAIL)

.PHONY: prod
prod: ## Start Hyperschedule API server in production mode
	$(SERVER) $(PROD_ARGS) $(ARGS) $(IGNORE_FAIL)

.PHONY: realprod
realprod: ## Start Hyperschedule API server, for use in production only
	$(SERVER) $(PROD_ARGS) $(REALPROD_ARGS)

.PHONY: test
test: ## Run unit and integration tests
	python -m unittest discover -s hyperschedule/tests

.PHONY: lint
lint: ## Run linters on source code
	find hyperschedule -name '*.py' -exec flake8 '{}' ';'

.PHONY: ci
ci: test lint ## Run CI checks

.PHONY: sandwich
sandwich: ## https://xkcd.com/149/
	@if [ "$${EUID}" != 0 ]; then			\
		echo "What? Make it yourself." >&2;	\
		exit 1;					\
	else						\
		echo "Okay." >&2;			\
	fi

.PHONY: help
help: ## Show this message
	@echo "usage:" >&2
	@grep -h "[#]# " $(MAKEFILE_LIST)	| \
		sed 's/^/  make /'		| \
		sed 's/:[^#]*[#]# /|/'		| \
		sed 's/%/LANG/'			| \
column -t -s'|' >&2

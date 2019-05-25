PIPENV := pipenv run
SERVER := python -m hyperschedule.server
PROD := cache=no debug=no
HEROKU := expose=yes kill_orphans=yes port=${PORT} snitch=yes
TEST := python -m unittest discover -s hyperschedule/tests
LINT := find hyperschedule -name '*.py' -exec flake8 '{}' ';'
IGNORE_FAIL := || true

.PHONY: dev
dev:
	$(PIPENV) $(SERVER) $(ARGS) $(IGNORE_FAIL)

.PHONY: prod
prod:
	$(PIPENV) $(SERVER) $(PROD) $(ARGS) $(IGNORE_FAIL)

.PHONY: heroku
heroku:
	$(SERVER) $(PROD) $(HEROKU)

.PHONY: test
test:
	$(PIPENV) $(TEST)

.PHONY: lint
lint:
	$(PIPENV) $(LINT)

.PHONY: travis
travis: test lint

.PHONY: sandwich
sandwich:
	@if (( $EUID != 0 )); then			\
		echo "What? Make it yourself." >&2;	\
		exit 1;					\
	else						\
		echo "Okay." >&2;			\
	fi

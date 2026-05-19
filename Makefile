.PHONY: install dev-server dev-gui build-gui lint test release

VENV := .venv
PYTHON := $(VENV)/bin/python

install:
	bash install.sh

dev-server:
	$(PYTHON) emusync.py server start

dev-gui:
	cd gui && npm run dev || (test -x /usr/lib/electron/electron && ELECTRON_EXEC_PATH=/usr/lib/electron/electron npm run dev)

build-gui:
	cd gui && npm run build

lint:
	$(VENV)/bin/python -m py_compile server/config.py server/store.py server/mdns.py server/api.py server/sync_client.py emusync.py
	@echo "Python syntax OK"

test:
	$(PYTHON) -m pytest tests/ -v

release:
	@test -n "$(VERSION)" || (echo "Usage: make release VERSION=v1.0.0" && exit 1)
	git tag $(VERSION)
	git push origin $(VERSION)

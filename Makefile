.PHONY: install dev-server dev-gui build-gui lint

VENV := .venv
PYTHON := $(VENV)/bin/python

install:
	bash install.sh

dev-server:
	$(PYTHON) emusync.py server start

dev-gui:
	cd gui && npm run dev

build-gui:
	cd gui && npm run build

lint:
	$(VENV)/bin/python -m py_compile server/config.py server/store.py server/mdns.py server/api.py server/sync_client.py emusync.py
	@echo "Python syntax OK"

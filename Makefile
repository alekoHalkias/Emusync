.PHONY: install dev-server dev-gui build-gui lint test release install-service uninstall-service

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
	$(VENV)/bin/python -m py_compile server/config.py server/store/*.py server/mdns.py server/api.py server/sync_client.py emusync.py cli/*.py
	@echo "Python syntax OK"

test:
	$(PYTHON) -m pytest tests/ -v

release:
	@test -n "$(VERSION)" || (echo "Usage: make release VERSION=v1.0.0" && exit 1)
	git tag $(VERSION)
	git push origin $(VERSION)

install-service:
	@EXEC="$(CURDIR)/emusync"; \
	test -x "$$EXEC" || (echo "Run 'bash install.sh' first to create the launcher." && exit 1); \
	SERVICE_DIR="$$HOME/.config/systemd/user"; \
	mkdir -p "$$SERVICE_DIR"; \
	sed "s|EMUSYNC_EXEC|$$EXEC|g" "$(CURDIR)/emusync-server.service" > "$$SERVICE_DIR/emusync-server.service"; \
	systemctl --user daemon-reload; \
	systemctl --user enable --now emusync-server; \
	echo "emusync-server service installed and started."; \
	echo "It will start automatically on login (including Steam Deck Gaming Mode)."

uninstall-service:
	-systemctl --user disable --now emusync-server 2>/dev/null; \
	rm -f "$$HOME/.config/systemd/user/emusync-server.service"; \
	systemctl --user daemon-reload; \
	echo "emusync-server service removed."

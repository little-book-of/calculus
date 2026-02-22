SHELL := /bin/bash

QUARTO_VERSION ?= 1.6.43
QUARTO_DEB := quarto-$(QUARTO_VERSION)-linux-amd64.deb
QUARTO_DEB_URL := https://github.com/quarto-dev/quarto-cli/releases/download/v$(QUARTO_VERSION)/$(QUARTO_DEB)

.PHONY: help install-quarto install-translate-deps translate-zh check-quarto render render-en render-vi render-zh preview clean

help:
	@echo "Available targets:"
	@echo "  make install-quarto  # Install Quarto CLI (Linux .deb)"
	@echo "  make check-quarto    # Show Quarto version"
	@echo "  make install-translate-deps # Install Python dependencies for translation"
	@echo "  make translate-zh    # Translate English content into zh/"
	@echo "  make render-en       # Render English book page"
	@echo "  make render-vi       # Render Vietnamese book page"
	@echo "  make render-zh       # Render Chinese book page"
	@echo "  make render          # Render full multilingual website"
	@echo "  make preview         # Live preview website"
	@echo "  make clean           # Remove rendered site output"

install-quarto:
	@if command -v quarto >/dev/null 2>&1; then \
		echo "Quarto already installed: $$(quarto --version)"; \
		exit 0; \
	fi
	@echo "Installing Quarto v$(QUARTO_VERSION)..."
	@curl -fsSL -o /tmp/$(QUARTO_DEB) $(QUARTO_DEB_URL)
	@sudo dpkg -i /tmp/$(QUARTO_DEB) || sudo apt-get install -f -y
	@rm -f /tmp/$(QUARTO_DEB)
	@echo "Installed: $$(quarto --version)"

check-quarto:
	@quarto --version

install-translate-deps:
	@python3 -m pip install -r scripts/requirements.txt

translate-zh: install-translate-deps
	@python3 scripts/translate_to_zh.py

render-en: check-quarto
	@quarto render en/index.qmd

render-vi: check-quarto
	@quarto render vi/index.qmd

render-zh: check-quarto
	@quarto render zh/index.qmd

render: check-quarto
	@quarto render

preview: check-quarto
	@quarto preview

clean:
	@rm -rf _site .quarto

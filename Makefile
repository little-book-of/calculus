SHELL := /bin/bash

QUARTO_VERSION ?= 1.6.43
QUARTO_DEB := quarto-$(QUARTO_VERSION)-linux-amd64.deb
QUARTO_DEB_URL := https://github.com/quarto-dev/quarto-cli/releases/download/v$(QUARTO_VERSION)/$(QUARTO_DEB)

TRANSLATE_SOURCE ?= en/index.qmd
TRANSLATE_TARGET ?= ja
TRANSLATE_OUTPUT ?= $(TRANSLATE_TARGET)/index.qmd
TRANSLATE_CHUNK_SIZE ?= 1800
TRANSLATE_MAX_WORKERS ?= 6
TRANSLATE_RATE_LIMIT ?= 4
TRANSLATE_RETRIES ?= 4

.PHONY: help install-quarto check-quarto install-translate-deps translate translate-ja render render-en render-vi render-zh render-ja preview clean

help:
	@echo "Available targets:"
	@echo "  make install-quarto         # Install Quarto CLI (Linux .deb)"
	@echo "  make check-quarto           # Show Quarto version"
	@echo "  make install-translate-deps # Install translation script dependencies"
	@echo "  make translate              # Translate source to target language"
	@echo "  make translate-ja           # Translate English book to Japanese"
	@echo "  make render-en              # Render English book page"
	@echo "  make render-vi              # Render Vietnamese book page"
	@echo "  make render-zh              # Render Chinese book page"
	@echo "  make render-ja              # Render Japanese book page"
	@echo "  make render                 # Render full multilingual website"
	@echo "  make preview                # Live preview website"
	@echo "  make clean                  # Remove rendered site output"

install-quarto:
	@if command -v quarto >/dev/null 2>&1; then \
		echo "Quarto already installed: $$(quarto --version)"; \
		exit 0; \
	fi
	@echo "Installing Quarto v$(QUARTO_VERSION)..."
	@curl -fsSL -o /tmp/$(QUARTO_DEB) $(QUARTO_DEB_URL)
	@dpkg -i /tmp/$(QUARTO_DEB) || apt-get install -f -y
	@rm -f /tmp/$(QUARTO_DEB)
	@echo "Installed: $$(quarto --version)"

check-quarto:
	@quarto --version

install-translate-deps:
	@python3 -m pip install -r scripts/requirements.txt

translate: install-translate-deps
	@python3 scripts/translate_book.py \
		--source-lang en \
		--target-lang $(TRANSLATE_TARGET) \
		--source $(TRANSLATE_SOURCE) \
		--output $(TRANSLATE_OUTPUT) \
		--chunk-size $(TRANSLATE_CHUNK_SIZE) \
		--max-workers $(TRANSLATE_MAX_WORKERS) \
		--rate-limit $(TRANSLATE_RATE_LIMIT) \
		--retries $(TRANSLATE_RETRIES)

translate-ja:
	@$(MAKE) translate TRANSLATE_TARGET=ja TRANSLATE_OUTPUT=ja/index.qmd

render-en: check-quarto
	@quarto render en/index.qmd

render-vi: check-quarto
	@quarto render vi/index.qmd

render-zh: check-quarto
	@quarto render zh/index.qmd

render-ja: check-quarto
	@quarto render ja/index.qmd

render: check-quarto
	@quarto render

preview: check-quarto
	@quarto preview

clean:
	@rm -rf _site .quarto

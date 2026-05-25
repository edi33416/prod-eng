SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = .
BUILDDIR      = build

# Detect OS for the open target
UNAME := $(shell uname)
ifeq ($(UNAME), Darwin)
  OPEN = open
else
  OPEN = xdg-open
endif

.PHONY: help html open clean docker-build docker-open

help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

open: html
	$(OPEN) $(BUILDDIR)/html/index.html

clean:
	rm -rf $(BUILDDIR)

docker-build:
	cd docker && docker compose build
	cd docker && UID=$(shell id -u) GID=$(shell id -g) docker compose run --rm docs-build make html

docker-open: docker-build
	$(OPEN) $(BUILDDIR)/html/index.html

# Catch-all: forward any other targets (html, latex, epub, …) to sphinx-build.
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

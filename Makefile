SPHINX_BUILD ?= $(HOME)/.local/bin/sphinx-build

.PHONY: help clean html pdf epub serve install-deps

help:
	@echo "FAIR EVA documentation - Available commands"
	@echo ""
	@echo "  make install-deps    Install documentation dependencies"
	@echo "  make html            Generate HTML documentation"
	@echo "  make pdf             Generate PDF documentation"
	@echo "  make epub            Generate ePub documentation"
	@echo "  make all             Generate HTML, PDF and ePub"
	@echo "  make serve           Generate HTML and serve at http://localhost:8000"
	@echo "  make clean           Cleanup generated files"
	@echo "  make help            Show this message"

install-deps:
	pip install --break-system-packages -r docs/requirements.txt

html:
	$(SPHINX_BUILD) -W -b html -d docs/_build/doctrees docs docs/_build/html

pdf:
	$(SPHINX_BUILD) -W -b pdf -d docs/_build/doctrees docs docs/_build/pdf

epub:
	$(SPHINX_BUILD) -W -b epub -d docs/_build/doctrees docs docs/_build/epub

all: clean html pdf epub
	@echo "Generate documentation in docs/_build/"

serve: html
	@echo "Serving documentation at http://localhost:8000"
	@python3 -m http.server --directory docs/_build/html 8000

clean:
	rm -rf docs/_build/

.PHONY: help clean html pdf epub serve install-deps all

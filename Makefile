SPHINX_BUILD ?= $(HOME)/.local/bin/sphinx-build

.PHONY: help clean html pdf epub serve install-deps

help:
	@echo "Documentación FAIR EVA - Comandos disponibles"
	@echo ""
	@echo "  make install-deps    Instala las dependencias de documentación"
	@echo "  make html            Genera documentación en HTML"
	@echo "  make pdf             Genera documentación en PDF"
	@echo "  make epub            Genera documentación en ePub"
	@echo "  make all             Genera HTML, PDF y ePub"
	@echo "  make serve           Genera HTML y sirve en http://localhost:8000"
	@echo "  make clean           Limpia los archivos generados"
	@echo "  make help            Muestra este mensaje"

install-deps:
	pip install --break-system-packages -r docs/requirements.txt

html:
	$(SPHINX_BUILD) -W -b html -d docs/_build/doctrees docs docs/_build/html

pdf:
	$(SPHINX_BUILD) -W -b pdf -d docs/_build/doctrees docs docs/_build/pdf

epub:
	$(SPHINX_BUILD) -W -b epub -d docs/_build/doctrees docs docs/_build/epub

all: clean html pdf epub
	@echo "Documentación generada en docs/_build/"

serve: html
	@echo "Sirviendo documentación en http://localhost:8000"
	@python3 -m http.server --directory docs/_build/html 8000

clean:
	rm -rf docs/_build/

.PHONY: help clean html pdf epub serve install-deps all

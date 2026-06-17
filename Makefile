.PHONY: build manifest metadata corpus variations coverage xlsx corpus-zip test smoke commit clean help

help:
	@echo "Targets:"
	@echo "  make build      - reconstrói ptd_scraper.ipynb a partir de notebook_cells/"
	@echo "  make manifest   - (re)gera output/manifest.json (build_manifest.py)"
	@echo "  make metadata   - (re)gera os descritores de dados abertos em output/"
	@echo "  make corpus     - (re)gera o corpus harmonizado em output/harmonized/"
	@echo "  make variations - (re)gera output/variations.csv (catálogo tipado de divergências)"
	@echo "  make coverage   - (re)gera output/coverage_summary.csv (cobertura por órgão)"
	@echo "  make xlsx       - (re)gera output/PTD-corpus.xlsx (pasta Excel pronta p/ uso)"
	@echo "  make corpus-zip - empacota só o corpus (harmonized/ + manifest) em corpus_<snapshot>.zip"
	@echo "  make test       - roda pytest sobre tests/"
	@echo "  make smoke      - smoke test do notebook (sintaxe, deps, carga)"
	@echo "  make commit     - build + git add -A + git commit"
	@echo "  make clean      - remove artefatos de execução local (ptd_output/)"

build:
	python build_notebook.py

manifest:
	python build_manifest.py

metadata:
	python build_metadata.py

corpus:
	python build_corpus.py

variations:
	python build_variations.py

coverage:
	python build_coverage.py

xlsx:
	python build_xlsx.py

corpus-zip:
	python build_corpus.py --zip

test:
	python -m pytest -v tests/

smoke:
	python smoke_test.py

commit: build
	git add -A
	git commit

clean:
	rm -rf ptd_output/

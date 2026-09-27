# Comandi utili per lo sviluppo e l'uso quotidiano dell'automazione.

PYTHON ?= python3
YEAR ?= 2026

.PHONY: help install test check today dry-run preview gallery doctor clean

help:  ## Mostra questo aiuto
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Installa le dipendenze
	$(PYTHON) -m pip install -r requirements.txt

test:  ## Esegue la suite di test
	$(PYTHON) -m pytest tests/ -q

check:  ## Valida la libreria dei 365 giorni
	$(PYTHON) -m lifezen check

today:  ## Genera e pubblica il contenuto di oggi
	$(PYTHON) -m lifezen run

dry-run:  ## Genera senza pubblicare
	$(PYTHON) -m lifezen run --dry-run --story

preview:  ## Anteprima di un mese (es. make preview MONTH=3)
	$(PYTHON) -m lifezen preview --month $(MONTH) --year $(YEAR) --sheet --columns 6

gallery:  ## Crea il calendario HTML dell'anno
	$(PYTHON) -m lifezen gallery --year $(YEAR)

doctor:  ## Diagnosi completa
	$(PYTHON) -m lifezen doctor

clean:  ## Rimuove gli artefatti locali
	rm -rf output/ __pycache__ lifezen/__pycache__ tests/__pycache__ .pytest_cache

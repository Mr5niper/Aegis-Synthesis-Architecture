.PHONY: venv install nexus gui headless build clean

VENV=.venv
PY=$(VENV)/bin/python

venv:
	python -m venv $(VENV)

install: venv
	$(PY) -m pip install -U pip
	$(PY) -m pip install -r requirements.txt

nexus:
	$(PY) -m uvicorn src.nexus_server:app --host 0.0.0.0 --port 7861

gui:
	$(PY) -m src.main_gui

headless:
	$(PY) -m src.main_headless

build:
	$(PY) build_executable.py

clean:
	rm -rf build dist __pycache__ src/**/__pycache__
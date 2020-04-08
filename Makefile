.PHONY: reformat check venv

PYTHON_FILES = tests/**/*.py

all: venv

reformat:
	scripts/format-code.sh $(PYTHON_FILES)

check:
	scripts/check-code.sh $(PYTHON_FILES)

venv:
	scripts/create-venv.sh

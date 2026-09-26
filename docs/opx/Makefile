# Build the OPX architecture write-up. Needs latexmk + pdflatex (TeX Live /
# MiKTeX). "make" -> opx_architecture.pdf; "make clean" removes build files.

MAIN = opx_architecture
SECTIONS = $(wildcard sections/*.tex)

.PHONY: all clean

all: $(MAIN).pdf

$(MAIN).pdf: $(MAIN).tex $(SECTIONS)
	latexmk -pdf -interaction=nonstopmode $(MAIN).tex

clean:
	latexmk -C $(MAIN).tex
	-rm -f $(MAIN).bbl $(MAIN).run.xml

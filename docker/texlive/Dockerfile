# Compile sandbox image for paper-diff
FROM texlive/texlive:latest

# Ensure latexmk is present (usually included)
RUN which latexmk && latexmk -v | head -n 1

WORKDIR /work

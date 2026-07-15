# Lightweight compile image for paper-diff fixtures / basic articles.
# For heavy packages, replace with texlive/texlive:latest or scheme-full.
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        texlive-latex-base \
        texlive-latex-recommended \
        texlive-fonts-recommended \
        latexmk \
        latexdiff \
        bash \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work

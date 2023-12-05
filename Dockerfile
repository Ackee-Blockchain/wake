FROM python:3.11-bullseye
# tree sitter bug blocks smaller image
# FROM python:3.11-slim-bullseye

LABEL maintainer=Ackee-Blockchain
LABEL desc="Python-based development and testing framework for Solidity"
LABEL src="https://github.com/Ackee-Blockchain/wake"

COPY . /wake
WORKDIR /wake
RUN pip3 install .
RUN curl -L https://foundry.paradigm.xyz | bash
RUN . ~/.bashrc && foundryup
WORKDIR /workspace

ENTRYPOINT [ "/bin/bash" ]
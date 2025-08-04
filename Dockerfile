FROM python:3.11-slim-bullseye

LABEL maintainer=Ackee-Blockchain
LABEL desc="Python-based development and testing framework for Solidity"
LABEL src="https://github.com/Ackee-Blockchain/wake"

SHELL ["/bin/bash", "-c"]
RUN apt update -y
RUN apt install -y curl git pkg-config libssl-dev libatomic1 build-essential

RUN curl https://sh.rustup.rs -sSf | sh -s -- --default-toolchain=stable --profile=minimal -y
ENV PATH="/root/.cargo/bin:${PATH}"

COPY . /wake
WORKDIR /wake
RUN pip3 install .
RUN curl -L https://foundry.paradigm.xyz | bash
RUN . ~/.bashrc && foundryup
WORKDIR /workspace

ENTRYPOINT [ "/bin/bash" ]

from setuptools import setup, find_packages

install_requires = [
    "pydantic >= 1.9.0",
    "typing_extensions >= 4.0, < 5",
    "requests >= 2.20, < 3.0",
    "tomli >= 2.0.0, < 3",
    "networkx >= 2.5, < 3",
    "StrEnum",
]

# Also: [pyright](https://github.com/microsoft/pyright/) (distributed through npm)
extras_require = dict(
    tests=[
        "pytest >= 6.2.5, < 7.0",
        "pytest-asyncio >= 0.17, < 1",
    ],
    dev=[
        "black",
        "portray",
        "ipython",
    ],
)

setup(
    name="woke",
    description="Woke is a static analyzer and symbolic execution engine for Solidity.",
    url="https://github.com/Ackee-Blockchain/woke",
    author="Ackee Blockchain",
    version="0.1.0",
    packages=find_packages(),
    python_requires=">=3.7",
    install_requires=install_requires,
    extras_require=extras_require,
    license="ISC",
    long_description=open("README.md", "r", encoding="utf-8").read(),
    entry_points=dict(console_scripts=[]),
)

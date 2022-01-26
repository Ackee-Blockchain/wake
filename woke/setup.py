from setuptools import setup, find_packages

install_requires = []

# Also: [pyright](https://github.com/microsoft/pyright/) (distributed through npm)
extras_require = dict(
    tests=["pytest >= 6.2.5, < 7.0"],
    dev=["black, portray"],
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

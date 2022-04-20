from setuptools import setup, find_packages

install_requires = [
    "pydantic >= 1.9.0",
    "typing_extensions >= 4.0, < 5",
    "aiohttp >= 3.8, < 4",
    "aiofiles >= 0.8.0",
    "tomli >= 2.0.0, < 3",
    "networkx >= 2.5, < 3",
    "pycryptodomex >= 3.12, < 4",
    "click >= 8, < 9",
    "rich >= 10.16",
    "pathvalidate >= 2.5.0, < 3",
    "StrEnum",
]

# Also: [pyright](https://github.com/microsoft/pyright/) (distributed through npm)
extras_require = dict(
    tests=[
        "pytest >= 6.2.5, < 7.0",
        "pytest-asyncio >= 0.17, < 1",
        "GitPython >= 3.1.20, < 4",
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
    entry_points=dict(
        console_scripts=[
            "woke=woke.x_cli.__main__:main",
        ]
    ),
)

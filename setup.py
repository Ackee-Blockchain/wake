from setuptools import setup, find_packages
from pathlib import Path

this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

install_requires = [
    "pydantic >= 1.9.1",
    "typing_extensions >= 4.0, < 5",
    "aiohttp >= 3.8, < 4",
    "aiofiles >= 0.8.0",
    "tomli >= 2.0.0, < 3",
    "networkx >= 2.5, < 3",
    "click >= 8, < 9",
    "rich-click >= 1.6.0, < 2",
    "rich >= 10.16",
    "pathvalidate >= 2.5.0, < 3",
    "intervaltree >= 3.1",
    "graphviz >= 0.19",
    "tblib >= 1.7.0, < 2",
    "eth_utils >= 2.0.0, < 3",
    "eth_abi >= 3.0.0, < 4",
    "eth-hash[pycryptodome] >= 0.3.3, < 1",
    "websocket-client >= 1.4.0",
    "pywin32 >= 302; platform_system == 'Windows'",
    "watchdog >= 2.2.0, < 3",
    "pytest >= 7, < 8",
    "pdbr >= 0.7.7, < 1",
]

# Also: [pyright](https://github.com/microsoft/pyright/) (distributed through npm)
extras_require = dict(
    tests=[
        "pytest-asyncio >= 0.17, < 1",
        "GitPython >= 3.1.20, < 4",
    ],
    dev=[
        "black",
        "mkdocs-material >= 8.3.9",
        "mkdocstrings[python]",
        "pymdown-extensions >= 9.0",
        "pygments",
        "mike",
        "isort >= 5.10.0, < 6",
    ],
)

setup(
    name="woke",
    description="Woke is a Python-based development and testing framework for Solidity.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Ackee-Blockchain/woke",
    author="Ackee Blockchain",
    version="2.0.0-rc1",
    packages=find_packages(exclude=("examples", "tests",)),
    keywords=[
        "solidity",
        "ethereum",
        "blockchain",
        "review",
        "audit",
        "security",
        "compiler",
        "solidity audit",
        "solidity security"
      ],
    python_requires=">=3.7",
    install_requires=install_requires,
    extras_require=extras_require,
    license="ISC",
    entry_points=dict(
        console_scripts=[
            "woke=woke.cli.__main__:main",
            "woke-solc=woke.cli.__main__:woke_solc",
        ]
    ),
)

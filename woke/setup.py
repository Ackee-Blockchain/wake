from setuptools import setup, find_packages

install_requires = []

tests_require = ['pytest >= 6.25, < 0.7']

extras_require = dict(dev = [])

setup(
    name="woke",
    description="Woke is a static analyzer and symbolic execution engine for Solidity.",
    url="https://github.com/Ackee-Blockchain/woke",
    author="Ackee Blockchain",
    version="0.1.0",
    packages=find_packages(),
    python_requires=">=3.7",
    install_requires=install_requires,
    tests_require=tests_require,
    extras_require=extras_require,
    license="ISC",
    long_description=open("README.adoc", "r", encoding="utf-8").read(),
    entry_points=dict(console_scripts = [])
)

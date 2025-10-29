"""
Setup script for personal vault.
"""

from setuptools import setup, find_packages

setup(
    name="personal-vault",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "click>=8.0.0",
        "cryptography>=41.0.0",
        "mcp>=1.0.0",
    ],
    entry_points={
        'console_scripts': [
            'vault=advanced_vault.cli.main:cli',
        ],
    },
    python_requires='>=3.8',
)

from setuptools import setup, find_packages

# Read requirements.txt, ignore comments
try:
    with open("requirements.txt", "r") as f:
        REQUIRES = [line.split("#", 1)[0].strip() for line in f if line.strip()]
except:
    print("'requirements.txt' not found!")
    REQUIRES = list()

setup(
    name="finpilot-ai",
    version="1.0.0",
    include_package_data=True,
    author="badhope",
    author_email="badhope@noreply.gitcode.com",
    url="https://gitcode.com/badhope/FinPilot",
    license="MIT",
    packages=find_packages(),
    install_requires=REQUIRES,
    description="FinPilot AI: An Open-Source AI Agent Platform for Financial Applications using LLMs",
    long_description="""FinPilot AI""",
    classifiers=[
        # Trove classifiers
        # Full list: https://pypi.python.org/pypi?%3Aaction=list_classifiers
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: Implementation :: CPython",
        "Programming Language :: Python :: Implementation :: PyPy",
    ],
    keywords="Financial Large Language Models, AI Agents",
    platforms=["any"],
    python_requires=">=3.10, <3.14",
)

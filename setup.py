from setuptools import setup, find_packages

setup(
    name="sentinel-sdk",
    version="1.0.0",
    description="AI-powered auto-healing plugin for any Python web framework",
    packages=find_packages(),
    install_requires=[
        "google-generativeai>=0.5.0",
        "elasticsearch>=8.0.0",
        "python-dotenv>=1.0.0",
    ],
    extras_require={
        "flask":   ["flask>=2.0"],
        "fastapi": ["fastapi>=0.100", "starlette>=0.27"],
        "django":  ["django>=4.0"],
    },
    python_requires=">=3.8",
)

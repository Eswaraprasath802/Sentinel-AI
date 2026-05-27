from setuptools import setup, find_packages

setup(
    name             = "sentinel-sdk",
    version          = "2.0.3",
    description      = "AI Auto-Healing Plugin — Gemini + Elastic MCP",
    packages         = find_packages(),
    python_requires  = ">=3.9",
    install_requires = [
        "flask>=3.0.0",
        "elasticsearch>=8.13.0",
        "google-genai>=0.8.0",
        "python-dotenv>=1.0.1",
        "twilio>=9.0.0",
        "psutil>=5.9.0",
    ],
)

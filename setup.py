import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="HMD-DGB",
    version="1.0.0",
    author="Jeroen van Oosterhout",
    author_email="",
    description="Connects Home Assistant entities to physical GPIO pins using durable bindings",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="",
    packages=setuptools.find_packages(),
    install_requires=[
        "fastapi>=0.115.6,<1",
        "uvicorn>=0.34.0,<1",
        "psutil==6.1.1",
        "gpiozero==2.0.1",
        "lgpio==0.2.2.0",
        "homeassistant-api==5.0.2",
        "ha-mqtt-discoverable==0.23.0",
        "durable-rules==2.0.28"
    ],
    extras_require={},
    classifiers=[
        "Programming Language :: Python :: 3"
    ],
    python_requires='>=3.10.0',
    license = "MIT"
)

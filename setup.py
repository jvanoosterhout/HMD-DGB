import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="PinAPI",
    version="0.0.2",
    author="Jeroen van Oosterhout",
    author_email="",
    description="Interface to configure and read/write GPIO pins remotelly on a raspberry pi",
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
        "homeassistant-api==4.2.2.post2"
    ],
    extras_require={},
    classifiers=[
        "Programming Language :: Python :: 3"
    ],
    python_requires='>=3.10.11',
    license = "MIT"
)

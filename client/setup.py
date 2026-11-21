from setuptools import setup, find_packages

setup(
    name="daz-cloud-render",
    version="0.1.0",
    description="DAZ Studio Cloud Rendering auf Vast.ai",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[],
    entry_points={
        "console_scripts": [
            "daz-cloud-render=daz_cloud_render.cli:main",
        ],
    },
    license="MIT",
)

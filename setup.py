from setuptools import setup

setup(
    name="fem",
    version="1.1.0",
    py_modules=["main"],   # 明确把 main.py 作为模块
    entry_points={
        "console_scripts": [
            "fem = main:main",
        ],
    },
)

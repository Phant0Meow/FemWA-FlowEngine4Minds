# setup.py
# 代码原则：所有代码不许写try静默兜底不报错，有错必须报错。

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    # ── 以下信息从 pyproject.toml 自动读取，无需重复写 ──
    # name, version, author, description, license, python_requires, install_requires, classifiers, url 全部省略

    # ── 以下为构建相关，必须保留 ──
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    py_modules=["main"],
    entry_points={
        "console_scripts": [
            "femwa = main:main",
        ],
    },
    include_package_data=True,
)

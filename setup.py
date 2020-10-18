from importlib.machinery import SourceFileLoader
from pathlib import Path

from setuptools import setup

description = 'pytest plugin for testing cloudflare workers'
THIS_DIR = Path(__file__).resolve().parent
try:
    long_description = THIS_DIR.joinpath('README.md').read_text()
except FileNotFoundError:
    long_description = description

# avoid loading the package before requirements are installed:
version = SourceFileLoader('version', 'pytest_cloudflare_worker/version.py').load_module()

setup(
    name='pytest-cloudflare-worker',
    version=version.VERSION,
    description=description,
    long_description=long_description,
    long_description_content_type='text/markdown',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.8',
        'Intended Audience :: Developers',
        'Intended Audience :: Information Technology',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Operating System :: Unix',
        'Operating System :: POSIX :: Linux',
        'Environment :: MacOS X',
        'Topic :: Internet',
        'Framework :: Pytest',
        'Framework :: AsyncIO',
    ],
    author='Samuel Colvin',
    author_email='s@muelcolvin.com',
    url='https://github.com/samuelcolvin/pytest-cloudflare-worker',
    license='MIT',
    packages=['pytest_cloudflare_worker'],
    entry_points={
        'pytest11': ['cloudflare_worker = pytest_cloudflare_worker.plugin'],
    },
    python_requires='>=3.8',
    zip_safe=True,
    install_requires=[
        'requests>=2.24.0',
        'websockets>=8.1',
        'pytest>=6.0.0',
        'toml>=0.10.1',
    ],
)

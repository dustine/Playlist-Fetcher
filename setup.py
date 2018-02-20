#!python3

from setuptools import setup, find_packages

# To use a consistent encoding
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='playlist_fetcher',
    version='0.1.0-dev1',
    packages=find_packages(),

    install_requires=['youtube_dl', 'tqdm', 'colorama'],
    python_requires='>=3',

    entry_points={
        'console_scripts': [
            'playlist_fetcher=playlist_fetcher.command_line:main',
        ],
    },
    package_data={
        '': ['*.txt', '*.rst'],
    },

    author='Dustine Camacho',
    author_email='dustineCamacho@gmail.com',
    license='GPLv3',
    description='Indexes and downloads playlists using youtube-dl',
    long_description=long_description,
    url='http://github.com/dustine/playlist_fetcher',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Topic :: Multimedia',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
    ],
    zip_safe=False
)

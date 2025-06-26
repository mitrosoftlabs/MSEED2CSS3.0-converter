#!/usr/bin/env python3

from setuptools import setup, find_packages
import os

# Read the README file for long description
here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

# Read requirements
install_requires = [
    'obspy>=1.3.0',
    'numpy>=1.19.0', 
    'sqlalchemy>=1.4.0',
    'pytz>=2021.1',
    'pisces>=0.3.0',
    'matplotlib>=3.3.0',
    'requests>=2.25.0',
]

setup(
    name='mseed-pipeline-converter',
    version='2.1.0',
    description='A robust pipeline for converting MiniSEED waveform data to CSS3.0 format',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='MitroSoft Labs',
    author_email='mitrosoftlabs@gmail.com',
    url='https://github.com/mitrosoftlabs/mseed_pipeline_converter',
    project_urls={
        'Bug Reports': 'https://github.com/mitrosoftlabs/mseed_pipeline_converter/issues',
        'Source': 'https://github.com/mitrosoftlabs/mseed_pipeline_converter',
        'Documentation': 'https://github.com/mitrosoftlabs/mseed_pipeline_converter/wiki',
    },
    
    packages=find_packages(),
    py_modules=['mseed_pipeline_converter'],
    
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Science/Research',
        'Topic :: Scientific/Engineering :: Physics',
        'License :: Other/Proprietary License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Operating System :: OS Independent',
    ],
    
    keywords='seismology, miniseed, css3.0, fdsn, waveform, seismic-data, earthquake',
    
    python_requires='>=3.8',
    install_requires=install_requires,
    
    extras_require={
        'dev': [
            'pytest>=6.0',
            'pytest-cov>=2.0',
            'black>=21.0',
            'flake8>=3.8',
            'mypy>=0.800',
        ],
        'plotting': [
            'matplotlib>=3.3.0',
            'cartopy>=0.18.0',
        ],
    },
    
    entry_points={
        'console_scripts': [
            'mseed2css=mseed_pipeline_converter:main',
            'mseed-converter=mseed_pipeline_converter:main',
        ],
    },
    
    include_package_data=True,
    zip_safe=False,
    
    # Additional metadata
    license='CC BY-NC 4.0',
    platforms=['any'],
)
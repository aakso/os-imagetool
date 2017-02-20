from setuptools import setup, find_packages

setup(
    name='os-imagetool',
    author='Anton Aksola',
    author_email='aakso@iki.fi',
    license='Apache License, Version 2.0',
    version='0.0.1',
    packages=find_packages(),
    install_requires=[
        'python-glanceclient', 'requests', 'python-dateutil'
    ],
    entry_points=dict(
        console_scripts=[
            'os_imagetool=os_imagetool.cmd.imagetool:main'
        ]
    ))
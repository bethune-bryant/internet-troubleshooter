from setuptools import setup, find_packages

from internet_troubleshooter import __version__

setup(
    name='internet_troubleshooter',
    version=__version__,

    url='https://github.com/bethune-bryant/internet-troubleshooter',
    author='Bryant Nelson',
    author_email='bryantstutoringservice@gmail.com',

    packages=find_packages(),

    entry_points={'console_scripts': [
        'checkinternet = internet_troubleshooter.checkinternet:main',
    ]},

    setup_requires=['wheel'],
)
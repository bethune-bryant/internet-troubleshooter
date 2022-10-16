from setuptools import setup, find_packages

from internet_troubleshooter import __version__

setup(
    name='internet_troubleshooter',
    version=__version__,

    url='https://github.com/bethune-bryant/internet-troubleshooter',
    author='Bryant Nelson',
    author_email='bryantstutoringservice@gmail.com',

    #packages=find_packages(),

    scripts=['internet_troubleshooter/checkinternet.py'],
)
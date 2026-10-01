from setuptools import setup, find_packages

setup(
    name='oasira_b2b',
    version='1.0.67',
    description='Oasira Business Integration for Home Assistant',
    author='EffortlessHome',
    packages=find_packages(),
    install_requires=[
        'oasira==0.2.18',
        'google-auth==2.28.1',
        'gTTS>=2.5.4',
        'httpx>=0.27.0'
    ],
)
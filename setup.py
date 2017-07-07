from setuptools import setup

if __name__ == "__main__":
    setup(
        name="insights-web",
        version="0.1.0",
        description="Insights Web",
        packages=["insights_web"],
        install_requires=[
            'boto3',
            'logstash_formatter',
            'insights-core',
            'flask==0.12.1',
            'uWSGI==2.0.15'
        ]
    )

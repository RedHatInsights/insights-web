from setuptools import setup

with open("insights_web/VERSION") as fp:
    version = fp.read().strip()

if __name__ == "__main__":
    setup(
        name="insights-web",
        version=version,
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

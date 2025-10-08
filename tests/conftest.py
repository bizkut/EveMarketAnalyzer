import os

def pytest_configure(config):
    """
    Allows plugins and conftest files to perform initial configuration.
    This hook is called for every plugin and initial conftest file
    after command line options have been parsed.
    """
    os.environ['POSTGRES_SERVER'] = 'localhost'
    os.environ['POSTGRES_USER'] = 'testuser'
    os.environ['POSTGRES_PASSWORD'] = 'testpassword'
    os.environ['POSTGRES_DB'] = 'testdb'
    os.environ['DATABASE_URL'] = 'postgresql://testuser:testpassword@localhost/testdb'
    os.environ['REDIS_HOST'] = 'localhost'
    os.environ['REDIS_PORT'] = '6379'
    os.environ['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'
    os.environ['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/0'
    os.environ['API_KEY'] = 'testkey'
    os.environ['LOG_LEVEL'] = 'INFO'
    os.environ['ESI_BASE_URL'] = 'https://esi.evetech.net/latest'
    os.environ['USER_AGENT'] = 'TestAgent'
    os.environ['ENV'] = 'test'
import sys


def test_python_versjon():
    assert sys.version_info[:2] == (3, 12)

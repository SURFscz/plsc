from test.base_test import BaseTest
import logging
import pytest
import requests

logger = logging.getLogger(__name__)

class TestFoobar(BaseTest):

    def test_foobar(self):
        logger.debug("test_foobar")
        url = 'http://localhost:3000/people/1'
        r = requests.get(url).json()
        logger.debug(f"json: {r}")
        assert r['name'] == "harry"

from unittest import TestCase
from json_server.handlers import Handler
from gera2ld.pyserve import run_forever, start_server_aiohttp

from plsc.sldap import sLDAP

import threading
import asyncio
import socket
import time

import logging
import os

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class BaseTest(TestCase):

    dst_conf = {
        'uri': os.environ["LDAP_URL"],
        'basedn': os.environ["LDAP_BASE_DN"],
        'binddn': os.environ["LDAP_BIND_DN"],
        'passwd': os.environ["LDAP_ADMIN_PASSWORD"]
    }

    @classmethod
    def setUpClass(cls):
        def start_server(loop):
            logger.debug("BaseTest start_server")
            handle = Handler('test/sbs.json')
            asyncio.set_event_loop(loop)
            run_forever(start_server_aiohttp(handle, ':3080'))

        def check_server():
            logger.debug("BaseTest check_server")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            while sock.connect_ex(('127.0.0.1', 3080)) == 111:
                time.sleep(0.1)

        logger.debug("BaseTest setUpClass")
        cls.loop = asyncio.new_event_loop()
        cls.x = threading.Thread(target=start_server, args=(cls.loop,), )
        cls.x.start()
        check_server()

    @classmethod
    def tearDownClass(cls):
        logger.debug("BaseTest tearDownClass")
        cls.loop.call_soon_threadsafe(cls.loop.stop)
        cls.x.join()

    def setUp(self):
        logger.debug("BaseTest setUp")
        self.dst = sLDAP(self.dst_conf)

    def tearDown(self):
        logger.debug("BaseTest tearDown")


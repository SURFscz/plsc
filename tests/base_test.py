from unittest import TestCase

from json_server.handlers import Handler
from gera2ld.pyserve import run_forever, start_server_aiohttp

from plsc.sldap import sLDAP
from plsc.sbs import SBS

import plsc_ordered
import plsc_flat
import threading
import asyncio
import socket
import time

import logging
import os

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

DEFAULT_LOCAL_PORT = 3080
class BaseTest(TestCase):

    src_conf = {
        'host': os.environ.get("SBS_URL", "http://localhost:{}".format(DEFAULT_LOCAL_PORT) ),
        'user': os.environ.get("SBS_USER","sysread"),
        'passwd': os.environ.get("SBS_PASS","secret"),
        'ipv4_only': True
    }

    dst_conf = {
        'uri': os.environ["LDAP_URL"],
        'basedn': "dc=services,{}".format(os.environ["LDAP_BASE_DN"]),
        'binddn': os.environ["LDAP_BIND_DN"],
        'passwd': os.environ["LDAP_ADMIN_PASSWORD"]
    }

    @classmethod
    def setUpClass(cls):
        def start_server(loop):
            logger.debug("BaseTest start_server")
            handle = Handler('test/sbs.json')
            asyncio.set_event_loop(loop)
            run_forever(start_server_aiohttp(handle, ':{}'.format(DEFAULT_LOCAL_PORT)))

        def check_server():
            logger.debug("BaseTest check_server")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            while sock.connect_ex(('127.0.0.1', DEFAULT_LOCAL_PORT)) == 111:
                time.sleep(0.1)

        if not os.environ.get("SBS_URL", None):
            logger.debug("BaseTest setUpClass")
            cls.loop = asyncio.new_event_loop()
            cls.x = threading.Thread(target=start_server, args=(cls.loop,), )
            cls.x.start()
            check_server()
        else:
            cls.loop = None
      
    @classmethod
    def tearDownClass(cls):
        if cls.loop:
            logger.debug("BaseTest tearDownClass")
            cls.loop.call_soon_threadsafe(cls.loop.stop)
            cls.x.join()

    def setUp(self):
        """ Run a complete PLSC cycle, 1st ordered structure, 2nd flat structure...
        """

        logger.debug("BaseTest setUp")

        logger.debug(self.src_conf)
        logger.debug(self.dst_conf)

        self.src = SBS(self.src_conf)
        self.dst = sLDAP(self.dst_conf)

        logger.debug("- Ordered structure...")
        plsc_ordered.create(self.src, self.dst)
        plsc_ordered.cleanup(self.dst)

        logger.debug("- Flat structure...")
        plsc_flat.create(self.dst, self.dst)
        plsc_flat.cleanup(self.dst, self.dst)

    def tearDown(self):
        logger.debug("BaseTest tearDown")


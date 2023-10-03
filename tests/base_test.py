from unittest import TestCase

from aiohttp import web

from gera2ld.pyserve import run_forever, start_server_aiohttp

from sldap import SLdap
from sbs import SBS

import logging
import os
import plsc_ordered
import plsc_flat
import threading
import asyncio
import socket
import time
import json

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class APIHandler:
    def __init__(self):
        logger.debug("Initializng API HANDLER !")

    async def __call__(self, request):
        method = getattr(self, f'do_{request.method.lower()}', None)
        if method is None:
            raise web.HTTPNotImplemented()

        result = method(request)
        if asyncio.iscoroutine(result):
            result = await result
        return result

    @staticmethod
    def do_get(request):
        try:
            with open(f".{request.path}", 'r') as f:
                data = f.read()
                return web.json_response(json.loads(data))

        except Exception as e:
            logger.error(f"Exception: {str(e)}")
            return web.json_response({}, status=404)


DEFAULT_LOCAL_PORT = 3333


class BaseTest(TestCase):

    src_conf = {
        'recorder': (os.environ.get("SBS_API_RECORDING", "NO").upper() == "YES"),
        'host': os.environ.get("SBS_URL", "http://localhost:{}".format(DEFAULT_LOCAL_PORT)),
        'user': os.environ.get("SBS_USER", "sysread"),
        'passwd': os.environ.get("SBS_PASS", "secret"),
        'verify_ssl': (os.environ.get("SBS_VERIFY_SSL", "NO").upper() == "YES"),
        'ipv4_only': True
    }

    dst_conf = {
        'uri': os.environ["LDAP_URL"],
        'basedn': os.environ["LDAP_BASE_DN"],
        'binddn': os.environ["LDAP_BIND_DN"],
        'passwd': os.environ["LDAP_ADMIN_PASSWORD"],
        'sizelimit': int(os.environ.get("LDAP_SIZELIMIT", 500))
    }

    @classmethod
    def setUpClass(cls):
        def start_server(loop):
            logger.debug("BaseTest start_server")
            handle = APIHandler()
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

        logger.info("BaseTest setUp")

        logger.debug(self.src_conf)
        logger.debug(self.dst_conf)

        self.src = SBS(self.src_conf)
        self.dst = SLdap(self.dst_conf)

        logger.info("Creating: Ordered structure...")
        plsc_ordered.create(self.src, self.dst)
        plsc_ordered.cleanup(self.dst)

        logger.info("Creating: Flat structure...")
        plsc_flat.create(self.dst, self.dst)
        plsc_flat.cleanup(self.dst, self.dst)

    def tearDown(self):
        logger.info("BaseTest tearDown")

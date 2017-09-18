#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
sys.dont_write_bytecode = True

try:
    import gevent
    import gevent.monkey
    gevent.monkey.patch_all(os=False, signal=False, subprocess=False)
except ImportError:
    print('Could not find gevent! Please install gevent-1.0.0 or above.\n'
          'Exit...')
    sys.exit(-1)

try:
    import OpenSSL
except ImportError:
    print('Could not find pyOpenSSL! Please install pyOpenSSL-16.0.0 or above.\n'
          'Exit...')
    sys.exit(-1)

# Scan config start
import os
dir = os.path.abspath(os.path.dirname(__file__))
g_infile = 'ip_range_in.txt'
g_outfile = 'ip_range_out.txt'
g_infile = os.path.join(dir, g_infile)
g_outfile = os.path.join(dir, g_outfile)
g_per_save_num = 10
g_save_interval = 60 * 10
g_threads = 500
g_timeout = 4
g_conn_timeout = 1
g_handshake_timeout = 1.5
g_server_name = b'www.google.com'
g_http_req = (
    b'HEAD / HTTP/1.1\r\n'
    b'Host: www.appspot.com\r\n'
    b'Connection: Close\r\n\r\n'
    )
gws_ciphers = (
    'TLSv1.2:'
    '!ECDHE-RSA-AES128-GCM-SHA256:'
    '!AES128-GCM-SHA256:'
    '!aNULL:!eNULL:!MD5:!DSS:!RC4:!3DES'
    )
GoogleG23PKP = set((
# https://pki.google.com/GIAG2.crt
b'''\
-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAnCoEd1zYUJE6BqOC4NhQ
SLyJP/EZcBqIRn7gj8Xxic4h7lr+YQ23MkSJoHQLU09VpM6CYpXu61lfxuEFgBLE
XpQ/vFtIOPRT9yTm+5HpFcTP9FMN9Er8n1Tefb6ga2+HwNBQHygwA0DaCHNRbH//
OjynNwaOvUsRBOt9JN7m+fwxcfuU1WDzLkqvQtLL6sRqGrLMU90VS4sfyBlhH82d
qD5jK4Q1aWWEyBnFRiL4U5W+44BKEMYq7LqXIBHHOZkQBKDwYXqVJYxOUnXitu0I
yhT8ziJqs07PRgOXlwN+wLHee69FM8+6PnG33vQlJcINNYmdnfsOEXmJHjfFr45y
aQIDAQAB
-----END PUBLIC KEY-----
''',
# https://pki.goog/gsr2/GIAG3.crt
# https://pki.goog/gsr2/GTSGIAG3.crt
b'''\
-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAylJL6h7/ziRrqNpyGGjV
Vl0OSFotNQl2Ws+kyByxqf5TifutNP+IW5+75+gAAdw1c3UDrbOxuaR9KyZ5zhVA
Cu9RuJ8yjHxwhlJLFv5qJ2vmNnpiUNjfmonMCSnrTykUiIALjzgegGoYfB29lzt4
fUVJNk9BzaLgdlc8aDF5ZMlu11EeZsOiZCx5wOdlw1aEU1pDbcuaAiDS7xpp0bCd
c6LgKmBlUDHP+7MvvxGIQC61SRAPCm7cl/q/LJ8FOQtYVK8GlujFjgEWvKgaTUHF
k5GiHqGL8v7BiCRJo0dLxRMB3adXEmliK+v+IO9p+zql8H4p7u2WFvexH6DkkCXg
MwIDAQAB
-----END PUBLIC KEY-----
''',
# https://pki.goog/gsr4/GIAG3ECC.crt
b'''\
-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEG4ANKJrwlpAPXThRcA3Z4XbkwQvW
hj5J/kicXpbBQclS4uyuQ5iSOGKcuCRt8ralqREJXuRsnLZo0sIT680+VQ==
-----END PUBLIC KEY-----
'''))
g_context = OpenSSL.SSL.Context(OpenSSL.SSL.TLSv1_2_METHOD)
g_context.set_session_cache_mode(OpenSSL.SSL.SESS_CACHE_OFF)
g_context.set_cipher_list(gws_ciphers)
# Scan config end

# Load/Save scan data function start
import re
import threading

get_ip_prefix = re.compile(
    '^\s*'
    '('
    '(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}'
    ')').search
g_ip_prefix_set = set()
wLock = threading.Lock()

def load_ip_range(ip_prefix_set=g_ip_prefix_set, file=g_infile):
    ip_prefix_set.clear()
    with open(file, 'r') as f:
        for line in f:
            ip_prefix = get_ip_prefix(line)
            if ip_prefix:
                ip_prefix_set.add(ip_prefix.group(1))

def save_ip_range(ip_prefix_list, file=g_outfile):
    with wLock:
        with open(file, 'a') as f:
            for ip_prefix in ip_prefix_list:
                f.write(ip_prefix)
                f.write('0/24\n')
# Load/Save scan data function end

# Scan function start
import time
import socket
import struct
from openssl_wrap import SSLConnection

def get_ssl_socket(sock, server_hostname=None, context=g_context):
    ssl_sock = SSLConnection(context, sock)
    if server_hostname:
        ssl_sock.set_tlsext_host_name(server_hostname)
    return ssl_sock

def google_verify(sock, g23pkp=GoogleG23PKP):
    # Verify certificates for Google web sites.
    certs = sock.get_peer_cert_chain()
    if len(certs) < 3:
        raise OpenSSL.SSL.Error('No intermediate CA was found.')
    pkp = OpenSSL.crypto.dump_publickey(OpenSSL.crypto.FILETYPE_PEM, certs[1].get_pubkey())
    if pkp not in g23pkp:
        raise OpenSSL.SSL.Error('The intermediate CA is mismatching.')

def get_status_code(sock, http_req=g_http_req):
    sock.send(http_req)
    return sock.read(12)[-3:]

def get_ip_info(ip,
                conn_timeout=g_conn_timeout,
                handshake_timeout=g_handshake_timeout,
                timeout=g_timeout,
                server_name=g_server_name,
                offlinger_val=struct.pack('ii', 1, 0)):
    start_time = time.time()
    sock = None
    ssl_sock = None
    #domain = None
    status_code = None
    try:
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, offlinger_val)
        sock.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, True)
        ssl_sock = get_ssl_socket(sock, server_name)
        ssl_sock.settimeout(conn_timeout)
        ssl_sock.connect((ip, 443))
        ssl_sock.settimeout(handshake_timeout)
        ssl_sock.do_handshake()
        handshaked_time = time.time() - start_time
        if handshaked_time > handshake_timeout:
            raise socket.timeout('handshake cost %dms timed out' % int(handshaked_time*1000))
        ssl_sock.settimeout(timeout)
        google_verify(ssl_sock)
        #domain = ssl_sock.get_peer_certificate().get_subject().CN
        status_code = get_status_code(ssl_sock)
    except Exception as e:
        #print(e)
        pass
    finally:
        if ssl_sock:
            ssl_sock.close()
        if sock:
            sock.close()
    # Get '302' redirect when this IP provide Google App Engine server.
    return status_code == b'302'
# Scan function end

class gae_scanner(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.Lock = threading.Lock()
        self.sub_addr = 0
        self.ip_prefix_list = []

    def save_data(self):
        save_ip_range(self.ip_prefix_list)
        self.ip_prefix_list = []

    def run(self,
            ip_prefix_set=g_ip_prefix_set,
            per_save_num=g_per_save_num,
            save_interval=g_save_interval):
        try:
            self.ip_prefix = ip_prefix_set.pop()
        except KeyError:
            return
        last_save_time = time.time()
        while True:
            try:
                if self.sub_addr > 255:
                    self.sub_addr = 0
                    self.ip_prefix = ip_prefix_set.pop()
                ip = '%s%d' % (self.ip_prefix, self.sub_addr)
                self.sub_addr += 1
                is_gae = get_ip_info(ip)
                if is_gae:
                    self.ip_prefix_list.append(self.ip_prefix)
                    print("%s is ok, left:%d" % (self.ip_prefix, len(ip_prefix_set)))
                    self.sub_addr = 256
                    if len(self.ip_prefix_list) >= per_save_num:
                        self.save_data()
                        last_save_time = time.time()
                        continue
            except KeyError:
                if self.ip_prefix_list:
                    self.save_data()
                break
            except Exception as e:
                print('Error occur: %r' % e)
                continue
            if self.ip_prefix_list:
                now = time.time()
                if now - last_save_time > save_interval:
                    self.save_data()
                    last_save_time = now

def main():
    load_ip_range()
    threads_list = []
    for i in range(g_threads):
        scanner = gae_scanner()
        scanner.setDaemon(True)
        #scanner.setName('SCANNER%s' % str(i + 1).rjust(4, '0'))
        scanner.start()
        threads_list.append(scanner)
    for p in threads_list:
        p.join()

if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-

import os
import sys
import time
import re
import urllib
import urllib2
import cookielib
import base64
import mimetools
import json
import itertools

from utilities import Debug

_IS_LIBTORRENT = True
import xbmc, xbmcgui, xbmcaddon, xbmcvfs

__settings__ = xbmcaddon.Addon(id='plugin.video.myshows')
RE = {
    'content-disposition': re.compile('attachment;\sfilename="*([^"\s]+)"|\s')
}

# ################################
#
# HTTP
#
# ################################

class HTTP:
    def __init__(self):
        self._dirname = xbmc.translatePath('special://temp')  #.decode('utf-8').encode('cp1251')
        for subdir in ('xbmcup', sys.argv[0].replace('plugin://', '').replace('/', '')):
            self._dirname = os.path.join(self._dirname, subdir)
            if not xbmcvfs.exists(self._dirname):
                xbmcvfs.mkdir(self._dirname)


    def fetch(self, request, **kwargs):
        self.con, self.fd, self.progress, self.cookies, self.request = None, None, None, None, request

        if not isinstance(self.request, HTTPRequest):
            self.request = HTTPRequest(url=self.request, **kwargs)

        self.response = HTTPResponse(self.request)

        #Debug('XBMCup: HTTP: request: ' + str(self.request))

        try:
            self._opener()
            self._fetch()
        except Exception, e:
            xbmc.log('XBMCup: HTTP: ' + str(e), xbmc.LOGERROR)
            if isinstance(e, urllib2.HTTPError):
                self.response.code = e.code
            self.response.error = e
        else:
            self.response.code = 200

        if self.fd:
            self.fd.close()
            self.fd = None

        if self.con:
            self.con.close()
            self.con = None

        if self.progress:
            self.progress.close()
            self.progress = None

        self.response.time = time.time() - self.response.time

        xbmc.log('XBMCup: HTTP: response: ' + str(self.response), xbmc.LOGDEBUG)

        return self.response


    def _opener(self):

        build = [urllib2.HTTPHandler()]

        if self.request.redirect:
            build.append(urllib2.HTTPRedirectHandler())

        if self.request.proxy_host and self.request.proxy_port:
            build.append(urllib2.ProxyHandler(
                {self.request.proxy_protocol: self.request.proxy_host + ':' + str(self.request.proxy_port)}))

            if self.request.proxy_username:
                proxy_auth_handler = urllib2.ProxyBasicAuthHandler()
                proxy_auth_handler.add_password('realm', 'uri', self.request.proxy_username,
                                                self.request.proxy_password)
                build.append(proxy_auth_handler)

        if self.request.cookies:
            self.request.cookies = os.path.join(self._dirname, self.request.cookies)
            self.cookies = cookielib.MozillaCookieJar()
            if os.path.isfile(self.request.cookies):
                self.cookies.load(self.request.cookies)
            build.append(urllib2.HTTPCookieProcessor(self.cookies))

        urllib2.install_opener(urllib2.build_opener(*build))


    def _fetch(self):
        params = {} if self.request.params is None else self.request.params

        if self.request.upload:
            boundary, upload = self._upload(self.request.upload, params)
            req = urllib2.Request(self.request.url)
            req.add_data(upload)
        else:

            if self.request.method == 'POST':
                if isinstance(params, dict) or isinstance(params, list):
                    params = urllib.urlencode(params)
                req = urllib2.Request(self.request.url, params)
            else:
                req = urllib2.Request(self.request.url)

        for key, value in self.request.headers.iteritems():
            req.add_header(key, value)

        if self.request.upload:
            req.add_header('Content-type', 'multipart/form-data; boundary=%s' % boundary)
            req.add_header('Content-length', len(upload))

        if self.request.auth_username and self.request.auth_password:
            req.add_header('Authorization', 'Basic %s' % base64.encodestring(
                ':'.join([self.request.auth_username, self.request.auth_password])).strip())

        #self.con = urllib2.urlopen(req, timeout=self.request.timeout)
        self.con = urllib2.urlopen(req)
        self.response.headers = self._headers(self.con.info())

        if self.request.download:
            self._download()
        else:
            self.response.body = self.con.read()

        if self.request.cookies:
            self.cookies.save(self.request.cookies)


    def _download(self):
        fd = open(self.request.download, 'wb')
        if self.request.progress:
            self.progress = xbmcgui.DialogProgress()
            self.progress.create(u'Download')

        bs = 1024 * 8
        size = -1
        read = 0
        name = None

        if self.request.progress:
            if 'content-length' in self.response.headers:
                size = int(self.response.headers['content-length'])
            if 'content-disposition' in self.response.headers:
                r = RE['content-disposition'].search(self.response.headers['content-disposition'])
                if r:
                    name = urllib.unquote(r.group(1))

        while 1:
            buf = self.con.read(bs)
            if buf == '':
                break
            read += len(buf)
            fd.write(buf)

            if self.request.progress:
                self.progress.update(*self._progress(read, size, name))

        self.response.filename = self.request.download


    def _upload(self, upload, params):
        res = []
        boundary = mimetools.choose_boundary()
        part_boundary = '--' + boundary

        if params:
            for name, value in params.iteritems():
                res.append([part_boundary, 'Content-Disposition: form-data; name="%s"' % name, '', value])

        if isinstance(upload, dict):
            upload = [upload]

        for obj in upload:
            name = obj.get('name')
            filename = obj.get('filename', 'default')
            content_type = obj.get('content-type')
            try:
                body = obj['body'].read()
            except AttributeError:
                body = obj['body']

            if content_type:
                res.append([part_boundary,
                            'Content-Disposition: file; name="%s"; filename="%s"' % (name, urllib.quote(filename)),
                            'Content-Type: %s' % content_type, '', body])
            else:
                res.append([part_boundary,
                            'Content-Disposition: file; name="%s"; filename="%s"' % (name, urllib.quote(filename)), '',
                            body])

        result = list(itertools.chain(*res))
        result.append('--' + boundary + '--')
        result.append('')
        return boundary, '\r\n'.join(result)


    def _headers(self, raw):
        headers = {}
        for line in raw.headers:
            pair = line.split(':', 1)
            if len(pair) == 2:
                tag = pair[0].lower().strip()
                value = pair[1].strip()
                if tag and value:
                    headers[tag] = value
        return headers


    def _progress(self, read, size, name):
        res = []
        if size < 0:
            res.append(1)
        else:
            res.append(int(float(read) / (float(size) / 100.0)))
        if name:
            res.append(u'File: ' + name)
        if size != -1:
            res.append(u'Size: ' + self._human(size))
        res.append(u'Load: ' + self._human(read))
        return res

    def _human(self, size):
        human = None
        for h, f in (('KB', 1024), ('MB', 1024 * 1024), ('GB', 1024 * 1024 * 1024), ('TB', 1024 * 1024 * 1024 * 1024)):
            if size / f > 0:
                human = h
                factor = f
            else:
                break
        if human is None:
            return (u'%10.1f %s' % (size, u'byte')).replace(u'.0', u'')
        else:
            return u'%10.2f %s' % (float(size) / float(factor), human)


class HTTPRequest:
    def __init__(self, url, method='GET', headers=None, cookies=None, params=None, upload=None, download=None,
                 progress=False, auth_username=None, auth_password=None, proxy_protocol='http', proxy_host=None,
                 proxy_port=None, proxy_username=None, proxy_password='', timeout=20.0, redirect=True, gzip=False):
        if headers is None:
            headers = {}

        self.url = url
        self.method = method
        self.headers = headers

        self.cookies = cookies

        self.params = params

        self.upload = upload
        self.download = download
        self.progress = progress

        self.auth_username = auth_username
        self.auth_password = auth_password

        self.proxy_protocol = proxy_protocol
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password

        self.timeout = timeout

        self.redirect = redirect

        self.gzip = gzip

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, ','.join('%s=%r' % i for i in self.__dict__.iteritems()))


class HTTPResponse:
    def __init__(self, request):
        self.request = request
        self.code = None
        self.headers = {}
        self.error = None
        self.body = None
        self.filename = None
        self.time = time.time()

    def __repr__(self):
        args = ','.join('%s=%r' % i for i in self.__dict__.iteritems() if i[0] != 'body')
        if self.body:
            args += ',body=<data>'
        else:
            args += ',body=None'
        return '%s(%s)' % (self.__class__.__name__, args)


class UTorrent:
    def config(self, login, password, host, port, url=None):
        self.login = login
        self.password = password

        self.url = 'http://' + host
        if port:
            self.url += ':' + str(port)
        self.url += '/gui/'

        self.http = HTTP()

        self.re = {
            'cookie': re.compile('GUID=([^;]+);'),
            'token': re.compile("<div[^>]+id='token'[^>]*>([^<]+)</div>")
        }

    def listdirs(self):
        obj = self.action('action=list-dirs')
        if not obj:
            return None
        items = []
        clean = []
        for r in obj.get('download-dirs', []):
            available = int(r['available'])
            if available > 1024:
                memory = '[%s GB]' % str(available / 1024)
            else:
                memory = '[%s MB]' % str(available)
            items.append(r['path'] + ' ' + memory)
            path = r['path']
            if path[len(path) - 1:] != '\\': path += '\\'
            clean.append(path)
        return items, clean

    def list(self):
        obj = self.action('list=1')
        if not obj:
            return None

        res = []
        for r in obj.get('torrents', []):
            res.append({
                'id': r[0],
                'status': self.get_status(r[1], r[4] / 10),
                'name': r[2],
                'size': r[3],
                'progress': r[4] / 10,
                'download': r[5],
                'upload': r[6],
                'ratio': float(r[7]) / 1000,
                'upspeed': r[8],
                'downspeed': r[9],
                'eta': r[10],
                'peer': r[12] + r[14],
                'leach': r[12],
                'seed': r[14],
                'add': r[23],
                'finish': r[24],
                'dir': r[26]
            })

        return res

    def listfiles(self, id):
        obj = self.action('action=getfiles&hash=' + id)
        if not obj:
            return None
        res = []
        i = -1

        for x in obj['files'][1]:
            i += 1
            if x[1] >= 1024 * 1024 * 1024:
                size = str(x[1] / (1024 * 1024 * 1024)) + 'GB'
            elif x[1] >= 1024 * 1024:
                size = str(x[1] / (1024 * 1024)) + 'MB'
            elif x[1] >= 1024:
                size = str(x[1] / 1024) + 'KB'
            else:
                size = str(x[1]) + 'B'
            res.append((x[0], (int(x[2] * 100 / x[1])), i, size))
        return res

    def dirid(self, dirname):
        if __settings__.getSetting("torrent_save") == '0':
            dirid = self.listdirs()[1].index(dirname)
        else:
            dirname = __settings__.getSetting("torrent_dir")
            clean = self.listdirs()[1]
            try:
                dirid = clean.index(dirname)
            except:
                dirid = 0
        return dirid

    def add(self, torrent, dirname):
        dirid = self.dirid(dirname)
        res = self.action('action=add-file&download_dir=' + str(dirid),
                          {'name': 'torrent_file', 'download_dir': str(dirid),
                           'content-type': 'application/x-bittorrent', 'body': torrent})
        return True if res else None

    def add_url(self, torrent, dirname):
        dirid = self.dirid(dirname)
        res = self.action('action=add-url&download_dir=' + str(dirid) + '&s=' + urllib.quote(torrent))
        return True if res else None

    def setprio(self, id, ind):
        obj = self.action('action=getfiles&hash=' + id)

        if not obj or ind == None:
            return None

        i = -1
        for x in obj['files'][1]:
            i += 1
            if x[3] == 2: self.setprio_simple(id, '0', i)

        res = self.setprio_simple(id, '3', ind)

        return True if res else None

    def setprio_simple(self, id, prio, ind):
        obj = self.action('action=setprio&hash=%s&p=%s&f=%s' % (id, prio, ind))

        if not obj or ind == None:
            return None

        return True if obj else None

    def delete(self, id):
        pass

    def action(self, uri, upload=None):
        cookie, token = self.get_token()
        if not cookie:
            return None

        req = HTTPRequest(self.url + '?' + uri + '&token=' + token, headers={'Cookie': cookie},
                          auth_username=self.login, auth_password=self.password)
        if upload:
            req.upload = upload

        response = self.http.fetch(req)
        if response.error:
            return None
        else:
            try:
                obj = json.loads(response.body)
            except:
                return None
            else:
                return obj

    def action_simple(self, action, id):
        obj = self.action('action=%s&hash=%s' % (action, id))
        return True if obj else None

    def get_token(self):
        response = self.http.fetch(self.url + 'token.html', auth_username=self.login, auth_password=self.password)
        if response.error:
            return None, None

        r = self.re['cookie'].search(response.headers.get('set-cookie', ''))
        if r:
            cookie = r.group(1).strip()
            r = self.re['token'].search(response.body)
            if r:
                token = r.group(1).strip()
                if cookie and token:
                    return 'GUID=' + cookie, token

        return None, None

    def get_status(self, status, progress):
        mapping = {
            'error': 'stopped',
            'paused': 'stopped',
            'forcepaused': 'stopped',
            'stopped': 'stopped',
            'notloaded': 'check_pending',
            'checked': 'checking',
            'queued': 'download_pending',
            'downloading': 'downloading',
            'forcedownloading': 'downloading',
            'finished': 'seed_pending',
            'queuedseed': 'seed_pending',
            'seeding': 'seeding',
            'forceseeding': 'seeding'
        }
        return mapping[self.get_status_raw(status, progress)]

    def get_status_raw(self, status, progress):
        """
            Return status: notloaded, error, checked,
                           paused, forcepaused,
                           queued,
                           downloading,
                           finished, forcedownloading
                           queuedseed, seeding, forceseeding
        """

        started = bool(status & 1)
        checking = bool(status & 2)
        start_after_check = bool(status & 4)
        checked = bool(status & 8)
        error = bool(status & 16)
        paused = bool(status & 32)
        queued = bool(status & 64)
        loaded = bool(status & 128)

        if not loaded:
            return 'notloaded'

        if error:
            return 'error'

        if checking:
            return 'checked'

        if paused:
            if queued:
                return 'paused'
            else:
                return 'forcepaused'

        if progress == 100:

            if queued:
                if started:
                    return 'seeding'
                else:
                    return 'queuedseed'

            else:
                if started:
                    return 'forceseeding'
                else:
                    return 'finished'
        else:

            if queued:
                if started:
                    return 'downloading'
                else:
                    return 'queued'

            else:
                if started:
                    return 'forcedownloading'

        return 'stopped'


class Transmission:
    def config(self, login, password, host, port, url):
        self.login = login
        self.password = password

        self.url = 'http://' + host
        if port:
            self.url += ':' + str(port)

        if url[0] != '/':
            url = '/' + url
        if url[-1] != '/':
            url += '/'

        self.url += url

        self.http = HTTP()

        self.token = '0'

    def list(self):
        obj = self.action({'method': 'torrent-get', 'arguments': {
        'fields': ['id', 'status', 'name', 'totalSize', 'sizeWhenDone', 'leftUntilDone', 'downloadedEver',
                   'uploadedEver', 'uploadRatio', 'rateUpload', 'rateDownload', 'eta', 'peersConnected', 'peersFrom',
                   'addedDate', 'doneDate', 'downloadDir', 'fileStats', 'peersConnected', 'peersGettingFromUs',
                   'peersSendingToUs']}})
        if obj is None:
            return None

        res = []
        for r in obj['arguments'].get('torrents', []):
            if len(r['fileStats']) > 1:
                res.append({
                    'id': str(r['id']),
                    'status': self.get_status(r['status']),
                    'name': r['name'],
                    'size': r['totalSize'],
                    'progress': 0 if not r['sizeWhenDone'] else int(
                        100.0 * float(r['sizeWhenDone'] - r['leftUntilDone']) / float(r['sizeWhenDone'])),
                    'download': r['downloadedEver'],
                    'upload': r['uploadedEver'],
                    'upspeed': r['rateUpload'],
                    'downspeed': r['rateDownload'],
                    'ratio': float(r['uploadRatio']),
                    'eta': r['eta'],
                    'peer': r['peersConnected'],
                    'seed': r['peersSendingToUs'],
                    'leech': r['peersGettingFromUs'],
                    'add': r['addedDate'],
                    'finish': r['doneDate'],
                    'dir': os.path.join(r['downloadDir'], r['name'])
                })
            else:
                res.append({
                    'id': str(r['id']),
                    'status': self.get_status(r['status']),
                    'name': r['name'],
                    'size': r['totalSize'],
                    'progress': 0 if not r['sizeWhenDone'] else int(
                        100.0 * float(r['sizeWhenDone'] - r['leftUntilDone']) / float(r['sizeWhenDone'])),
                    'download': r['downloadedEver'],
                    'upload': r['uploadedEver'],
                    'upspeed': r['rateUpload'],
                    'downspeed': r['rateDownload'],
                    'ratio': float(r['uploadRatio']),
                    'eta': r['eta'],
                    'peer': r['peersConnected'],
                    'seed': r['peersSendingToUs'],
                    'leech': r['peersGettingFromUs'],
                    'add': r['addedDate'],
                    'finish': r['doneDate'],
                    'dir': r['downloadDir']
                })

        return res

    def listdirs(self):
        obj = self.action({'method': 'session-get'})
        if obj is None:
            return None

        res = [obj['arguments'].get('download-dir')]
        Debug('[Transmission][listdirs]: %s' % (str(res)))
        return res, res

    def listfiles(self, id):
        obj = self.action({"method": "torrent-get", "arguments": {
        "fields": ["id", "activityDate", "corruptEver", "desiredAvailable", "downloadedEver", "fileStats",
                   "haveUnchecked", "haveValid", "peers", "startDate", "trackerStats", "comment", "creator",
                   "dateCreated", "files", "hashString", "isPrivate", "pieceCount", "pieceSize"],
        "ids": [int(id)]}})['arguments']['torrents'][0]
        if obj is None:
            return None

        res = []
        i = -1

        lenf = len(obj['files'])
        for x in obj['files']:
            i += 1
            if x['length'] >= 1024 * 1024 * 1024:
                size = str(x['length'] / (1024 * 1024 * 1024)) + 'GB'
            elif x['length'] >= 1024 * 1024:
                size = str(x['length'] / (1024 * 1024)) + 'MB'
            elif x['length'] >= 1024:
                size = str(x['length'] / 1024) + 'KB'
            else:
                size = str(x['length']) + 'B'
            if lenf > 1:
                x['name'] = x['name'].strip('/\\').replace('\\', '/')
                x['name'] = x['name'].replace(x['name'].split('/')[0] + '/', '')
            res.append([x['name'], (int(x['bytesCompleted'] * 100 / x['length'])), i, size])
        return res

    def add(self, torrent, dirname):
        if self.action({'method': 'torrent-add',
                        'arguments': {'download-dir': dirname, 'metainfo': base64.b64encode(torrent)}}) is None:
            return None
        return True

    def add_url(self, torrent, dirname):
        if self.action({'method': 'torrent-add', 'arguments': {'download-dir': dirname, 'filename': torrent}}) is None:
            return None
        return True

    def delete(self, id):
        pass

    def setprio(self, id, ind):
        obj = self.action({"method": "torrent-get", "arguments": {"fields": ["id", "fileStats", "files"],
                                                                  "ids": [int(id)]}})['arguments']['torrents'][0]
        if not obj or ind == None:
            return None

        inds = []
        i = -1

        for x in obj['fileStats']:
            i += 1
            if x['wanted'] == True and x['priority'] == 0:
                inds.append(i)

        if len(inds) > 1: self.action(
            {"method": "torrent-set", "arguments": {"ids": [int(id)], "priority-high": inds, "files-unwanted": inds}})

        res = self.setprio_simple(id, '3', ind)

        #self.action_simple('start',id)

        return True if res else None

    def setprio_simple(self, id, prio, ind):
        if ind == None:
            return None

        res = None
        inds = [int(ind)]

        if prio == '3':
            res = self.action(
                {"method": "torrent-set", "arguments": {"ids": [int(id)], "priority-high": inds, "files-wanted": inds}})
        elif prio == '0':
            res = self.action({"method": "torrent-set",
                               "arguments": {"ids": [int(id)], "priority-high": inds, "files-unwanted": inds}})

        return True if res else None

    def action(self, request):
        try:
            jsobj = json.dumps(request)
        except:
            return None
        else:

            while True:
                # пробуем сделать запрос
                if self.login:
                    response = self.http.fetch(self.url + 'rpc/', method='POST', params=jsobj,
                                               headers={'X-Transmission-Session-Id': self.token,
                                                        'X-Requested-With': 'XMLHttpRequest',
                                                        'Content-Type': 'charset=UTF-8'}, auth_username=self.login,
                                               auth_password=self.password)
                else:
                    response = self.http.fetch(self.url + 'rpc/', method='POST', params=jsobj,
                                               headers={'X-Transmission-Session-Id': self.token,
                                                        'X-Requested-With': 'XMLHttpRequest',
                                                        'Content-Type': 'charset=UTF-8'})

                if response.error:

                    # требуется авторизация?
                    if response.code == 401:
                        if not self.get_auth():
                            return None

                    # требуется новый токен?
                    elif response.code == 409:
                        if not self.get_token(response.error):
                            return None

                    else:
                        return None

                else:
                    try:
                        obj = json.loads(response.body)
                    except:
                        return None
                    else:
                        return obj

    def action_simple(self, action, id):
        actions = {'start': {"method": "torrent-start", "arguments": {"ids": [int(id)]}},
                   'stop': {"method": "torrent-stop", "arguments": {"ids": [int(id)]}},
                   'remove': {"method": "torrent-remove", "arguments": {"ids": [int(id)], "delete-local-data": False}},
                   'removedata': {"method": "torrent-remove",
                                  "arguments": {"ids": [int(id)], "delete-local-data": True}}}
        obj = self.action(actions[action])
        return True if obj else None

    def get_auth(self):
        response = self.http.fetch(self.url, auth_username=self.login, auth_password=self.password)
        if response.error:
            if response.code == 409:
                return self.get_token(response.error)
        return False

    def get_token(self, error):
        token = error.headers.get('x-transmission-session-id')
        if not token:
            return False
        self.token = token
        return True

    def get_status(self, code):
        mapping = {
            0: 'stopped',
            1: 'check_pending',
            2: 'checking',
            3: 'download_pending',
            4: 'downloading',
            5: 'seed_pending',
            6: 'seeding'
        }
        return mapping[code]


class Download():
    def __init__(self):
        self.handle()

    def handle(self):
        config = self.get_torrent_client()

        if self.client == 'utorrent':
            self.client = UTorrent()

        elif self.client == 'transmission':
            self.client = Transmission()

        self.client.config(host=config['host'], port=config['port'], login=config['login'], password=config['password'],
                           url=config['url'])
        #print(self.client.list())
        return True

    def get_torrent_client(self):
        self.setting = __settings__
        client = self.setting.getSetting("torrent")
        config = {}
        if client == '0':
            self.client = 'utorrent'
            config = {
                'host': self.setting.getSetting("torrent_utorrent_host"),
                'port': self.setting.getSetting("torrent_utorrent_port"),
                'url': '',
                'login': self.setting.getSetting("torrent_utorrent_login"),
                'password': self.setting.getSetting("torrent_utorrent_password")
            }
        elif client == '1':
            self.client = 'transmission'
            config = {
                'host': self.setting.getSetting("torrent_transmission_host"),
                'port': self.setting.getSetting("torrent_transmission_port"),
                'url': self.setting.getSetting("torrent_transmission_url"),
                'login': self.setting.getSetting("torrent_transmission_login"),
                'password': self.setting.getSetting("torrent_transmission_password")
            }

        return config

    def add(self, torrent, dirname):
        return self.client.add(torrent, dirname)

    def add_url(self, torrent, dirname):
        return self.client.add_url(torrent, dirname)

    def list(self):
        return self.client.list()

    def listdirs(self):
        return self.client.listdirs()

    def listfiles(self, id):
        return self.client.listfiles(id)

    def add(self, torrent, dirname):
        return self.client.add(torrent, dirname)

    def delete(self, id):
        return self.client.delete(id)

    def setprio(self, id, ind):
        return self.client.setprio(id, ind)

    def setprio_simple(self, id, prio, ind):
        #Debug('[setprio_simple] '+str((id, prio, ind)))
        return self.client.setprio_simple(id, prio, ind)

    def action_simple(self, action, id):
        return self.client.action_simple(action, id)

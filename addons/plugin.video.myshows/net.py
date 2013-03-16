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
import thread
import tempfile

#try:
#    import libtorrent
#except ImportError:
#    _IS_LIBTORRENT = False
#else:
#    _IS_LIBTORRENT = True



#import libtorrent
_IS_LIBTORRENT = True
import xbmc, xbmcgui, xbmcaddon, xbmcvfs
__settings__ = xbmcaddon.Addon(id='plugin.video.myshows')
RE = {
    'content-disposition': re.compile('attachment;\sfilename="*([^"\s]+)"|\s')
}

# ################################
#
#   HTTP
#
# ################################

class HTTP:
    def __init__(self):
        self._dirname = xbmc.translatePath('special://temp')#.decode('utf-8').encode('cp1251')
        for subdir in ('xbmcup', sys.argv[0].replace('plugin://', '').replace('/', '')):
            self._dirname = os.path.join(self._dirname, subdir)
            if not xbmcvfs.exists(self._dirname):
                xbmcvfs.mkdir(self._dirname)
    
    
    def fetch(self, request, **kwargs):
        self.con, self.fd, self.progress, self.cookies, self.request = None, None, None, None, request
        
        if not isinstance(self.request, HTTPRequest):
            self.request = HTTPRequest(url=self.request, **kwargs)
        
        self.response = HTTPResponse(self.request)
        
        xbmc.log('XBMCup: HTTP: request: ' + str(self.request), xbmc.LOGDEBUG)
        
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
            build.append(urllib2.ProxyHandler({self.request.proxy_protocol: self.request.proxy_host + ':' + str(self.request.proxy_port)}))
            
            if self.request.proxy_username:
                proxy_auth_handler = urllib2.ProxyBasicAuthHandler()
                proxy_auth_handler.add_password('realm', 'uri', self.request.proxy_username, self.request.proxy_password)
                build.append(proxy_auth_handler)
        
        if self.request.cookies:
            self.request.cookies = os.path.join(self._dirname, self.request.cookies)
            self.cookies = cookielib.MozillaCookieJar()
            if os.path.isfile(self.request.cookies):
                self.cookies.load(self.request.cookies)
            build.append(urllib2.HTTPCookieProcessor(self.cookies))
                
        urllib2.install_opener( urllib2.build_opener(*build) )
    
    
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
            req.add_header('Authorization', 'Basic %s' % base64.encodestring(':'.join([self.request.auth_username, self.request.auth_password])).strip())
        
        #self.con = urllib2.urlopen(req, timeout=self.request.timeout)
        self.con = urllib2.urlopen(req)
        self.response.headers = self._headers( self.con.info() )
        
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
        
        bs = 1024*8
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
                res.append([part_boundary, 'Content-Disposition: file; name="%s"; filename="%s"' % (name, urllib.quote(filename)), 'Content-Type: %s' % content_type, '', body])
            else:
                res.append([part_boundary, 'Content-Disposition: file; name="%s"; filename="%s"' % (name, urllib.quote(filename)), '', body])
        
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
            res.append(int( float(read)/(float(size)/100.0) ))
        if name:
            res.append(u'File: ' + name)
        if size != -1:
            res.append(u'Size: ' + self._human(size))
        res.append(u'Load: ' + self._human(read))
        return res
    
    def _human(self, size):
        human = None
        for h, f in (('KB', 1024), ('MB', 1024*1024), ('GB', 1024*1024*1024), ('TB', 1024*1024*1024*1024)):
            if size/f > 0:
                human = h
                factor = f
            else:
                break
        if human is None:
            return (u'%10.1f %s' % (size, u'byte')).replace(u'.0', u'')
        else:
            return u'%10.2f %s' % (float(size)/float(factor), human)

class HTTPRequest:
    def __init__(self, url, method='GET', headers=None, cookies=None, params=None, upload=None, download=None, progress=False, auth_username=None, auth_password=None, proxy_protocol='http', proxy_host=None, proxy_port=None, proxy_username=None, proxy_password='', timeout=20.0, redirect=True, gzip=False):
        
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

    def list(self):
        obj = self.action('list=1')
        if not obj:
            return None

        res = []
        for r in obj.get('torrents', []):
            res.append({
                'id': r[0],
                'status': self.get_status(r[1], r[4]/10),
                'name': r[2],
                'size': r[3],
                'progress': r[4]/10,
                'download': r[5],
                'upload': r[6],
                'ratio': r[7],
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
        obj = self.action('action=getfiles&hash='+id)
        if not obj:
            return None
        res=[]
        i=-1
        for x in obj['files'][1]:
            i+=1
            res.append((x[0],(int(float(x[2])/float(x[1])*100)),i))
        return res

    def add(self, torrent, dirname):
        obj = self.action('action=getsettings')

        if not obj:
            return None

        old_dir = None
        setting = [x[2] for x in obj['settings'] if x[0] == 'dir_active_download']
        if setting:
            old_dir = setting[0]

        if isinstance(dirname, unicode):
            dirname = dirname.encode('windows-1251')

        obj = self.action('action=setsetting&s=dir_active_download_flag&v=true&s=dir_active_download&v=' + urllib.quote(dirname, ''))
        if not obj:
            return None

        res = self.action('action=add-file', {'name': 'torrent_file', 'content-type': 'application/x-bittorrent', 'body': torrent})

        if old_dir:
            self.action('action=setsetting&s=dir_active_download&v=' + urllib.quote(old_dir.encode('windows-1251'), ''))

        return True if res else None

    def add_url(self, torrent, dirname):
        obj = self.action('action=getsettings')
        if not obj:
            return None

        old_dir = None
        setting = [x[2] for x in obj['settings'] if x[0] == 'dir_active_download']

        if setting:
            old_dir = setting[0]

        if isinstance(dirname, unicode):
            dirname = dirname.encode('windows-1251')

        obj = self.action('action=setsetting&s=dir_active_download_flag&v=true&s=dir_active_download&v=' + urllib.quote(dirname, ''))
        if not obj:
            return None

        #obj = self.action('action=getsettings')
        #setting = [x[2] for x in obj['settings'] if x[0] == 'dir_active_download']
        #print str(setting)

        res = self.action('action=add-url&s='+urllib.quote(torrent))

        if old_dir:
            self.action('action=setsetting&s=dir_active_download&v=' + urllib.quote(old_dir.encode('windows-1251'), ''))

        return True if res else None

    def setprio(self, id, ind):
        obj = self.action('action=getfiles&hash='+id)

        if not obj or ind==None:
            return None

        i=-1
        for x in obj['files'][1]:
            i+=1
            if x[3]==2: self.action('action=setprio&hash=%s&p=%s&f=%s' %(id, '0', i))

        res=self.action('action=setprio&hash=%s&p=%s&f=%s' %(id, '3', ind))

        return True if res else None

    def delete(self, id):
        pass

    def action(self, uri, upload=None):
        cookie, token = self.get_token()
        if not cookie:
            return None

        req = HTTPRequest(self.url + '?' + uri + '&token=' + token, headers={'Cookie': cookie}, auth_username=self.login, auth_password=self.password)
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
            'error':            'stopped',
            'paused':           'stopped',
            'forcepaused':      'stopped',
            'stopped':          'stopped',
            'notloaded':        'check_pending',
            'checked':          'checking',
            'queued':           'download_pending',
            'downloading':      'downloading',
            'forcedownloading': 'downloading',
            'finished':         'seed_pending',
            'queuedseed':       'seed_pending',
            'seeding':          'seeding',
            'forceseeding':     'seeding'
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


        started = bool( status & 1 )
        checking = bool( status & 2 )
        start_after_check = bool( status & 4 )
        checked = bool( status & 8 )
        error = bool( status & 16 )
        paused = bool( status & 32 )
        queued = bool( status & 64 )
        loaded = bool( status & 128 )

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

class Download(UTorrent):
    def __init__(self):
        self.handle()

    def handle(self):
        config = self.get_torrent_client()
        self.config(host=config['host'], port=config['port'], login=config['login'], password=config['password'], url=config['url'])
        #print(client.list())
        return True

    def get_torrent_client(self):
        self.setting=__settings__
        config = {
            'host': self.setting.getSetting("torrent_utorrent_host"),
            'port': self.setting.getSetting("torrent_utorrent_port"),
            'url': '',
            'login': self.setting.getSetting("torrent_utorrent_login"),
            'password': self.setting.getSetting("torrent_utorrent_password")
        }

        return config




# ################################
#
#   LIBTORRENT
#
# ################################
"""
class LibTorrent:
    def __init__(self):
        self.is_install = _IS_LIBTORRENT
    
    
    def list(self, torrent, reverse=False):
        files = [{'id': i, 'name': x.path.split(os.sep)[-1], 'size': x.size} for i, x in enumerate(self._torrent_info(torrent).files())]
        files.sort(cmp=lambda f1, f2: cmp(f1['name'], f2['name']))
        if reverse:
            files.reverse()
        return files
        
    
    def play(self, torrent, file_id, dirname, seed=None, info=None, notice=False, buffer=45):
        torrent_info = self._torrent_info(torrent)
        
        # length
        selfile = torrent_info.files()[file_id]
        self._filename = os.path.join(dirname, selfile.path.decode('utf8'))
        self._fname = self._filename.split(os.sep.decode('utf8'))[-1].encode('utf8')
        offset = (buffer+5)*1024*1024 / torrent_info.piece_length()
        start = selfile.offset / torrent_info.piece_length()
        end = (selfile.offset + selfile.size) / torrent_info.piece_length()
        buffer = buffer*1024*1024
        
        # start session
        self._session = libtorrent.session()
        
        # start DHT
        self._session.start_dht()
        self._session.add_dht_router('router.bittorrent.com', 6881)
        self._session.add_dht_router('router.utorrent.com', 6881)
        self._session.add_dht_router('router.bitcomet.com', 6881)
        self._session.listen_on(6881, 6891)
        
        # events
        self._session.set_alert_mask(libtorrent.alert.category_t.storage_notification)
        
        # add torrent
        if seed is not None:
            if seed:
                self._session.set_upload_rate_limit(seed)
            #self._handle = self._session.add_torrent({'ti': torrent_info, 'save_path': dirname.encode('utf8'), 'paused': False, 'auto_managed': False, 'seed_mode': True})
            self._handle = self._session.add_torrent({'ti': torrent_info, 'save_path': dirname.encode('utf8')})
        else:
            self._handle = self._session.add_torrent({'ti': torrent_info, 'save_path': dirname.encode('utf8')})
        
        # low priority
        for i in range(torrent_info.num_pieces()):
            self._handle.piece_priority(i, 0)
        
        # high priority
        for i in range(start, start + offset):
            if i <= end:
                self._handle.piece_priority(i, 7)
        
        # sequential
        self._handle.set_sequential_download(True)
        
        self._stop = False
        self._complete = False
        
        thread.start_new_thread(self._download, (start, end))
        
        percent = 0
        size = 0
        firstsize = selfile.size if selfile.size < buffer else buffer
        persize = firstsize/100
        
        progress = xbmcgui.DialogProgress()
        progress.create(u'Please Wait')
        progress.update(0, self._fname, u'Size: ' + self._human(firstsize) + u' / ' + self._human(selfile.size).strip(), u'Load: ' + self._human(0))
        
        while percent < 100:
            time.sleep(1)
            size = self._handle.file_progress()[file_id]
            percent = int(size/persize)
            progress.update(percent, self._fname, u'Size: ' + self._human(firstsize) + u' / ' + self._human(selfile.size).strip(), u'Load: ' + self._human(size))
            if progress.iscanceled():
                progress.close()
                return self._end()
        progress.close()
        
        if info:
            info['size'] = selfile.size
            xbmc.Player().play(self._filename.encode('utf8'), info)
        else:
            xbmc.Player().play(self._filename.encode('utf8'))
        
        while xbmc.Player().isPlaying():
            if not self._complete:
                priorities = self._handle.piece_priorities()
                status = self._handle.status()
                download = 0
                
                if len(status.pieces):
                    
                    for i in range(start, end + 1):
                        if priorities[i] != 0 and not status.pieces[i]:
                            download += 1
                            
                    for i in range(start, end + 1):
                        if priorities[i] == 0 and download < offset:
                            self._handle.piece_priority(i, 1)
                            download += 1
                    
                    for i in range(start, end + 1):
                        if not status.pieces[i]:
                            break
                    else:
                        self._complete = True
                        
                        if notice:
                            if not isinstance(notice, basestring):
                                notice = xbmcaddon.Addon(id=sys.argv[0].replace('plugin://', '').replace('/', '')).getAddonInfo('icon')
                            if notice:
                                xbmc.executebuiltin('XBMC.Notification("%s", "%s", %s, "%s")' % ('Download complete', self._fname, 5000, notice))
                            else:
                                xbmc.executebuiltin('XBMC.Notification("%s", "%s", %s)' % ('Download complete', self._fname, 5000))
            
            time.sleep(1)
        
        return self._end()
    
    
    def _end(self):
        self._stop = True
        
        try:
            self._session.remove_torrent(self._handle)
        except:
            pass
        
        return self._filename if self._complete else None
        
        
    def _download(self, start, end):
        cache = {}
        
        for i in range(start, end + 1):
            
            if i in cache:
                del cache[i]
                continue
            
            while True:
                status = self._handle.status()
                if not status.pieces or status.pieces[i]:
                    break
                time.sleep(0.5)
                if self._stop:
                    return
                
            self._handle.read_piece(i)
            
            while True:
                part = self._session.pop_alert()
                if isinstance(part, libtorrent.read_piece_alert):
                    if part.piece == i:
                        break
                    else:
                        cache[part.piece] = part.buffer
                    break
                time.sleep(0.5)
                if self._stop:
                    return
            
            time.sleep(0.1)
            if self._stop:
                return
    
    
    def _torrent_info(self, torrent):
        filename = os.tempnam()
        file(filename, 'wb').write(torrent)
        torrent_info = libtorrent.torrent_info(filename)
        os.unlink(filename)
        return torrent_info
    
    def _human(self, size):
        human = None
        for h, f in (('KB', 1024), ('MB', 1024*1024), ('GB', 1024*1024*1024), ('TB', 1024*1024*1024*1024)):
            if size/f > 0:
                human = h
                factor = f
            else:
                break
        if human is None:
            return (u'%10.1f %s' % (size, u'byte')).replace(u'.0', u'')
        else:
            return u'%10.2f %s' % (float(size)/float(factor), human)
    

    """
#!/usr/bin/python
# -*- coding: utf-8 -*-
#/*
# *      Copyright (C) 2011 Silen
# *
# *
# *  This Program is free software; you can redistribute it and/or modify
# *  it under the terms of the GNU General Public License as published by
# *  the Free Software Foundation; either version 2, or (at your option)
# *  any later version.
# *
# *  This Program is distributed in the hope that it will be useful,
# *  but WITHOUT ANY WARRANTY; without even the implied warranty of
# *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# *  GNU General Public License for more details.
# *
# *  You should have received a copy of the GNU General Public License
# *  along with this program; see the file COPYING.  If not, write to
# *  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *  http://www.gnu.org/copyleft/gpl.html
# */
import re, os, urllib, urllib2, cookielib, time
from time import gmtime, strftime
import urlparse

import demjson3 as json

import xbmc, xbmcgui, xbmcplugin, xbmcaddon

Addon = xbmcaddon.Addon(id='plugin.video.nowfilms.ru')
icon = xbmc.translatePath(os.path.join(Addon.getAddonInfo('path'),'icon.png'))
fcookies = xbmc.translatePath(os.path.join(Addon.getAddonInfo('path'), r'resources', r'data', r'cookies.txt'))

# load XML library
try:
    sys.path.append(os.path.join(Addon.getAddonInfo('path'), r'resources', r'lib'))
    from BeautifulSoup  import BeautifulSoup
except:
    try:
        sys.path.insert(0, os.path.join(Addon.getAddonInfo('path'), r'resources', r'lib'))
        from BeautifulSoup  import BeautifulSoup
    except:
        sys.path.append(os.path.join(os.getcwd(), r'resources', r'lib'))
        from BeautifulSoup  import BeautifulSoup
        icon = xbmc.translatePath(os.path.join(os.getcwd().replace(';', ''),'icon.png'))

import HTMLParser
hpar = HTMLParser.HTMLParser()

h = int(sys.argv[1])

def showMessage(heading, message, times = 3000):
    xbmc.executebuiltin('XBMC.Notification("%s", "%s", %s, "%s")'%(heading, message, times, icon))

#---------- parameter/info structure -------------------------------------------
class Param:
    page        = '1'
    genre       = ''
    genre_name  = ''
    genre_flag  = 0
    max_page    = 0
    count       = 0
    url         = ''
    pl          = ''
    search      = ''

class Info:
    img         = ''
    url         = '*'
    title       = ''
    year        = ''
    genre       = ''
    country     = ''
    director    = ''
    text        = ''
    artist      = ''
    orig        = ''
    duration    = ''
    rating      = ''

#---------- get web page -------------------------------------------------------
def get_HTML(url, post = None, ref = None):
    request = urllib2.Request(url, post)

    try:
        host = urlparse.urlsplit(url).hostname
        if host==None:
            host = url.replace('http://', '').split('/')[0]
            if host==None:
                host = 'nowfilms.ru'
    except:
        host = 'nowfilms.ru'

    if ref==None:
        ref='http://'+host

    request.add_header('User-Agent', 'Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 5.1; Trident/4.0; Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1) ; .NET CLR 1.1.4322; .NET CLR 2.0.50727; .NET CLR 3.0.4506.2152; .NET CLR 3.5.30729; .NET4.0C)')
    request.add_header('Host',   host)
    request.add_header('Accept', '*/*')
    request.add_header('Accept-Language', 'ru-RU')
    request.add_header('Referer',             ref)

    try:
        f = urllib2.urlopen(request)
    except IOError, e:
        if hasattr(e, 'reason'):
           xbmc.log('We failed to reach a server.')
        elif hasattr(e, 'code'):
           xbmc.log('The server couldn\'t fulfill the request.')

    html = f.read()

    return html

#---------- get parameters -----------------------------------------------------
def Get_Parameters(params):
    #-- page
    try:    p.page = urllib.unquote_plus(params['page'])
    except: p.page = '1'
    #-- genre
    try:    p.genre = urllib.unquote_plus(params['genre'])
    except: p.genre = ''
    try:    p.genre_flag = int(urllib.unquote_plus(params['genre_flag']))
    except: p.genre_flag = 0
    # movie count
    try:    p.max_page = int(urllib.unquote_plus(params['max_page']))
    except: p.max_page = 0
    # movie count
    try:    p.count = int(urllib.unquote_plus(params['count']))
    except: p.count = 0
    #-- url
    try:    p.url = urllib.unquote_plus(params['url'])
    except: p.url = ''
    #-- pl
    try:    p.pl = urllib.unquote_plus(params['pl'])
    except: p.pl = ''
    #-- search
    try:    p.search = urllib.unquote_plus(params['search'])
    except: p.search = ''

    #-----
    return p

# ----- search on site --------------------------------------------------------
def get_Search_HTML(search_str):
    print search_str
    url = 'http://nowfilms.ru/index.php?do=search'
    str = search_str.decode('utf-8').encode('windows-1251')

    values = {
            'beforeafter'	    : 'after',
            'catlist[]'         : 0,
            'do'	            : 'search',
            'full_search'	    : 1,
            'replyless'	        : 0,
            'replylimit'	    : 0,
            'resorder'	        : 'asc',
            'result_from'	    : 1,
            'result_num'	    : 1000,
            'search_start'	    : 1,
            'searchdate'	    : 0,
            'searchuser'        : '',
            'showposts'	        : 0,
            'sortby'	        : 'title',
            'story'	            : str,
            'subaction'	        : 'search',
            'titleonly'	        : 3
        }

    post = urllib.urlencode(values)

    html = get_HTML(url, post)

    return html

#---------- get HD720.RU URL --------------------------------------------------
def Get_URL(par):
    url = par.url+'page/'+par.page+'/'

    return url

#----------- get page count & number of movies ---------------------------------
def Get_Page_and_Movies_Count(par):
    url = par.url
    html = get_HTML(url)
    # -- parsing web page ------------------------------------------------------
    soup = BeautifulSoup(html, fromEncoding="windows-1251")
    try:
        max_page = 0
        for rec in soup.find("div", {"class":"navigation"}).findAll('a'):
            try:
                if max_page < int(rec.text):
                    max_page = int(rec.text)
            except:
                pass

        if len(soup.find("div", {"class":"header_submenu"}).findAll('a')) > 0:
            par.genre_flag = 1
        #-- #2 -------------------------------------------------------------------------
        url += '/page/%i/'%max_page
        html = get_HTML(url)

        # -- parsing web page ------------------------------------------------------
        soup = BeautifulSoup(html, fromEncoding="windows-1251")
        count = 25*(max_page-1)+len(soup.findAll("td", {"class":"short"}))
    except:
        max_page = 1
        count = len(soup.findAll("td", {"class":"short"}))

    return max_page, count


#----------- get Header string -------------------------------------------------
def Get_Header(par):

    info  = 'Фильмов: ' + '[COLOR FF00FF00]' + str(par.count) + '[/COLOR]'

    if par.max_page > 1:
        info += ' | Pages: ' + '[COLOR FF00FF00]'+ par.page + '/' + str(par.max_page) +'[/COLOR]'

    if par.genre <> '':
        info += ' | Жанр: ' + '[COLOR FFFFFF00]'+ par.genre + '[/COLOR]'

    #-- info line
    name    = info
    i = xbmcgui.ListItem(name, iconImage=icon, thumbnailImage=icon)
    u = sys.argv[0] + '?mode=EMPTY'
    u += '&name=%s'%urllib.quote_plus(name)
    #-- filter parameters
    u += '&page=%s'%urllib.quote_plus(par.page)
    u += '&genre=%s'%urllib.quote_plus(par.genre)
    u += '&max_page=%s'%urllib.quote_plus(str(par.max_page))
    u += '&count=%s'%urllib.quote_plus(str(par.count))
    xbmcplugin.addDirectoryItem(h, u, i, True)

    #-- genres
    if par.genre == '' and par.genre_flag == 1 and par.page == '1':
        name    = '[COLOR FFFFFF00][Жанры][/COLOR]'
        i = xbmcgui.ListItem(name, iconImage=icon, thumbnailImage=icon)
        u = sys.argv[0] + '?mode=GENRES'
        u += '&name=%s'%urllib.quote_plus(name)
        #-- filter parameters
        u += '&url=%s'%urllib.quote_plus(par.url)
        xbmcplugin.addDirectoryItem(h, u, i, True)

    #-- previous page
    if int(par.page) > 1 :
        name    = '[COLOR FF00FF00][PAGE -1][/COLOR]'
        i = xbmcgui.ListItem(name, iconImage=icon, thumbnailImage=icon)
        u = sys.argv[0] + '?mode=MOVIE'
        u += '&name=%s'%urllib.quote_plus(name)
        #-- filter parameters
        u += '&page=%s'%urllib.quote_plus(str(int(par.page)-1))
        u += '&url=%s'%urllib.quote_plus(str(par.url))
        u += '&genre=%s'%urllib.quote_plus(par.genre)
        xbmcplugin.addDirectoryItem(h, u, i, True)

    #-- previous page
    if int(par.page) >= 10 :
        name    = '[COLOR FF00FF00][PAGE -10][/COLOR]'
        i = xbmcgui.ListItem(name, iconImage=icon, thumbnailImage=icon)
        u = sys.argv[0] + '?mode=MOVIE'
        u += '&name=%s'%urllib.quote_plus(name)
        #-- filter parameters
        u += '&page=%s'%urllib.quote_plus(str(int(par.page)-10))
        u += '&url=%s'%urllib.quote_plus(str(par.url))
        u += '&genre=%s'%urllib.quote_plus(par.genre)
        xbmcplugin.addDirectoryItem(h, u, i, True)

def Empty():
    return False

#---------- movie list ---------------------------------------------------------
def Movie_List(params):
        #-- get filter parameters
        par = Get_Parameters(params)

        # show search dialog
        if par.search == 'Y':
            skbd = xbmc.Keyboard()
            skbd.setHeading('Поиск сериалов.')
            skbd.doModal()
            if skbd.isConfirmed():
                SearchStr = skbd.getText().split(':')
                url = 'http://allserials.tv/search/node/'+urllib.quote(SearchStr[0])
                par.search = SearchStr[0]
            else:
                return False
            #-- get and parce result
            html = get_Search_HTML(par.search)
            soup = BeautifulSoup(html, fromEncoding="windows-1251")

            for rec in soup.findAll('div', {'class':'full'}):
                if rec.find('div', {'class':'full2'}).find('a'):
                    mi.url = rec.find('div', {'class':'full2'}).find('a')['href']
                    print mi.url
                    if '/music/' in mi.url or '/play/' in mi.url or '/soft/' in mi.url:
                        continue

                    mi.title = rec.find('div', {'class':'full2'}).find('a').text.encode('utf-8')
                    mi.img = rec.find('div', {'class':'full5 full6'}).find('img')['src']
                    if mi.img[:4] <> 'http':
                        mi.img = 'http://nowfilms.ru'+mi.img
                    #-- paint title ---
                    try:
                        m = min(mi.title.index('/'), mi.title.index('('))
                    except:
                        try:
                            m = mi.title.index('/')
                        except:
                            try:
                                m = mi.title.index('(')
                            except:
                                m = len(mi.title)

                    title = '[COLOR FF00FFFF]'+mi.title[0:m]+'[/COLOR]'+mi.title[m:]
                    i = xbmcgui.ListItem(title, iconImage=mi.img, thumbnailImage=mi.img)
                    u = sys.argv[0] + '?mode=SOURCE'
                    u += '&name=%s'%urllib.quote_plus(mi.title)
                    u += '&url=%s'%urllib.quote_plus(mi.url)
                    u += '&img=%s'%urllib.quote_plus(mi.img)
                    xbmcplugin.addDirectoryItem(h, u, i, True)

        else:
            # -- get total number of movies and pages if not provided
            if par.count == 0:
                (par.max_page, par.count) = Get_Page_and_Movies_Count(par)

            # -- add header info
            Get_Header(par)

            #== get movie list =====================================================
            url = Get_URL(par)
            html = get_HTML(url)

            # -- parsing web page --------------------------------------------------
            soup = BeautifulSoup(html, fromEncoding="windows-1251")

            # -- get movie info
            for rec in soup.findAll("td", {"class":"short"}):
                #try:
                mi.url      = rec.find('div', {'class':'racun2'}).find('a')['href']
                mi.img      = 'http://nowfilms.ru'+rec.find('div', {'class':'racun2'}).find('img')['src']

                mi.title    = rec.find('div', {'class':'short2'}).find('a').text.encode('utf-8')
                #-- paint title ---
                try:
                    m = min(mi.title.index('/'), mi.title.index('('))
                except:
                    try:
                        m = mi.title.index('/')
                    except:
                        try:
                            m = mi.title.index('(')
                        except:
                            m = len(mi.title)

                title = '[COLOR FF00FFFF]'+mi.title[0:m]+'[/COLOR]'+mi.title[m:]

                mi.genre = ''
                for g in rec.find('div', {'class':'short1'}).findAll('a'):
                    try:
                        mi.year = int(g.text)
                    except:
                        if mi.genre <> '':
                            mi.genre += ', '
                        mi.genre += g.text.replace('_','').encode('utf-8')

                i = xbmcgui.ListItem(title, iconImage=mi.img, thumbnailImage=mi.img)
                u = sys.argv[0] + '?mode=SOURCE'
                u += '&name=%s'%urllib.quote_plus(mi.title)
                u += '&url=%s'%urllib.quote_plus(mi.url)
                u += '&img=%s'%urllib.quote_plus(mi.img)
                i.setInfo(type='video', infoLabels={ 'title':      mi.title,
                            						'genre':       mi.genre})
                #i.setProperty('fanart_image', mi.img)
                xbmcplugin.addDirectoryItem(h, u, i, True)
                #except:
                    #pass
            #-- next page link
            if int(par.page) < par.max_page :
                name    = '[COLOR FF00FF00][PAGE +1][/COLOR]'
                i = xbmcgui.ListItem(name, iconImage=icon, thumbnailImage=icon)
                u = sys.argv[0] + '?mode=MOVIE'
                u += '&name=%s'%urllib.quote_plus(name)
                #-- filter parameters
                u += '&page=%s'%urllib.quote_plus(str(int(par.page)+1))
                u += '&url=%s'%urllib.quote_plus(par.url)
                u += '&genre=%s'%urllib.quote_plus(par.genre)
                xbmcplugin.addDirectoryItem(h, u, i, True)


            if int(par.page)+10 <= par.max_page :
                name    = '[COLOR FF00FF00][PAGE +10][/COLOR]'
                i = xbmcgui.ListItem(name, iconImage=icon, thumbnailImage=icon)
                u = sys.argv[0] + '?mode=MOVIE'
                u += '&name=%s'%urllib.quote_plus(name)
                #-- filter parameters
                u += '&page=%s'%urllib.quote_plus(str(int(par.page)+10))
                u += '&url=%s'%urllib.quote_plus(str(par.url))
                u += '&genre=%s'%urllib.quote_plus(par.genre)
                xbmcplugin.addDirectoryItem(h, u, i, True)
            #xbmc.log("** "+str(pcount)+"  :  "+str(mcount))

        xbmcplugin.endOfDirectory(h)

#---------- source list ---------------------------------------------------------
def Source_List(params):
    url  = urllib.unquote_plus(params['url'])
    img  = urllib.unquote_plus(params['img'])
    name = urllib.unquote_plus(params['name'])

    #== get movie list =====================================================
    list = Get_PlayList(url, name)

    if len(list) == 1:
        url = '*'

    for rec in list:
        i = xbmcgui.ListItem(rec['name'], iconImage=img, thumbnailImage=img)
        u = sys.argv[0] + '?mode=PLAY'
        u += '&name=%s'%urllib.quote_plus(name)
        u += '&url=%s'%urllib.quote_plus(rec['url'])
        u += '&img=%s'%urllib.quote_plus(img)
        u += '&pl=%s'%urllib.quote_plus(url)
        if url <> '*':
            u += '&sel=%s'%urllib.quote_plus(rec['name'].encode('utf-8'))
        #i.setProperty('fanart_image', img)
        xbmcplugin.addDirectoryItem(h, u, i, False)

    xbmcplugin.endOfDirectory(h)

def Get_PlayList(url, name):
	print url

	html = get_HTML(url)

	list = []
	# -- parsing web page --------------------------------------------------
	soup = BeautifulSoup(html, fromEncoding="windows-1251")
	#xbmc.log('[NOWFILMS.RU html=]'+str(soup))
	# -- get movie info
	allResults = soup.findAll('param', attrs={'name': 'flashvars'})

	#xbmc.log('[NOWFILMS.RU] found links =%s' %allResults)
	for res in allResults:
		video = ''
		#xbmc.log('[NOWFILMS.RU] processing result=%s' %res)
		for rec in res['value'].split('&'):
			#xbmc.log('[NOWFILMS.RU] processing rec=%s' %rec)
			if rec.split('=',2)[0] == 'pl':
				video = rec.split('=',1)[1]
			if rec.split('=',2)[0] == 'file':
				video = rec.split('=',1)[1]
			#if rec.split('=',1)[0] == 'st':
				#video = rec.split('=',1)[1]
		if video <> '':
			if video[-3:] == 'txt':
				html = get_HTML(video)
				html = html.replace('\n', '')
				if html[0] <> '[' and html[-1] == ']':
					html = html[:-1]
				pl = json.loads(html.decode('utf-8'))

				for rec in pl['playlist']:
					try:
						for rec1 in rec['playlist']:
							list.append({'name': rec['comment'].replace('<b>','').replace('</b>','')+' - '+rec1['comment'], 'url': rec1['file']})
					except:
						list.append({'name': rec['comment'], 'url': rec['file']})
			else:
				list.append({'name': name, 'url': video})

	return list

#---------- get genge list -----------------------------------------------------
def Genre_List(params):
    #-- get filter parameters
    par = Get_Parameters(params)

    #-- get generes
    url = par.url
    html = get_HTML(url)

    # -- parsing web page ------------------------------------------------------
    soup = BeautifulSoup(html, fromEncoding="windows-1251")

    for rec in soup.find("div", {"class":"header_submenu"}).findAll('a'):
        if rec.text == u'Фильмы онлайн':
            break
        url      = rec['href']
        if url[0]=='/':
            url = 'http://nowfilms.ru'+url

        name     = rec.text.encode('utf-8')

        i = xbmcgui.ListItem(name, iconImage=icon, thumbnailImage=icon)
        u = sys.argv[0] + '?mode=MOVIE'
        u += '&name=%s'%urllib.quote_plus(name)
        #-- filter parameters
        u += '&page=%s'%urllib.quote_plus('1')
        u += '&genre=%s'%urllib.quote_plus(name)
        u += '&url=%s'%urllib.quote_plus(url)
        xbmcplugin.addDirectoryItem(h, u, i, True)

    xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.endOfDirectory(h)

#---------- get type list -----------------------------------------------------
def Type_List(params):
    #-- get filter parameters
    par = Get_Parameters(params)

    #-- get generes
    url = 'http://nowfilms.ru'
    html = get_HTML(url)

    # -- search ----------------------------------------------------------------
    name    = '[COLOR FF00FFF0]' + '[ПОИСК]' + '[/COLOR]'
    i = xbmcgui.ListItem(name, iconImage=icon, thumbnailImage=icon)
    u = sys.argv[0] + '?mode=MOVIE'
    #-- filter parameters
    u += '&search=%s'%urllib.quote_plus('Y')
    xbmcplugin.addDirectoryItem(h, u, i, True)

    # -- parsing web page ------------------------------------------------------
    soup = BeautifulSoup(html, fromEncoding="windows-1251")

    for rec in soup.find("div", {"class":"header_menu"}).findAll('a', {"href":re.compile("/films|/dokumentalnyy|/multfilm|/anime|/serial")}):
        if rec.text <> u'Видео':
            name = rec.text.encode('utf-8')
            url  = rec['href']

            i = xbmcgui.ListItem('[COLOR FFFFCC33]'+name+'[/COLOR]', iconImage=icon, thumbnailImage=icon)
            u = sys.argv[0] + '?mode=MOVIE'
            u += '&name=%s'%urllib.quote_plus(name)
            #-- filter parameters
            u += '&page=%s'%urllib.quote_plus('1')
            u += '&url=%s'%urllib.quote_plus(url)
            xbmcplugin.addDirectoryItem(h, u, i, True)

    xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.endOfDirectory(h)


#-------------------------------------------------------------------------------

def PLAY(params):
    # -- parameters
    url     = urllib.unquote_plus(params['url'])
    img     = urllib.unquote_plus(params['img'])
    name    = urllib.unquote_plus(params['name'])
    plurl   = urllib.unquote_plus(params['pl'])

    if plurl == '*':
        # -- play video
        i = xbmcgui.ListItem(name, path = urllib.unquote(url), thumbnailImage=img)
        xbmc.Player().play(url, i)
    else:
        sel     = urllib.unquote_plus(params['sel'])
        pl=xbmc.PlayList(1)
        pl.clear()
        flag = 0

        list = Get_PlayList(plurl, name)

        for rec in list:
            if rec['name'].encode('utf-8') == sel:
                flag = 1

            if flag == 1:
                i = xbmcgui.ListItem(rec['name'], path = urllib.unquote(rec['url']), thumbnailImage=img)
                i.setProperty('IsPlayable', 'true')
                pl.add(rec['url'], i)

        xbmc.Player().play(pl)

#-------------------------------------------------------------------------------

def unescape(text):
    try:
        text = hpar.unescape(text)
    except:
        text = hpar.unescape(text.decode('utf8'))

    try:
        text = unicode(text, 'utf-8')
    except:
        text = text

    return text

def get_url(url):
    return "http:"+urllib.quote(url.replace('http:', ''))

#-------------------------------------------------------------------------------
def get_params(paramstring):
	param=[]
	if len(paramstring)>=2:
		params=paramstring
		cleanedparams=params.replace('?','')
		if (params[len(params)-1]=='/'):
			params=params[0:len(params)-2]
		pairsofparams=cleanedparams.split('&')
		param={}
		for i in range(len(pairsofparams)):
			splitparams={}
			splitparams=pairsofparams[i].split('=')
			if (len(splitparams))==2:
				param[splitparams[0]]=splitparams[1]
	return param
#-------------------------------------------------------------------------------
params=get_params(sys.argv[2])

# get cookies from last session
cj = cookielib.MozillaCookieJar(fcookies)
hr  = urllib2.HTTPCookieProcessor(cj)
opener = urllib2.build_opener(hr)
urllib2.install_opener(opener)

p  = Param()
mi = Info()

mode = None

try:
	mode = urllib.unquote_plus(params['mode'])
except:
	Type_List(params)

if mode == 'MOVIE':
	Movie_List(params)
if mode == 'SOURCE':
	Source_List(params)
elif mode == 'GENRES':
    Genre_List(params)
elif mode == 'EMPTY':
    Empty()
elif mode == 'PLAY':
	PLAY(params)



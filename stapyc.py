#!/bin/env python3

from urllib.request import urlopen
from urllib.parse import urlparse
from urllib.error import HTTPError
from bs4 import BeautifulSoup
import datetime
import os
import re
import logging
import configparser
# import string
conf = configparser.ConfigParser()
CONF_FILE = "stapyc.ini"

TEXT_CHARACTERS = "".join(list(map(chr, range(32, 127))) + list("\n\r\t\b"))


def make_dirs(f_path):
    f_name, f_ext = os.path.splitext(f_path)
    if not f_ext:
        f_path = f_path + "/index.html"
    os.makedirs(os.path.dirname(f_path), exist_ok=True)
    return f_path


def get_page(url):
    print("GET {}".format(url))
    try:
        content = urlopen(url).read()
        content.decode()
        return BeautifulSoup(content, "html.parser")
    except UnicodeDecodeError:
        parts = urlparse(url)
        f_path = "{}/{}/{}".format(conf[domain]["dest_dir"], parts.hostname, parts.path)
        f_path = make_dirs(f_path)
        with open(f_path, "wb") as f:
            f.write(content)
    except UnicodeEncodeError:
        print("Error : unable to get {}".format(url))

        return None

def write_local_page(soup, url):
    parts = urlparse(url)
    url_path = parts.path if parts.path else "index.html"
    f_path = "{}/{}/{}".format(conf[domain]["dest_dir"], parts.hostname, url_path)
    f_path = make_dirs(f_path)
    with open(f_path, "w", encoding='utf-8') as f:
        f.write(str(soup))
    return parts.path

def clean_page(domain, soup):
    for ci in conf[domain]["clean_ids"].split(" "):
        for e in soup.findAll(id=ci):
            e.decompose()
    for cc in conf[domain]["clean_class"].split(" "):
        for e in soup.findAll(class_=cc):
            e.decompose()

def get_css_parts(domain, css):
    css = css.decode()
    for l in re.findall(r'url\(([(..)/].*?)\)', css):
        src = "http://{}/{}".format(domain, l)
        url = l.split("?")[0]
        f_path = "{}/{}/{}/{}".format(conf[domain]["dest_dir"], domain, conf[domain]["static_path"], url)
        f_path = make_dirs(f_path)
        with open(f_path, "wb") as f:
            f.write(urlopen(src).read())
        css = css.replace("url({})".format(l), "url(/{}/{})".format(conf[domain]["static_path"], url))
        print("STATIC INC {}".format(src))
    return css.encode()


def get_statics(domain, soup):
    for el in soup.findAll('img') + soup.findAll('link') + soup.findAll('script'):
        attr = 'src' if el.get('src') else "href"
        src = el.get(attr)
        if src:
            parts = urlparse(src)
            # Add hostname if needed
            if not parts.hostname:
                src = "http://{}/{}".format(domain, src)

            f_path = "{}/{}/{}/{}".format(conf[domain]["dest_dir"], domain, conf[domain]["static_path"], parts.path)
            el[attr] = "/{}/{}".format(conf[domain]["static_path"], parts.path)
            if os.path.exists(f_path):
                continue
            print("STATIC {}".format(src))
            f_path = make_dirs(f_path)
            try:
                content = urlopen(src).read()
                if os.path.splitext(f_path)[1] == ".css":
                    content = get_css_parts(domain, content)
                if content:
                    with open(f_path, "wb") as f:
                        f.write(content)
            except Exception:
                pass

def is_downloadable_link(domain, href):
    if not href or href.startswith("#"):
        return None

    href = href.split("#")[0]

    if href[:5] not in ("http:", 'https'):
        return href
    parts = urlparse(href)

    if parts.hostname == domain or parts.hostname in conf[domain]["aliases"].split(" "):
        return parts.path

def get_links(domain, soup):
    links = set()
    for a in soup.findAll('a'):
        h = a.get('href')
        href = is_downloadable_link(domain, a.get('href'))
        a["href"] = href
        if href:
            links.add("https://{}/{}".format(domain, href))
    return links

def sniff(domain, url):
    try:
        s = get_page(url)
    except HTTPError:
        print("Error : unable to get {}".format(url))
        return []
    if not s:
        return []
    el = s.find(id=conf[domain]["disclaimer_place_id"])
    if el:
        el.append(BeautifulSoup(conf[domain]["disclaimer"].format(datetime.date.today().strftime(conf[domain]["date_format"])), "html.parser"))
    else:
        print("Warning : Unable to find {} to insert disclaimer at {}".format(conf[domain]["disclaimer_place_id"], url))
    clean_page(domain, s)
    links = get_links(domain, s)
    get_statics(domain, s)
    write_local_page(s, url)
    return links

def write_about_copy_files(domain):
    for f in conf[domain]["about_static_copy_files"].split(" "):
        f_path = "{}/{}/{}".format(conf[domain]["dest_dir"], domain, f)
        with open(f_path, "w") as f:
            f.write(conf[domain]["about_static_copy"])

if __name__ == "__main__":

    urls_done = []
    try:
        conf.read(CONF_FILE)
    except Exception:
        print("Error, unable to parse conf file {}".format(CONF_FILE))
        raise

    for domain in conf.sections():
        url = "{}://{}".format(conf[domain]["proto"], domain)
        parts = urlparse(url)
        urls = list(sniff(domain, url))
        urls_done.append(domain)
        while urls:
            url = urls.pop()
            urls_done.append(url)
            for u in sniff(domain, url):
                if u not in urls_done:
                    urls.append(u)
        write_about_copy_files(domain)

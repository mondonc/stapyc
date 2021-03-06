#!/usr/bin/python3

from urllib.request import urlopen
from urllib.parse import urlparse
from urllib.error import HTTPError
from bs4 import BeautifulSoup
import datetime
import os
import re
import configparser
conf = configparser.ConfigParser()
CONF_FILE = "stapyc.ini"


urls_done = []

TEXT_CHARACTERS = "".join(list(map(chr, range(32, 127))) + list("\n\r\t\b"))


def make_dirs(f_path):
    f_name, f_ext = os.path.splitext(f_path)
    if not f_ext:
        f_path = f_path + "/index.html"
    os.makedirs(os.path.dirname(f_path), exist_ok=True)
    return f_path


def get_page(url):
    # print("GET {}".format(url))
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
        print("Error unicode : unable to get {}".format(url))
    except Exception:
        print("Error : unable to get {}".format(url))


def write_local_page(soup, url):
    parts = urlparse(url)
    url_path = parts.path if parts.path else "index.html"
    f_path = "{}/{}/{}".format(conf[domain]["dest_dir"], parts.hostname, url_path)
    f_path = make_dirs(f_path)
    with open(f_path, "w", encoding='utf-8') as f:
        f.write(str(soup))
    return parts.path


def clean_page(domain, soup):
    for ci in [ci for ci in conf[domain]["clean_ids"].split(" ") if ci]:
        for e in soup.findAll(id=ci):
            e.decompose()
    for cc in [cc for cc in conf[domain]["clean_class"].split(" ") if cc]:
        for e in soup.findAll(class_=cc):
            e.decompose()


def get_css_parts(domain, css):
    css = css.decode()
    for link in re.findall(r'url\(([(..)/].*?)\)', css):
        src = "http://{}/{}".format(domain, link)
        url = link.split("?")[0]

        if url in urls_done:
            continue

        f_path = "{}/{}/{}/{}".format(conf[domain]["dest_dir"], domain, conf[domain]["static_path"], url)
        f_path = make_dirs(f_path)

        urls_done.append(src)
        with open(f_path, "wb") as f:
            f.write(urlopen(src).read())
        css = css.replace("url({})".format(link), "url(/{}/{})".format(conf[domain]["static_path"], url))
        # print("STATIC INC {}".format(src))
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
            if os.path.exists(f_path) or src in urls_done:
                continue
            # print("STATIC {}".format(src))
            urls_done.append(src)
            f_path = make_dirs(f_path)
            try:
                content = urlopen(src).read()
                if os.path.splitext(f_path)[1] == ".css":
                    content = get_css_parts(domain, content)
                if content:
                    with open(f_path, "wb") as f:
                        f.write(content)
            except Exception as e:
                print("Error getting statics {} : {}".format(src, str(e)))
                pass


def is_downloadable_link(domain, href):
    if not href or href.startswith("#"):
        return None

    href = href.split("#")[0]

    if href[:5] not in ("http:", 'https'):
        return href

    parts = urlparse(href)
    if parts.hostname == domain or conf[domain]["aliases"] and parts.hostname in conf[domain]["aliases"].split(" "):
        return parts.path


def get_links(domain, soup):
    links = set()
    for a in soup.findAll('a'):
        href = is_downloadable_link(domain, a.get('href'))
        if href:
            if any(ignored in href for ignored in conf[domain]["ignore_path"].split(" ")):
                a["href"] = ""
            else:
                a["href"] = href
                links.add("https://{}/{}".format(domain, href))
    return links


def sniff(domain, url):
    try:
        s = get_page(url)
    except HTTPError:
        # print("Error : unable to get {}".format(url))
        try:
            write_local_page(BeautifulSoup(conf[domain]["about_static_copy"], "html.parser"), url)
        except Exception:
            print("Error : unable to get {} and to write about_static_copy".format(url))
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
        f_dir = "{}/{}/{}".format(conf[domain]["dest_dir"], domain, f)
        os.makedirs(f_dir, exist_ok=True)
        f_path = "{}/index.html".format(f_dir)
        with open(f_path, "w") as f:
            f.write(conf[domain]["about_static_copy"])
    return ["{}://{}/{}".format(conf[domain]["proto"], domain, f) for f in conf[domain]["about_static_copy_files"].split(" ")]


if __name__ == "__main__":

    try:
        conf.read(CONF_FILE)
    except Exception:
        print("Error, unable to parse conf file {}".format(CONF_FILE))
        raise

    for domain in conf.sections():

        pid = os.fork()
        if pid == 0:
            continue

        print("Getting {}...".format(domain))
        urls_done.extend(write_about_copy_files(domain))

        url = "{}://{}".format(conf[domain]["proto"], domain)
        urls = list(sniff(domain, url))
        urls_done.append(domain)

        while urls:
            url = urls.pop()
            urls_done.append(url)
            for u in sniff(domain, url):
                if u not in urls_done:
                    urls.append(u)
        write_about_copy_files(domain)

        if pid:
            break

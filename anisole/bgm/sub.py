import re
import subprocess
import xmlrpc.client
from collections import Iterable
from shutil import rmtree
from typing import Dict, List

import click
from hanziconv import HanziConv

from anisole import BASE_PATH
from anisole.utils import all_videos, parse_anime_ep, parse_eps_list


def append_or_extend(li: list, ele, remove=False):
    if remove:
        if isinstance(ele, Iterable):
            for e in ele:
                if e in li:
                    li.remove(e)
        else:
            if ele in li:
                li.remove(ele)
    else:
        if isinstance(ele, Iterable):
            li.extend(ele)
        else:
            li.append(ele)


class Sub:
    """A subscription object.
    """

    wd = BASE_PATH / "anime"
    _fields = [
        "marked",
        "keyword",
        "includes",
        "excludes",
        "prefers",
        "regex",
        "bid",
        "img",
    ]

    def __init__(
        self,
        name: str,
        uid: int = None,
        keyword: str = None,
        regex=None,
        includes: List[str] = None,
        excludes: List[str] = None,
        prefers: List[str] = None,
        bid: int = None,
        img: str = None,
        **kwargs,
    ):

        self._uid = None
        self._fp = None
        self._name = name

        self.name = name
        self.uid = uid
        self.bid = bid
        self.img = img
        if not keyword:
            keyword = name
        self.keyword = keyword
        self.regex = re.compile(regex) if regex else None
        self.includes = []
        self.include(kw=includes)
        self.excludes = []
        self.exclude(kw=excludes)
        self.prefers = []
        self.prefer(kw=prefers)

        self.links = {}

        self.marked = kwargs.get("marked", 0)

    @classmethod
    def load_from(cls, sub_dict: dict, links=None):
        name = sub_dict.pop("name")
        obj = cls(name, **sub_dict)
        obj.links = links or {}
        return obj

    def dump_to(self):
        sub_dict = {"uid": self.uid, "name": self.name}
        sub_dict.update({field: self.__dict__[field] for field in self._fields})
        return sub_dict, self.links

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, val):
        if val and isinstance(val, str):
            self._name = val

            new_fp = self.wd / val
            old_fp = self._fp

            if old_fp:
                old_fp.rename(new_fp)
            else:
                new_fp.mkdir(parents=True, exist_ok=True)
            self._fp = new_fp

    @property
    def uid(self):
        return self._uid

    @uid.setter
    def uid(self, val):
        if val is None:
            self._uid = None
            return
        if isinstance(val, int) and val > 0:
            self._uid = val
        else:
            raise ValueError("UID should be a positive integer!")

    @property
    def fp(self):
        return self._fp

    @property
    def bgm_url(self):
        if self.bid:
            return f"http://bgm.tv/subject/{self.bid}"
        return None

    def download(self, tag_str, all_=False):
        """Download files with aria2.

        Returns:
            results: a list of Tuple[title, path].
        """
        s = xmlrpc.client.ServerProxy("http://localhost:6800/rpc")

        aria2 = s.aria2

        # temporarily stores a list of (episode, idx)
        eis = []

        # tag defaults to most recent episode
        if not tag_str:
            ep = max(self.links.keys())
            tag_str = str(ep)

        for ep, idx in parse_eps_list(tag_str):
            eis.append((ep, idx))

        # if downloads all episodes
        if all_:
            eps = [ep for ep, _ in eis]
            for ep in self.links:
                if ep > 0 and ep not in eps:
                    eis.append((ep, 0))

        results = []
        for ep, idx in eis:
            link = self.links[ep][idx]
            magnet = link["link"]

            # path = str(self.get_fp_by_ep(ep))
            path = str(self.fp)
            aria2.addUri("token:", [magnet], {"dir": path})
            results.append((link["title"], path))

        return results

    def play(self, tag):
        """play the video. If tag is falsy, play the latest episode.
        Returns:
            f: `Path` or None.
        """
        play_dic = self.play_dic
        if not tag:
            ep = max(play_dic.keys())
            tag = str(ep)
        li = tag.split(":", 1)
        if len(li) == 1:
            li.append("0")
        ep = int(li[0])
        idx = int(li[1])

        if ep in play_dic and 0 <= idx < len(play_dic[ep]):
            f = play_dic[ep][idx]
            subprocess.run(["open", f], check=True)
            return f
        return None

    @property
    def play_dic(self):
        """Return a dictionary of {episode: List[path]}"""
        pd = {}

        for f in all_videos(self.fp):
            ep = parse_anime_ep(f.stem)
            li = pd.setdefault(ep, [])
            li.append(f)
        return {k: v for k, v in sorted(pd.items(), key=lambda x: x[0])}

    @property
    def downloaded(self):
        pl_a = {k: v for k, v in self.play_dic.items() if v}
        keys = [k for k in pl_a.keys() if isinstance(k, int)]
        if keys:
            return max(keys)
        else:
            return 0

    @property
    def episoded(self):
        """Max episode"""
        episodes = self.links.keys()
        if episodes:
            eps = max(episodes)
        else:
            eps = 0
        return eps

    def get_fp_by_ep(self, ep: int, mkdir=True):
        path = self.fp / str(ep)
        if mkdir:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def re(self, regex):
        if regex:
            self.regex = re.compile(regex)

    def include(self, kw=None, nkw=None, clear: bool = False):
        if clear:
            self.includes = []

        if kw:
            append_or_extend(self.includes, kw)
        if nkw:
            append_or_extend(self.includes, nkw, remove=True)

    def exclude(self, kw=None, nkw=None, clear: bool = False):
        if clear:
            self.excludes = []

        if kw:
            append_or_extend(self.excludes, kw)
        if nkw:
            append_or_extend(self.excludes, nkw, remove=True)

    def prefer(self, kw=None, nkw=None, clear: bool = False):
        if clear:
            self.prefers = []

        if kw:
            append_or_extend(self.prefers, kw)
        if nkw:
            append_or_extend(self.prefers, nkw, remove=True)

    def clutter_item(self, item):
        content = item.content
        if self.is_valid(content):
            li = self.links.setdefault(content["episode"], [])
            li.append(content)

    def sort(self):
        for _, li in self.links.items():
            li.sort(key=self.get_priority, reverse=True)

    def get_priority(self, item):
        priority = 0
        for p in self.prefers:
            point = 1
            while p.startswith("#"):
                p = p.split("#", 1)[-1]
                point += 1
            if p == "chs" and item["chs"]:
                priority += point
            elif p == "1080P" and ("1080" in item["title"]):
                priority += point
            elif p == "720P" and ("720" in item["title"]):
                priority += point
            else:
                if p in item["title"]:
                    priority += point
        return priority

    def is_valid(self, content):
        text = content["tag"] + content["title"]
        text = HanziConv.toSimplified(text)

        if self.regex:
            if not self.regex.search(text):
                return False

        pass_exc = True
        for exc in self.excludes:
            if exc in text:
                pass_exc = False
                break

        pass_inc = True
        if self.includes:
            pass_inc = False
            for inc in self.includes:
                if inc in text:
                    pass_inc = True

        return pass_exc and pass_inc

    def echo(self, fg_1="white", detailed=0, nl=False, dim_on_old=False):
        if self.bid:
            fg_1 = "cyan"
        if detailed == -1:
            click.secho(f"{self.name}", nl=False)
        else:
            new = self.marked < self.episoded
            click.secho(
                f"{self.uid:<4}{self.name} ({self.episoded},{self.downloaded},{self.marked})",
                fg=fg_1,
                nl=False,
                dim=(not new) and dim_on_old,
            )
        if detailed > 0:
            click.echo("")
            click.secho(f"    --keyword: {self.keyword}", nl=False)
            if self.bid:
                click.echo("")
                click.secho(f"    --bgm: {self.bgm_url}", nl=False)
            if self.regex:
                click.echo("")
                click.secho(f"    --regex: {self.regex.pattern}", nl=False)
            if self.includes:
                click.echo("")
                click.secho(f"    --includes: {self.includes}", nl=False)
            if self.excludes:
                click.echo("")
                click.secho(f"    --excludes: {self.excludes}", nl=False)
            if self.prefers:
                click.echo("")
                click.secho(f"    --prefers: {self.prefers}", nl=False)

            click.echo("")
            click.secho(f'    --local: "{self.fp}"', nl=False)

            if detailed > 1 and self.links:
                click.echo("")
                click.secho(f"    --links:", nl=False)
                for episode, li in sorted(
                    self.links.items(), key=lambda x: x[0], reverse=True
                ):
                    # echo all links
                    click.echo("")
                    extra_str = "(合集)" if episode == -1 else ""
                    click.secho(f"      @{episode}{extra_str}:", fg="yellow", nl=False)
                    for i, item in enumerate(li):
                        click.echo("")
                        click.secho(f"       {i:>4} {item['title']}", nl=False)

        if nl:
            click.echo("")


class SubJar:
    def __init__(self):
        self.content: Dict[int, Sub] = {}

    @property
    def ids(self) -> set:
        return self.content.keys()

    def store(self, sub: Sub) -> Sub:
        """store the subscription into the Jar. Automatically adjust uid."""
        if isinstance(sub.uid, int) and sub.uid > 0:
            if sub.uid in self.ids:
                old_sub = self.content[sub.uid]
                old_sub.uid = self._gen_uid()
                self.content[old_sub.uid] = old_sub
        else:
            sub.uid = self._gen_uid()
        self.content[sub.uid] = sub
        return sub

    def get_sub_by_bid(self, bid: int):
        for sub in self.content.values():
            if sub.bid == bid:
                return sub
        return None

    def rm(self, uid, save_files=False):
        """remove subscription.

        Args:
            uid (int):
            save_files (bool, optional): save downloaded files. Defaults to False.

        Returns:
            (sub, new_fp): a tuple of deleted subscription and file_path for downloaded
        """
        if uid in self.ids:
            sub = self.content.pop(uid)
            if save_files:
                new_fp = sub.fp.parent / sub.name
                new_fp.mkdir(parents=True, exist_ok=True)
                sub.fp.rename(new_fp)
            else:
                rmtree(sub.fp)
                new_fp = None
            return sub, new_fp
        return False

    def _gen_uid(self) -> int:
        i = 1
        while True:
            if i not in self.ids:
                break
            else:
                i += 1
        return i

    @classmethod
    def load_from(cls, sub_dicts, links_dict):
        """Load from (a list of sub info, a dictionary of uid->links)"""
        jar = cls()
        for sub_dict in sub_dicts:
            uid = sub_dict["uid"]
            links = links_dict.pop(uid, {})
            sub = Sub.load_from(sub_dict, links)
            jar.content[uid] = sub
        return jar

    def dump_to(self):
        """Return (a list of sub info, a dictionary of uid->links)"""
        links_dict = {}
        sub_dicts = []
        for sub in sorted(self.content.values(), key=lambda s: s.uid):
            sub: Sub
            uid = sub.uid
            sub_dict, links = sub.dump_to()
            sub_dicts.append(sub_dict)
            links_dict[uid] = links

        return sub_dicts, links_dict

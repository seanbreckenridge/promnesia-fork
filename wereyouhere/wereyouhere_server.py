#!/usr/bin/python3
__package__ = 'wereyouhere' # ugh. hacky way to make hug work properly...

import argparse
import os
import sys
from datetime import timedelta, datetime
from pathlib import Path
import logging
from functools import lru_cache
from typing import Collection, List, NamedTuple, Dict

from kython import setup_logzero
from kython.kcache import Binder

import hug # type: ignore
import hug.types as T # type: ignore

from sqlalchemy import create_engine, MetaData, exists # type: ignore
from sqlalchemy import Column, Table # type: ignore


from .common import PathWithMtime, Config, DbVisit, Url, import_config, Loc
from .normalise import normalise_url

_ENV_CONFIG = 'WEREYOUHERE_CONFIG'

# meh. need this since I don't have hooks in hug to initialize logging properly..
@lru_cache(1)
def get_logger():
    logger = logging.getLogger('wereyouhere')
    setup_logzero(logger, level=logging.DEBUG)
    return logger


@lru_cache(1)
def _load_config(mpath: PathWithMtime) -> Config:
    return import_config(mpath.path)


def load_config() -> Config:
    cp = os.environ.get(_ENV_CONFIG)
    assert cp is not None
    return _load_config(PathWithMtime.make(Path(cp)))

# TODO use that?? https://github.com/timothycrosley/hug/blob/develop/tests/test_async.py

    # def reg_visit(v):
    #     # TODO parse loc
    #     for vis in v['visits']:
    #         dt = fromisoformat(vis['dt'])
    #         if dt.tzinfo is None:
    #             dt = config.FALLBACK_TIMEZONE.localize(dt)


# TODO how to return exception in error?

def as_json(v: DbVisit) -> Dict:
    # TODO check utc
   #  "09 Aug 2018 19:48",
   #  "06 Aug 2018 21:36--21:37",
    # TODO perhaps tag merging should be done by browser as well?
    # TODO also local should be suppressed if any other tag with this timestamp is present
    dts = v.dt.strftime('%d %b %Y %H:%M')
    loc = v.locator
    # # TODO is locator always present??
    return {
        # TODO do not display year if it's current year??
        'dt': dts,
        'tags': [v.tag],
        'context': v.context,
        'locator': {
            'title': loc.title,
            'href' : loc.href,
        },
    }

@lru_cache(1)
def get_stuff(): # TODO better name
    # ok, it will always load from the same db file; but intermediate would be kinda an optional dump.
    config = load_config()
    db_path = Path(config.OUTPUT_DIR) / 'visits.sqlite' # TODO FIXME need to update it
    assert db_path.exists()

    # TODO how to open read only?
    engine = create_engine(f'sqlite:///{db_path}')

    binder = Binder(clazz=DbVisit)

    meta = MetaData(engine)
    table = Table('visits', meta, *binder.columns)

    return engine, binder, table


@hug.local()
@hug.post('/visits')
def visits(
        url: T.text,
):
    logger = get_logger()
    config = load_config()

    logger.info('url: %s', url)
    url = normalise_url(url)
    logger.info('normalised url: %s', url)

    engine, binder, table = get_stuff()

    query = table.select().where(table.c.norm_url == url)

    with engine.connect() as conn:
        visits = [binder.from_row(row) for row in conn.execute(query)]

    logger.debug('got %d visits from db', len(visits))

    vlist = []
    for vis in visits:
        dt = vis.dt
        if dt.tzinfo is None:
            dt = config.FALLBACK_TIMEZONE.localize(dt)
            vis = vis._replace(dt=dt)
        vlist.append(vis)
    if len(vlist) is None:
        return None # TODO handle empty list in client?
    else:
        return list(map(as_json, vlist))


@hug.local()
@hug.post('/visited')
def visited(
        urls, # TODO type
):
    logger = get_logger()

    logger.debug(urls)
    nurls = list(map(normalise_url, urls))
    logger.debug('normalised: %s', nurls)

    engine, binder, table = get_stuff()

    results = []
    # TODO optimize and implement properly..
    with engine.connect() as conn:
        for nurl in nurls:
            query = exists(table.select().where(table.c.norm_url == nurl)).select()
            [res] = conn.execute(query)
            results.append(res[0])
    return results


def run(port: str, config: Path):
    env = os.environ.copy()
    # # not sure if there is a simpler way to communicate with the server...
    env[_ENV_CONFIG] = str(config)
    os.execvpe(
        '/home/karlicos/.local/bin/hug',
        [
            'wereyouhere-server',
            '-p', port,
            '-f', __file__,
        ],
        env,
    )


_DEFAULT_CONFIG = Path('config.py')

from contextlib import contextmanager
import json
from subprocess import Popen, PIPE
from subprocess import check_output, check_call
import time

TEST_PORT = "16556" # TODO random?

@contextmanager
def _test_helper(tmp_path):
    tdir = Path(tmp_path)
    # TODO ugh. quite hacky...
    from shutil import copy
    template_config = Path(__file__).parent.parent / 'testdata' / 'test_config.py'
    copy(template_config, tdir)
    config = tdir / 'test_config.py'
    with config.open('a') as fo:
        fo.write(f"OUTPUT_DIR = '{tdir}'")

    path = (Path(__file__).parent.parent / 'run').absolute()


    check_call([str(path), 'extract', '--config', config])

    cmd = [str(path), 'serve', '--port', TEST_PORT, '--config', config]
    with Popen(cmd) as server: # type: ignore
        print("Giving few secs to start server up")
        time.sleep(3)
        print("Started server up")
        # TODO which url??

        yield

        print("DONE!!!!")
        server.kill()


def test_query(tmp_path):
    test_url = 'https://takeout.google.com/settings/takeout'
    with _test_helper(tmp_path):
        for q in range(3):
            print(f"querying {q}")
            cmd = [
                'http', 'post', f'http://localhost:{TEST_PORT}/visits', f'url={test_url}',
            ]
            response = json.loads(check_output(cmd).decode('utf8'))
            assert len(response) > 0

def test_visited(tmp_path):
    test_url = 'https://takeout.google.com/settings/takeout'
    with _test_helper(tmp_path):
        cmd = [
            'http', 'post',  f'http://localhost:{TEST_PORT}/visited', f"""urls:=["{test_url}","http://badurl.org"]""",
        ]
        response = json.loads(check_output(cmd))
        assert response == [True, False]


def setup_parser(p):
    p.add_argument('--port', type=str, default='13131', help='Port for communicating with extension')
    p.add_argument('--config', type=Path, default=_DEFAULT_CONFIG, help='Path to config')


def main():
    setup_logzero(get_logger(), level=logging.DEBUG)
    p = argparse.ArgumentParser('wereyouhere server', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    setup_parser(p)
    args = p.parse_args()
    run(port=args.port, config=args.config)


if __name__ == '__main__':
    main()


